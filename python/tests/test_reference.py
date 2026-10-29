"""Tests for the Python reference implementation.

Independent checks, in order of strength:
  1. RFC 8785 test data published by the RFC's author (vendored).
  2. Number formatting compared with Node.js (the ECMAScript algorithm itself), if node is on PATH.
  3. Whole-value output compared with the `rfc8785` package (Trail of Bits), if installed.
  4. Every known answer in ../vectors re-derived, and the generator output up to date.
"""

from __future__ import annotations

import json
import random
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

from mcp_digest import DigestError, canonicalize, compare, digest_result, parse  # noqa: E402
from mcp_digest.__main__ import verify  # noqa: E402
from mcp_digest.jcs import serialize_number  # noqa: E402

DATA = HERE / "data" / "rfc8785"


# ------------------------------------------------------------------ 1. RFC 8785 test data

@pytest.mark.parametrize("name", sorted(p.name for p in (DATA / "input").glob("*.json")))
def test_rfc8785_testdata(name):
    got = canonicalize(parse((DATA / "input" / name).read_bytes())).encode("utf-8")
    assert got == (DATA / "output" / name).read_bytes()


@pytest.mark.parametrize("value,text", [
    (0.0, "0"), (-0.0, "0"), (1.0, "1"), (-1.5, "-1.5"), (1e21, "1e+21"), (1e20, "100000000000000000000"),
    (1e-6, "0.000001"), (1e-7, "1e-7"), (5e-324, "5e-324"), (1.7976931348623157e308, "1.7976931348623157e+308"),
    (123456789012345680000.0, "123456789012345680000"), (0.1 + 0.2, "0.30000000000000004"),
    (9007199254740993.0, "9007199254740992"), (333333333.3333333, "333333333.3333333"),
])
def test_number_examples(value, text):
    assert serialize_number(value) == text


# ------------------------------------------------------------------ 2. numbers vs Node.js

def _random_doubles(n: int, seed: int = 8785) -> list[float]:
    rng = random.Random(seed)
    out: list[float] = []
    while len(out) < n:
        x = struct.unpack("<d", rng.getrandbits(64).to_bytes(8, "little"))[0]
        if x == x and abs(x) != float("inf"):
            out.append(x)
    out += [rng.uniform(-1e6, 1e6) for _ in range(n // 4)]
    out += [float(rng.randint(-10**16, 10**16)) for _ in range(n // 4)]
    out += [rng.randint(1, 999) * 10.0 ** rng.randint(-30, 30) for _ in range(n // 4)]
    return out


def test_numbers_match_ecmascript_fixture():
    pairs = json.loads((HERE / "data" / "es-numbers.json").read_text())
    assert len(pairs) > 1000
    for bits, expected in pairs:
        x = struct.unpack(">d", bytes.fromhex(bits))[0]
        assert serialize_number(x) == expected, bits


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_numbers_match_ecmascript_live():
    xs = _random_doubles(20000)
    script = "const xs=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(xs.map(String)))"
    # Pass doubles as exact hex-free JSON via repr (round-trips exactly in both languages).
    payload = "[" + ",".join(repr(x) for x in xs) + "]"
    res = subprocess.run(["node", "-e", script], input=payload, capture_output=True, text=True, check=True)
    expected = json.loads(res.stdout)
    mismatches = [(x, e, serialize_number(x)) for x, e in zip(xs, expected) if serialize_number(x) != e]
    assert not mismatches, mismatches[:5]


# ------------------------------------------------------------------ 3. vs the rfc8785 package

def _random_value(rng: random.Random, depth: int = 0):
    kind = rng.randrange(7 if depth < 4 else 4)
    if kind == 0:
        return rng.choice([None, True, False])
    if kind == 1:
        return rng.choice([0, 1, -7, 2**40, 3.25, -1e-9, 6.02e23])
    if kind in (2, 3):
        alphabet = "aZ09 \"\\/\t\n\u0001\u007fé€\U0001F600ד"
        return "".join(rng.choice(alphabet) for _ in range(rng.randrange(8)))
    if kind == 4:
        return [_random_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    keys = ("".join(rng.choice("abABé\U0001F600｡_1") for _ in range(rng.randrange(1, 5)))
            for _ in range(rng.randrange(5)))
    return {k: _random_value(rng, depth + 1) for k in keys}


def test_matches_rfc8785_package():
    rfc8785 = pytest.importorskip("rfc8785")
    rng = random.Random(1)
    for _ in range(3000):
        v = _random_value(rng)
        assert canonicalize(v) == rfc8785.dumps(v).decode("utf-8"), v


# ------------------------------------------------------------------ strict parsing

@pytest.mark.parametrize("raw,code", [
    (b'{"a":1,"a":2}', "duplicate-key"),
    (b'{"x":{"a":1,"\\u0061":2}}', "duplicate-key"),  # same name after unescaping
    (b'["\\ud800"]', "lone-surrogate"),
    (b'{"\\udc00":1}', "lone-surrogate"),
    (b"[NaN]", "invalid-json"),
    (b"[Infinity]", "invalid-json"),
    (b"[1e400]", "number-out-of-range"),
    (b"[" + b"9" * 400 + b"]", "number-out-of-range"),
    (b'["\xff"]', "invalid-utf8"),
    (b"\xef\xbb\xbf[]", "invalid-json"),
    (b"[1,]", "invalid-json"),
    (b"[1] [2]", "invalid-json"),
])
def test_parse_rejects(raw, code):
    with pytest.raises(DigestError) as exc:
        parse(raw)
    assert exc.value.code == code


@pytest.mark.parametrize("raw,code", [
    ('{"tools":{}}', "not-a-tool-list"),
    ('{"tool":[]}', "not-a-tool-list"),
    ('{"tools":[1]}', "not-a-tool-list"),
    ('{"tools":[{"description":"x"}]}', "bad-tool-name"),
    ('{"tools":[{"name":""}]}', "bad-tool-name"),
    ('{"tools":[{"name":7}]}', "bad-tool-name"),
    ('{"tools":[{"name":"a"},{"name":"a"}]}', "duplicate-tool-name"),
])
def test_result_rejects(raw, code):
    with pytest.raises(DigestError) as exc:
        digest_result(raw)
    assert exc.value.code == code


def test_profiles_and_domain_separation():
    raw = '{"tools":[{"name":"a","description":"d","title":"t"}],"nextCursor":"ignored"}'
    digests = {p: digest_result(raw, p).set_digest for p in ("desc", "four-field", "full")}
    # desc and four-field select the same members here, but the domain prefix keeps them distinct.
    assert len(set(digests.values())) == 3
    r = digest_result(raw, "full")
    assert r.canonical == '[{"description":"d","name":"a","title":"t"}]'
    assert set(r.tool_digests) == {"a"} and r.tool_digests["a"] != r.set_digest
    assert compare(raw, raw.replace('"title":"t"', '"title":"u"'), "four-field") == "same"
    assert compare(raw, raw.replace('"title":"t"', '"title":"u"'), "full") == "differ"


def test_empty_tool_list_is_valid():
    assert digest_result('{"tools":[]}').canonical == "[]"


# ------------------------------------------------------------------ 4. vectors

def test_vectors_known_answers(capsys):
    assert verify(ROOT / "vectors") == 0


def test_vectors_up_to_date():
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_vectors.py"), "--check"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
