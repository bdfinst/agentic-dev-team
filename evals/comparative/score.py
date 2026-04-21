#!/usr/bin/env python3
"""score.py — comparative testing harness.

Scores the opus_repo_scan_test reference pipeline and our /security-assessment
pipeline against ground-truth.yaml. Emits a side-by-side scorecard for
recall, precision, severity agreement, and suppression correctness.

Usage:
    python3 evals/comparative/score.py \\
        --reference /path/to/opus_repo_scan_test/results/reports \\
        --ours memory

Either --reference or --ours can be omitted; the harness emits a single-
column scorecard for just one system.

Exits non-zero on any tool error, zero when scoring completes (regardless
of whether either system met a pass threshold — there is no pass threshold,
only measurement).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
GROUND_TRUTH_PATH = REPO / "evals/comparative/ground-truth.yaml"


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class EmittedFinding:
    source: str            # "reference" | "ours"
    rule_id: str | None
    file: str              # repo-relative
    line: int | None
    severity: str | None   # presentational (CRITICAL/HIGH/MEDIUM/LOW) or None
    message: str = ""


@dataclass
class ExpectedFinding:
    id: str
    category: str
    reference_concern: str
    rule_id_patterns: list[str]
    expected_file: str
    line_range: tuple[int, int]
    line_tolerance: int
    expected_severity: str
    description: str
    also_at: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MatchResult:
    expected_id: str
    matched: bool
    matched_by: str = ""       # which rule_id pattern or location rule matched
    matched_finding: EmittedFinding | None = None
    severity_agreement: int | None = None  # tier-delta; None if unmatched


# ── Loading ───────────────────────────────────────────────────────────────────


def load_ground_truth() -> tuple[list[ExpectedFinding], list[dict], dict]:
    """Returns (expected_findings, expected_suppressions, severity_ranks)."""
    with GROUND_TRUTH_PATH.open() as f:
        data = yaml.safe_load(f)

    expected = []
    for ef in data["expected_findings"]:
        expected.append(ExpectedFinding(
            id=ef["id"],
            category=ef["category"],
            reference_concern=ef["reference_concern"],
            rule_id_patterns=ef["rule_id_patterns"],
            expected_file=ef["expected_file"],
            line_range=tuple(ef["line_range"]),
            line_tolerance=ef.get("line_tolerance", 5),
            expected_severity=ef["expected_severity"],
            description=ef["description"],
            also_at=ef.get("also_at", []),
        ))
    return expected, data.get("expected_suppressions", []), data["severity_ranks"]


# ── Emitted-finding parsers ───────────────────────────────────────────────────


UNIFIED_SEVERITY_TO_PRESENTATIONAL = {
    "error": "HIGH",        # exec-report-generator maps error -> HIGH by default
    "warning": "MEDIUM",
    "suggestion": "LOW",
    "info": "LOW",
}


def parse_ours(ours_dir: Path) -> list[EmittedFinding]:
    """Parse our pipeline's output.

    Looks for:
      - memory/findings-*.jsonl          — raw unified findings
      - memory/disposition-*.json        — fp-reduced with presentational severity
      - memory/report-*.md               — executive report

    Prefers disposition > findings > report so presentational severity is used.
    """
    findings: list[EmittedFinding] = []

    # Pass 1 — disposition register(s) (best signal)
    dispositions = list(ours_dir.glob("disposition-*.json"))
    for disp_path in dispositions:
        with disp_path.open() as f:
            reg = json.load(f)
        for entry in reg.get("entries", []):
            f_obj = entry.get("finding", {})
            # Presentational severity from contract v1.1.0 mapping:
            # score >= 7 AND error = CRITICAL; score 4-6 AND error = HIGH; etc.
            # We approximate by reading exploitability.score.
            unified_sev = f_obj.get("severity", "warning")
            exploit_score = (entry.get("exploitability") or {}).get("score", 5)
            presentational = _map_presentational(unified_sev, exploit_score)
            findings.append(EmittedFinding(
                source="ours",
                rule_id=f_obj.get("rule_id"),
                file=f_obj.get("file", ""),
                line=f_obj.get("line"),
                severity=presentational,
                message=f_obj.get("message", ""),
            ))

    # Pass 2 — raw findings (only those NOT in disposition register)
    if not dispositions:
        for jl in ours_dir.glob("findings-*.jsonl"):
            with jl.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    findings.append(EmittedFinding(
                        source="ours",
                        rule_id=obj.get("rule_id"),
                        file=obj.get("file", ""),
                        line=obj.get("line"),
                        severity=UNIFIED_SEVERITY_TO_PRESENTATIONAL.get(
                            obj.get("severity", "warning"), "MEDIUM"
                        ),
                        message=obj.get("message", ""),
                    ))

    return findings


def _map_presentational(unified_severity: str, exploit_score: float) -> str:
    """Mirrors contract v1.1.0 § Severity mapping table."""
    if unified_severity == "error":
        if exploit_score >= 7:
            return "CRITICAL"
        if exploit_score >= 4:
            return "HIGH"
        return "MEDIUM"
    if unified_severity == "warning":
        if exploit_score >= 7:
            return "HIGH"
        if exploit_score >= 3:
            return "MEDIUM"
        return "LOW"
    return "LOW"


# ── Reference parser ──────────────────────────────────────────────────────────


# Reference report structure per opus_repo_scan_test/docs/static-analysis-agents.md:
# Findings appear in detailed blocks with the shape:
#   ### SECRETS-001 — <title>
#   **File**: path/to/file.py
#   **Line**: 42
#   **Severity**: CRITICAL
#   **CWE**: CWE-798
#   ...
# (or in condensed form in the Medium/Low section)

REF_FINDING_BLOCK = re.compile(
    r"###?\s+(?P<id>[A-Z0-9]+-[0-9]+)\s*—?\s*(?P<title>[^\n]+?)\s*\n"
    r"(?:.*?\*\*File\*\*:\s*`?(?P<file>[^\s`]+)`?\s*\n)?"
    r"(?:.*?\*\*Line\*\*:\s*(?P<line>[0-9]+)\s*\n)?"
    r"(?:.*?\*\*Severity\*\*:\s*(?P<severity>[A-Z]+))?",
    re.DOTALL,
)


def parse_reference(reports_dir: Path) -> list[EmittedFinding]:
    """Parse the reference's four markdown reports under results/reports/.

    Extracts each finding block by regex over the Critical/High/Medium/Low
    sections. Severity is taken from either the section header or an explicit
    **Severity**: field.
    """
    findings: list[EmittedFinding] = []
    for md in reports_dir.glob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in REF_FINDING_BLOCK.finditer(text):
            findings.append(EmittedFinding(
                source="reference",
                rule_id=m.group("id"),  # reference uses IDs like SECRETS-001 rather than rule names
                file=m.group("file") or "",
                line=int(m.group("line")) if m.group("line") else None,
                severity=(m.group("severity") or "").upper() or None,
                message=m.group("title").strip(),
            ))
    return findings


# ── Matching ──────────────────────────────────────────────────────────────────


def match_finding(exp: ExpectedFinding, emitted: list[EmittedFinding]) -> MatchResult:
    """Try to match one expected finding against the emitted list.

    Matching rules (in order):
      1. rule_id glob match + file path prefix match + line within line_tolerance
      2. file path match + line within line_tolerance (rule_id missing or non-matching)

    The strongest match wins.
    """
    best: MatchResult | None = None
    for ef in emitted:
        # Check location (file + line)
        ef_file_norm = ef.file.lstrip("/")
        if not _file_matches(exp.expected_file, ef_file_norm):
            # Also try the also_at alternates
            alt_match = False
            for alt in exp.also_at:
                if _file_matches(alt["file"], ef_file_norm):
                    alt_match = True
                    break
            if not alt_match:
                continue

        if ef.line is not None:
            within_range = any(
                low - exp.line_tolerance <= ef.line <= high + exp.line_tolerance
                for low, high in [exp.line_range] + [tuple(alt.get("line_range", exp.line_range)) for alt in exp.also_at]
            )
            if not within_range:
                continue

        # Check rule_id pattern
        rule_id_match = False
        matched_pattern = ""
        if ef.rule_id:
            for pat in exp.rule_id_patterns:
                if fnmatch(ef.rule_id, pat):
                    rule_id_match = True
                    matched_pattern = pat
                    break

        # Score the match
        score = 1  # location-only
        if rule_id_match:
            score = 2

        if best is None or score > (2 if best.matched_by.startswith("rule") else 1):
            best = MatchResult(
                expected_id=exp.id,
                matched=True,
                matched_by=f"rule:{matched_pattern}" if rule_id_match else "location-only",
                matched_finding=ef,
            )

    return best or MatchResult(expected_id=exp.id, matched=False)


def _file_matches(expected_path: str, actual_path: str) -> bool:
    """Normalize and compare. Expected is repo-relative; actual may have fixture-repo/ prefix."""
    # Strip any fixture-repo/ or evals/comparative/fixture-repo/ prefix from actual
    for prefix in ("evals/comparative/fixture-repo/", "fixture-repo/", "./"):
        if actual_path.startswith(prefix):
            actual_path = actual_path[len(prefix):]
            break
    return actual_path.endswith(expected_path) or expected_path.endswith(actual_path)


# ── Suppression checks ────────────────────────────────────────────────────────


def check_suppressions(
    emitted: list[EmittedFinding], expected_suppressions: list[dict]
) -> tuple[int, int, list[str]]:
    """Return (correctly_suppressed, incorrectly_emitted, details)."""
    correct = 0
    incorrect = 0
    details: list[str] = []
    for supp in expected_suppressions:
        exp_file = supp["expected_file"]
        line_range = tuple(supp["line_range"])
        emitted_on_suppressed = [
            ef for ef in emitted
            if _file_matches(exp_file, ef.file)
            and ef.line is not None
            and line_range[0] - 2 <= ef.line <= line_range[1] + 2
        ]
        if not emitted_on_suppressed:
            correct += 1
            details.append(f"  {supp['id']}: correctly suppressed ({exp_file}:{line_range})")
        else:
            incorrect += 1
            details.append(
                f"  {supp['id']}: INCORRECTLY emitted "
                f"({exp_file}:{line_range}) — "
                f"{len(emitted_on_suppressed)} finding(s) should have been suppressed"
            )
    return correct, incorrect, details


# ── Scorecard ─────────────────────────────────────────────────────────────────


@dataclass
class SystemScore:
    name: str
    total_expected: int
    matches: list[MatchResult] = field(default_factory=list)
    extra_emissions: list[EmittedFinding] = field(default_factory=list)
    correct_suppressions: int = 0
    incorrect_suppressions: int = 0
    total_suppressions: int = 0

    @property
    def recall(self) -> float:
        matched = sum(1 for m in self.matches if m.matched)
        return matched / self.total_expected if self.total_expected else 0.0

    @property
    def severity_agreement_tight(self) -> float:
        """Fraction of matched findings with severity within ±1 tier."""
        tight = [m for m in self.matches if m.matched and m.severity_agreement is not None and abs(m.severity_agreement) <= 1]
        matched = [m for m in self.matches if m.matched]
        return len(tight) / len(matched) if matched else 0.0

    def precision_estimate(self) -> tuple[int, int]:
        """Returns (emitted_on_ground_truth, emitted_not_on_ground_truth).
        This is an estimate — a finding not in ground-truth may still be a
        real finding that the ground-truth missed."""
        matched_findings = {id(m.matched_finding) for m in self.matches if m.matched}
        on_gt = sum(1 for m in self.matches if m.matched)
        not_on_gt = len([e for e in self.extra_emissions if id(e) not in matched_findings])
        return on_gt, not_on_gt


def compute_score(
    name: str, emitted: list[EmittedFinding],
    expected: list[ExpectedFinding], expected_suppressions: list[dict],
    severity_ranks: dict[str, int],
) -> SystemScore:
    score = SystemScore(name=name, total_expected=len(expected))
    matched_emitted_ids: set[int] = set()

    for exp in expected:
        result = match_finding(exp, emitted)
        if result.matched and result.matched_finding is not None:
            emitted_sev = result.matched_finding.severity
            if emitted_sev and emitted_sev in severity_ranks:
                result.severity_agreement = (
                    severity_ranks[emitted_sev] - severity_ranks[exp.expected_severity]
                )
            matched_emitted_ids.add(id(result.matched_finding))
        score.matches.append(result)

    # Emissions that didn't match any expected finding
    for ef in emitted:
        if id(ef) not in matched_emitted_ids:
            score.extra_emissions.append(ef)

    # Suppressions
    correct, incorrect, _details = check_suppressions(emitted, expected_suppressions)
    score.correct_suppressions = correct
    score.incorrect_suppressions = incorrect
    score.total_suppressions = len(expected_suppressions)
    return score


# ── Reporting ─────────────────────────────────────────────────────────────────


def print_scorecard(scores: list[SystemScore]) -> None:
    # Header
    names = [s.name for s in scores]
    print("\n" + "=" * 78)
    print("Comparative testing scorecard")
    print("=" * 78)

    def row(label: str, values: list[str]) -> str:
        return f"  {label:<40}" + "".join(f"{v:<18}" for v in values)

    print(row("", names))
    print(row("-" * 40, ["-" * 16] * len(names)))

    # Recall
    print(row(
        "Recall (findings caught)",
        [f"{sum(1 for m in s.matches if m.matched)}/{s.total_expected} ({s.recall:.0%})" for s in scores],
    ))

    # Severity agreement
    print(row(
        "Severity agreement (±1 tier)",
        [f"{s.severity_agreement_tight:.0%}" for s in scores],
    ))

    # Suppression correctness
    print(row(
        "Suppressions (correct/total)",
        [f"{s.correct_suppressions}/{s.total_suppressions}" for s in scores],
    ))

    # Extra emissions
    print(row(
        "Extra emissions (potential FPs)",
        [str(len(s.extra_emissions)) for s in scores],
    ))

    # Per-concern recall
    print("\n  Recall by reference concern:")
    concerns = sorted({m.expected_id[:m.expected_id.rfind('-')] if '-' in m.expected_id else m.expected_id
                       for s in scores for m in s.matches})
    # Simpler: group by reference_concern attribute from the expected list
    expected, _sup, _ranks = load_ground_truth()
    by_concern: dict[str, list[str]] = {}
    for ef in expected:
        by_concern.setdefault(ef.reference_concern, []).append(ef.id)

    for concern in sorted(by_concern):
        ids = by_concern[concern]
        vals = []
        for s in scores:
            matched_here = sum(1 for m in s.matches if m.expected_id in ids and m.matched)
            vals.append(f"{matched_here}/{len(ids)}")
        print(row(f"  {concern}", vals))

    # Per-finding detail
    print("\n  Per-finding detail:")
    # Header
    header = f"  {'ID':<8} {'Category':<14} {'Expected severity':<18}" + "".join(f"{s.name:<18}" for s in scores)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for ef in expected:
        cols = [f"  {ef.id:<8} {ef.category:<14} {ef.expected_severity:<18}"]
        for s in scores:
            m = next((m for m in s.matches if m.expected_id == ef.id), None)
            if not m or not m.matched:
                cols.append(f"{'MISS':<18}")
            else:
                sev = m.matched_finding.severity if m.matched_finding else "?"
                delta = m.severity_agreement
                sym = "=" if delta == 0 else ("↑" if (delta or 0) > 0 else "↓")
                cols.append(f"{sev:<6}{sym}{abs(delta or 0):<2}{m.matched_by[:8]:<8}")
        print("".join(cols))

    print()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, help="path to opus_repo_scan_test/results/reports/ directory")
    p.add_argument("--ours", type=Path, help="path to our memory/ directory (contains findings-* / disposition-* / report-*)")
    args = p.parse_args()

    if not args.reference and not args.ours:
        print("error: must supply at least one of --reference or --ours", file=sys.stderr)
        return 2

    expected, expected_suppressions, severity_ranks = load_ground_truth()
    scores: list[SystemScore] = []

    if args.reference:
        if not args.reference.is_dir():
            print(f"error: reference path is not a directory: {args.reference}", file=sys.stderr)
            return 2
        ref_emitted = parse_reference(args.reference)
        scores.append(compute_score("reference", ref_emitted, expected, expected_suppressions, severity_ranks))

    if args.ours:
        if not args.ours.is_dir():
            print(f"error: ours path is not a directory: {args.ours}", file=sys.stderr)
            return 2
        ours_emitted = parse_ours(args.ours)
        scores.append(compute_score("ours", ours_emitted, expected, expected_suppressions, severity_ranks))

    print_scorecard(scores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
