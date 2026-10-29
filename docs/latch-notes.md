# Latch against the vectors

Latch commit `de954a8` (2026-09-26), driven by `runner/latch-harness`. The harness parses each
listing the way `latch-mcp/src/stdio.rs` does (`serde_json::from_slice::<Value>` on the
JSON-RPC line, then `from_value::<ToolDescriptor>` per tool) and runs
`ToolRegistry::reconcile` on `before`, then on `after`. It does not exercise the stdio
transport itself, because Latch speaks the `2026-07-28` revision (`server/discover`),
which the fixture server does not implement.

## Results

- **Drift caught: 18/18.** Description, schema, annotation and tool-set changes are all
  detected, including nested parameter descriptions that a description-only pin misses.
- **Full scope: 6/6.** `descriptor_fingerprint` covers every member, including `title`,
  `outputSchema`, `_meta`, `icons` and unknown members.
- **Better than RFC 8785 on large integers.** serde_json keeps `9007199254740993` exact, so
  `limit-int-beyond-2-53` is flagged; a JCS digest cannot see that change.
- **False alarms: 2/9 equivalence vectors.** `eq-number-forms` (`20` vs `2e1`, `1` vs `1.0`)
  and `eq-negative-zero` (`0` vs `-0.0`). serde_json stores these as an integer in one listing
  and a float in the other, and serializes them differently (`20` vs `20.0`), so the sorted-key
  canonicalization in `schema.rs` produces different bytes. A server that switches JSON
  libraries would put its tools into `CHANGED` without any real change.
- **One miss: `reject-duplicate-key-evil-first`.** The stdio reader parses the whole line into
  a `serde_json::Value`, where a repeated member name keeps the last value. A listing with
  `"description": <malicious>, ..., "description": <original>` therefore pins and compares the
  original text. Whether that matters depends on what reads the same bytes next: a first-wins
  parser downstream would see the malicious text. Rejecting duplicate member names while
  reading (as `reject-*` vectors expect) closes this.

## Design note: tools that appear after the pin

On `drift-tool-added` and `drift-tool-renamed`, the new tool is inserted with state
`ACTIVE` and `registry.active_tool(...)` returns `Ok` immediately (the harness records
this in `results/latch.json`). Calls still go through `latch-core` policy evaluation,
which is deny-by-default, so this is only exposed if a policy rule matches tools by
wildcard. Worth deciding explicitly whether tools first seen after the initial
discovery should start in a pending state.

## Suggested fixes (small)

1. In `fingerprint_value`, canonicalize numbers before hashing (for example, re-encode every
   number as an f64 written per RFC 8785, or adopt the `mcp-digest` crate's serializer).
   That fixes both false alarms. Keep the exact-integer behaviour as a separate check if
   you want to keep catching 2^53+ changes.
2. Parse MCP stdout with a reader that rejects duplicate member names (the strict parser
   in `rust/src/json.rs` here is dependency-free and under 400 lines), or validate with a
   duplicate-detecting pass before `from_slice::<Value>`.
3. Add `runner/latch-harness` (or the vectors directly) to Latch's adversarial test matrix.
