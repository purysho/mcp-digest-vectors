"""Adapters wrap one pinning tool each.

An adapter is an object with:
    name: str                          short id used on the command line
    description: str, url: str
    probe() -> str                     return a version string, or raise Unavailable(reason)
    pin(ctx) -> None                   record a baseline while the server serves "before"
    check(ctx) -> Outcome              compare against the baseline while it serves "after"

`ctx` (runner.run.Ctx) gives a private workdir and HOME, a ready-made .mcp.json,
the fixture server command, and an env dict to pass to subprocesses.
"""

from __future__ import annotations

from dataclasses import dataclass


class Unavailable(RuntimeError):
    """The tool is not installed or cannot run here."""


class HarnessError(RuntimeError):
    """The adapter could not drive the tool for this vector (not a verdict on the tool)."""


@dataclass
class Outcome:
    result: str  # "unchanged" | "changed" | "error"
    detail: str = ""


def registry() -> dict:
    from . import builtin, thirdparty

    adapters = {}
    for module in (builtin, thirdparty):
        for a in module.ADAPTERS:
            adapters[a.name] = a
    return adapters
