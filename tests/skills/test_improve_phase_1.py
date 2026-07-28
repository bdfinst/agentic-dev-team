"""Contract for the /test-improve skill Phase 1 (analyze via /test-health).

Issue #536 — consolidation of /test-modernize + /test-upgrade. Slice 2 of
the orchestrator plan: Phase 1 delegates analysis to /test-health.

This fixture only greps static SKILL.md text; no git or state-mutating
operations are performed, so hermetic tempdir wiring is not required.

Ported from tests/skills/test_improve_phase_1_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, grep_multiline, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_1_section() -> str:
    return section(_text(), r"^### Phase 1")


def test_test_improve_skill_md_exists():
    assert SKILL.is_file()


def test_body_contains_a_phase_1_section_header():
    assert grep(r"^### Phase 1", _text())


def test_phase_1_names_test_health_as_the_sole_worker():
    assert grep(r"/test-health", _phase_1_section())


def test_phase_1_explicitly_does_not_invoke_cd_test_architecture():
    s = _phase_1_section()
    assert grep(r"/cd-test-architecture", s, ignore_case=True)
    assert grep(
        r"(not|no[t]?[[:space:]]+invoke[d]?|NOT).*(/cd-test-architecture)|"
        r"(/cd-test-architecture).*(not|NOT|no[t]?[[:space:]]+invoke)",
        s,
        ignore_case=True,
    )


def test_phase_1_explicitly_does_not_invoke_test_design():
    s = _phase_1_section()
    assert grep(r"/test-design", s, ignore_case=True)
    assert grep(
        r"(not|no[t]?[[:space:]]+invoke[d]?|NOT).*(/test-design)|"
        r"(/test-design).*(not|NOT|no[t]?[[:space:]]+invoke)",
        s,
        ignore_case=True,
    )


def test_phase_1_explicitly_does_not_invoke_mutation_testing_separately():
    s = _phase_1_section()
    assert grep(r"/mutation-testing", s, ignore_case=True)
    assert grep(
        r"(not|no[t]?[[:space:]]+invoke[d]?|NOT).*(/mutation-testing)|"
        r"(/mutation-testing).*(not|NOT|no[t]?[[:space:]]+invoke|separately)",
        s,
        ignore_case=True,
    )


def test_phase_1_mutation_off_branch_is_documented():
    assert grep(
        r"mutation.*(off|not[[:space:]]+enabled|omit)",
        _phase_1_section(),
        ignore_case=True,
    )


def test_phase_1_mutation_section_reflects_tristate_mode():
    """#1126: the rolled-up mutation section is omitted/not-enabled for `off`
    and present for `kill-loop` and `baseline+kill-loop`."""
    s = _phase_1_section()
    assert grep(r"`off`", s)
    # Bind the non-off modes to the "present" reading (not a bare `present`
    # grep, which would match "represent"/"presently" anywhere in the section).
    assert grep_multiline(r"`kill-loop`.{0,200}present|present.{0,200}`kill-loop`", s, ignore_case=True)
    assert grep(r"`baseline\+kill-loop`", s)
    # And the `off` reading is omitted/not-enabled, distinct from "present".
    assert grep_multiline(r"`off`.{0,200}(omitted|not enabled)", s, ignore_case=True)


def test_phase_1_human_gate_names_the_ordered_improvement_plan():
    assert grep(
        r"ordered[[:space:]]+improvement[[:space:]]+plan",
        _phase_1_section(),
        ignore_case=True,
    )


def test_phase_1_gate_blocks_phase_4_until_approval():
    """#1422: Phase 1 now immediately precedes Phase 4 (Triage) in the
    reordered execution sequence (0 -> 2 -> 3 -> 1 -> 4 -> ...), so Phase 1's
    human gate blocks Phase 4, not Phase 2."""
    s = _phase_1_section()
    assert grep(r"\*\*Phase 4 does not run\*\*", s)
    assert not grep(r"\*\*Phase 2 does not run\*\*", s)


# --- test-counts-before.json existing-snapshot guard (issue #1412, Slice 2) --


def test_phase_1_fresh_slug_writes_test_counts_before_without_prompt():
    """No existing test-counts-before.json for the slug -> write directly,
    no prompt needed."""
    s = _phase_1_section()
    assert grep(r"[Nn]o[[:space:]]+existing[[:space:]]+file", s)
    assert grep_multiline(
        r"[Nn]o[[:space:]]+existing[[:space:]]+file.{0,80}no[[:space:]]+prompt",
        s,
        ignore_case=True,
    )


def test_phase_1_existing_snapshot_prompts_with_keep_overwrite_default_keep():
    s = _phase_1_section()
    assert grep(r"test-counts-before\.json", s)
    assert grep_multiline(
        r"overwrite it\s+\(starts a fresh\s+before/after comparison\)", s
    )
    assert grep_multiline(r"\[keep/overwrite,\s+default: keep\]", s)


def test_phase_1_declining_overwrite_keeps_existing_file_and_reuses_it():
    s = _phase_1_section()
    assert grep_multiline(
        r"keep.{0,80}(leaves the existing file untouched|untouched).{0,80}reuses it",
        s,
        ignore_case=True,
    )


def test_phase_1_confirming_overwrite_replaces_existing_snapshot():
    s = _phase_1_section()
    assert grep(
        r"overwrite.{0,40}replaces the existing file with a\s+fresh snapshot",
        s,
        ignore_case=True,
    ) or grep_multiline(
        r"overwrite.{0,80}replaces.{0,40}fresh snapshot", s, ignore_case=True
    )


def test_phase_1_unrecognized_answer_reprompts_with_identical_text():
    s = _phase_1_section()
    assert grep_multiline(
        r"[Uu]nrecognized answer.{0,60}re-prompts with the identical",
        s,
    )
    assert grep(
        r"never silently falls back to the default", s, ignore_case=True
    )


def test_phase_1_non_interactive_defaults_to_keep_and_logs_the_decision():
    s = _phase_1_section()
    assert grep(
        r"non-interactive.{0,40}\(no usable TTY / `DEV_TEAM_AUTO_APPROVE=1`\)",
        s,
    )
    assert grep_multiline(
        r"defaults to \*\*keep existing\*\*.{0,60}logs the\s+auto-decision",
        s,
    )
    assert grep(r"decision-defaults\.md", s)


# --- malformed-file-treated-as-absent branch (issue #1502) -------------------


def test_phase_1_malformed_snapshot_treated_as_absent_with_warning():
    """A corrupt/unparseable test-counts-before.json is treated as absent —
    a fresh capture with a warning, never silently kept — matching the shared
    re-capture axis the two newer guards already implement (#1502)."""
    s = _phase_1_section()
    assert grep(r"malformed|corrupt", s, ignore_case=True)
    assert grep_multiline(
        r"(malformed or\s+corrupt|fails to parse).{0,120}treat it as absent",
        s,
        ignore_case=True,
    )
    assert grep(r"never as a snapshot to keep", s, ignore_case=True)
    assert grep(r"emit a warning", s, ignore_case=True)


def test_phase_1_snapshot_guard_cites_the_shared_recapture_axis():
    """Phase 1's guard cites decision-defaults.md's re-capture axis for the
    *why* rather than continuing to duplicate an incomplete copy (#1502)."""
    s = _phase_1_section()
    assert grep(r"decision-defaults\.md", s)
    assert grep(
        r"Re-capture: keep vs\. overwrite an existing\s+tracked artifact",
        s,
        ignore_case=True,
    )
