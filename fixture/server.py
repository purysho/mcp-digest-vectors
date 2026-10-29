#!/usr/bin/env python3
"""A stdio MCP server that serves one side of a test vector, byte for byte.

    python3 fixture/server.py --vector vectors/eq-key-order.json --side-file /tmp/side

The side file contains "before" or "after" and is re-read on every tools/list,
so a long-lived client sees the change, and a client that respawns the server
sees it too. With --side, the side is fixed.

The tools/list result is spliced into the JSON-RPC response as raw bytes, so
whatever the vector contains (key order, escapes, duplicate keys, invalid UTF-8)
reaches the client's JSON parser exactly as written. Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

SERVER_INFO = {"name": "mdv-fixture", "version": "0.1.0"}
DEFAULT_PROTOCOL = "2025-06-18"


def load_raw(vector: dict, side: str) -> bytes:
    if f"{side}_b64" in vector:
        raw = base64.b64decode(vector[f"{side}_b64"])
    else:
        raw = vector[side].encode("utf-8")
    if b"\n" in raw or b"\r" in raw:
        raise SystemExit("vector side contains a line break; stdio framing needs single-line JSON")
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True, type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--side", choices=["before", "after"])
    group.add_argument("--side-file", type=Path)
    ap.add_argument("--log", type=Path, help="append received methods here (for debugging adapters)")
    args = ap.parse_args()
    vector = json.loads(args.vector.read_text(encoding="utf-8"))

    def current_side() -> str:
        if args.side:
            return args.side
        try:
            s = args.side_file.read_text().strip()
        except FileNotFoundError:
            return "before"
        return s if s in ("before", "after") else "before"

    out = sys.stdout.buffer

    def send(obj_id, result_raw: bytes | None = None, error: dict | None = None) -> None:
        head = b'{"jsonrpc":"2.0","id":' + json.dumps(obj_id).encode() + b","
        if error is not None:
            body = b'"error":' + json.dumps(error).encode()
        else:
            body = b'"result":' + result_raw
        out.write(head + body + b"}\n")
        out.flush()

    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send(None, error={"code": -32700, "message": "parse error"})
            continue
        method = msg.get("method")
        if args.log:
            with args.log.open("a") as f:
                f.write(f"{method} side={current_side()}\n")
        if "id" not in msg:
            continue  # notification, e.g. notifications/initialized
        mid = msg["id"]
        if method == "initialize":
            proto = (msg.get("params") or {}).get("protocolVersion") or DEFAULT_PROTOCOL
            result = {"protocolVersion": proto, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": SERVER_INFO}
            send(mid, json.dumps(result).encode())
        elif method == "tools/list":
            send(mid, load_raw(vector, current_side()))
        elif method == "ping":
            send(mid, b"{}")
        elif method in ("resources/list", "prompts/list", "resources/templates/list"):
            key = {"resources/list": "resources", "prompts/list": "prompts",
                   "resources/templates/list": "resourceTemplates"}[method]
            send(mid, json.dumps({key: []}).encode())
        elif method == "tools/call":
            send(mid, b'{"content":[{"type":"text","text":"fixture: calls are not implemented"}],"isError":true}')
        else:
            send(mid, error={"code": -32601, "message": f"method not found: {method}"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
