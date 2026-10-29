"""Adapters for tools outside this repo.

`latch` has been run (results/latch.json). The others were written from each
project's published documentation and have NOT been run yet: the sandbox that
produced the first results did not allow installing third-party tools. Each one
probes for its CLI on PATH and reports itself unavailable otherwise. Expect to
adjust flags or output parsing on the first real run; please send fixes upstream.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from . import HarnessError, Outcome, Unavailable

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT = 120


def _cmd(env_var: str, default: str) -> list[str]:
    return shlex.split(os.environ.get(env_var, default))


def _run(ctx, argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, cwd=ctx.workdir, env=ctx.env, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"timed out: {' '.join(argv)}") from exc


def _tail(p: subprocess.CompletedProcess) -> str:
    return (p.stdout[-300:] + " | " + p.stderr[-300:]).strip(" |")


def _probe(argv: list[str], hint: str) -> str:
    if shutil.which(argv[0]) is None:
        raise Unavailable(f"`{argv[0]}` not on PATH; {hint}")
    try:
        out = subprocess.run(argv + ["--version"], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise Unavailable("--version timed out") from None
    return (out.stdout or out.stderr).strip().splitlines()[0][:40] if (out.stdout or out.stderr) else "unknown"


# ------------------------------------------------------------------ Latch (run)


class Latch:
    name = "latch"
    description = "purysho/Latch ToolRegistry::reconcile (stdio parsing emulated), commit de954a8"
    url = "https://github.com/purysho/Latch"
    binary = Path(os.environ.get("MDV_LATCH_HARNESS", ROOT / "runner/latch-harness/target/release/latch-harness"))

    def probe(self) -> str:
        if not self.binary.exists():
            raise Unavailable("build it: cargo build --release --manifest-path runner/latch-harness/Cargo.toml")
        return "de954a8"

    def pin(self, ctx) -> None:
        pass  # the harness pins and checks in one process

    def check(self, ctx) -> Outcome:
        p = subprocess.run([str(self.binary), str(ctx.vector_path)], capture_output=True, text=True, timeout=TIMEOUT)
        try:
            out = json.loads(p.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            raise HarnessError(f"harness output: {_tail(p)}") from None
        if out["result"] == "harness-error":
            raise HarnessError(out["detail"])
        return Outcome(out["result"], out["detail"])


# ------------------------------------------------------------------ written from docs, not yet run


class Mcpward:
    """https://github.com/TsvetanG2/mcpward — `mcpward baseline`, then `mcpward diff` (exit 1 on drift)."""

    name = "mcpward"
    description = "mcpward baseline/diff, drift only, fail_on: low (written from docs, not yet run)"
    url = "https://github.com/TsvetanG2/mcpward"

    def probe(self) -> str:
        return _probe(_cmd("MDV_MCPWARD", "mcpward"), "npm install -g mcpward (Node 22+)")

    def _config(self, ctx) -> None:
        cmd = ctx.server_cmd
        cfg = (
            "server:\n  transport: stdio\n"
            f"  command: {json.dumps(cmd[0])}\n  args: {json.dumps(cmd[1:])}\n"
            "checks:\n  compliance: false\n  schema: false\n  security: false\n  errors: false\n"
            "  collision:\n    enabled: false\n"
            "  drift:\n    baseline: ./mcpward.lock.json\n    fail_on: low\n    full_text: true\n"
        )
        (ctx.workdir / "mcpward.yaml").write_text(cfg)

    def pin(self, ctx) -> None:
        self._config(ctx)
        p = _run(ctx, _cmd("MDV_MCPWARD", "mcpward") + ["baseline"])
        if p.returncode != 0 or not (ctx.workdir / "mcpward.lock.json").exists():
            raise HarnessError(f"baseline failed: {_tail(p)}")

    def check(self, ctx) -> Outcome:
        p = _run(ctx, _cmd("MDV_MCPWARD", "mcpward") + ["diff"])
        if p.returncode == 0:
            return Outcome("unchanged", _tail(p))
        if p.returncode == 1 and "DRIFT" in p.stdout:
            return Outcome("changed", _tail(p))
        return Outcome("error", _tail(p))


class McpScrutiny:
    """https://github.com/bryand410/mcp-scrutiny — baseline --probe, then scan --baseline (exit 1 = finding, 2 = error)."""

    name = "mcp-scrutiny"
    description = "mcp-scrutiny baseline/scan, drift findings only (written from docs, not yet run)"
    url = "https://github.com/bryand410/mcp-scrutiny"

    def probe(self) -> str:
        return _probe(_cmd("MDV_SCRUTINY", "mcp-scrutiny"), "pip install mcp-scrutiny (Python 3.11+)")

    def pin(self, ctx) -> None:
        p = _run(ctx, _cmd("MDV_SCRUTINY", "mcp-scrutiny") +
                 ["baseline", "--config", str(ctx.config_path), "--probe", "--out", "mcp-baseline.json"])
        if p.returncode != 0 or not (ctx.workdir / "mcp-baseline.json").exists():
            raise HarnessError(f"baseline failed: {_tail(p)}")

    def check(self, ctx) -> Outcome:
        p = _run(ctx, _cmd("MDV_SCRUTINY", "mcp-scrutiny") +
                 ["scan", "--config", str(ctx.config_path), "--probe", "--baseline", "mcp-baseline.json",
                  "--fail-on", "info", "--format", "json"])
        if p.returncode == 2:
            return Outcome("error", _tail(p))
        # Other detectors (poisoning, etc.) also fire on "after" text, so look for drift findings specifically.
        try:
            report = json.loads(p.stdout)
        except json.JSONDecodeError:
            raise HarnessError(f"unparseable JSON output: {_tail(p)}") from None
        blob = json.dumps(report).lower()
        return Outcome("changed" if '"drift' in blob or "rug pull" in blob else "unchanged", p.stdout[-300:])


class Guardbench:
    """https://github.com/Manishmaurya89/mcp-guardbench — inspect --update-pins, then inspect (exit 1 + CHANGED)."""

    name = "guardbench"
    description = "guardbench inspect with pins (written from docs, not yet run)"
    url = "https://github.com/Manishmaurya89/mcp-guardbench"

    def probe(self) -> str:
        return _probe(_cmd("MDV_GUARDBENCH", "guardbench"), "pip install mcp-guardbench")

    def pin(self, ctx) -> None:
        p = _run(ctx, _cmd("MDV_GUARDBENCH", "guardbench") + ["inspect", str(ctx.config_path), "--update-pins"])
        if not list(ctx.workdir.glob("guardbench-pins.json")):
            raise HarnessError(f"no pin file written: {_tail(p)}")

    def check(self, ctx) -> Outcome:
        p = _run(ctx, _cmd("MDV_GUARDBENCH", "guardbench") + ["inspect", str(ctx.config_path)])
        text = p.stdout + p.stderr
        if "Changed since pinned" in text or "CHANGED" in text:
            return Outcome("changed", _tail(p))
        if p.returncode not in (0, 1):
            return Outcome("error", _tail(p))
        return Outcome("unchanged", _tail(p))


ADAPTERS = [Latch(), Mcpward(), McpScrutiny(), Guardbench()]
