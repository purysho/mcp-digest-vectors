"""Command line: digest a tools/list result, or check an implementation's output against the vectors.

    python -m mcp_digest digest result.json [--profile full]
    python -m mcp_digest verify ../vectors          # re-derive every known answer
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

from .digest import PROFILES, digest_result
from .jcs import DigestError


def load_side(vector: dict, side: str) -> bytes:
    if f"{side}_b64" in vector:
        return base64.b64decode(vector[f"{side}_b64"])
    return vector[side].encode("utf-8")


def verify(vectors_dir: Path) -> int:
    failures = 0
    files = sorted(p for p in vectors_dir.glob("*.json") if p.name != "index.json")
    for path in files:
        v = json.loads(path.read_text(encoding="utf-8"))
        for profile in PROFILES:
            want = v["known_answers"][profile]
            for side in ("before", "after"):
                expected = want[side]
                try:
                    got = digest_result(load_side(v, side), profile)
                    got_obj = {"set": got.set_digest, "tools": got.tool_digests}
                except DigestError as exc:
                    got_obj = {"reject": exc.code}
                ok = ("reject" in expected and "reject" in got_obj) or got_obj == expected
                if not ok:
                    failures += 1
                    print(f"FAIL {v['id']} [{profile}/{side}]: expected {expected}, got {got_obj}")
    print(f"{len(files)} vectors x {len(PROFILES)} profiles x 2 sides checked, {failures} failure(s)")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mcp_digest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digest", help="digest a tools/list result read from a file or '-'")
    d.add_argument("file")
    d.add_argument("--profile", default="full", choices=sorted(PROFILES))
    vr = sub.add_parser("verify", help="check this implementation against a vectors directory")
    vr.add_argument("vectors", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "verify":
        return verify(args.vectors)
    raw = sys.stdin.buffer.read() if args.file == "-" else Path(args.file).read_bytes()
    try:
        r = digest_result(raw, args.profile)
    except DigestError as exc:
        print(json.dumps({"reject": exc.code, "detail": str(exc)}))
        return 2
    print(json.dumps({"profile": r.profile, "set": r.set_digest, "tools": r.tool_digests}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
