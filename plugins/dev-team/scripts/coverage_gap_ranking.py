#!/usr/bin/env python3
"""coverage_gap_ranking.py — rank uncovered-line buckets by module and decide
whether a coverage percentage target is reachable without new test seams
(issues #1786, #1787).

Why this exists. `/test-improve` Phase 5 used to order its work by **mutation
survivors**. A surviving mutant can only exist on a line a test already
executes, so a survivor-ordered priority list structurally steers *away* from
0%-covered layers — precisely where the missing coverage lives. In the
nextgen-core Pass-1 retro, ~3,884 of the ~4,190 lines needed to reach 90% sat
in a `Repositories` layer at 0-11% coverage that Phase 5 never touched, while
the whole phase went into adding mutation-kill assertions to `Pipes` layers
already at 88-95%. This script computes the ranking that replaces that
ordering — from the coverage report itself, deterministically, never estimated
by a model.

It answers two questions:

1. **Where is the uncovered code?** (issue #1786) — per-module buckets ranked
   by uncovered lines descending. This is the ordering input for
   `/test-improve` Phase 1's improvement plan and Phase 4's Story set.
2. **Can a stated coverage target be reached at all under `no-refactor`?**
   (issue #1787) — arithmetic, not judgement: if the lines still needed to hit
   the target exceed every uncovered line sitting in a module that *already
   has an established test seam*, the target is unreachable without
   production-code seams, and `/test-improve` Phase 0 must say so before work
   starts rather than waiving a gate later.

Module grouping. Records that name their own module (coverlet assemblies,
jacoco packages) keep it. Everything else is bucketed by the first
`--group-depth` path segments, relative to `--repo-root` when given — and when
it is not, relative to the deepest directory prefix every absolute path shares
(`derive_common_root`), because otherwise a report with absolute paths collapses
into a single bucket and the seam classification below degenerates into one
global coverage-vs-threshold comparison. A grouping that still ends up with one
bucket for many files sets `grouping_degenerate: true` in the output so it can
never be read as a verdict.

Seam classification is the one tunable judgement: a module whose line coverage
is below `--seam-threshold-pct` (default 10.0) is treated as having **no
established test seam** — nothing there is proven reachable by a test-only
change. Everything else in this script is counting. The threshold is recorded
in the output so a verdict is always readable against the assumption that
produced it.

Supported report formats (auto-detected — the same set `/coverage-baseline`
already parses for its line/branch percentages):

| Format            | Detected by                              | Module key      |
|-------------------|------------------------------------------|-----------------|
| `lcov`            | `SF:` records                            | path prefix     |
| `cobertura`       | XML root `<coverage>` with `<packages>`  | path prefix     |
| `jacoco-csv`      | CSV header with `LINE_MISSED`            | `PACKAGE`       |
| `istanbul-summary`| JSON with a `total.lines` block          | path prefix     |
| `istanbul-final`  | JSON whose file entries carry `s`/`b`    | path prefix     |
| `coverage-py`     | JSON with `files` + `totals`             | path prefix     |
| `coverlet`        | JSON assembly -> file -> class -> method | assembly name   |

Exit codes:

- `0` — ranking produced; no target given, or the target is `reachable`,
  `already_met`, or `not_measured`.
- `2` — nothing to rank: a report path that does not exist, a report that
  fails to parse, or a report that parses to zero coverage records. An empty
  scan is never reported as an all-clear (same fail-loud posture as
  `gherkin_stub_gate.py`).
- `3` — a stated target is `unreachable_without_seams`. Callers gate on this.

Stdlib-only (ADR 0014/0015), Python 3.10+ floor (ADR 0031).

Usage:
    python3 coverage_gap_ranking.py --report coverage/lcov.info
    python3 coverage_gap_ranking.py --report coverage.json \\
        --target-line-pct 90 --target-branch-pct 90 --json \\
        --out .dev-team-reports/test-improve/<slug>/data/coverage-gap-ranking.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

import coverage_report_parse

DEFAULT_SEAM_THRESHOLD_PCT = 10.0
DEFAULT_GROUP_DEPTH = 2
DEFAULT_TOP = 20

VERDICT_ALREADY_MET = "already_met"
VERDICT_REACHABLE = "reachable"
VERDICT_UNREACHABLE = "unreachable_without_seams"
VERDICT_NOT_MEASURED = "not_measured"

# Worst-first precedence used to collapse the per-target verdicts into one.
# `not_measured` outranks `reachable` deliberately: a positive overall verdict
# must never rest on a dimension the report could not measure at all.
_VERDICT_PRECEDENCE = (
    VERDICT_UNREACHABLE,
    VERDICT_NOT_MEASURED,
    VERDICT_REACHABLE,
    VERDICT_ALREADY_MET,
)

# ---------------------------------------------------------------------------
# format detection + parsing — delegated to the shared coverage_report_parse
# module (issue #1873), which owns the one canonical record type
# (covered_statements/total_statements/covered_branches/total_branches) and
# every per-format parser. Re-exported here so this script's own callers and
# tests keep importing `ReportError`/`detect_format` from this module.
# ---------------------------------------------------------------------------

ReportError = coverage_report_parse.ReportError
detect_format = coverage_report_parse.detect_format


def _record(
    path: str,
    lines_total: int,
    lines_covered: int,
    branches_total: int = 0,
    branches_covered: int = 0,
    module: str | None = None,
) -> dict:
    return {
        "path": path,
        "lines_total": lines_total,
        "lines_covered": lines_covered,
        "branches_total": branches_total,
        "branches_covered": branches_covered,
        "module": module,
    }


def parse_report(path: Path, fmt: str) -> list[dict]:
    """Parse `path` as `fmt` via the shared `coverage_report_parse` module,
    translating its `CoverageRecord`s (`covered_statements`/
    `total_statements`/`covered_branches`/`total_branches`) into this
    script's own `lines_total`/`lines_covered`/`branches_total`/
    `branches_covered` record shape — the vocabulary `rank_modules`,
    `build_report`, and the CLI's JSON output already use."""
    records = coverage_report_parse.parse_report(path, fmt)
    return [
        _record(
            r.path,
            r.total_statements,
            r.covered_statements,
            r.total_branches,
            r.covered_branches,
            r.module,
        )
        for r in records
    ]


# ---------------------------------------------------------------------------
# module grouping + ranking
# ---------------------------------------------------------------------------


def module_key(file_path: str, group_depth: int, repo_root: str | None = None) -> str:
    """Group a source path into a module bucket: its first `group_depth` path
    segments, relative to `repo_root` when the path is inside it."""
    normalized = file_path.replace("\\", "/")
    if repo_root:
        root = repo_root.replace("\\", "/").rstrip("/")
        if normalized.startswith(root + "/"):
            normalized = normalized[len(root) + 1 :]
    segments = [s for s in normalized.split("/") if s not in ("", ".")]
    if len(segments) <= 1:
        return "."
    return "/".join(segments[: max(1, min(group_depth, len(segments) - 1))])


def derive_common_root(files: list[dict]) -> str | None:
    """The longest shared directory prefix of the ABSOLUTE, path-grouped
    records, or None when there isn't one.

    Why this is not optional politeness: istanbul/nyc `coverage-final.json`
    keys (and several other writers' output) are absolute, so without stripping
    the shared prefix every file lands in the same `abs/src`-style bucket. One
    bucket makes `seam` a single global yes/no and the reachability check
    degenerates into "is total coverage above the seam threshold" — the seam
    gate stops discriminating exactly when it matters most. Records that carry
    an explicit `module` (coverlet assemblies, jacoco packages) are excluded:
    their grouping never consults the path."""
    paths = [
        r["path"].replace("\\", "/")
        for r in files
        if not r.get("module") and r["path"].replace("\\", "/").startswith("/")
    ]
    if len(paths) < 2:
        return None
    segments = [p.split("/")[:-1] for p in paths]
    shared: list[str] = []
    for parts in zip(*segments):
        if len(set(parts)) != 1:
            break
        shared.append(parts[0])
    root = "/".join(shared)
    return root if root.strip("/") else None


def _pct(covered: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(covered * 100.0 / total, 2)


def rank_modules(
    files: list[dict],
    group_depth: int = DEFAULT_GROUP_DEPTH,
    seam_threshold_pct: float = DEFAULT_SEAM_THRESHOLD_PCT,
    repo_root: str | None = None,
) -> list[dict]:
    """Collapse file records into module buckets ranked by uncovered lines
    descending (ties broken by module name for deterministic output)."""
    buckets: dict[str, dict] = {}
    for record in files:
        key = record.get("module") or module_key(record["path"], group_depth, repo_root)
        bucket = buckets.setdefault(
            key,
            {
                "module": key,
                "files": 0,
                "lines_total": 0,
                "lines_covered": 0,
                "branches_total": 0,
                "branches_covered": 0,
            },
        )
        bucket["files"] += 1
        for field in ("lines_total", "lines_covered", "branches_total", "branches_covered"):
            bucket[field] += record[field]

    modules = []
    for bucket in buckets.values():
        line_pct = _pct(bucket["lines_covered"], bucket["lines_total"])
        modules.append(
            {
                **bucket,
                "uncovered_lines": bucket["lines_total"] - bucket["lines_covered"],
                "uncovered_branches": bucket["branches_total"] - bucket["branches_covered"],
                "line_pct": line_pct,
                "branch_pct": _pct(bucket["branches_covered"], bucket["branches_total"]),
                "seam": (
                    "established"
                    if line_pct is not None and line_pct >= seam_threshold_pct
                    else "absent"
                ),
            }
        )
    modules.sort(key=lambda m: (-m["uncovered_lines"], m["module"]))
    for rank, module in enumerate(modules, start=1):
        module["rank"] = rank
    return modules


# ---------------------------------------------------------------------------
# reachability verdict
# ---------------------------------------------------------------------------


def _target_block(
    target_pct: float,
    total: int,
    covered: int,
    modules: list[dict],
    uncovered_field: str,
    seam_threshold_pct: float,
    unit: str,
) -> dict:
    if total <= 0:
        return {
            "target_pct": target_pct,
            "verdict": VERDICT_NOT_MEASURED,
            "current_pct": None,
            f"{unit}_needed": None,
            f"reachable_uncovered_{unit}": None,
            f"seam_blocked_uncovered_{unit}": None,
            "basis": (
                f"the coverage report carries no {unit} data, so no {unit} "
                "target verdict can be computed"
            ),
        }

    current_pct = _pct(covered, total)
    # Exact arithmetic, not `target_pct / 100.0 * total`: a float product a
    # single ULP above the exact integer makes math.ceil return integer+1
    # (60.24% of 1250 -> 754 instead of 753), inflating `needed` by one line
    # and able to flip a reachable target to exit 3. Fraction(str(...)) reads
    # the target as the decimal it was written as.
    needed = max(0, math.ceil(Fraction(str(target_pct)) * total / 100) - covered)
    reachable = sum(m[uncovered_field] for m in modules if m["seam"] == "established")
    blocked = sum(m[uncovered_field] for m in modules if m["seam"] == "absent")

    # The verdict comes from the integer counts, never from the 2dp-rounded
    # `current_pct`: a rounded percentage can read as meeting a target the
    # report is still a line short of, and then disagree with `needed` in this
    # same block.
    if needed == 0:
        verdict = VERDICT_ALREADY_MET
    elif needed > reachable:
        verdict = VERDICT_UNREACHABLE
    else:
        verdict = VERDICT_REACHABLE

    return {
        "target_pct": target_pct,
        "verdict": verdict,
        "current_pct": current_pct,
        f"{unit}_needed": needed,
        f"reachable_uncovered_{unit}": reachable,
        f"seam_blocked_uncovered_{unit}": blocked,
        "basis": (
            f"{needed} more covered {unit} needed for {target_pct}%; {reachable} "
            f"uncovered {unit} sit in modules with an established test seam "
            f"(line coverage >= {seam_threshold_pct}%), {blocked} in modules "
            "with none"
        ),
    }


def _overall_verdict(blocks: list[dict | None]) -> str | None:
    verdicts = [b["verdict"] for b in blocks if b]
    if not verdicts:
        return None
    for candidate in _VERDICT_PRECEDENCE:
        if candidate in verdicts:
            return candidate
    return None  # pragma: no cover - every verdict is in the precedence tuple


def build_report(
    paths: list[Path],
    target_line_pct: float | None = None,
    target_branch_pct: float | None = None,
    group_depth: int = DEFAULT_GROUP_DEPTH,
    seam_threshold_pct: float = DEFAULT_SEAM_THRESHOLD_PCT,
    repo_root: str | None = None,
    top: int = 0,
) -> tuple[int, dict]:
    """Parse every report, rank the modules, and resolve the target verdicts.

    Returns `(exit_code, payload)`; raises ReportError when nothing is
    rankable (the caller maps that to exit 2)."""
    files: list[dict] = []
    formats: list[str] = []
    for path in paths:
        if not path.is_file():
            raise ReportError(f"coverage report not found: {path}")
        fmt = detect_format(path)
        formats.append(fmt)
        files.extend(parse_report(path, fmt))

    files = [f for f in files if f["lines_total"] > 0 or f["branches_total"] > 0]
    if not files:
        raise ReportError(
            "no coverage records parsed from "
            + ", ".join(str(p) for p in paths)
            + " — refusing to report a ranking from zero evidence"
        )

    effective_root = repo_root or derive_common_root(files)
    modules = rank_modules(files, group_depth, seam_threshold_pct, effective_root)
    lines_total = sum(m["lines_total"] for m in modules)
    lines_covered = sum(m["lines_covered"] for m in modules)
    branches_total = sum(m["branches_total"] for m in modules)
    branches_covered = sum(m["branches_covered"] for m in modules)

    line_block = (
        _target_block(
            target_line_pct,
            lines_total,
            lines_covered,
            modules,
            "uncovered_lines",
            seam_threshold_pct,
            "lines",
        )
        if target_line_pct is not None
        else None
    )
    branch_block = (
        _target_block(
            target_branch_pct,
            branches_total,
            branches_covered,
            modules,
            "uncovered_branches",
            seam_threshold_pct,
            "branches",
        )
        if target_branch_pct is not None
        else None
    )

    listed = modules if top <= 0 else modules[:top]
    payload = {
        "report": [str(p) for p in paths],
        "formats": formats,
        "group_depth": group_depth,
        "seam_threshold_pct": seam_threshold_pct,
        "common_root_stripped": effective_root,
        # One bucket for many files is a collapsed grouping, not a finding: the
        # seam classification degenerates into a single global
        # coverage-vs-threshold comparison. Flagged so it can never be read as
        # a verdict.
        "grouping_degenerate": len(modules) == 1 and len(files) > 1,
        "totals": {
            "files": len(files),
            "modules": len(modules),
            "lines_total": lines_total,
            "lines_covered": lines_covered,
            "line_pct": _pct(lines_covered, lines_total),
            "branches_total": branches_total,
            "branches_covered": branches_covered,
            "branch_pct": _pct(branches_covered, branches_total),
        },
        "line_target": line_block,
        "branch_target": branch_block,
        "verdict": _overall_verdict([line_block, branch_block]),
        "modules": listed,
        "modules_truncated": len(listed) < len(modules),
    }
    exit_code = 3 if payload["verdict"] == VERDICT_UNREACHABLE else 0
    return exit_code, payload


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def render_text(payload: dict) -> str:
    totals = payload["totals"]
    branch_summary = (
        f", branch {totals['branch_pct']}%"
        if totals["branch_pct"] is not None
        else ", branch not measured"
    )
    lines = [
        (
            f"Coverage-gap ranking — {totals['files']} file(s), "
            f"{totals['modules']} module(s), line {totals['line_pct']}%{branch_summary}"
        ),
        (
            f"seam threshold: {payload['seam_threshold_pct']}% line coverage "
            f"· group depth: {payload['group_depth']}"
        ),
        "",
        f"{'rank':>4}  {'uncovered':>9}  {'line %':>7}  {'seam':<12}  module",
    ]
    for module in payload["modules"]:
        lines.append(
            f"{module['rank']:>4}  {module['uncovered_lines']:>9}  "
            f"{module['line_pct'] if module['line_pct'] is not None else '-':>7}  "
            f"{module['seam']:<12}  {module['module']}"
        )
    if payload["modules_truncated"]:
        lines.append("  … truncated by --top")
    for label, key in (("line", "line_target"), ("branch", "branch_target")):
        block = payload[key]
        if block:
            lines.append("")
            lines.append(
                f"{label} target {block['target_pct']}% -> {block['verdict']}: "
                f"{block['basis']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coverage_gap_ranking.py",
        description=(
            "Rank uncovered-line buckets by module and decide whether a "
            "coverage target is reachable without new test seams."
        ),
    )
    parser.add_argument(
        "--report",
        dest="reports",
        action="append",
        type=Path,
        required=True,
        help="Coverage report to parse (repeatable).",
    )
    parser.add_argument(
        "--repo-root",
        help="Strip this prefix from absolute source paths before grouping.",
    )
    parser.add_argument(
        "--group-depth",
        type=int,
        default=DEFAULT_GROUP_DEPTH,
        help=f"Path segments per module bucket (default: {DEFAULT_GROUP_DEPTH}).",
    )
    parser.add_argument("--target-line-pct", type=float, help="Stated line target.")
    parser.add_argument("--target-branch-pct", type=float, help="Stated branch target.")
    parser.add_argument(
        "--seam-threshold-pct",
        type=float,
        default=DEFAULT_SEAM_THRESHOLD_PCT,
        help=(
            "Module line coverage at or above which a test seam counts as "
            f"established (default: {DEFAULT_SEAM_THRESHOLD_PCT})."
        ),
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        help=f"List only the top N modules; 0 = all (default: {DEFAULT_TOP}).",
    )
    parser.add_argument("--out", type=Path, help="Also write the JSON payload here.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        exit_code, payload = build_report(
            args.reports,
            target_line_pct=args.target_line_pct,
            target_branch_pct=args.target_branch_pct,
            group_depth=args.group_depth,
            seam_threshold_pct=args.seam_threshold_pct,
            repo_root=args.repo_root,
            top=args.top,
        )
    except ReportError as exc:
        message = f"ERROR: {exc}"
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(message, file=sys.stderr)
        return 2

    rendered = json.dumps(payload, indent=2)
    if args.out:
        _write_atomic(args.out, rendered + "\n")
    print(rendered if args.json else render_text(payload))
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
