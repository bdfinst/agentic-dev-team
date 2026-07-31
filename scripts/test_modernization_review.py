"""test_modernization_review.py — Phase validator for /test-modernize workflow.

Validates that a phase's deliverable artifacts match the phase's acceptance
criteria before the workflow is allowed to advance to the next phase.

Usage:
  python3 scripts/test_modernization_review.py \\
    --repo <slug> --phase <N> [--base-dir <path>]

Exit codes (matches review_result contract):
  0 = pass (all checks green)
  1 = fail (hard errors found)
  2 = warn (warnings only)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# This script stays at repo-root (dev/CI tooling, not shipped — #1636), but
# review_result.py itself lives under the plugin, so both `lib` dirs land on
# sys.path: this repo-root scripts/lib/ (unrelated modules) and the plugin's
# scripts/lib/ (review_result.py). Explicit path import below, not `lib.`, so
# the two same-named namespace packages never have to merge implicitly.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "plugins" / "dev-team" / "scripts" / "lib"),
)
from review_result import build_result, main_exit, make_issue

# ---------------------------------------------------------------------------
# Artifact resolution
# ---------------------------------------------------------------------------


def resolve_artifacts(base_dir: Path, repo: str, phase: int) -> dict:
    """Return a dict of named artifact paths relative to base_dir."""
    memory_root = base_dir / "memory" / "test-modernize" / repo
    features_dir = base_dir / "features" / "test-modernize"
    return {
        "phase_md": memory_root / f"phase-{phase}.md",
        "phase3_md": memory_root / "phase-3.md",
        "features_dir": features_dir,
        "bindings_json": memory_root / "gherkin-bindings.json",
        "disabled_tests_json": memory_root / "disabled-tests.json",
        "memory_root": memory_root,
    }


# ---------------------------------------------------------------------------
# Phase 2 — Gherkin cross-reference
# ---------------------------------------------------------------------------


def extract_scenario_titles(feature_files: list[Path]) -> list[str]:
    """Return all Scenario titles from a list of .feature files."""
    titles: list[str] = []
    scenario_re = re.compile(r"^\s+Scenario:\s+(.+)$")
    for path in feature_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            m = scenario_re.match(line)
            if m:
                titles.append(m.group(1).strip())
    return titles


def validate_phase_2(paths: dict) -> tuple:
    """Validate phase 2 artifacts: cross-reference .feature scenarios vs bindings.

    Returns (errors, warnings).
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    features_dir: Path = paths["features_dir"]
    bindings_path: Path = paths["bindings_json"]

    # Gather feature files
    feature_files: list[Path] = []
    if features_dir.is_dir():
        feature_files = list(features_dir.glob("*.feature"))

    scenario_titles = extract_scenario_titles(feature_files)
    scenario_titles_lower = {t.lower(): t for t in scenario_titles}

    # Load bindings
    bindings: dict = {}
    if bindings_path.exists():
        try:
            bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            errors.append(
                make_issue(
                    "error",
                    file=str(bindings_path),
                    line=0,
                    message=f"gherkin-bindings.json is not valid JSON: {bindings_path}",
                )
            )
            return errors, warnings

    bindings_keys_lower = {k.lower(): k for k in bindings}

    # Scenarios not in bindings → error
    for title in scenario_titles:
        if title.lower() not in bindings_keys_lower:
            errors.append(
                make_issue(
                    "error",
                    file=str(paths["bindings_json"]),
                    line=0,
                    message=f"Scenario '{title}' found in .feature file but missing from gherkin-bindings.json",
                    suggested_fix="Add an entry for this scenario to gherkin-bindings.json",
                )
            )

    # Bindings not in any scenario → warning (orphan)
    for key in bindings:
        if key.lower() not in scenario_titles_lower:
            warnings.append(
                make_issue(
                    "warning",
                    file=str(paths["bindings_json"]),
                    line=0,
                    message=f"Binding key '{key}' in gherkin-bindings.json does not match any Scenario in .feature files",
                    suggested_fix="Remove orphaned binding or add matching Scenario to a .feature file",
                )
            )

    return errors, warnings


# ---------------------------------------------------------------------------
# Phase 3 — disabled-tests.json schema validation
# ---------------------------------------------------------------------------


def validate_phase_3(paths: dict) -> tuple:
    """Validate phase 3 artifacts: disabled-tests.json schema check.

    Returns (errors, warnings).
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    disabled_path: Path = paths["disabled_tests_json"]

    if not disabled_path.exists():
        # No disabled tests — acceptable
        return errors, warnings

    try:
        entries = json.loads(disabled_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(
            make_issue(
                "error",
                file=str(disabled_path),
                line=0,
                message=f"disabled-tests.json is not valid JSON: {exc}",
            )
        )
        return errors, warnings

    if not isinstance(entries, list):
        errors.append(
            make_issue(
                "error",
                file=str(disabled_path),
                line=0,
                message="disabled-tests.json must be a JSON array",
            )
        )
        return errors, warnings

    for i, entry in enumerate(entries):
        test_name = entry.get("test", f"entry[{i}]")
        if "reason" not in entry:
            errors.append(
                make_issue(
                    "error",
                    file=str(disabled_path),
                    line=0,
                    message=f"Entry '{test_name}' missing required field 'reason'",
                    suggested_fix="Add a 'reason' field drawn from the cannot-fail taxonomy",
                )
            )
        if "skip_tag" not in entry:
            errors.append(
                make_issue(
                    "error",
                    file=str(disabled_path),
                    line=0,
                    message=f"Entry '{test_name}' missing required field 'skip_tag'",
                    suggested_fix="Add a 'skip_tag' field (e.g. '@skip-foo')",
                )
            )

    return errors, warnings


# ---------------------------------------------------------------------------
# Phase 4 — coverage regression check
# ---------------------------------------------------------------------------


def parse_coverage_number(text: str) -> float | None:
    """Extract the first coverage percentage or decimal from text.

    Tries: 'Coverage: 80%', 'coverage: 80.0', 'current coverage: 78.5%'
    Returns float or None if not found.
    """
    # Match 'coverage' label (case-insensitive) followed by a number + optional %
    pattern = re.compile(r"(?i)coverage[^\d]*(\d+\.?\d*)\s*%?", re.MULTILINE)
    m = pattern.search(text)
    if m:
        return float(m.group(1))
    return None


def validate_phase_4(paths: dict) -> tuple:
    """Validate phase 4 artifacts: coverage must not regress vs phase-3 baseline.

    Returns (errors, warnings).
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    phase3_path: Path = paths["phase3_md"]
    phase4_path: Path = paths["phase_md"]

    # Need phase-3 for baseline
    if not phase3_path.exists():
        errors.append(
            make_issue(
                "error",
                file=str(phase3_path),
                line=0,
                message=f"phase-3.md not found at {phase3_path} — cannot establish baseline for phase-4 comparison",
                suggested_fix="Ensure phase 3 was completed and phase-3.md contains a Coverage line",
            )
        )
        return errors, warnings

    baseline_text = phase3_path.read_text(encoding="utf-8")
    baseline = parse_coverage_number(baseline_text)
    if baseline is None:
        errors.append(
            make_issue(
                "error",
                file=str(phase3_path),
                line=0,
                message="Could not parse coverage baseline from phase-3.md",
                suggested_fix="Add a line like 'Coverage: 80%' to phase-3.md",
            )
        )
        return errors, warnings

    current_text = phase4_path.read_text(encoding="utf-8")
    current = parse_coverage_number(current_text)
    if current is None:
        errors.append(
            make_issue(
                "error",
                file=str(phase4_path),
                line=0,
                message="Could not parse current coverage from phase-4.md",
                suggested_fix="Add a line like 'Coverage: 82%' to phase-4.md",
            )
        )
        return errors, warnings

    if current < baseline:
        delta = baseline - current
        errors.append(
            make_issue(
                "error",
                file=str(phase4_path),
                line=0,
                message=f"Coverage regression: phase-4 reports {current}% but phase-3 baseline was {baseline}% "
                f"(delta: -{delta:.1f}%)",
                suggested_fix="Add tests to recover the coverage regression before advancing",
            )
        )

    return errors, warnings


# ---------------------------------------------------------------------------
# Phase 5 — quality targets validation
# ---------------------------------------------------------------------------


def validate_phase_5(paths: dict) -> tuple:
    """Validate phase 5 quality target blocks.

    Each target block must have measured_value. If measured_value < threshold,
    next_action is required.

    Returns (errors, warnings).
    """
    errors: list[dict] = []
    warnings: list[dict] = []

    phase5_path: Path = paths["phase_md"]
    text = phase5_path.read_text(encoding="utf-8")

    # Find all target blocks. A block is a sequence of lines starting with
    # '- target:' and containing key: value pairs until the next '- target:'
    # or end of the quality targets section.
    # Strategy: split on '- target:' tokens, then parse each block.
    # We search for measured_value, threshold, next_action in each block.

    block_pattern = re.compile(r"(?m)^[ \t]*-[ \t]+target:[ \t]*(.+)$")
    measured_re = re.compile(r"(?m)measured_value:\s*(\d+\.?\d*)")
    threshold_re = re.compile(r"(?m)threshold:\s*(\d+\.?\d*)")
    next_action_re = re.compile(r"(?m)next_action:\s*(.+)")

    # Split text on target block headers
    parts = block_pattern.split(text)
    # parts[0] = text before first target, parts[1] = first target name, parts[2] = first block body, ...
    # i.e. alternating [pre, name, body, name, body, ...]

    if len(parts) <= 1:
        # No target blocks found — nothing to validate
        return errors, warnings

    # Iterate target blocks: parts[1], parts[2] → name, body; parts[3], parts[4] → name, body; ...
    i = 1
    while i < len(parts) - 1:
        target_name = parts[i].strip()
        block_body = parts[i + 1]
        i += 2

        # Check measured_value present
        mv_match = measured_re.search(block_body)
        if not mv_match:
            errors.append(
                make_issue(
                    "error",
                    file=str(phase5_path),
                    line=0,
                    message=f"Quality target '{target_name}' missing required field 'measured_value'",
                    suggested_fix="Add 'measured_value: <N>' to the target block",
                )
            )
            continue

        measured = float(mv_match.group(1))

        # Check threshold
        th_match = threshold_re.search(block_body)
        if th_match:
            threshold = float(th_match.group(1))
            if measured < threshold:
                # Need next_action
                na_match = next_action_re.search(block_body)
                if not na_match:
                    errors.append(
                        make_issue(
                            "error",
                            file=str(phase5_path),
                            line=0,
                            message=f"Quality target '{target_name}' has measured_value {measured} below "
                            f"threshold {threshold} but is missing 'next_action'",
                            suggested_fix="Add 'next_action: <description>' to explain how the gap will be closed",
                        )
                    )

    return errors, warnings


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def validate_phase(phase: int, paths: dict) -> tuple:
    """Dispatch to the appropriate phase validator.

    Returns (errors, warnings).
    """
    if phase == 2:
        return validate_phase_2(paths)
    if phase == 3:
        return validate_phase_3(paths)
    if phase == 4:
        return validate_phase_4(paths)
    if phase == 5:
        return validate_phase_5(paths)
    # Phase 1 and others: no structural script checks yet — pass through
    return [], []


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate test-modernize phase artifacts."
    )
    parser.add_argument("--repo", required=True, help="Repo slug")
    parser.add_argument("--phase", required=True, type=int, help="Phase number (1-5)")
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Root directory for memory/ (default: CWD)",
    )
    args = parser.parse_args()

    import re as _re

    if not _re.fullmatch(r"[a-zA-Z0-9_.\-]+", args.repo):
        print(
            json.dumps(
                build_result(
                    [
                        {
                            "severity": "error",
                            "confidence": "high",
                            "file": "",
                            "line": 0,
                            "message": f"Invalid --repo slug '{args.repo}': must match [a-zA-Z0-9_.\\-]+",
                            "suggestedFix": "Pass a simple repo slug without path separators or '..' components.",
                        }
                    ],
                    [],
                )
            ),
            flush=True,
        )
        sys.exit(1)
    base_dir = Path(args.base_dir).resolve()
    paths = resolve_artifacts(base_dir, args.repo, args.phase)

    # Gate: phase artifact must exist
    phase_md: Path = paths["phase_md"]
    if not phase_md.exists():
        result = build_result(
            errors=[
                make_issue(
                    "error",
                    file=str(phase_md),
                    line=0,
                    message=f"phase artifact not found at {phase_md}",
                    suggested_fix=f"Run phase {args.phase} of /test-modernize to create this file",
                )
            ],
            warnings=[],
            summary=f"Phase {args.phase} artifact not found for repo '{args.repo}'",
        )
        return main_exit(result)

    errors, warnings = validate_phase(args.phase, paths)
    result = build_result(
        errors=errors,
        warnings=warnings,
        summary=(
            f"Phase {args.phase} validation for '{args.repo}': "
            f"{len(errors)} error(s), {len(warnings)} warning(s)"
        ),
    )
    return main_exit(result)


if __name__ == "__main__":
    sys.exit(main())
