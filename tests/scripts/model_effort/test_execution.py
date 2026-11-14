"""Running a planned run through the CLI: both arms' trials, outcomes and harness errors."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest
from _model_effort_support import (
    ARM_COUNT,
    BASELINE_TWO_ARM_ESTIMATE,
    CANDIDATE_TWO_ARM_ESTIMATE,
    CAUSE_LIMIT,
    CLEAN_FORM_ARGS,
    HAIKU_MODEL_ID,
    PASS_VERDICT,
    RUN_ID,
    SCOUT_HAIKU_ARGS,
    SCOUT_TRIALS,
    SONNET_MODEL_ID,
    TRIAL_COST,
    StubClaude,
    World,
    _arm_block,
    _cli,
    _deps_raising_after,
    _deps_timing_out,
    _deps_with_canned_trials,
    _expected_session_config,
    _flag_value,
    _init_event,
    _outcomes,
    _passing_stub,
    _result_event,
    _stream,
    _verdict_call,
    _written,
    assert_cut_at_limit,
)
from model_effort import external, grading, plan
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL

FAIL_VERDICT = {"status": "fail", "issues": [], "summary": "Layer violation."}


def _unparseable_call(model_id: str) -> dict:
    result = _result_event("No JSON here.", model_usage={model_id: {}})
    return {"stdout": _stream(_init_event(model_id), result)}


def _two_arm_stub(world: World) -> StubClaude:
    """Calls alternate baseline, candidate over clean-form x3 then layered-svc x3.

    The candidate's second clean-form trial returns no JSON and its first
    layered-svc trial calls WebFetch.
    """
    stub = StubClaude(world.stub_dir)
    baseline_pass = _verdict_call(PASS_VERDICT, SONNET_MODEL_ID)
    baseline_fail = _verdict_call(FAIL_VERDICT, SONNET_MODEL_ID)
    candidate_pass = _verdict_call(PASS_VERDICT, HAIKU_MODEL_ID)
    candidate_fail = _verdict_call(FAIL_VERDICT, HAIKU_MODEL_ID)
    stub.queue(
        baseline_pass,
        candidate_pass,
        baseline_pass,
        _unparseable_call(HAIKU_MODEL_ID),
        baseline_pass,
        candidate_pass,
        baseline_fail,
        _verdict_call(FAIL_VERDICT, HAIKU_MODEL_ID, "WebFetch"),
        baseline_fail,
        candidate_fail,
        baseline_fail,
        candidate_fail,
    )
    return stub


def _run_two_arm_scenario(world: World) -> tuple[int, dict, StubClaude]:
    stub = _two_arm_stub(world)
    code = _cli(world, stub, *SCOUT_HAIKU_ARGS, "--trials", str(SCOUT_TRIALS))
    return code, _written(world), stub


def _trial(outcome_name: str, error: str | None = None) -> dict:
    return {
        "outcome": outcome_name,
        "cost_usd": TRIAL_COST,
        "cost_reported": True,
        "grader_messages": [],
        "error": error,
        "judge_cost_usd": None,
    }


def _fixture_block(stem: str, kind: str, clean: bool, trials: list[dict]) -> dict:
    return {"stem": stem, "kind": kind, "expected_clean": clean, "trials": trials}


class TestTwoArmRun:
    def test_run_metadata_records_identity_status_and_the_baseline_session_config(
        self, world
    ):
        code, written, _ = _run_two_arm_scenario(world)

        assert code == 0
        assert [path.name for path in world.artifacts] == [f"{RUN_ID}.json"]
        assert {key: value for key, value in written.items() if key != "arms"} == {
            "run_id": RUN_ID,
            "status": "complete",
            "abort_reason": None,
            "created": "2026-10-08T12:30:45Z",
            "git_sha": "abc123",
            "agent": "scout",
            "grader": "expected-findings",
            "judge": None,
            "tier_change_eligible": True,
            "fidelity": "read-only-profile",
            "knowledge_dir": str(world.deps.eval_paths.knowledge_dir),
            "session_config": _expected_session_config(SONNET_MODEL_ID),
        }

    def test_artifact_git_sha_is_null_when_the_repository_has_no_head(self, world):
        deps = dataclasses.replace(world.deps, read_git_sha=lambda: None)

        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=deps,
        )

        assert _written(world)["git_sha"] is None

    def test_baseline_arm_records_configuration_trials_and_totals(self, world):
        _, written, _ = _run_two_arm_scenario(world)

        assert _arm_block(written, BASELINE_LABEL) == {
            "label": "baseline",
            "model": "sonnet",
            "model_id": SONNET_MODEL_ID,
            "model_id_note": None,
            "effort": "high",
            "tools_enabled": ["Read", "Grep"],
            "tools_withheld": ["mcp__x__y", "Bash(graphify *)"],
            "trials_per_fixture": SCOUT_TRIALS,
            "estimated_cost_usd": pytest.approx(BASELINE_TWO_ARM_ESTIMATE),
            "estimated_judge_cost_usd": 0.0,
            "session_config": _expected_session_config(SONNET_MODEL_ID),
            "fixtures": [
                _fixture_block("clean-form", "file", True, [_trial("pass")] * 3),
                _fixture_block("layered-svc", "directory", False, [_trial("pass")] * 3),
            ],
            "totals": {
                "timeout": 0,
                "cli_error": 0,
                "tool_violation": 0,
                "parse_failure": 0,
                "judge_error": 0,
                "graded_fail": 0,
                "pass": 6,
                "clean_fixture_false_positives": 0,
                "actual_cost_usd": pytest.approx(0.06),
                "unreported_trials_estimate_usd": 0.0,
                "judge_cost_usd": 0.0,
            },
        }

    def test_candidate_arm_records_its_parse_failure_and_tool_violation(self, world):
        _, written, _ = _run_two_arm_scenario(world)

        assert _arm_block(written, CANDIDATE_LABEL) == {
            "label": "candidate",
            "model": "haiku",
            "model_id": HAIKU_MODEL_ID,
            "model_id_note": None,
            "effort": "high",
            "tools_enabled": ["Read", "Grep"],
            "tools_withheld": ["mcp__x__y", "Bash(graphify *)"],
            "trials_per_fixture": SCOUT_TRIALS,
            "estimated_cost_usd": pytest.approx(CANDIDATE_TWO_ARM_ESTIMATE),
            "estimated_judge_cost_usd": 0.0,
            "session_config": _expected_session_config(HAIKU_MODEL_ID),
            "fixtures": [
                _fixture_block(
                    "clean-form",
                    "file",
                    True,
                    [
                        _trial("pass"),
                        _trial("parse_failure", "no JSON object in the result text"),
                        _trial("pass"),
                    ],
                ),
                _fixture_block(
                    "layered-svc",
                    "directory",
                    False,
                    [
                        _trial(
                            "tool_violation", "tools outside the enabled set: WebFetch"
                        ),
                        _trial("pass"),
                        _trial("pass"),
                    ],
                ),
            ],
            "totals": {
                "timeout": 0,
                "cli_error": 0,
                "tool_violation": 1,
                "parse_failure": 1,
                "judge_error": 0,
                "graded_fail": 0,
                "pass": 4,
                "clean_fixture_false_positives": 0,
                "actual_cost_usd": pytest.approx(0.06),
                "unreported_trials_estimate_usd": 0.0,
                "judge_cost_usd": 0.0,
            },
        }

    def test_arms_alternate_trial_by_trial_fixture_by_fixture(self, world):
        _, _, stub = _run_two_arm_scenario(world)

        calls = stub.calls
        assert [_flag_value(c["argv"], "--model") for c in calls] == [
            "sonnet",
            "haiku",
        ] * 6
        staged = [sorted(c["files_before"]) for c in calls]
        assert staged[:6] == [["clean-form.html"]] * 6
        assert staged[6:] == [["layered-svc/src/app.py"]] * 6

    def test_candidate_inherits_baseline_values_for_omitted_flags(self, world):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            "scout",
            "--fixtures",
            "clean-form",
            "--effort",
            "low",
            "--trials",
            "1",
        )

        written = _written(world)
        baseline = _arm_block(written, BASELINE_LABEL)
        candidate = _arm_block(written, CANDIDATE_LABEL)
        assert (baseline["model"], baseline["effort"]) == ("sonnet", "high")
        assert (candidate["model"], candidate["effort"]) == ("sonnet", "low")

    def test_fixtures_flag_restricts_the_run_to_the_named_stems(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *SCOUT_HAIKU_ARGS,
            "--fixtures",
            "layered-svc",
            "--trials",
            "1",
        )

        assert code == 0
        assert len(stub.calls) == 2
        assert all("layered-svc/src/app.py" in c["files_before"] for c in stub.calls)

    def test_a_fixture_named_twice_runs_once_per_arm(self, world):
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli(
            world,
            StubClaude(world.stub_dir),
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "clean-form,clean-form",
            "--trials",
            "1",
            deps=deps,
        )

        written = _written(world)
        assert code == 0
        assert len(trial_calls) == ARM_COUNT
        for label in (BASELINE_LABEL, CANDIDATE_LABEL):
            stems = [f["stem"] for f in _arm_block(written, label)["fixtures"]]
            assert stems == ["clean-form"]

    def test_enabled_tools_reach_the_cli_and_withheld_tools_only_the_artifact(
        self, world
    ):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        for call in stub.calls:
            assert _flag_value(call["argv"], "--tools") == "Read,Grep"
            assert not any("mcp__" in arg for arg in call["argv"])
        for arm in _written(world)["arms"]:
            assert arm["tools_withheld"] == ["mcp__x__y", "Bash(graphify *)"]

    def test_artifact_path_is_reserved_empty_before_the_first_trial(self, world):
        stub = _passing_stub(world, observe=str(world.artifact_path))

        _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        assert stub.calls[0]["observed"] == {"exists": True, "size": 0}

    def test_trial_that_times_out_is_recorded_as_a_timeout_in_the_artifact(self, world):
        _cli(
            world,
            StubClaude(world.stub_dir),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=_deps_timing_out(world),
        )

        baseline = _arm_block(_written(world), BASELINE_LABEL)
        trial = baseline["fixtures"][0]["trials"][0]
        assert baseline["totals"]["timeout"] == 1
        assert (trial["outcome"], trial["error"]) == (
            "timeout",
            "trial exceeded the time limit",
        )


class TestToolViolationFollowsThePlansToolProfile:
    def test_a_tool_the_default_profile_allows_but_the_agent_does_not_is_a_violation(
        self, world
    ):
        stub = StubClaude(
            world.stub_dir,
            **_verdict_call(PASS_VERDICT, SONNET_MODEL_ID, "Glob"),
        )

        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        trial = _arm_block(written, BASELINE_LABEL)["fixtures"][0]["trials"][0]
        assert code == 0
        assert _arm_block(written, BASELINE_LABEL)["tools_enabled"] == ["Read", "Grep"]
        assert trial["outcome"] == "tool_violation"
        assert trial["error"] == "tools outside the enabled set: Glob"


class TestUnexpectedTrialError:
    def test_error_in_a_trial_keeps_the_completed_trials_and_marks_the_artifact_harness_error(
        self, world, capsys
    ):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 3, RuntimeError("staging exploded")),
        )

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "harness-error",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]
        assert "run stopped early (harness-error)" in err
        assert "RuntimeError: staging exploded" in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_error_text_in_the_stop_notice_is_cut_at_the_cause_limit(
        self, world, capsys
    ):
        long_message = "m" * (4 * CAUSE_LIMIT)
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 1, RuntimeError(long_message)),
        )

        assert_cut_at_limit(capsys.readouterr().err, "RuntimeError: ", "m")

    def test_terminal_control_sequences_in_the_error_are_shown_escaped(
        self, world, capsys
    ):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 1, RuntimeError("\x1b[2Jgone")),
        )

        err = capsys.readouterr().err
        assert "\x1b" not in err
        assert "RuntimeError: \\x1b[2Jgone" in err

    def test_staging_failure_while_grading_is_a_harness_error_not_a_graded_fail(
        self, world, capsys, monkeypatch
    ):
        def failing_copy(*_args, **_kwargs):
            raise OSError("no space left")

        monkeypatch.setattr(plan, "check_expected_entries", lambda *_args: None)
        monkeypatch.setattr(grading, "shutil", SimpleNamespace(copy2=failing_copy))

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "2")

        written = _written(world)
        assert code == 1
        assert written["abort_reason"] == "harness-error"
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]
        assert "OSError: no space left" in capsys.readouterr().err

    def test_grader_whose_return_shape_changed_is_a_harness_error_not_a_graded_fail(
        self, world, capsys, monkeypatch
    ):
        monkeypatch.setattr(plan, "check_expected_entries", lambda *_args: None)
        monkeypatch.setattr(
            external.eval_grade(), "run_grading", lambda **_kwargs: "drifted"
        )

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "2")

        written = _written(world)
        assert code == 1
        assert written["abort_reason"] == "harness-error"
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]
        assert "ExternalContractError" in capsys.readouterr().err

    def test_error_in_the_first_trial_still_writes_an_artifact_with_no_results(
        self, world
    ):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 0, RuntimeError("no staging dir")),
        )

        written = _written(world)
        assert code == 1
        assert written["abort_reason"] == "harness-error"
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]
