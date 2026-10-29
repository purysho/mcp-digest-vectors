"""Minimal stdio MCP client used by the built-in adapters. Standard library only."""

from __future__ import annotations

import json
import subprocess


class ClientError(RuntimeError):
    pass


def list_tools_raw(command: list[str], env: dict | None = None, timeout: float = 20) -> bytes:
    """Spawn a stdio MCP server, initialize, call tools/list and return the raw `result` bytes.

    The fixture server always writes `"result":` as the last member of the response,
    so the raw result is everything between that marker and the final `}`.
    """
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "mdv-runner", "version": "0.1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    stdin = b"".join(json.dumps(m).encode() + b"\n" for m in msgs)
    try:
        proc = subprocess.run(command, input=stdin, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ClientError("server timed out") from exc
    for line in proc.stdout.splitlines():
        if line.startswith(b'{"jsonrpc":"2.0","id":2,'):
            marker = b'"result":'
            at = line.find(marker)
            if at < 0 or not line.endswith(b"}"):
                raise ClientError(f"tools/list failed: {line[:200]!r}")
            return line[at + len(marker):-1]
    raise ClientError(f"no tools/list response; stderr: {proc.stderr[-300:]!r}")
