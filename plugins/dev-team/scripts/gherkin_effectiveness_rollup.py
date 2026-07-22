#!/usr/bin/env python3
"""gherkin_effectiveness_rollup.py — roll up gherkin-derive scenario data
against the coverage/mutation measurements the plugin already computes,
so there is a signal on whether BDD-derived tests catch more real defects
than ad hoc ones (issue #1296).

Today `/gherkin-derive` writes a surface inventory (`gherkin.md`) and
`/gherkin-public` writes a scenario→Story map (`gherkin-bindings.json`), while
`/coverage-baseline`, `/coverage-delta`, and the mutation baseline/history
files separately track coverage and mutation-survivor counts. Nothing
correlates the two. This script reads whatever of those files exist for one
workflow run and emits one JSONL record per discovered scenario to
`metrics/gherkin-derive-effectiveness.jsonl` (append-only, per the
`performance-metrics` skill's convention).

**Attribution granularity is honest, not exact.** No file in this plugin
today maps an individual scenario to the specific test(s) that exercise it
at the mutation/coverage level — `gherkin-bindings.json` maps a scenario to a
*Story* (which may bind several tests), and coverage/mutation deltas are
measured per-file or repo-wide, not per-scenario. This script therefore
reports the best available repo/workflow-level coverage and mutation deltas
alongside each scenario's provenance and binding mode, and does NOT claim a
delta is caused solely by that scenario's test. Treat the emitted
`coverage_delta` / `mutation_delta` fields as workflow-level context for the
scenario, not as isolated per-scenario attribution.

The surface-inventory table format is not fixed by `/gherkin-derive` today,
so parsing is deliberately lenient: any markdown table under the file is
scanned for columns whose header contains "surface", "source", "provenance",
or "mode" (case-insensitive); a file with no such table yields a warning on
stderr and zero scenario records, rather than crashing.

Stdlib-only. Python 3.8+ (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_OUT = Path("metrics/gherkin-derive-effectiveness.jsonl")

_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_SEPARATOR_CELL_RE = re.compile(r"^\s*:?-{2,}:?\s*$")

# Header keywords this parser recognizes, mapped to the output field name.
_COLUMN_KEYWORDS: Dict[str, str] = {
    "surface": "surface",
    "source": "discovery_source",
    "provenance": "provenance",
    "mode": "binding_mode",
    "file": "files",
}


class RollupWarning(Exception):
    """Non-fatal condition worth surfacing on stderr; callers keep going."""


def _split_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_surface_table(text: str) -> List[Dict[str, str]]:
    """Return one dict per data row of the first markdown table whose header
    matches at least one column in `_COLUMN_KEYWORDS`. Returns [] if no such
    table is found."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:
        header_match = _TABLE_ROW_RE.match(lines[i])
        sep_match = _TABLE_ROW_RE.match(lines[i + 1]) if header_match else None
        if header_match and sep_match:
            sep_cells = _split_row(lines[i + 1])
            if all(_SEPARATOR_CELL_RE.match(c) for c in sep_cells if c):
                header_cells = [c.lower() for c in _split_row(lines[i])]
                field_for_col = {}
                for idx, cell in enumerate(header_cells):
                    for keyword, field in _COLUMN_KEYWORDS.items():
                        if keyword in cell:
                            field_for_col[idx] = field
                            break
                if field_for_col:
                    rows: List[Dict[str, str]] = []
                    j = i + 2
                    while j < len(lines) and _TABLE_ROW_RE.match(lines[j]):
                        cells = _split_row(lines[j])
                        row = {
                            field: cells[idx]
                            for idx, field in field_for_col.items()
                            if idx < len(cells)
                        }
                        if row:
                            rows.append(row)
                        j += 1
                    return rows
        i += 1
    return []


def load_scenarios(gherkin_md: Optional[Path]) -> List[Dict[str, str]]:
    if gherkin_md is None:
        return []
    if not gherkin_md.is_file():
        raise RollupWarning(f"surface inventory not found: {gherkin_md}")
    rows = parse_surface_table(gherkin_md.read_text(encoding="utf-8"))
    if not rows:
        raise RollupWarning(f"no recognizable surface table in: {gherkin_md}")
    return rows


def load_json(path: Optional[Path]) -> Optional[dict]:
    if path is None:
        return None
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_bindings(bindings_json: Optional[Path]) -> Dict[str, object]:
    data = load_json(bindings_json)
    return data if isinstance(data, dict) else {}


def scenario_key(surface: str) -> str:
    """Best-effort key to look up a surface in `gherkin-bindings.json`, which
    is keyed `<feature-file>::<scenario-name>`. The inventory table has no
    fixed scenario-name column, so this matches by surface/feature-file
    prefix rather than requiring an exact key."""
    return surface.strip()


def coverage_delta(baseline: Optional[dict], current: Optional[dict]) -> Optional[dict]:
    if not baseline or not current:
        return None
    delta = {}
    for field in ("line_pct", "branch_pct"):
        b, c = baseline.get(field), current.get(field)
        if isinstance(b, (int, float)) and isinstance(c, (int, float)):
            delta[field] = round(c - b, 2)
    return delta or None


def mutation_delta(baseline: Optional[dict], current: Optional[dict]) -> Optional[dict]:
    if not baseline or not current:
        return None
    b, c = baseline.get("survivors_after"), current.get("survivors_after")
    if isinstance(b, (int, float)) and isinstance(c, (int, float)):
        return {"survivors_after_delta": c - b}
    return None


def build_records(
    scenarios: List[Dict[str, str]],
    bindings: Dict[str, object],
    cov_delta: Optional[dict],
    mut_delta: Optional[dict],
) -> List[dict]:
    records = []
    for row in scenarios:
        surface = row.get("surface", "")
        record = {
            "surface": surface or None,
            "discovery_source": row.get("discovery_source"),
            "provenance": row.get("provenance"),
            "binding_mode": row.get("binding_mode"),
            "bound_story": bindings.get(scenario_key(surface)),
            "coverage_delta": cov_delta,
            "mutation_delta": mut_delta,
        }
        records.append(record)
    return records


def append_jsonl(records: List[dict], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True))
            fh.write("\n")
    return len(records)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gherkin-md", type=Path, help="surface inventory markdown (gherkin.md)")
    parser.add_argument("--bindings-json", type=Path, help="gherkin-bindings.json, if present")
    parser.add_argument("--baseline-coverage", type=Path, help="baseline-coverage.json")
    parser.add_argument("--current-coverage", type=Path, help="latest coverage measurement (same shape as baseline-coverage.json)")
    parser.add_argument("--baseline-mutation", type=Path, help="baseline-mutation.json")
    parser.add_argument("--current-mutation", type=Path, help="latest mutation measurement (same shape as baseline-mutation.json)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output JSONL path (default: {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    try:
        scenarios = load_scenarios(args.gherkin_md)
    except RollupWarning as exc:
        print(f"gherkin_effectiveness_rollup: {exc}", file=sys.stderr)
        scenarios = []

    if not scenarios:
        print("gherkin_effectiveness_rollup: no scenarios to roll up; nothing written", file=sys.stderr)
        return 0

    bindings = load_bindings(args.bindings_json)
    cov_delta = coverage_delta(load_json(args.baseline_coverage), load_json(args.current_coverage))
    mut_delta = mutation_delta(load_json(args.baseline_mutation), load_json(args.current_mutation))

    records = build_records(scenarios, bindings, cov_delta, mut_delta)
    count = append_jsonl(records, args.out)
    print(f"gherkin_effectiveness_rollup: wrote {count} record(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
