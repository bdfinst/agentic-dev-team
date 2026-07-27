"""Content-guard tests for `apply-test-doubles/SKILL.md` (issue #1437, final
sub-issue of epic #1431, depends on #1433/#1434/#1435/#1436, all merged).
Traces to the (transient) plan file
plans/issue-1437-apply-test-doubles-skill.md — cite the issue number
alongside the plan path since the plan file is gitignored/transient (deleted
after implementation, per this repo's CLAUDE.md) and issue #1437 is the
durable reference once it's gone.

This file covers Step 1.1 (report-vs-target resolution, the three-part
structural validity check, and companion setup-guide-file location via the
report's own `**Target**` header field) and Step 1.2 (the re-entrant
`### 2. Apply Step 4b's decision logic` step: citing, not restating, Step
4b's branching rules; the off-gate-eligibility parsing rule; the re-offer
rule for already-resolved components; `--component` scoping and its two
unmatched/non-eligible cases; the zero-eligible terminal state; and the
non-blocking plugin-version staleness advisory). Step 1.3 (dispatch
mechanics, single-command acceptance criterion, registry rows) lands in a
later commit and is out of scope here.

Every assertion below is scoped to a named heading/section (via the local
`_resolve_section`/`_decision_section` helpers, built from the shared
`section()`/`grep()`/`collapsed()` helpers in `skill_doc_helpers.py`) rather
than an unscoped whole-file substring check, per this session's established
false-positive-avoidance discipline and the plan's explicit AC (every new
content-guard assertion scoped to a named heading/section via the existing
helpers).
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
    """Extract the new skill's `### 1. Resolve report or target` step,
    bounded at the next `### ` sibling heading (Step 1.2's `### 2. Apply
    Step 4b's decision logic`) — `section()`'s default boundary. An earlier
    version of this helper overrode the boundary to `^## ` from when Step
    1.1 was the file's only content and no `### ` sibling existed yet to
    bound against; left uncorrected once Step 1.2 landed, it silently
    over-captured Step 2's content into every Step-1-scoped assertion
    here. Fixed to the default `^### ` boundary now that a real sibling
    exists."""
    return section(
        text if text is not None else _text(),
        r"^### 1\. Resolve report or target",
    )


def _collapsed_resolve_section() -> str:
    return collapsed(_resolve_section())


def _decision_section(text: str | None = None) -> str:
    """Extract the new skill's `### 2. Apply Step 4b's decision logic` step
    (Step 1.2). Uses `section()`'s default `^### ` sibling-heading boundary
    — correct today (there is no later `### ` sibling yet, so extraction
    runs to EOF) and self-correcting once Step 1.3 adds `### 3. Dispatch`,
    unlike `_resolve_section` above, which had to override its boundary to
    `^## ` because at Step 1.1 time there was no later `### ` sibling to
    bound against at all."""
    return section(
        text if text is not None else _text(),
        r"^### 2\. Apply Step 4b's decision logic",
    )


def _collapsed_decision_section() -> str:
    return collapsed(_decision_section())


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


# --- Step 1.2: decision applied exactly once, regardless of path ------------


def test_decision_applied_exactly_once_named_skipped_steps_on_fast_path():
    sec = _collapsed_decision_section()
    assert grep(
        r"the \*\*only\*\* place a decision is made this invocation, "
        r"regardless of which path produced the resolved report",
        sec,
    )
    assert grep(
        r"\*\*Fast path\*\*\s*—\s*Steps 0, 1, 2, 2b, 3, 3b, 5, and 6 never "
        r"ran at all this invocation",
        sec,
    )


def test_target_path_inline_step_4b_is_noop_decision_still_made_once():
    sec = _collapsed_decision_section()
    assert grep(r"\*\*Target path\*\*\s*—\s*those same steps did run", sec)
    assert grep(r"their own inline Step 4b was a no-op", sec)
    assert grep(r"because Step 1 already forwards `?--yes`?", sec, ignore_case=True)
    assert grep(
        r"is still the first and only place the operator is actually "
        r"prompted",
        sec,
    )


# --- Step 1.2: citation, not restatement ------------------------------------


def test_decision_logic_cites_cd_test_architecture_step_4b_not_restated():
    sec = _collapsed_decision_section()
    assert grep(
        r"Apply exactly the decision procedure in "
        r"`?\.\./cd-test-architecture/SKILL\.md`?'s `?### 4b\. "
        r"Build-vs-document decision \(off-gate adapter test doubles\)`? "
        r"heading",
        sec,
    )
    assert grep(
        r"its Database-specific branch, its Downstream-service branch, and "
        r"that branch's library-vs-hand-rolled sub-question",
        sec,
    )
    assert grep(r"is not restated here", sec)
    # Negative: the Database-specific branch's own caveat text (Step 4b's
    # actual branching content) must not be duplicated verbatim here.
    assert not grep(
        r"cannot verify actual SQL, mapping, or schema correctness", sec
    )
    assert not grep(r"propose a Story titled", sec)


def test_cd_test_architecture_4b_heading_pinned_for_citation_break_detection():
    # Pins the exact heading text this new skill cites against the real,
    # shipped source of truth — a future rename/renumber in
    # cd-test-architecture/SKILL.md breaks this loudly instead of silently
    # drifting out of sync with what apply-test-doubles cites.
    upstream = CD_TEST_ARCHITECTURE_SKILL.read_text(encoding="utf-8")
    assert grep(
        r"^### 4b\. Build-vs-document decision \(off-gate adapter test "
        r"doubles\)\s*$",
        upstream,
    )


# --- Step 1.2: off-gate-eligibility parsing rule ----------------------------


def test_off_gate_eligibility_parsing_rule_stated_explicitly():
    sec = _collapsed_decision_section()
    assert grep(
        r"off-gate-eligible \*\*iff\*\* it has at least one row in the "
        r"Target architecture table whose `?Build/Document status`? cell "
        r"holds a non-blank value",
        sec,
    )


# --- Step 1.2: already-resolved components are re-offered ------------------


def test_already_resolved_component_reoffered_status_may_change():
    sec = _collapsed_decision_section()
    assert grep(
        r"re-offered this decision on every run, regardless of its "
        r"currently-recorded `?Build/Document status`?\s*—\s*including a "
        r"component already resolved to `?Build \(testcontainers\)`? or "
        r"`?Build \(Fake\)`?",
        sec,
    )
    assert grep(r"the operator may change a prior decision", sec)


# --- Step 1.2: --component scoping ------------------------------------------


def test_component_flag_scopes_to_one_component_others_untouched():
    sec = _collapsed_decision_section()
    assert grep(
        r"only that component's row resolves through this decision\s*—\s*"
        r"no other component's row is touched",
        sec,
    )


def test_no_component_flag_processes_every_eligible_component_in_one_batch():
    sec = _collapsed_decision_section()
    assert grep(
        r"every off-gate-eligible component in the resolved report is "
        r"processed in one batched pass, mirroring Step 4b's own batching "
        r"rule",
        sec,
    )


def test_component_flag_unmatched_name_reports_no_match_takes_no_action():
    sec = _collapsed_decision_section()
    assert grep(
        r"`?<name>`? does not appear anywhere in the resolved report's "
        r"Target architecture table\s*—\s*state that `?<name>`? was not "
        r"found in the resolved report",
        sec,
    )


def test_component_flag_matches_non_eligible_component_reports_no_decision_point():
    sec = _collapsed_decision_section()
    assert grep(
        r"no Target architecture row with a non-blank `?Build/Document "
        r"status`? cell\s*—\s*state that `?<name>`? has no build-vs-document "
        r"decision to apply",
        sec,
    )


def test_component_flag_never_fuzzy_matched_to_similarly_named_component():
    sec = _collapsed_decision_section()
    assert grep(r"never a fuzzy or nearest-match substitution", sec)


# --- Step 1.2: zero eligible components -------------------------------------


def test_zero_eligible_components_reports_nothing_to_apply_no_dispatch():
    sec = _collapsed_decision_section()
    assert grep(
        r"finds no off-gate-eligible component, state that there is "
        r"nothing to apply and take no further action",
        sec,
    )


# --- Step 1.2: non-blocking plugin-version staleness advisory --------------


def test_plugin_version_staleness_advisory_when_provenance_differs():
    sec = _collapsed_decision_section()
    assert grep(
        r"the same resolver `?/version`? and `?/upgrade`? already use",
        sec,
    )
    assert grep(
        r"sh \"?\$CLAUDE_PLUGIN_ROOT/hooks/py\.sh\"? "
        r"\"?\$CLAUDE_PLUGIN_ROOT/hooks/lib/plugin_version\.py\"?",
        sec,
    )
    assert grep(
        r"Compare it against the resolved report's Provenance `?dev-team "
        r"plugin version`? field",
        sec,
    )
    assert grep(
        r"emit one non-blocking advisory line naming both versions",
        sec,
    )
    assert grep(r"before applying Step 4b's current logic", sec)
    assert grep(r"This never blocks or alters the decision logic itself", sec)
