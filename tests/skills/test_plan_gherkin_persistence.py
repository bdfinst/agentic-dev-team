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


class TestPlanCreationDetection:
    def test_invokes_the_detection_script_via_plugin_root(self) -> None:
        assert (
            "${CLAUDE_PLUGIN_ROOT}/scripts/detect_bdd_convention.py" in PLAN_SKILL
        ), "/plan must shell to the detection script, not re-derive signals in prose"

    def test_states_the_conservative_precedence(self) -> None:
        assert grep(
            r"feature-files.*>.*manifest.*>.*none|"
            r"\.feature files.*>.*manifest.*>.*no signal",
            PLAN_SKILL,
        ), "the feature-files > manifest > none precedence must be stated"

    def test_detection_failure_falls_back_to_no_signal(self) -> None:
        assert grep(r"non-zero", PLAN_SKILL) and "no-signal" in PLAN_SKILL, (
            "a non-zero detection exit must be treated as no-signal"
        )
        assert "stderr" in PLAN_SKILL, "the detection failure's stderr is surfaced"

    def test_prompt_hint_names_the_real_destination_shape(self) -> None:
        assert "y = features/<plan-slug>/" in PLAN_SKILL, (
            "the prompt hint must show the actual nested destination, "
            "not a bare features/"
        )
        assert "n = plan file only" in PLAN_SKILL
        assert "c = custom path" in PLAN_SKILL

    def test_custom_path_is_validated_with_reprompt_and_escape(self) -> None:
        assert grep(r"repo-relative", PLAN_SKILL), (
            "custom paths must be validated as repo-relative"
        )
        assert grep(r"vendored", PLAN_SKILL), (
            "custom paths must be rejected under vendored trees"
        )
        assert grep(r"re-prompt", PLAN_SKILL), (
            "an invalid custom path re-prompts with the reason"
        )
        assert grep(r"`y` or `n`.*escape|escape.*`y` or `n`", PLAN_SKILL), (
            "the re-prompt accepts y or n as an escape from retrying"
        )

    def test_recorded_decision_is_echoed(self) -> None:
        assert grep(r"[Ee]cho.*(decision|Gherkin persistence)", PLAN_SKILL), (
            "the resolved decision must be echoed in the run output"
        )

    def test_headless_no_signal_skips_with_log_line(self) -> None:
        assert "skipping the Gherkin persistence prompt (non-interactive)" in (
            PLAN_SKILL
        ), "non-interactive no-signal runs log the skip and never block"

    def test_reruns_honor_the_recorded_decision(self) -> None:
        assert grep(
            r"already (exists and )?records? a .*(decision|Gherkin persistence)|"
            r"\*\*Gherkin persistence\*\*:.*before any prompt",
            PLAN_SKILL,
        ), "re-runs read the existing plan file's metadata line before prompting"
        assert grep(r"[Ee]diting (that|the) (metadata )?line", PLAN_SKILL), (
            "editing the metadata line is the documented way to change the decision"
        )


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
