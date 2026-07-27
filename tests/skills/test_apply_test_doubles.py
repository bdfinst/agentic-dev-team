"""Content-guard tests for `apply-test-doubles/SKILL.md` (issue #1437, final
sub-issue of epic #1431, depends on #1433/#1434/#1435/#1436, all merged).
Traces to the (transient) plan file
plans/issue-1437-apply-test-doubles-skill.md — cite the issue number
alongside the plan path since the plan file is gitignored/transient (deleted
after implementation, per this repo's CLAUDE.md) and issue #1437 is the
durable reference once it's gone.

This file covers Step 1.1 (report-vs-target resolution, the three-part
structural validity check, and companion setup-guide-file location via the
report's own `**Target**` header field — recovered from content, never the
report's on-disk filename, and slugified/containment-checked before use),
Step 1.2 (the re-entrant `### 2. Apply Step 4b's decision logic` step:
citing, not restating, Step 4b's branching rules; the off-gate-eligibility
parsing rule, itself cited from cd-test-architecture's own Output section;
the re-offer rule for already-resolved components; `--component` scoping —
applied as a post-hoc filter on *both* paths, never forwarded into the
`/cd-test-architecture` self-invocation — and its two unmatched/non-eligible
cases; the zero-eligible terminal state; this step's own non-interactive
behavior; and the non-blocking plugin-version staleness advisory, including
its resolver-failure handling), and Step 1.3 (the `### 3. Dispatch` step:
the write-back of the resolved report's own `Build/Document status` cell —
including its full cell contract (verbatim caveat, `Double` column,
revert-clears-caveat), write-failure handling, and the deliberately
untouched report Provenance block — the advisory-only Story proposal, the
setup-guide's inclusion-vs-Classification distinction (inclusion is
decision-independent, Classification is re-emitted on change), the honest
no-automated-materialization-path statement for `/issues-from-assessment`,
the single-ready-to-run-command acceptance criterion, and the corrected
`cd-test-architecture/SKILL.md` maintainer note). Registry rows for the
new skill are verified by `tests/repo/test_registry_sync.py`, not here.

Most assertions below are scoped to a named heading/section (via the local
`_resolve_section`/`_decision_section`/`_dispatch_section` helpers, or the
shared `cd_test_architecture_output_section`/`cd_test_architecture_
downstream_service_branch_section` helpers, all built on
`section()`/`grep()`/`collapsed()` in `skill_doc_helpers.py`) rather than an
unscoped whole-file substring check. A small number of cross-file assertions
against `cd-test-architecture/SKILL.md` are necessarily broader than a
single section (e.g. confirming no test anywhere still pins the stale
maintainer-note phrase) — each such case is called out inline with why an
unscoped read is the correct choice there, rather than claimed away by a
blanket "everything is scoped" statement.
"""

from __future__ import annotations

import pytest

from skill_doc_helpers import (
    PLUGIN_ROOT,
    cd_test_architecture_downstream_service_branch_section,
    cd_test_architecture_output_section,
    collapsed,
    frontmatter,
    grep,
    section,
)

SKILL = PLUGIN_ROOT / "skills" / "apply-test-doubles" / "SKILL.md"
CD_TEST_ARCHITECTURE_SKILL = (
    PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"
)


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _upstream_text() -> str:
    return CD_TEST_ARCHITECTURE_SKILL.read_text(encoding="utf-8")


def _database_specific_branch_section(text: str) -> str:
    """Extract cd-test-architecture/SKILL.md's `#### Database-specific
    branch` subsection. Not promoted to skill_doc_helpers.py — used only
    here, once; promote per this repo's established "second use" precedent
    if another test file ever needs it (see cd_test_architecture_output_
    section's own docstring for that precedent)."""
    return section(text, r"^#### Database-specific branch", boundary_pattern=r"^#### ")


def _resolve_section(text: str | None = None) -> str:
    """Extract the new skill's `### 1. Resolve report or target` step,
    bounded at the next `### ` sibling heading (`### 2. Apply Step 4b's
    decision logic`) — `section()`'s default boundary."""
    return section(
        text if text is not None else _text(),
        r"^### 1\. Resolve report or target",
    )


def _collapsed_resolve_section() -> str:
    return collapsed(_resolve_section())


def _decision_section(text: str | None = None) -> str:
    """Extract the new skill's `### 2. Apply Step 4b's decision logic` step,
    bounded at the next `### ` sibling heading (`### 3. Dispatch`, which
    exists in the shipped file) — `section()`'s default boundary."""
    return section(
        text if text is not None else _text(),
        r"^### 2\. Apply Step 4b's decision logic",
    )


def _collapsed_decision_section() -> str:
    return collapsed(_decision_section())


def _dispatch_section(text: str | None = None) -> str:
    """Extract the new skill's `### 3. Dispatch` step — the file's last
    section, so `section()`'s default `^### ` boundary runs to EOF (no
    later `### ` sibling exists)."""
    return section(
        text if text is not None else _text(),
        r"^### 3\. Dispatch",
    )


def _collapsed_dispatch_section() -> str:
    return collapsed(_dispatch_section())


# --- Frontmatter -------------------------------------------------------------


def test_skill_file_exists_with_correct_frontmatter():
    assert SKILL.is_file()
    fm = frontmatter(_text())
    assert grep(r"^name:\s*apply-test-doubles\s*$", fm)
    assert grep(r"^role:\s*worker\s*$", fm)
    assert grep(r"^user-invocable:\s*true\s*$", fm)
    assert grep(
        r'^argument-hint:\s*"\[<report-path-or-target>\]\s*\[--component <name>\]'
        r'\s*\[--yes\]"\s*$',
        fm,
    )


def test_parse_arguments_documents_yes_flag():
    parse_args = collapsed(section(_text(), r"^## Parse Arguments"))
    assert grep(
        r"`?--yes`? — run non-interactively: this step's own re-entrant "
        r"Step 4b prompt \(Step 2\) is skipped",
        parse_args,
        ignore_case=True,
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
        r"always forwarding `?--yes`? so its own inline Step 4b prompt "
        r"never fires",
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
    #
    # Scoped to the `## Output` section (not a bare whole-file grep): the
    # skill's own top-level `# CD Test Architecture` doc heading (its H1,
    # outside `## Output`) is a different occurrence of the same string as
    # the *report's own* title line inside the Output section's fenced
    # template — an unscoped grep for the title would pass even if the
    # template's title line were deleted, since the doc H1 alone satisfies
    # it. Scoping to `## Output` means only the template's own title line
    # can satisfy this assertion.
    output = cd_test_architecture_output_section(_upstream_text())
    assert grep(r"^# CD Test Architecture\s*$", output)
    assert grep(r"^### Target architecture \(per component\)\s*$", output)
    # The table *header* line itself, not an unscoped substring match that
    # prose mentioning "Build/Document status" elsewhere could satisfy even
    # if the actual column were removed from the table.
    assert grep(
        r"^\|\s*Component\s*\|\s*Layer\s*\|.*\|\s*Build/Document status\s*\|\s*$",
        output,
    )


def test_blank_cell_off_gate_eligibility_convention_documented_upstream():
    # This new skill's off-gate-eligibility rule cites this exact upstream
    # sentence rather than asserting the blank-vs-set convention
    # independently — pin it here so a future edit to that sentence is
    # caught alongside the citing skill's own test.
    output = cd_test_architecture_output_section(_upstream_text())
    assert grep(
        r"A row Step 4 did not flag for that decision.*carries \*\*no "
        r"value in this column at all\*\*.*left blank, never one of the "
        r"three enum values and never guessed",
        collapsed(output),
    )


# --- --component is never forwarded to cd-test-architecture -----------------


def test_component_flag_never_forwarded_to_cd_test_architecture_on_target_path():
    sec = _collapsed_resolve_section()
    assert grep(
        r"a full-target assessment, never scoped by `?--component`? at "
        r"invocation",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"including the `?--component <name>`? filter, applied post-hoc "
        r"there",
        sec,
        ignore_case=True,
    )
    parse_args = collapsed(section(_text(), r"^## Parse Arguments"))
    assert grep(
        r"\*\*never\*\* forwarded as `?cd-test-architecture`?'s own "
        r"`?--component`? argument on the target path",
        parse_args,
        ignore_case=True,
    )
    # Negative companion: the abandoned "single-component-scoped fresh
    # assessment" design is not described anywhere in this new file.
    assert not grep(r"single-component-scoped fresh assessment", _text())


def test_target_path_resolves_fresh_report_path_per_upstream_output_rule():
    # arch-review round-2 fix-verification: Step 1 previously left implicit
    # how the target path locates the report it just asked
    # cd-test-architecture to produce — now load-bearing since Step 3's
    # write-back needs a real path to mutate.
    sec = _collapsed_resolve_section()
    assert grep(
        r"resolve the fresh report at "
        r"`?\.dev-team-reports/cd-test-architecture-<app>\.md`?, per "
        r"`?\.\./cd-test-architecture/SKILL\.md`?'s own Output Path rule",
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


def test_companion_path_derivation_reconciled_with_cd_test_architecture_write_time_rule():
    sec = _collapsed_resolve_section()
    assert grep(
        r"this intentionally differs from how `?cd-test-architecture`? "
        r"itself names the companion file at write time",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"this skill instead reads a report whose file may have been "
        r"renamed or relocated since it was written",
        sec,
        ignore_case=True,
    )


def test_companion_app_value_slugified_and_containment_checked():
    sec = _collapsed_resolve_section()
    assert grep(
        r"before interpolating `?<app>`? into a path, slugify it",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"confirm the resulting path still resolves inside "
        r"`?\.dev-team-reports/`?",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"treat the companion file as not found.*rather than writing "
        r"outside that directory",
        sec,
        ignore_case=True,
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
        r"\*\*Fast path\*\*\s*—\s*Steps 0, 1, 2, 2b, 3, 3b, 4, 5, and 6 "
        r"never ran at all this invocation",
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


def test_negative_citation_assertions_are_sound_against_real_upstream_text():
    # Companion pin for the two negative assertions above: proves both
    # regexes are capable of matching real Step 4b content (and therefore
    # would catch a future restatement), rather than being silently
    # vacuous — the same discipline test_cd_test_architecture_
    # 4b_heading_pinned_for_citation_break_detection already applies to the
    # heading citation.
    db_branch = collapsed(_database_specific_branch_section(_upstream_text()))
    assert grep(r"cannot verify actual SQL, mapping, or schema correctness", db_branch)
    downstream_branch = collapsed(
        cd_test_architecture_downstream_service_branch_section(_upstream_text())
    )
    assert grep(r"propose a Story titled", downstream_branch)


def test_cd_test_architecture_4b_heading_pinned_for_citation_break_detection():
    # Pins the exact heading text this new skill cites against the real,
    # shipped source of truth — a future rename/renumber in
    # cd-test-architecture/SKILL.md breaks this loudly instead of silently
    # drifting out of sync with what apply-test-doubles cites.
    upstream = _upstream_text()
    assert grep(
        r"^### 4b\. Build-vs-document decision \(off-gate adapter test "
        r"doubles\)\s*$",
        upstream,
    )


def test_cite_dont_restate_rationale_stated_inline():
    # ai-provenance-review (round-3 panel): the cite-vs-extract rationale
    # lived only in the transient, gitignored plan file, with no durable
    # record surviving its deletion. A one-sentence inline rationale here
    # is the lighter alternative to a full ADR that finding itself offered.
    sec = _collapsed_decision_section()
    assert grep(
        r"the one architecturally significant decision in this skill, "
        r"made explicit so it survives independent of any one plan "
        r"document",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"this citation was chosen over physically relocating Step 4b's "
        r"content into a shared file",
        sec,
        ignore_case=True,
    )


# --- Step 1.2: off-gate-eligibility parsing rule ----------------------------


def test_off_gate_eligibility_parsing_rule_cited_not_independently_derived():
    sec = _collapsed_decision_section()
    assert grep(
        r"cited from `?cd-test-architecture`?'s own Output section, not "
        r"independently derived",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"off-gate-eligible \*\*iff\*\* it has at least one Target "
        r"architecture row with a non-blank `?Build/Document status`? cell",
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


# --- Step 1.2: this step's own non-interactive behavior ---------------------


def test_non_interactive_behavior_documented_for_own_prompt():
    sec = _collapsed_decision_section()
    assert grep(r"surface no prompt for this step either", sec, ignore_case=True)
    assert grep(
        r"a component with \*\*no prior recorded decision\*\* defaults to "
        r"`?Document-only`?, exactly mirroring what a non-interactive "
        r"`?cd-test-architecture`? run would have produced",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"a component with an \*\*existing recorded decision\*\* is left "
        r"exactly as recorded, not silently re-resolved to `?Document-only`?",
        sec,
        ignore_case=True,
    )
    # Negative: round-2 fix-verification found the prior wording claimed
    # every eligible component resolves to Document-only under --yes,
    # contradicting an already-decided report's own recorded status.
    assert not grep(
        r"every off-gate-eligible component resolves to `?Document-only`?, "
        r"no Story is proposed",
        sec,
        ignore_case=True,
    )


# --- Step 1.2: non-blocking plugin-version staleness advisory --------------


def test_plugin_version_staleness_advisory_cites_version_resolver_only():
    sec = _collapsed_decision_section()
    # ai-provenance-review + arch-review (round-3 panel, independently):
    # `/upgrade` does NOT use hooks/lib/plugin_version.py — only `/version`
    # does. The claim must name `/version` alone.
    assert grep(r"the same resolver `?/version`? already uses", sec)
    # test-review round-2 fix-verification: broadened from the narrower
    # exact-phrase pin (which would miss any reworded reintroduction) to a
    # blanket "no legitimate reason to mention /upgrade at all" check.
    assert not grep(r"/upgrade", sec, ignore_case=True)
    assert grep(
        r"sh \"?\$CLAUDE_PLUGIN_ROOT/hooks/py\.sh\"? "
        r"\"?\$CLAUDE_PLUGIN_ROOT/hooks/lib/plugin_version\.py\"?",
        sec,
    )


def test_plugin_version_resolver_failure_and_unknown_value_skip_advisory():
    sec = _collapsed_decision_section()
    assert grep(
        r"if the resolver instead exits non-zero.*prints nothing, or the "
        r"parsed value is the literal `?unknown`?.*emit no advisory and "
        r"proceed silently",
        sec,
        ignore_case=True,
    )


def test_plugin_version_staleness_advisory_when_provenance_differs():
    sec = _collapsed_decision_section()
    assert grep(
        r"compare the resolved version against the resolved report's "
        r"Provenance `` `?dev-team`? plugin version `` field",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"emit one non-blocking advisory line naming both versions",
        sec,
    )
    assert grep(r"before applying Step 4b's current logic", sec)
    assert grep(r"This never blocks or alters the decision logic itself", sec)


def test_provenance_field_name_matches_report_template_exactly():
    # ai-provenance-review: the cited field name must be byte-exact with
    # report-template.md's canonical spelling — backticks around only
    # `dev-team`, not the whole phrase.
    template = (PLUGIN_ROOT / "knowledge" / "report-template.md").read_text(
        encoding="utf-8"
    )
    provenance_section = section(template, r"^## Provenance \(closing section\)")
    assert grep(r"`dev-team` plugin version", collapsed(provenance_section))
    output = cd_test_architecture_output_section(_upstream_text())
    assert grep(r"`dev-team` plugin version", collapsed(output))


# --- Step 1.3: dispatch mechanics --------------------------------------------


def test_dispatch_never_writes_a_story_file_advisory_only():
    sec = _collapsed_dispatch_section()
    assert grep(
        r"`?cd-test-architecture`? is advisory only.*it proposes a "
        r"downstream Story, it never invokes `?/build`? or edits code "
        r"directly",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"Step 4b's live invocation proposes a Story within its own "
        r"report/chat output \(Step 6's only documented output channel\), "
        r"never as a separate file",
        sec,
        ignore_case=True,
    )
    # Negative: the old, incorrect claim that this skill itself writes a
    # Story file is gone — the only "Story file" text remaining should be
    # part of the negated "never ... writes a Story file itself" sentence.
    assert not grep(
        r"writes or updates that component's Story file", sec, ignore_case=True
    )


def test_dispatch_writes_back_build_document_status_cell():
    sec = _collapsed_dispatch_section()
    assert grep(
        r"Write back the resolved report's `?Build/Document status`? cell",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"matching the \*\*full cell contract\*\*",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the next `?/apply-test-doubles`? run against the same report "
        r"would re-read the stale status",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"this write-back is unique to this skill\s*:\s*Step 4b's live "
        r"invocation writes the cell once, at report-creation time, and "
        r"never needs to revise it",
        sec,
        ignore_case=True,
    )


def test_write_back_carries_full_cell_contract_caveat_and_double_column():
    # arch-review + ai-provenance-review round-2 fix-verification: the
    # write-back originally specified only the enum value, but
    # cd-test-architecture's Output section's cell contract also requires
    # the branch-specific caveat (Build (Fake)) and the resolved tool name
    # (Double column) — omitting either produces a report violating the
    # very contract this bullet claims to honor.
    sec = _collapsed_dispatch_section()
    assert grep(
        r"a `?Build \(Fake\)`? write carries that branch's caveat verbatim "
        r"in the same cell",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the `?Double \(to run config-free\)`? column is updated to name "
        r"it, per the Output section's own tool-citation rule",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"A row reverting to `?Document-only`? or `?Build "
        r"\(testcontainers\)`? has any previously-written caveat text "
        r"removed from the cell",
        sec,
        ignore_case=True,
    )


def test_write_back_handles_write_failure_and_leaves_provenance_untouched():
    # arch-review round-2 fix-verification: the write-back had no failure
    # handling (report-output-location.md's non-fatal-write convention)
    # and no statement of how it interacts with the report's own
    # Provenance block, which the version-skew advisory (Step 2) reads on
    # every subsequent run.
    sec = _collapsed_dispatch_section()
    assert grep(
        r"if the write fails \(permission, read-only path\), state that "
        r"plainly and surface the resolved decisions in chat instead",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"never proceed as if the write succeeded",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"the report's own header and Provenance block.*are deliberately "
        r"left untouched by this write-back",
        sec,
        ignore_case=True,
    )


def test_dispatch_proposes_story_text_for_build_outcome_advisory_only():
    sec = _collapsed_dispatch_section()
    assert grep(
        r"For a component resolving to a Build outcome, propose a Story",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"it never invokes `?/build`? or writes a Story file itself",
        sec,
        ignore_case=True,
    )


def test_setup_guide_inclusion_independent_but_classification_reemitted_on_change():
    # arch-review + ai-provenance-review round-2 fix-verification: the
    # original claim ("not touched by this step... nothing to update
    # there") was false against cd-test-architecture's own Companion
    # Classification list, which keys section content on the resolved
    # Build variant and library choice — exactly what Step 2 lets the
    # operator change. Corrected to distinguish inclusion (independent)
    # from Classification (not independent, must be re-emitted on change).
    sec = _collapsed_dispatch_section()
    assert grep(
        r"per-component \*inclusion\* is independent of this decision; "
        r"its \*Classification\* is not",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"both of which Step 2 explicitly lets the operator change",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"re-emit that component's setup-guide section per the "
        r"Classification rule so the guide never names a tool the report "
        r"no longer recommends",
        sec,
        ignore_case=True,
    )
    # Negative: the old, disproven "nothing to update there" claim is gone.
    assert not grep(
        r"there is nothing for this step to update there", sec, ignore_case=True
    )


def test_dispatch_states_no_automated_story_materialization_path():
    # arch-review + ai-provenance-review round-2 fix-verification: the
    # original citation claimed /issues-from-assessment materializes this
    # step's proposed Story, but that skill's Step 2 never reads
    # Build/Document status or reproduces Step 4b's Story shapes — it
    # derives its own, independent per-(component, layer) Stories.
    # Corrected to state the honest parity with Step 4b's own live
    # invocation: advisory chat/report output only, no materialization.
    sec = _collapsed_dispatch_section()
    assert grep(
        r"there is no automated materialization path today, the same as "
        r"Step 4b's own live invocation",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"`?\.\./issues-from-assessment/SKILL\.md`? derives its own "
        r"Stories directly from the Target architecture table.*"
        r"independent of the Build/Document decision or this step's "
        r"proposed Story text",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"it is not a consumer of what this step just proposed, and this "
        r"skill does not invent a second materialization mechanism to "
        r"bridge that gap",
        sec,
        ignore_case=True,
    )
    # Negative: the old, disproven "established, single-owner path to real
    # Stories" claim is gone.
    assert not grep(
        r"the established, single-owner path from a "
        r"cd-test-architecture-shaped report to real Stories",
        sec,
        ignore_case=True,
    )


def test_issues_from_assessment_step_2_does_not_read_build_document_status():
    # Companion pin proving the corrected claim above is itself accurate:
    # issues-from-assessment's Step 2 genuinely has no Build/Document-
    # status-aware or Step-4b-Story-shape-aware logic to hand off to.
    issues_from_assessment = PLUGIN_ROOT / "skills" / "issues-from-assessment" / "SKILL.md"
    assert issues_from_assessment.is_file()
    step_2 = collapsed(
        section(
            issues_from_assessment.read_text(encoding="utf-8"),
            r"^### 2\. Read the assessment \+ derive children",
        )
    )
    assert grep(
        r"Target architecture \(per component\).*Phase-5 Stories per "
        r"\(component, layer\)",
        step_2,
    )
    assert not grep(r"Build/Document status", step_2, ignore_case=True)


def test_invocation_is_single_path_argument_component_only_other_scoping_arg():
    sec = _collapsed_dispatch_section()
    assert grep(
        r"Invocation is exactly `?/apply-test-doubles <path>`?\s*—\s*"
        r"`?--component <name>`? is the only other \*\*scoping\*\* "
        r"argument",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"`?--yes`?, per Parse Arguments, controls interactivity, not "
        r"scope",
        sec,
        ignore_case=True,
    )
    assert grep(r"No other argument is ever required", sec, ignore_case=True)


def test_maintainer_note_removed_no_longer_says_not_yet_shipped():
    # No existing test pins the stale phrase (verified by repo-wide search
    # before writing this test) — this is a fresh assertion, not an update
    # to an existing test. The maintainer note is dropped entirely (not
    # reworded) now that a real, shipped source — apply-test-doubles/
    # SKILL.md's own Parse Arguments section — replaces what it used to
    # forward-reference (arch-review, round-3 panel). Unscoped
    # deliberately: the assertion's whole point is that the old phrase is
    # gone from the *entire* file, not just one section, so a
    # section-scoped read would under-check exactly the thing being
    # verified.
    upstream = collapsed(_upstream_text())
    assert not grep(r"not yet shipped", upstream, ignore_case=True)
    assert not grep(r"Maintainer note, not emitted content", upstream, ignore_case=True)


def test_maintainer_note_area_cites_apply_test_doubles_parse_arguments():
    # arch-review: the closing-command description should ground itself in
    # the now-shipped skill's own contract, not a quoted (and already
    # drifted) issue-text excerpt.
    upstream = collapsed(_upstream_text())
    assert grep(
        r"per `?\.\./apply-test-doubles/SKILL\.md`?'s own Parse Arguments "
        r"section, not restated here",
        upstream,
        ignore_case=True,
    )
    assert not grep(r"quoted verbatim", upstream, ignore_case=True)
