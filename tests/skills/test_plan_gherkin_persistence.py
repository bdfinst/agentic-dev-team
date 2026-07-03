"""Content guards for /plan's Gherkin .feature persistence (issue #537).

Structural sensors over the /plan skill prose and template: the decision is
recorded in plan metadata, detection runs at plan creation with a conservative
prompt/fallback flow, and the byte-for-byte export happens only after the
approval gate via plan_gherkin_export.py.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

PLAN_SKILL = (PLUGIN_ROOT / "skills" / "plan" / "SKILL.md").read_text()
PLAN_TEMPLATE = (
    PLUGIN_ROOT / "skills" / "plan" / "references" / "plan-template.md"
).read_text()


class TestTemplateCarriesPersistenceDecision:
    def test_metadata_block_has_gherkin_persistence_line(self) -> None:
        assert grep(r"^\*\*Gherkin persistence\*\*:", PLAN_TEMPLATE), (
            "plan-template.md metadata block must carry the "
            "'**Gherkin persistence**:' line re-runs honor"
        )

    def test_line_documents_the_three_value_shapes(self) -> None:
        for shape in ("destination dir", "plan-file-only", "custom:"):
            assert shape in PLAN_TEMPLATE, (
                "the Gherkin persistence metadata line must document the "
                "'{}' value shape".format(shape)
            )
