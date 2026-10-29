"""Built-in adapters: the reference digest, and three naive baselines that show why
canonical form and strict parsing matter. They talk to the fixture server through
the same stdio MCP protocol a real client uses."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import Outcome

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "runner"))

from mcp_digest import DigestError, digest_result  # noqa: E402
from mcpclient import list_tools_raw  # noqa: E402


class _HashAdapter:
    url = "https://github.com/purysho/mcp-digest-vectors"

    def probe(self) -> str:
        return "builtin"

    def fingerprint(self, raw: bytes) -> str:
        raise NotImplementedError

    def _fp(self, ctx) -> str:
        return self.fingerprint(list_tools_raw(ctx.server_cmd, env=ctx.env))

    def pin(self, ctx) -> None:
        (ctx.workdir / f"{self.name}.pin").write_text(self._fp(ctx))

    def check(self, ctx) -> Outcome:
        pinned = (ctx.workdir / f"{self.name}.pin").read_text()
        try:
            now = self._fp(ctx)
        except Exception as exc:  # the tool refuses this input: fail closed
            return Outcome("error", f"{type(exc).__name__}: {exc}"[:200])
        return Outcome("unchanged" if now == pinned else "changed")


class Reference(_HashAdapter):
    name = "reference"
    description = "mcp-tool-digest/v1-draft, full profile (this repo)"

    def fingerprint(self, raw: bytes) -> str:
        try:
            return digest_result(raw, "full").set_digest
        except DigestError as exc:
            raise RuntimeError(f"rejected: {exc.code}") from None


class RawBytes(_HashAdapter):
    name = "naive-raw-bytes"
    description = "Baseline: SHA-256 of the raw tools/list bytes"

    def fingerprint(self, raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()


class SortedJson(_HashAdapter):
    name = "naive-sorted-json"
    description = "Baseline: Python json.loads, then json.dumps(sort_keys=True)"

    def fingerprint(self, raw: bytes) -> str:
        doc = json.loads(raw)
        text = json.dumps(doc, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


class DescriptionOnly(_HashAdapter):
    name = "naive-description-only"
    description = "Baseline: hash of each tool's name and description (first SEP-3452 draft scope)"

    def fingerprint(self, raw: bytes) -> str:
        doc = json.loads(raw)
        pairs = sorted((t.get("name"), t.get("description")) for t in doc["tools"])
        text = json.dumps(pairs, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


ADAPTERS = [Reference(), RawBytes(), SortedJson(), DescriptionOnly()]
