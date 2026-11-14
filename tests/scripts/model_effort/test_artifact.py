"""Artifact assembly (model_effort.artifact)."""

from __future__ import annotations

import pytest
from ab_results import (
    READ_ONLY_PROFILE,
    arm_run_of,
    built_arm,
    flat_run_estimate,
    run_metadata,
    trial_result,
)
from model_effort import artifact, tools
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL
from model_effort.outcome import Outcome
from model_effort.run_status import AbortReason


class TestArtifactStatus:
    def test_run_without_an_abort_reason_is_complete(self):
        built = artifact.build_artifact(
            run_metadata(), [], flat_run_estimate(), READ_ONLY_PROFILE, None
        )

        assert (built["status"], built["abort_reason"]) == ("complete", None)

    @pytest.mark.parametrize(
        "reason", list(AbortReason), ids=lambda reason: reason.value
    )
    def test_run_with_an_abort_reason_is_incomplete_and_names_it(self, reason):
        built = artifact.build_artifact(
            run_metadata(), [], flat_run_estimate(), READ_ONLY_PROFILE, reason
        )

        assert (built["status"], built["abort_reason"]) == ("incomplete", reason.value)

    def test_abort_reasons_use_the_contract_strings(self):
        assert [reason.value for reason in AbortReason] == [
            "max-cost",
            "infra-failure",
            "interrupt",
            "harness-error",
        ]


class TestArtifactTools:
    def test_both_arms_record_the_plans_one_tool_profile(self):
        profile = tools.ToolProfile(
            enabled_tools=("Read", "Grep"),
            withheld_tools=("WebFetch",),
            refused_tools=(),
        )
        runs = [
            arm_run_of(BASELINE_LABEL, [trial_result(Outcome.PASS)]),
            arm_run_of(CANDIDATE_LABEL, [trial_result(Outcome.PASS)]),
        ]

        built = artifact.build_artifact(
            run_metadata(), runs, flat_run_estimate(), profile, None
        )

        assert [
            (arm["tools_enabled"], arm["tools_withheld"]) for arm in built["arms"]
        ] == [(["Read", "Grep"], ["WebFetch"])] * 2


class TestArtifactSessionConfig:
    def test_arm_session_config_comes_from_its_first_trial_with_an_init_event(self):
        first = {"model": "first"}
        arm = built_arm(
            [
                trial_result(Outcome.CLI_ERROR),
                trial_result(Outcome.PASS, session_config=first),
                trial_result(Outcome.PASS, session_config={"model": "later"}),
            ]
        )

        assert arm["session_config"] == first

    def test_arm_without_any_init_event_has_null_session_config(self):
        assert built_arm([trial_result(Outcome.CLI_ERROR)])["session_config"] is None

    def test_run_level_session_config_is_the_baseline_arms_whatever_the_arm_order(
        self,
    ):
        baseline = arm_run_of(
            BASELINE_LABEL,
            [trial_result(Outcome.PASS, session_config={"model": "base"})],
        )
        candidate = arm_run_of(
            CANDIDATE_LABEL,
            [trial_result(Outcome.PASS, session_config={"model": "cand"})],
        )

        built = artifact.build_artifact(
            run_metadata(),
            [candidate, baseline],
            flat_run_estimate(),
            READ_ONLY_PROFILE,
            None,
        )

        assert built["session_config"] == {"model": "base"}
