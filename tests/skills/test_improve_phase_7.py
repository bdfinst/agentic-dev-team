"""Contract for /test-improve Phase 7 — executive-summary report generation.

Issue #536, Slice 10 Step 10.2.

Ported from tests/skills/test_improve_phase_7_tests.bats (issue #674).
"""

from __future__ import annotations

from conftest import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "test-improve" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _phase_7_section() -> str:
    return section(_text(), r"^### Phase 7")


def test_body_contains_a_phase_7_section_header():
    assert grep(r"^### Phase 7", _text())


def test_phase_7_names_the_shipped_template_path():
    assert grep(
        r"plugins/dev-team/skills/test-improve/templates/executive-summary\.md",
        _phase_7_section(),
    )


def test_phase_7_names_the_output_path_shape():
    s = _phase_7_section()
    assert grep(r"reports/test-improve/", s)
    assert grep(r"<repo-slug>|<slug>", s, ignore_case=True)


def test_phase_7_documents_the_interpolation_rule():
    s = _phase_7_section()
    assert grep(r"interpolat|placeholder|substitut", s, ignore_case=True)
    assert grep(r"memory/test-improve/<slug>/", s)


def test_phase_7_documents_empty_section_not_applicable_rule():
    s = _phase_7_section()
    assert grep(r"not[[:space:]]+applicable", s, ignore_case=True)
    assert grep(
        r"(do[[:space:]]+not|never|not).*(disappear|hidden|omit)", s, ignore_case=True
    )


def test_phase_7_documents_parent_issue_post_or_feature_md_link_update():
    assert grep(
        r"parent[[:space:]]+issue|FEATURE\.md", _phase_7_section(), ignore_case=True
    )


def test_phase_7_documents_regeneratable_from_memory_contract():
    assert grep(
        r"regenerat|re-run.*Phase[[:space:]]+7|reproduce",
        _phase_7_section(),
        ignore_case=True,
    )
