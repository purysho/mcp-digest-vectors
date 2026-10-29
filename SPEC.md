# MCP Tool Definition Digest — v1-draft

Status: **draft for discussion**, written to inform
[SEP-3452](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3452)
and related tool-integrity proposals. Nothing here is normative for MCP itself.
The identifier `mcp-tool-digest/v1-draft` will change if the rules change.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 1. Problem

Several MCP clients, gateways and scanners pin tool definitions so they can
detect a "rug pull": a server changing what a tool says after a user approved
it. Each project hashes tool definitions its own way. They disagree on:

1. **Scope** — which fields of a tool are covered (description only? schema?
   annotations? `outputSchema`, `title`, `_meta`?).
2. **Canonical form** — how a JSON value becomes bytes before hashing.
3. **Failure handling** — what happens with input that two JSON parsers read
   differently (duplicate keys, lone surrogates, out-of-range numbers).

Disagreement on (2) causes false alarms. Disagreement on (1) and (3) causes
missed changes. This document fixes one answer for each so that the vectors in
`vectors/` have exact expected outputs, and records the choices that remain open.

## 2. Input

The input is the raw bytes of a `tools/list` result: a JSON object with a
`tools` array. Other members (for example `nextCursor`) are ignored.
Pagination is out of scope: callers concatenate pages before digesting.

An implementation MUST **reject** (produce no digest) when any of these hold:

| Code | Condition |
|---|---|
| `invalid-utf8` | The bytes are not valid UTF-8. |
| `invalid-json` | The bytes are not a single JSON value per RFC 8259. `NaN`, `Infinity`, comments and trailing commas are invalid. |
| `duplicate-key` | Any object, at any depth, has two members with the same name (compared after unescaping). |
| `lone-surrogate` | Any string, after unescaping, contains an unpaired UTF-16 surrogate. |
| `number-out-of-range` | Any number is not finite when read as an IEEE 754 binary64 value. |
| `not-a-tool-list` | The value is not an object with a `tools` member that is an array of objects. |
| `bad-tool-name` | A tool has no `name`, or `name` is not a non-empty string. |
| `duplicate-tool-name` | Two tools share a `name`. |

Rejecting is the security-relevant choice: a definition that two parsers can
read differently cannot be pinned meaningfully. A client that rejects SHOULD
treat the server as changed (fail closed), not as unchanged.

## 3. Scopes (profiles)

A profile selects which members of each tool object are digested. Selected
members are copied only if present; an absent member stays absent (it is not
turned into `null`), so absent, `null` and `{}` are three different states.

| Profile | Members selected |
|---|---|
| `desc` | `name`, `description` |
| `four-field` | `name`, `description`, `inputSchema`, `annotations` |
| `full` | every member of the tool object, including `title`, `outputSchema`, `icons`, `_meta` and any unknown member |

`desc` mirrors the first draft of SEP-3452 (pin the description). `four-field`
mirrors the scope used by several existing tools. `full` is the conservative
default this document **recommends**: anything the server sends may reach the
model or the client UI, so anything may carry an attack.

## 4. Canonical form

The selected object is serialized with the JSON Canonicalization Scheme,
[RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) (JCS):

- object members sorted by name, comparing UTF-16 code units;
- no insignificant whitespace;
- strings escaped minimally (`\"`, `\\`, `\b \f \n \r \t`, other controls as
  lowercase `\u00xx`), everything else written as UTF-8;
- numbers written with the ECMAScript `Number.prototype.toString` algorithm,
  so `1`, `1.0` and `1e0` are identical, and `-0` is written `0`.

No Unicode normalization is applied. `"é"` (U+00E9) and `"é"` (U+0065 U+0301)
are different strings and produce different digests.

## 5. Digests

```
tool_digest(t)  = "sha256:" || hex( SHA-256( "mcp-tool-digest/v1-draft/<profile>/tool" || 0x00 || JCS(select(t)) ) )
set_digest(ts)  = "sha256:" || hex( SHA-256( "mcp-tool-digest/v1-draft/<profile>/set"  || 0x00 || JCS([select(t) for t in ts sorted by name]) ) )
```

`<profile>` is the profile name from section 3. Tools are sorted by `name`
comparing UTF-16 code units, so server ordering does not matter. The domain
prefix stops a digest computed under one profile or for one purpose from being
mistaken for another.

## 6. Known limitations (by design of JCS)

- **Integers beyond 2^53 collapse.** JCS reads every number as binary64, so
  `9007199254740993` and `9007199254740992` serialize identically. A schema
  `maximum` can change without changing the digest. Vector
  `limit-int-beyond-2-53` demonstrates this. A future version could pin the
  original number text instead.
- **A digest proves what was listed, not what runs.** Pinning cannot show that
  `tools/call` executes the definition that was pinned, and it cannot detect a
  definition that was malicious when first approved.

## 7. Open questions (each has vectors)

| Id | Question | This draft's answer | Vectors |
|---|---|---|---|
| Q1 | Digest scope: description only, four fields, or the full object? | `full` recommended; all three defined | `scope-*` |
| Q2 | Canonical form: RFC 8785, or something else? | RFC 8785 | `eq-*` |
| Q3 | Parser differentials (duplicate keys, lone surrogates): reject or pick one reading? | reject | `reject-*` |
| Q4 | Unicode normalization before hashing? | none (byte-exact strings) | `drift-unicode-nfd` |
| Q5 | Large integers: accept the JCS collapse, or pin number text? | accept, documented | `limit-int-beyond-2-53` |
| Q6 | Should `_meta` be excluded as volatile? | no; included in `full` | `scope-meta-*` |
| Q7 | Should server `instructions` and `serverInfo` be digested with the tools? | out of scope for this draft: the input is a `tools/list` result only. A combined digest would wrap this one; see below. | none yet |

### Relationship to the SEP-3452 discussion

The SEP-3452 thread (closed 2026-10-26 pending working-group discussion)
converged on: complete tool objects sorted by name, RFC 8785, SHA-256 with
domain separation, plus server `instructions` and `serverInfo` as further
inputs, compared within one authorization scope. This draft's `full` profile
matches the tool part of that proposal. Participants asked for a vector file to
ship alongside the algorithm so clients can check compliance instead of
claiming it; that is what `vectors/` is meant to be. Adding an `instructions`
input is a natural v2 once its normalization (absent vs `""`) is agreed.

## 8. Conformance

An implementation conforms to a profile if, for every vector in `vectors/`:

- it rejects exactly the inputs the vector marks as rejected (any reject code
  is acceptable; codes are informative), and
- for every accepted input, its `set_digest` and each `tool_digest` equal the
  known answers in the vector, byte for byte.

`python/` and `rust/` are two independent implementations; CI checks that both
reproduce every known answer.
