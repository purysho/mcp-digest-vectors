"""Reference implementation of mcp-tool-digest/v1-draft (see SPEC.md)."""

from .digest import PROFILES, VERSION, ListDigest, compare, digest_result, select
from .jcs import DigestError, canonicalize, parse

__all__ = [
    "PROFILES",
    "VERSION",
    "DigestError",
    "ListDigest",
    "canonicalize",
    "compare",
    "digest_result",
    "parse",
    "select",
]
__version__ = "0.1.0"
