# mcp-digest-vectors

**Test vectors for pinning MCP tool definitions.** 45 labeled before/after pairs of
`tools/list` results, two independent reference implementations that agree on every
known answer, a fixture MCP server that serves the vectors byte for byte, and a runner
that scores real pinning tools against them.

MCP clients, gateways and scanners pin tool definitions to catch "rug pulls": a server
changing a tool after the user approved it. Each project hashes definitions its own way,
and they disagree on what to cover, how to canonicalize JSON, and what to do with input
that two parsers read differently. The result is false alarms on harmless changes and
silent misses on real ones. Recent discussion on
[SEP-3452](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3452)
converged on RFC 8785 over full tool objects and asked for exactly this: a vector file so
clients can *check* compliance instead of claiming it.

## What a vector looks like

```json
{
  "id": "reject-duplicate-key-evil-first",
  "category": "reject",
  "title": "Duplicate 'description' member, malicious value first",
  "before": "{\"tools\":[{\"name\":\"read_invoice\", ...}]}",
  "after":  "{\"tools\":[{\"name\":\"read_invoice\",\"description\":\"...attacker...\", ... \"description\":\"Read an invoice ...\"}]}",
  "expect": {"desc": "reject", "four-field": "reject", "full": "reject"},
  "security": "changed-or-error",
  "known_answers": {"full": {"before": {"set": "sha256:…", "tools": {"read_invoice": "sha256:…"}}, "after": {"reject": "duplicate-key"}}}
}
```

`before`/`after` are raw JSON text, so key order, escapes and duplicate members survive.
`expect` is hand-written per scope; `known_answers` are exact digests under
[`SPEC.md`](SPEC.md) (`mcp-tool-digest/v1-draft`).

| Category | Count | What it tests |
|---|---|---|
| `eq-*` equivalence | 9 | Same definition, different bytes: key order (including UTF-16 vs code-point ordering of astral-plane names), whitespace, `20`/`2e1`, `-0.0`, `\u` escapes, `\/`, tool order. Flagging these is a false alarm. |
| `drift-*` | 19 | Real changes: appended instructions, zero-width and homoglyph edits, NFD vs NFC, ANSI escapes, nested parameter descriptions, required fields, defaults, enums, `readOnlyHint` flips, tools added/removed/renamed. |
| `scope-*` | 6 | Members only a full-object digest sees: `title`, `outputSchema`, `_meta` (including MCP Apps `resourceUri`), `icons`, unknown members. |
| `reject-*` | 10 | Parser differentials: duplicate keys (malicious first / last / nested), duplicate tool names, lone surrogates, NaN, `1e400`, invalid UTF-8, missing names. |
| `limit-*` | 1 | Integers beyond 2^53, which RFC 8785 cannot distinguish. |

## Results so far

Full matrix: [`results/RESULTS.md`](results/RESULTS.md).

| Tool | No false alarm | Drift caught | Parser-differential handled | Full scope |
|---|---|---|---|---|
| reference (this repo) | 9/9 | 18/18 | 10/10 | 6/6 |
| [Latch](https://github.com/purysho/Latch) `de954a8` | 7/9 | 18/18 | 9/10 | 6/6 |
| baseline: raw-bytes SHA-256 | 0/9 | 18/18 | 10/10 | 6/6 |
| baseline: `json.dumps(sort_keys=True)` | 6/9 | 18/18 | 9/10 | 6/6 |
| baseline: description only (first SEP-3452 draft) | 9/9 | 10/18 | 6/10 | 0/6 |

Two findings stand out. A description-only pin misses every schema and annotation
change, including instructions hidden in a *parameter's* description. And any pin built
on a last-wins JSON parser (Python, JavaScript, Go, serde_json's `Value`) pins the
*safe* text when a server sends a duplicate `description` with the malicious value first.
See [`docs/latch-notes.md`](docs/latch-notes.md) for Latch specifics.

Adapters for [mcpward](https://github.com/TsvetanG2/mcpward),
[mcp-scrutiny](https://github.com/bryand410/mcp-scrutiny) and
[guardbench](https://github.com/Manishmaurya89/mcp-guardbench) are written from their
documentation but **have not been run yet**. Results for them, and adapters for other
tools, are very welcome.

## Quick start

```bash
# Python reference (standard library only)
cd python && python3 -m mcp_digest verify ../vectors
python3 -m mcp_digest digest some-tools-list-result.json --profile full

# Rust implementation (independent parser and serializer)
cd rust && cargo test

# Score tools
python3 runner/run.py --list
python3 runner/run.py                     # every available adapter
python3 runner/run.py -a reference --vector eq-key-order
```

Check your own implementation: for each vector, digest `before` and `after` (decode
`after_b64` if present) and compare with `known_answers`. Any reject code is acceptable
where a reject is expected.

## How the pieces are checked

- `python/` passes the RFC 8785 test data from the RFC author, 6,291 numbers formatted by
  ECMAScript itself (`scripts/gen_es_numbers.mjs`), and 3,000 random values compared with
  the `rfc8785` package.
- `rust/` has its own JSON parser and serializer (no serde in the digest path) and
  reproduces all 270 known answers, the same reject codes, the same numbers and the RFC
  test data.
- `scripts/gen_vectors.py` refuses to write a vector whose hand-written expectation
  disagrees with the reference, and CI fails if `vectors/` is stale.
- Every tool run includes a control (identical listing) to catch adapter bugs.

## Adding a tool

Write an adapter in `runner/adapters/` with `probe()`, `pin(ctx)` and `check(ctx)`;
`ctx` gives a private workdir and `HOME`, a ready `.mcp.json` pointing at the fixture
server, and the server command. See `runner/adapters/thirdparty.py`.

## Layout

```
SPEC.md                 digest draft: scopes, RFC 8785, reject rules, open questions
vectors/                45 vectors + index.json (generated; do not edit by hand)
scripts/                vector generator, ECMAScript number fixture generator
python/                 reference implementation + tests
rust/                   independent implementation + tests
fixture/server.py       stdio MCP server that serves one side of a vector, byte for byte
runner/                 runner, report, adapters, Latch harness
results/                latest run
```

## Limits

- Synthetic fixtures, one run, in a sandbox. A tool's score here says how it handles these
  inputs, not how secure it is.
- A digest proves what was listed, not what executes, and cannot catch a definition that
  was malicious when first approved.
- Server `instructions` and `serverInfo` are out of scope for v1-draft (see SPEC Q7).

## License

MIT for everything except `python/tests/data/rfc8785/`, which is Apache-2.0
(© Anders Rundgren), copied unchanged.
