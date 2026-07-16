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


def test_phase_1_gate_blocks_phase_2_until_approval():
    assert grep(
        r"(Phase 2|next phase).*(does not|not).*run|"
        r"do[[:space:]]+not[[:space:]]+advance|human[[:space:]]+gate",
        _phase_1_section(),
        ignore_case=True,
    )
