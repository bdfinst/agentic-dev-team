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
GHERKIN_REF = (
    PLUGIN_ROOT / "skills" / "plan" / "references" / "gherkin-persistence.md"
).read_text()
SKILLS_REGISTRY = (PLUGIN_ROOT / "knowledge" / "skills-registry.md").read_text()


class TestRegistryMentionsPersistence:
    def test_plan_row_mentions_feature_persistence(self) -> None:
        row = next(
            line
            for line in SKILLS_REGISTRY.splitlines()
            if line.startswith("| `/plan` ")
        )
        assert ".feature" in row, (
            "the /plan registry entry must mention .feature persistence"
        )


class TestSkillPointsAtTheProcedure:
    def test_step_three_references_the_extracted_procedure(self) -> None:
        assert "references/gherkin-persistence.md" in PLAN_SKILL, (
            "SKILL.md step 3 must point at the extracted persistence procedure"
        )


class TestPlanCreationDetection:
    def test_invokes_the_detection_script_via_plugin_root(self) -> None:
        assert (
            "${CLAUDE_PLUGIN_ROOT}/scripts/detect_bdd_convention.py" in GHERKIN_REF
        ), "/plan must shell to the detection script, not re-derive signals in prose"

    def test_states_the_conservative_precedence(self) -> None:
        assert grep(
            r"feature-files.*>.*manifest.*>.*none|"
            r"\.feature files.*>.*manifest.*>.*no signal",
            GHERKIN_REF,
        ), "the feature-files > manifest > none precedence must be stated"

    def test_detection_failure_falls_back_to_no_signal(self) -> None:
        assert grep(r"non-zero", GHERKIN_REF) and "no-signal" in GHERKIN_REF, (
            "a non-zero detection exit must be treated as no-signal"
        )
        assert "stderr" in GHERKIN_REF, "the detection failure's stderr is surfaced"

    def test_prompt_hint_names_the_real_destination_shape(self) -> None:
        assert "y = features/<plan-slug>/" in GHERKIN_REF, (
            "the prompt hint must show the actual nested destination, "
            "not a bare features/"
        )
        assert "n = plan file only" in GHERKIN_REF
        assert "c = custom path" in GHERKIN_REF

    def test_custom_path_is_validated_with_reprompt_and_escape(self) -> None:
        assert grep(r"repo-relative", GHERKIN_REF), (
            "custom paths must be validated as repo-relative"
        )
        assert grep(r"vendored", GHERKIN_REF), (
            "custom paths must be rejected under vendored trees"
        )
        assert grep(r"re-prompt", GHERKIN_REF), (
            "an invalid custom path re-prompts with the reason"
        )
        assert grep(r"`y` or `n`.*escape|escape.*`y` or `n`", GHERKIN_REF), (
            "the re-prompt accepts y or n as an escape from retrying"
        )

    def test_recorded_decision_is_echoed(self) -> None:
        assert grep(r"[Ee]cho.*(decision|Gherkin persistence)", GHERKIN_REF), (
            "the resolved decision must be echoed in the run output"
        )

    def test_recorded_value_is_the_directory_only(self) -> None:
        assert grep(r"export script appends `<plan-slug>/`", GHERKIN_REF), (
            "the metadata line records the destination directory only — the "
            "exporter appends <plan-slug>/, so recording the full landing "
            "path would double-nest"
        )

    def test_headless_no_signal_skips_with_log_line(self) -> None:
        assert "skipping the Gherkin persistence prompt (non-interactive)" in (
            GHERKIN_REF
        ), "non-interactive no-signal runs log the skip and never block"

    def test_headless_reuses_the_step_six_triad(self) -> None:
        sub_step = GHERKIN_REF
        for trigger in ("--yes", "DEV_TEAM_AUTO_APPROVE=1", "TTY"):
            assert trigger in sub_step, (
                "the persistence sub-step must name the step-6 non-interactive "
                "triad trigger '{}'".format(trigger)
            )

    def test_reruns_honor_the_recorded_decision(self) -> None:
        assert grep(
            r"already (exists and )?records? a .*(decision|Gherkin persistence)|"
            r"\*\*Gherkin persistence\*\*:.*before any prompt",
            GHERKIN_REF,
        ), "re-runs read the existing plan file's metadata line before prompting"
        assert grep(r"[Ee]diting (that|the) (metadata )?line", GHERKIN_REF), (
            "editing the metadata line is the documented way to change the decision"
        )


class TestPostApprovalExport:
    def test_export_instruction_sits_after_the_approval_gate(self) -> None:
        gate = PLAN_SKILL.index("### 6. Present for approval")
        export = PLAN_SKILL.index(
            "${CLAUDE_PLUGIN_ROOT}/scripts/plan_gherkin_export.py"
        )
        assert export > gate, (
            "the .feature export invocation must sit after the step-6 approval "
            "gate — drafts never write files"
        )

    def test_shells_to_the_export_script_from_the_repo_root(self) -> None:
        assert (
            "${CLAUDE_PLUGIN_ROOT}/scripts/plan_gherkin_export.py" in PLAN_SKILL
        ), "/plan must shell to the export script, not hand-copy Gherkin blocks"
        after_gate = PLAN_SKILL[PLAN_SKILL.index("### 6. Present for approval"):]
        assert grep(r"repo root", after_gate), (
            "the export destinations resolve against the cwd — the invocation "
            "must be pinned to the repo root"
        )

    def test_export_summary_is_shown_and_failure_surfaced(self) -> None:
        after_gate = PLAN_SKILL[PLAN_SKILL.index("### 6. Present for approval"):]
        assert grep(r"summary", after_gate), (
            "the export's written/overwritten summary is shown to the operator"
        )
        assert grep(r"non-zero.*(failure|fail)|failure.*non-zero", after_gate), (
            "a non-zero export exit is reported as a failure, never as success"
        )

    def test_tool_owned_directory_is_stated(self) -> None:
        assert grep(r"tool-owned", PLAN_SKILL), (
            "the skill must state <dir>/<plan-slug>/ is tool-owned (derived, "
            "overwritable)"
        )

    def test_constraint_one_carries_a_narrow_carveout(self) -> None:
        constraint = PLAN_SKILL[
            PLAN_SKILL.index("**Do not implement.**"):PLAN_SKILL.index(
                "**Every step must be TDD.**"
            )
        ]
        assert "derived `.feature`" in constraint and "approv" in constraint, (
            "constraint #1 must carry the explicit derived-.feature carve-out"
        )
        assert "plan_gherkin_export.py" in constraint, (
            "the carve-out is narrow: post-approval, via the export script only"
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
