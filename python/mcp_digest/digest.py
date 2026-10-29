"""mcp-tool-digest/v1-draft: per-tool and set digests over an MCP tools/list result."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .jcs import DigestError, _utf16_key, canonicalize, parse

VERSION = "mcp-tool-digest/v1-draft"

PROFILES: dict[str, tuple[str, ...] | None] = {
    "desc": ("name", "description"),
    "four-field": ("name", "description", "inputSchema", "annotations"),
    "full": None,  # every member
}


def select(tool: dict[str, Any], profile: str) -> dict[str, Any]:
    fields = PROFILES[profile]
    if fields is None:
        return dict(tool)
    return {k: tool[k] for k in fields if k in tool}


def _hash(profile: str, kind: str, canonical: str) -> str:
    h = hashlib.sha256()
    h.update(f"{VERSION}/{profile}/{kind}".encode("ascii") + b"\x00")
    h.update(canonical.encode("utf-8"))
    return "sha256:" + h.hexdigest()


def extract_tools(result: Any) -> list[dict[str, Any]]:
    """Validate a parsed tools/list result and return its tools sorted by name."""
    if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
        raise DigestError("not-a-tool-list", "expected an object with a 'tools' array")
    tools = result["tools"]
    seen: set[str] = set()
    for t in tools:
        if not isinstance(t, dict):
            raise DigestError("not-a-tool-list", "every tool must be an object")
        name = t.get("name")
        if not isinstance(name, str) or not name:
            raise DigestError("bad-tool-name", "tool name must be a non-empty string")
        if name in seen:
            raise DigestError("duplicate-tool-name", f"tool name {name!r} appears twice")
        seen.add(name)
    return sorted(tools, key=lambda t: _utf16_key(t["name"]))


@dataclass(frozen=True)
class ListDigest:
    profile: str
    set_digest: str
    tool_digests: dict[str, str]
    canonical: str  # JCS text that set_digest covers (without the domain prefix)


def digest_result(raw: bytes | str, profile: str = "full") -> ListDigest:
    """Digest the raw bytes of a tools/list result. Raises DigestError to reject."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {sorted(PROFILES)}")
    tools = extract_tools(parse(raw))
    selected = [select(t, profile) for t in tools]
    tool_digests = {t["name"]: _hash(profile, "tool", canonicalize(s)) for t, s in zip(tools, selected)}
    canonical = canonicalize(selected)
    return ListDigest(profile, _hash(profile, "set", canonical), tool_digests, canonical)


def compare(before: bytes | str, after: bytes | str, profile: str = "full") -> str:
    """Return 'same', 'differ' or 'reject' (if either side must be rejected)."""
    try:
        a = digest_result(before, profile)
        b = digest_result(after, profile)
    except DigestError:
        return "reject"
    return "same" if a.set_digest == b.set_digest else "differ"
