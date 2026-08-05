"""Verifies quality-targets-converge/SKILL.md's Step 2 "Coverage" bullet
delegates fully to `/coverage-delta` with no independent project-list logic
of its own (issue #1759, Slice 5, Step 5.4). No production edit to
`quality-targets-converge/SKILL.md` is needed for this — the bullet already
reads `invoke /coverage-delta <repo> --workflow <workflow> (no --story)`.

**What this file actually verifies, honestly stated.** quality-targets-
converge is prose with no runnable entry point of its own — there is no
function to call that "is" its documented `/coverage-delta` invocation. Two
distinct, genuinely load-bearing checks stand in for that:

1. **Cross-file contract compatibility**
   (`test_extracted_invocation_is_a_valid_instance_of_coverage_deltas_contract`).
   The extracted invocation's flags are checked against `coverage-delta`'s
   OWN documented `argument-hint` — a real cross-file check that fails if
   either file drifts: if `coverage-delta` dropped `--workflow` from its
   contract, or if `quality-targets-converge` started documenting a flag
   `coverage-delta` doesn't accept. This is NOT a same-function-twice
   tautology — the two facts being compared come from two independently-
   authored files.
2. **Shared-mechanism integration**
   (`test_coverage_delta_flow_matches_weighted_merge_directly`). The
   underlying `discover_*` -> `drift_check` -> `weighted_merge` chain
   (`coverage_delta_flow_helpers.run_delta_flow`, the same helper
   `test_coverage_delta_discovery_rederivation.py` and
   `test_coverage_delta_incident_reproduction.py` drive) is exercised and
   compared against `weighted_merge`'s direct output for an identical
   fixture. This is a legitimate integration test of the mechanism
   `/coverage-delta` itself runs — but it is NOT literally re-parsing and
   re-executing quality-targets-converge's own extracted invocation
   token-by-token; that invocation is prose describing a command, not code
   this test can call. Stated plainly so this test's name does not overclaim
   what its assertions establish.
"""

from __future__ import annotations

import re
import sys

from coverage_baseline_flow_helpers import stub_dotnet
from coverage_delta_flow_helpers import run_delta_flow
from skill_doc_helpers import PLUGIN_ROOT, frontmatter

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd
from coverage_config import weighted_merge

SKILL = PLUGIN_ROOT / "skills" / "quality-targets-converge" / "SKILL.md"
COVERAGE_DELTA_SKILL = PLUGIN_ROOT / "skills" / "coverage-delta" / "SKILL.md"

TEST_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
"""


def _text() -> str:
    return SKILL.read_text()


def _coverage_bullet_line(skill_text: str) -> str:
    for line in skill_text.splitlines():
        if line.strip().startswith("- **Coverage**"):
            return line
    raise AssertionError(
        "quality-targets-converge/SKILL.md's Step 2 has no '- **Coverage**' "
        "bullet — has the section been renamed or restructured?"
    )


def _extract_coverage_delta_invocation(skill_text: str) -> str:
    """Regex-extract the literal `/coverage-delta ...` invocation documented
    in the Coverage bullet — this is the extraction step that makes the test
    below fail for the right reason if the SKILL.md prose drifts (a stale
    flag, a wrong field name), rather than passing regardless of what the
    prose actually says."""
    bullet = _coverage_bullet_line(skill_text)
    match = re.search(r"invoke `(/coverage-delta[^`]*)`", bullet)
    assert match, (
        "Coverage bullet does not document a literal, backtick-quoted "
        f"`/coverage-delta ...` invocation: {bullet!r}"
    )
    return match.group(1)


def _extract_coverage_delta_argument_hint() -> str:
    """Regex-extract `coverage-delta/SKILL.md`'s own frontmatter
    `argument-hint` line — coverage-delta is the skill that actually defines
    what a valid `/coverage-delta` invocation looks like, so this is the
    contract the extracted invocation below is checked against."""
    fm = frontmatter(COVERAGE_DELTA_SKILL.read_text())
    match = re.search(r'^argument-hint:\s*"(.*)"\s*$', fm, re.MULTILINE)
    assert match, (
        "coverage-delta/SKILL.md frontmatter has no argument-hint line — "
        "has the frontmatter been restructured?"
    )
    return match.group(1)


def _flags_in(text: str) -> set[str]:
    """Extract every `--flag`-shaped token from `text`."""
    return set(re.findall(r"--[A-Za-z][A-Za-z-]*", text))


def write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sln(repo_root, name: str = "App.sln") -> None:
    write(repo_root / name, "Microsoft Visual Studio Solution File\n")


# ---------------------------------------------------------------------------
# Content-guard: the Coverage bullet delegates fully — no independent
# included/excluded list logic, no direct discovery-module reference.
# ---------------------------------------------------------------------------


def test_coverage_bullet_has_no_independent_frozen_list_logic():
    bullet = _coverage_bullet_line(_text())
    for forbidden in (
        "included",
        "excluded",
        "coverage_discovery",
        "discover_dotnet",
        "discover_js",
        "TestClassification",
    ):
        assert forbidden not in bullet


def test_extracted_invocation_has_no_independent_story_flag():
    invocation = _extract_coverage_delta_invocation(_text())
    assert "--story" not in invocation
    assert "--workflow" in invocation
    assert "<repo>" in invocation


# ---------------------------------------------------------------------------
# Cross-file contract check: the extracted invocation is a valid instance of
# coverage-delta's OWN documented contract — not an invented or drifted one.
# This is the genuinely load-bearing replacement for the tautological
# same-function-twice comparison the prior version of this file made: it
# fails for real if coverage-delta's argument-hint drops a flag
# quality-targets-converge relies on, or if quality-targets-converge starts
# documenting a flag coverage-delta doesn't accept.
# ---------------------------------------------------------------------------


def test_extracted_invocation_is_a_valid_instance_of_coverage_deltas_contract():
    invocation = _extract_coverage_delta_invocation(_text())
    accepted_flags = _flags_in(_extract_coverage_delta_argument_hint())
    used_flags = _flags_in(invocation)

    assert used_flags, (
        f"expected at least one --flag in the extracted invocation: {invocation!r}"
    )
    unknown_flags = used_flags - accepted_flags
    assert not unknown_flags, (
        f"quality-targets-converge documents flag(s) {sorted(unknown_flags)} "
        f"that coverage-delta's own argument-hint does not accept "
        f"({sorted(accepted_flags)}) — one of the two files has drifted."
    )
    # --story/--story-files are coverage-delta's own scoped-mutation flags
    # (Step 2b) — quality-targets-converge's call documents no --story,
    # so neither should appear here even though coverage-delta itself
    # accepts them.
    assert "--story" not in used_flags
    assert "--story-files" not in used_flags


# ---------------------------------------------------------------------------
# Integration: the shared discover_* -> drift_check -> weighted_merge chain
# (run_delta_flow) matches weighted_merge's direct output for an identical
# fixture. This exercises the mechanism /coverage-delta itself runs — it
# does NOT re-parse or re-execute quality-targets-converge's extracted
# invocation token-by-token (quality-targets-converge is prose with no
# runnable entry point of its own); see the module docstring.
# ---------------------------------------------------------------------------


def test_coverage_delta_flow_matches_weighted_merge_directly(tmp_path):
    invocation = _extract_coverage_delta_invocation(_text())
    # No --story means the extracted invocation is the plain delegating
    # call quality-targets-converge documents (2b's mutation gate is never
    # engaged for this call path) — this is what makes executing
    # run_delta_flow below faithful to what the prose actually documents.
    assert "--story" not in invocation

    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    project_b = "tests/ProjectB/ProjectB.csproj"
    write(tmp_path / project_a, TEST_CSPROJ)
    write(tmp_path / project_b, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}", "{project_b}"], "excluded": []}}',
        encoding="utf-8",
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}
    reports = {
        project_a: {
            "covered_statements": 10,
            "total_statements": 10,
            "covered_branches": 0,
            "total_branches": 0,
        },
        project_b: {
            "covered_statements": 500,
            "total_statements": 1000,
            "covered_branches": 0,
            "total_branches": 0,
        },
    }

    with stub_dotnet([project_a, project_b]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    result = run_delta_flow(discovered, config_path, baseline, reports)

    assert result.stopped is False
    direct = weighted_merge([reports[project_a], reports[project_b]])
    assert result.merged == direct


# ---------------------------------------------------------------------------
# Integration: the shared discover_* -> drift_check chain surfaces a hard
# failure, never a 0% coverage reading, for the same fixture shape as above.
# Like test_coverage_delta_flow_matches_weighted_merge_directly, this
# exercises the shared mechanism via run_delta_flow — it does not re-execute
# quality-targets-converge's extracted invocation itself (prose, not code);
# the invocation extraction here only confirms this fixture's call shape
# (no --story) matches what quality-targets-converge documents.
# ---------------------------------------------------------------------------


def test_extracted_invocation_surfaces_hard_failure_not_zero_percent(tmp_path):
    invocation = _extract_coverage_delta_invocation(_text())
    assert "--story" not in invocation

    sln(tmp_path)
    project_a = "tests/ProjectA/ProjectA.csproj"
    project_c = "tests/ProjectC/ProjectC.csproj"  # unaccounted-for
    write(tmp_path / project_a, TEST_CSPROJ)
    write(tmp_path / project_c, TEST_CSPROJ)

    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(
        f'{{"included": ["{project_a}"], "excluded": []}}', encoding="utf-8"
    )
    baseline = {"captured_at": "2026-08-04T12:00:00Z", "line_pct": 41.2, "branch_pct": 28.7}

    with stub_dotnet([project_a, project_c]):
        discovered = cdd.discover_dotnet_projects(tmp_path)

    result = run_delta_flow(discovered, config_path, baseline)

    assert result.stopped is True
    assert result.hard_failure_message is not None
    assert project_c in result.hard_failure_message
    # The hard failure is surfaced, not misread as a 0% coverage measurement
    # — no merged percentage is ever produced on this path.
    assert result.merged is None
