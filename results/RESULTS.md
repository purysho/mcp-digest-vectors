# Results

Generated 2026-10-29 by `runner/run.py` against 45 vectors (`mcp-tool-digest/v1-draft`).

Each tool pinned the fixture server while it served `before`, then checked it while it served `after`. Scores count only vectors with a clear security answer; `scope` and `informational` vectors are shown in the matrix but not scored. **These are results on synthetic fixtures, run once, in a sandbox; read the per-tool notes before drawing conclusions about any project.**

## Summary

| Tool | Version | Control | No false alarm on equivalent input | Drift caught | Parser-differential input refused or flagged | Full-scope members flagged | Harness errors |
|---|---|---|---|---|---|---|---|
| [reference](https://github.com/purysho/mcp-digest-vectors) | builtin | unchanged | 9/9 | 18/18 | 10/10 | 6/6 | 0 |
| [naive-raw-bytes](https://github.com/purysho/mcp-digest-vectors) | builtin | unchanged | 0/9 | 18/18 | 10/10 | 6/6 | 0 |
| [naive-sorted-json](https://github.com/purysho/mcp-digest-vectors) | builtin | unchanged | 6/9 | 18/18 | 9/10 | 6/6 | 0 |
| [naive-description-only](https://github.com/purysho/mcp-digest-vectors) | builtin | unchanged | 9/9 | 10/18 | 6/10 | 0/6 | 0 |
| [latch](https://github.com/purysho/Latch) | de954a8 | unchanged | 7/9 | 18/18 | 9/10 | 6/6 | 0 |
| [guardbench](https://github.com/Manishmaurya89/mcp-guardbench) | not run | – | – | – | – | – | `guardbench` not on PATH; pip install mcp-guardbench |
| [mcp-scrutiny](https://github.com/bryand410/mcp-scrutiny) | not run | – | – | – | – | – | `mcp-scrutiny` not on PATH; pip install mcp-scrutiny (Python 3.11+) |
| [mcpward](https://github.com/TsvetanG2/mcpward) | not run | – | – | – | – | – | `mcpward` not on PATH; npm install -g mcpward (Node 22+) |

Control = identical before/after listing; anything but `unchanged` means the tool cannot be used as a pin in this harness. Rows marked *not run* have adapters written from each project's documentation that have never been executed; install the tool and rerun to fill them in.

## Per-vector matrix

`pass` = the security-correct answer · **MISS** = reported unchanged after a real change · **FALSE ALARM** = flagged an equivalent listing · `error` = the tool failed on a changed listing · `flags`/`silent` = what the tool did on an unscored vector · `n/a` = the harness could not drive the tool for this vector.

| Vector | Expect | reference | naive-raw-bytes | naive-sorted-json | naive-description-only | latch |
|---|---|---|---|---|---|---|
| `eq-key-order` | unchanged | pass | **FALSE ALARM** | pass | pass | pass |
| `eq-whitespace` | unchanged | pass | **FALSE ALARM** | pass | pass | pass |
| `eq-number-forms` | unchanged | pass | **FALSE ALARM** | **FALSE ALARM** | pass | **FALSE ALARM** |
| `eq-negative-zero` | unchanged | pass | **FALSE ALARM** | **FALSE ALARM** | pass | **FALSE ALARM** |
| `eq-unicode-escapes` | unchanged | pass | **FALSE ALARM** | pass | pass | pass |
| `eq-solidus-escape` | unchanged | pass | **FALSE ALARM** | pass | pass | pass |
| `eq-control-escape` | unchanged | pass | **FALSE ALARM** | pass | pass | pass |
| `eq-astral-key-order` | unchanged | pass | **FALSE ALARM** | pass | pass | pass |
| `eq-tool-order` | unchanged | pass | **FALSE ALARM** | **FALSE ALARM** | pass | pass |
| `drift-description-appended` | changed | pass | pass | pass | pass | pass |
| `drift-zero-width` | changed | pass | pass | pass | pass | pass |
| `drift-homoglyph` | changed | pass | pass | pass | pass | pass |
| `drift-trailing-space` | changed | pass | pass | pass | pass | pass |
| `drift-unicode-nfd` | changed | pass | pass | pass | pass | pass |
| `drift-ansi-escape` | changed | pass | pass | pass | pass | pass |
| `drift-description-absent-to-empty` | changed | pass | pass | pass | pass | pass |
| `drift-tool-added` | changed | pass | pass | pass | pass | pass |
| `drift-tool-removed` | changed | pass | pass | pass | pass | pass |
| `drift-tool-renamed` | changed | pass | pass | pass | pass | pass |
| `drift-schema-property-description` | changed | pass | pass | pass | **MISS** | pass |
| `drift-schema-required-added` | changed | pass | pass | pass | **MISS** | pass |
| `drift-schema-default-changed` | changed | pass | pass | pass | **MISS** | pass |
| `drift-schema-enum-widened` | changed | pass | pass | pass | **MISS** | pass |
| `drift-schema-additional-properties` | changed | pass | pass | pass | **MISS** | pass |
| `drift-annotation-readonly-flip` | changed | pass | pass | pass | **MISS** | pass |
| `drift-annotation-destructive-flip` | changed | pass | pass | pass | **MISS** | pass |
| `drift-annotations-removed` | changed | pass | pass | pass | **MISS** | pass |
| `drift-annotations-absent-to-empty` | – | flags | flags | flags | silent | flags |
| `scope-title-changed` | – | flags | flags | flags | silent | flags |
| `scope-output-schema-changed` | – | flags | flags | flags | silent | flags |
| `scope-meta-ui-resource` | – | flags | flags | flags | silent | flags |
| `scope-meta-volatile` | – | flags | flags | flags | silent | flags |
| `scope-icons-changed` | – | flags | flags | flags | silent | flags |
| `scope-unknown-member` | – | flags | flags | flags | silent | flags |
| `reject-duplicate-key-evil-first` | changed or error | pass | pass | **MISS** | **MISS** | **MISS** |
| `reject-duplicate-key-evil-last` | changed or error | pass | pass | pass | pass | pass |
| `reject-duplicate-key-nested` | changed or error | pass | pass | pass | **MISS** | pass |
| `reject-duplicate-tool-name` | changed or error | pass | pass | pass | pass | pass |
| `reject-lone-surrogate` | changed or error | pass | pass | pass | pass | pass |
| `reject-nan` | changed or error | pass | pass | pass | **MISS** | pass |
| `reject-number-overflow` | changed or error | pass | pass | pass | **MISS** | pass |
| `reject-missing-name` | changed or error | pass | pass | pass | pass | pass |
| `reject-not-a-tool-list` | changed or error | pass | pass | pass | pass | pass |
| `reject-invalid-utf8` | changed or error | pass | pass | pass | pass | pass |
| `limit-int-beyond-2-53` | – | silent | flags | flags | silent | flags |

## Details for non-pass cells

### latch

- `eq-number-forms` (false-alarm): added=0 changed=2 missing=0 unchanged=1
- `eq-negative-zero` (false-alarm): added=0 changed=1 missing=0 unchanged=2
- `reject-duplicate-key-evil-first` (miss): added=0 changed=0 missing=0 unchanged=3

