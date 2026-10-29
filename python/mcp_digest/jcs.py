"""Strict JSON parsing and RFC 8785 (JCS) canonicalization, standard library only.

Parsing is strict on purpose: anything two JSON parsers could read differently
(duplicate keys, lone surrogates, non-finite numbers) is rejected rather than
resolved, so a digest never depends on which parser a client happens to use.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


class DigestError(ValueError):
    """Input that must be rejected. `code` matches the table in SPEC.md section 2."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


# ---------------------------------------------------------------- parsing


def _reject_constant(name: str) -> Any:
    raise DigestError("invalid-json", f"non-standard constant {name}")


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DigestError("duplicate-key", f"duplicate member name {key!r}")
        out[key] = value
    return out


def _parse_int(text: str) -> float:
    # JCS treats every number as IEEE 754 binary64.
    try:
        value = float(int(text))
    except OverflowError:
        raise DigestError("number-out-of-range", f"integer {text[:20]}... is not a finite double")
    return value


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise DigestError("number-out-of-range", f"number {text!r} is not a finite double")
    return value


def parse(raw: bytes | str) -> Any:
    """Parse JSON text strictly. Bytes must be UTF-8 (a leading BOM is rejected)."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise DigestError("invalid-utf8", str(exc)) from None
    else:
        text = raw
    if text.startswith("﻿"):
        raise DigestError("invalid-json", "byte order mark is not allowed")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_constant=_reject_constant,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
    except DigestError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise DigestError("invalid-json", str(exc)) from None
    _check_strings(value)
    return value


def _check_str(s: str) -> None:
    try:
        s.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise DigestError("lone-surrogate", "string contains an unpaired surrogate") from None


def _check_strings(value: Any) -> None:
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            _check_str(v)
        elif isinstance(v, dict):
            for k, item in v.items():
                _check_str(k)
                stack.append(item)
        elif isinstance(v, list):
            stack.extend(v)


# ---------------------------------------------------------------- serialization


def _utf16_key(s: str) -> bytes:
    # Big-endian UTF-16 bytes sort in the same order as UTF-16 code units.
    return s.encode("utf-16-be")


_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def serialize_string(s: str) -> str:
    out = ['"']
    for ch in s:
        esc = _ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def serialize_number(x: float) -> str:
    """ECMAScript Number.prototype.toString for a finite double (RFC 8785 section 3.2.2.3)."""
    if not math.isfinite(x):
        raise DigestError("number-out-of-range", f"{x!r} is not finite")
    if x == 0:
        return "0"  # also covers -0
    sign = "-" if x < 0 else ""
    # repr() gives the shortest digit string that round-trips, as ECMAScript requires.
    _, digit_tuple, exponent = Decimal(repr(abs(x))).as_tuple()
    digits = "".join(map(str, digit_tuple)).rstrip("0")
    exponent += len("".join(map(str, digit_tuple))) - len(digits)  # account for stripped zeros
    k = len(digits)
    n = exponent + k  # position of the decimal point relative to the digit string
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        body = f"{mantissa}e{'+' if e > 0 else '-'}{abs(e)}"
    return sign + body


def canonicalize(value: Any) -> str:
    """Return the RFC 8785 canonical text of an already-parsed JSON value."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        _check_str(value)
        return serialize_string(value)
    if isinstance(value, (int, float)):
        return serialize_number(float(value))
    if isinstance(value, list):
        return "[" + ",".join(canonicalize(v) for v in value) + "]"
    if isinstance(value, dict):
        for k in value:
            _check_str(k)
        items = sorted(value.items(), key=lambda kv: _utf16_key(kv[0]))
        return "{" + ",".join(serialize_string(k) + ":" + canonicalize(v) for k, v in items) + "}"
    raise TypeError(f"not a JSON value: {type(value).__name__}")
