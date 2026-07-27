"""Contract for issue #1450's gherkin-public and plan depth-audit notes.

The audit found no behavior change is warranted for either skill:

- /gherkin-public consumes a pre-built component map (/cd-test-architecture
  Phase 1) rather than discovering surfaces itself, so /gherkin-derive's
  mandatory in-depth analysis directive does not transfer here.
- /plan's per-slice Gherkin authoring step is deliberately spec-scoped and
  exploration-bounded, so the same directive would contradict its own
  designed scope there too.

This test locks both audit findings in as documented in the shipped skills,
not only in the issue. One file, mirroring the plan's single Slice-4
Gherkin feature covering both scenarios.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

GHERKIN_PUBLIC_SKILL = PLUGIN_ROOT / "skills" / "gherkin-public" / "SKILL.md"
PLAN_SKILL = PLUGIN_ROOT / "skills" / "plan" / "SKILL.md"


def test_gherkin_public_notes_section_references_issue_1450():
    assert grep(r"#1450", GHERKIN_PUBLIC_SKILL.read_text())


def test_gherkin_public_notes_section_explains_pre_built_component_map_rationale():
    text = GHERKIN_PUBLIC_SKILL.read_text()
    assert grep(r"pre-built component map", text, ignore_case=True)
    assert grep(r"cd-test-architecture", text, ignore_case=True)


def test_gherkin_public_notes_section_states_no_behavior_change():
    assert grep(
        r"no behavior change", GHERKIN_PUBLIC_SKILL.read_text(), ignore_case=True
    )


def test_plan_references_issue_1450():
    assert grep(r"#1450", PLAN_SKILL.read_text())


def test_plan_states_spec_scoped_rationale_near_gherkin_authoring_step():
    text = PLAN_SKILL.read_text()
    idx = text.find("author the Gherkin scenario")
    assert idx != -1
    idx2 = text.find("### 3. Create the plan", idx)
    section_text = text[idx : idx2 if idx2 != -1 else None]
    assert grep(r"spec-scoped", section_text, ignore_case=True)


def test_plan_states_no_behavior_change():
    assert grep(r"no behavior change", PLAN_SKILL.read_text(), ignore_case=True)
