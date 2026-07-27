"""Content-guard tests for `apply-test-doubles/SKILL.md` (issue #1437, final
sub-issue of epic #1431, depends on #1433/#1434/#1435/#1436, all merged).
Traces to the (transient) plan file
plans/issue-1437-apply-test-doubles-skill.md — cite the issue number
alongside the plan path since the plan file is gitignored/transient (deleted
after implementation, per this repo's CLAUDE.md) and issue #1437 is the
durable reference once it's gone.

This file covers Step 1.1 (the whole slice's first step): report-vs-target
resolution, the three-part structural validity check, and companion
setup-guide-file location via the report's own `**Target**` header field.
Steps 1.2 (Step 4b decision application, `--component` scoping, staleness
advisory) and 1.3 (dispatch mechanics, registry rows) land in later commits
and are out of scope here.

Every assertion below is scoped to the new skill file's `### 1. Resolve
report or target` step (via the local `_resolve_section` helper, built from
the shared `section()`/`grep()`/`collapsed()` helpers in
`skill_doc_helpers.py`) rather than an unscoped whole-file substring check,
per this session's established false-positive-avoidance discipline and the
plan's explicit AC (every new content-guard assertion scoped to a named
heading/section via the existing helpers).
"""

from __future__ import annotations

import pytest

from skill_doc_helpers import PLUGIN_ROOT, collapsed, frontmatter, grep, section

SKILL = PLUGIN_ROOT / "skills" / "apply-test-doubles" / "SKILL.md"
CD_TEST_ARCHITECTURE_SKILL = (
    PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"
)


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _resolve_section(text: str | None = None) -> str:
    """Extract the new skill's `### 1. Resolve report or target` step. No
    `##`-level heading exists yet in this file (Step 1.1 is the file's first
    content) so the default `^### ` boundary would swallow nothing early —
    bounded explicitly to `^## ` so a future `## Steps` sibling or later
    top-level section added in Step 1.2/1.3 can't silently truncate this
    extraction differently than intended."""
    return section(
        text if text is not None else _text(),
        r"^### 1\. Resolve report or target",
        boundary_pattern=r"^## ",
    )


def _collapsed_resolve_section() -> str:
    return collapsed(_resolve_section())


# --- Frontmatter -------------------------------------------------------------


def test_skill_file_exists_with_correct_frontmatter():
    assert SKILL.is_file()
    fm = frontmatter(_text())
    assert grep(r"^name:\s*apply-test-doubles\s*$", fm)
    assert grep(r"^role:\s*worker\s*$", fm)
    assert grep(r"^user-invocable:\s*true\s*$", fm)
    assert grep(
        r'^argument-hint:\s*"\[<report-path-or-target>\]\s*\[--component <name>\]"\s*$',
        fm,
    )


# --- Fast path: existing, structurally valid report --------------------------


def test_existing_report_with_full_structural_shape_takes_fast_path():
    sec = _collapsed_resolve_section()
    assert grep(
        r"All three present\s*→\s*the fast path: read that report's Target "
        r"architecture table directly, and do not invoke "
        r"`?/cd-test-architecture`?",
        sec,
        ignore_case=True,
    )


# --- Target path: nonexistent path string ------------------------------------


def test_nonexistent_path_string_takes_target_path():
    sec = _resolve_section()
    assert grep(
        r"Given, non-empty, resolves to no file or directory on disk",
        sec,
    )
    # Distinct row from the absent-argument case — both must appear, as two
    # separate table rows, not collapsed into one.
    assert grep(r"^\| Absent \|", sec)


# --- Target path: directory, not fast path -----------------------------------


def test_directory_path_takes_target_path_not_fast_path():
    sec = _collapsed_resolve_section()
    assert grep(
        r"Given, resolves to an existing directory.*a directory is not a "
        r"report; there is no file there to read",
        sec,
        ignore_case=True,
    )


# --- Absent path: explicit cwd/repo argument, never bare invocation ----------


def test_missing_path_takes_target_path_against_current_repo_as_explicit_argument():
    sec = _collapsed_resolve_section()
    assert grep(
        r"the current repo, passed to `?/cd-test-architecture`? as an "
        r"explicit resolved cwd/repo path argument\s*—\s*never a bare "
        r"invocation, which would trigger `?cd-test-architecture`?'s own "
        r"interactive target prompt",
        sec,
        ignore_case=True,
    )


# --- Target path always forwards --yes ---------------------------------------


def test_target_path_always_forwards_yes_to_cd_test_architecture():
    sec = _collapsed_resolve_section()
    assert grep(
        r"always forwarding `?--yes`?\s*—\s*so its own inline Step 4b "
        r"prompt never fires",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"this skill's own re-entrant Step 4b step.*is the sole place the "
        r"operator is prompted, on both paths uniformly",
        sec,
        ignore_case=True,
    )


# --- Structural validity: missing any marker takes target path, not error ---


STRUCTURAL_MARKERS = [
    pytest.param(r"# CD Test Architecture` title line", id="title"),
    pytest.param(
        r"### Target architecture \(per component\)` heading\s*—\s*level 3, "
        r"with\s*the `\(per component\)` suffix",
        id="heading",
    ),
    pytest.param(r"Build/Document status` column in that section's table", id="column"),
]


@pytest.mark.parametrize("marker_pattern", STRUCTURAL_MARKERS)
def test_existing_file_missing_any_structural_marker_takes_target_path_not_error(
    marker_pattern,
):
    sec = _collapsed_resolve_section()
    assert grep(marker_pattern, sec, ignore_case=True)
    # Positive: stated as the target path.
    assert grep(
        r"Missing any one of the three takes the target path too, treating "
        r"the file's path string as a target to assess",
        sec,
        ignore_case=True,
    )
    # Negative companion: never affirmatively described as an error.
    assert grep(r"not a malformed-report error", sec, ignore_case=True)
    assert not grep(r"is a malformed-report error", sec, ignore_case=True)


def test_all_three_structural_markers_verified_against_cd_test_architecture_skill():
    # Pins the exact strings this new skill cites against the real, shipped
    # source of truth — a future heading rename/renumber in
    # cd-test-architecture/SKILL.md breaks this loudly instead of silently
    # drifting out of sync with what apply-test-doubles actually checks for.
    upstream = CD_TEST_ARCHITECTURE_SKILL.read_text(encoding="utf-8")
    assert grep(r"^# CD Test Architecture\s*$", upstream)
    assert grep(r"^### Target architecture \(per component\)\s*$", upstream)
    assert grep(r"Build/Document status", upstream)


# --- --component forwarded on the target path --------------------------------


def test_component_forwarded_to_cd_test_architecture_on_target_path():
    sec = _collapsed_resolve_section()
    assert grep(
        r"forward `?--component <name>`? when given, as "
        r"`?cd-test-architecture`?'s own `?--component`? argument\s*—\s*"
        r"producing a single-component-scoped fresh assessment, not a "
        r"whole-app assessment filtered afterward",
        sec,
        ignore_case=True,
    )


# --- Companion setup guide located via Target header, not filename ----------


def test_setup_guide_located_via_report_target_header_not_filename():
    sec = _collapsed_resolve_section()
    assert grep(
        r"via the resolved report's own `?\*\*Target\*\*`? header field\s*"
        r"—\s*the `?<app>`? value recorded in the report's content\s*—\s*"
        r"never by the report file's name on disk",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"\.dev-team-reports/cd-test-architecture-<app>-test-double-setup\.md",
        sec,
    )


# --- Two non-error missing-companion-file outcomes ---------------------------


def test_zero_eligible_components_no_setup_guide_file_is_valid_not_error():
    sec = _collapsed_resolve_section()
    assert grep(
        r"zero off-gate-eligible rows \(no row with a non-blank "
        r"`?Build/Document status`? cell\)\s*—\s*nothing was ever expected "
        r"to be written for this report; take no further action",
        sec,
        ignore_case=True,
    )


def test_missing_companion_file_created_fresh_when_eligible_components_predate_1436():
    sec = _collapsed_resolve_section()
    assert grep(
        r"eligible rows but predates #1436 \(no companion file was ever "
        r"written for it\)\s*—\s*state this plainly, then create the "
        r"setup-guide artifact fresh at the derived path, exactly as "
        r"`?cd-test-architecture`? itself would on a first run",
        sec,
        ignore_case=True,
    )
