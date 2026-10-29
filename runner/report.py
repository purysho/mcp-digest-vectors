"""Turn results/<adapter>.json files into results/RESULTS.md."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

CELL = {"pass": "pass", "miss": "**MISS**", "false-alarm": "**FALSE ALARM**", "error": "error",
        "harness-error": "n/a"}
ORDER = ["reference", "naive-raw-bytes", "naive-sorted-json", "naive-description-only"]


def _cell(row: dict) -> str:
    if row["verdict"] == "info":
        return {"changed": "flags", "unchanged": "silent", "error": "error"}[row["outcome"]]
    return CELL[row["verdict"]]


def _score(rows: list[dict], categories: set[str] | None = None, security: set[str] | None = None) -> str:
    sel = [r for r in rows if (categories is None or r["category"] in categories)
           and (security is None or r["security"] in security) and r["verdict"] != "harness-error"]
    if not sel:
        return "–"
    return f"{sum(r['verdict'] == 'pass' for r in sel)}/{len(sel)}"


def write_report(out: Path, vectors: Path) -> None:
    records = [json.loads(p.read_text()) for p in sorted(out.glob("*.json"))]
    records.sort(key=lambda r: (not r.get("available"), ORDER.index(r["adapter"]) if r["adapter"] in ORDER else 99,
                                r["adapter"]))
    ran = [r for r in records if r.get("available")]
    index = json.loads((vectors / "index.json").read_text())["vectors"]

    lines = [
        "# Results",
        "",
        f"Generated {date.today().isoformat()} by `runner/run.py` against {len(index)} vectors "
        f"(`{json.loads((vectors / 'index.json').read_text())['version']}`).",
        "",
        "Each tool pinned the fixture server while it served `before`, then checked it while it served "
        "`after`. Scores count only vectors with a clear security answer; `scope` and `informational` "
        "vectors are shown in the matrix but not scored. **These are results on synthetic fixtures, run once, "
        "in a sandbox; read the per-tool notes before drawing conclusions about any project.**",
        "",
        "## Summary",
        "",
        "| Tool | Version | Control | No false alarm on equivalent input | Drift caught | Parser-differential input refused or flagged | Full-scope members flagged | Harness errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        if not r.get("available"):
            lines.append(f"| [{r['adapter']}]({r['url']}) | not run | – | – | – | – | – | {r['reason']} |")
            continue
        rows = r["rows"]
        scope = [x for x in rows if x["category"] == "scope" and x["verdict"] != "harness-error"]
        scope_s = f"{sum(x['outcome'] == 'changed' for x in scope)}/{len(scope)}" if scope else "–"
        herr = sum(x["verdict"] == "harness-error" for x in rows)
        lines.append(
            f"| [{r['adapter']}]({r['url']}) | {r['version']} | {r['control']} | "
            f"{_score(rows, {'equivalence'})} | {_score(rows, {'drift'}, {'changed'})} | "
            f"{_score(rows, {'reject'})} | {scope_s} | {herr} |"
        )

    lines += ["", "Control = identical before/after listing; anything but `unchanged` means the tool cannot be used as a pin "
              "in this harness. Rows marked *not run* have adapters written from each project's documentation that "
              "have never been executed; install the tool and rerun to fill them in.", ""]

    if ran:
        lines += ["## Per-vector matrix", "",
                  "`pass` = the security-correct answer · **MISS** = reported unchanged after a real change · "
                  "**FALSE ALARM** = flagged an equivalent listing · `error` = the tool failed on a changed listing · "
                  "`flags`/`silent` = what the tool did on an unscored vector · `n/a` = the harness could not drive "
                  "the tool for this vector.", ""]
        lines.append("| Vector | Expect | " + " | ".join(r["adapter"] for r in ran) + " |")
        lines.append("|---|---|" + "---|" * len(ran))
        by_id = {r["adapter"]: {x["id"]: x for x in r["rows"]} for r in ran}
        for v in index:
            expect = {"unchanged": "unchanged", "changed": "changed", "changed-or-error": "changed or error",
                      "informational": "–"}[v["security"]]
            cells = [_cell(by_id[r["adapter"]][v["id"]]) if v["id"] in by_id[r["adapter"]] else "" for r in ran]
            lines.append(f"| `{v['id']}` | {expect} | " + " | ".join(cells) + " |")

    notes = [r for r in records if r.get("available") and any(x["detail"] for x in r["rows"])]
    if notes:
        lines += ["", "## Details for non-pass cells", ""]
        for r in notes:
            interesting = [x for x in r["rows"] if x["verdict"] not in ("pass", "info") and x["detail"]]
            if not interesting:
                continue
            lines += [f"### {r['adapter']}", ""]
            for x in interesting[:15]:
                lines.append(f"- `{x['id']}` ({x['verdict']}): {x['detail'][:240]}")
            lines.append("")
    (out / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
