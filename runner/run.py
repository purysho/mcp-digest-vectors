#!/usr/bin/env python3
"""Score MCP pinning tools against the vectors.

For each vector: serve "before" from the fixture server, let the tool pin it,
switch the server to "after", ask the tool whether anything changed, and compare
its answer with what a security-minded pinning tool should say.

    python3 runner/run.py --list
    python3 runner/run.py                        # every adapter that is available
    python3 runner/run.py -a reference -a heldfast --vector eq-key-order
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))

from adapters import HarnessError, Outcome, Unavailable, registry  # noqa: E402

SERVER = ROOT / "fixture" / "server.py"
CONTROL_ID = "_control-identical"


@dataclass
class Ctx:
    workdir: Path
    home: Path
    vector_path: Path
    side_file: Path
    config_path: Path
    server_cmd: list[str]
    env: dict = field(default_factory=dict)

    def set_side(self, side: str) -> None:
        self.side_file.write_text(side)


def make_ctx(base: Path, vector_path: Path) -> Ctx:
    workdir = base
    home = workdir / "home"
    home.mkdir(parents=True, exist_ok=True)
    side_file = workdir / "side"
    side_file.write_text("before")
    server_cmd = [sys.executable, str(SERVER), "--vector", str(vector_path), "--side-file", str(side_file)]
    config = {"mcpServers": {"fixture": {"command": server_cmd[0], "args": server_cmd[1:]}}}
    config_path = workdir / ".mcp.json"
    config_path.write_text(json.dumps(config, indent=2))
    env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_DATA_HOME=str(home / ".local/share"), XDG_CACHE_HOME=str(home / ".cache"),
               NO_COLOR="1", CI="1")
    return Ctx(workdir, home, vector_path, side_file, config_path, server_cmd, env)


def verdict(security: str, outcome: str) -> str:
    if outcome == "harness-error":
        return "harness-error"
    if security == "informational":
        return "info"
    if security == "unchanged":
        return "pass" if outcome == "unchanged" else "false-alarm"
    if security == "changed":
        return {"changed": "pass", "unchanged": "miss", "error": "error"}[outcome]
    if security == "changed-or-error":
        return "miss" if outcome == "unchanged" else "pass"
    raise ValueError(security)


def run_one(adapter, vector_path: Path, scratch: Path, control: bool = False) -> Outcome:
    ctx = make_ctx(scratch, vector_path)
    ctx.set_side("before")
    adapter.pin(ctx)
    ctx.set_side("before" if control else "after")
    return adapter.check(ctx)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-a", "--adapter", action="append", help="adapter name (repeatable); default: all available")
    ap.add_argument("--vector", action="append", help="vector id (repeatable); default: all")
    ap.add_argument("--vectors", type=Path, default=ROOT / "vectors")
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    ap.add_argument("--keep", action="store_true", help="keep per-vector working directories")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    adapters = registry()
    if args.list:
        for name, a in adapters.items():
            try:
                status = a.probe()
            except Unavailable as exc:
                status = f"unavailable: {exc}"
            print(f"{name:28} {status:30} {a.description}")
        return 0

    index = json.loads((args.vectors / "index.json").read_text())["vectors"]
    vectors = [v for v in index if not args.vector or v["id"] in args.vector]
    chosen = args.adapter or list(adapters)
    args.out.mkdir(parents=True, exist_ok=True)

    for name in chosen:
        adapter = adapters[name]
        try:
            version = adapter.probe()
        except Unavailable as exc:
            print(f"== {name}: unavailable ({exc})")
            record = {"adapter": name, "description": adapter.description, "url": adapter.url,
                      "available": False, "reason": str(exc)}
            (args.out / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n")
            continue
        print(f"== {name} {version}")
        rows = []
        tmp_root = Path(tempfile.mkdtemp(prefix=f"mdv-{name}-"))
        started = time.time()
        # Control: identical before/after. A tool that flags this is not usable as a pin.
        try:
            control = run_one(adapter, args.vectors / f"{vectors[0]['id']}.json", tmp_root / CONTROL_ID, control=True)
        except Exception as exc:
            control = Outcome("harness-error", f"{type(exc).__name__}: {exc}")
        print(f"   control (identical listing): {control.result} {control.detail[:120]}")
        for v in vectors:
            path = args.vectors / f"{v['id']}.json"
            try:
                out = run_one(adapter, path, tmp_root / v["id"])
            except (HarnessError, Exception) as exc:  # noqa: B014 - keep going, record why
                detail = f"{type(exc).__name__}: {exc}"
                if not isinstance(exc, HarnessError):
                    detail += " | " + traceback.format_exc(limit=1).strip().splitlines()[-1]
                out = Outcome("harness-error", detail)
            vd = verdict(v["security"], out.result)
            rows.append({"id": v["id"], "category": v["category"], "security": v["security"],
                         "outcome": out.result, "verdict": vd, "detail": out.detail[:500]})
            print(f"   {v['id']:40} {out.result:13} {vd}")
        if not args.keep:
            shutil.rmtree(tmp_root, ignore_errors=True)
        record = {"adapter": name, "description": adapter.description, "url": adapter.url, "available": True,
                  "version": version, "control": control.result, "control_detail": control.detail,
                  "seconds": round(time.time() - started, 1), "rows": rows}
        (args.out / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")

    from report import write_report  # noqa: E402

    write_report(args.out, args.vectors)
    print(f"wrote {args.out / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
