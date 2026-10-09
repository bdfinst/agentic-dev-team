"""The CLI (scripts/model_effort_ab.py), end to end through a stub binary."""

from __future__ import annotations

import dataclasses
import io
import json
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

import model_effort_ab
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
    RaisingStdin,
    StubClaude,
    World,
    _arm_block,
    _cli,
    _deps_raising_after,
    _deps_timing_out,
    _deps_with_canned_trials,
    _expected_session_config,
    _flag_value,
    _gated_cli,
    _init_event,
    _make_file_fixture,
    _outcomes,
    _passing_stub,
    _result_event,
    _stderr_lines,
    _store_with_failing_replace,
    _stream,
    _verdict_call,
    _write_agent,
    _write_expected,
    _written,
    assert_cut_at_limit,
    assert_nothing_ran,
)
from model_effort import external, grading, paths, runner, trial_count
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
    }


def _fixture_block(stem: str, kind: str, clean: bool, trials: list[dict]) -> dict:
    return {"stem": stem, "kind": kind, "expected_clean": clean, "trials": trials}


class TestReadGitHeadSha:
    @pytest.mark.parametrize(
        "error",
        [OSError("git missing"), subprocess.CalledProcessError(128, "git")],
        ids=["git-not-installed", "not-a-repository"],
    )
    def test_a_failing_git_yields_none(self, monkeypatch, error):
        def failing_run(*_args, **_kwargs):
            raise error

        monkeypatch.setattr(model_effort_ab.subprocess, "run", failing_run)

        assert model_effort_ab._read_git_head_sha() is None

    @pytest.mark.skipif(
        shutil.which("git") is None or not (paths.REPO_ROOT / ".git").exists(),
        reason="needs git and a checkout with a .git entry",
    )
    def test_the_real_repository_yields_a_full_commit_hash(self):
        sha = model_effort_ab._read_git_head_sha()

        assert sha is not None and re.fullmatch(r"[0-9a-f]{40}", sha)


class TestDepsDefaults:
    def test_default_deps_use_the_shipped_directories_and_collaborators(self):
        deps = model_effort_ab.Deps()

        assert deps.eval_paths == paths.EvalPaths.default()
        assert deps.run_trial is runner.run_trial
        assert deps.read_git_sha is model_effort_ab._read_git_head_sha

    def test_default_stdin_is_the_process_stdin(self, monkeypatch):
        stream = io.StringIO()
        monkeypatch.setattr(sys, "stdin", stream)

        assert model_effort_ab.Deps().stdin is stream

    @pytest.mark.parametrize("is_tty", [True, False])
    def test_default_tty_check_follows_the_process_stdin(self, monkeypatch, is_tty):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: is_tty))

        assert model_effort_ab.Deps().stdin_is_tty() is is_tty

    def test_default_clock_reads_a_timezone_aware_time(self):
        assert model_effort_ab.Deps().clock().tzinfo is not None

    def test_each_default_deps_has_its_own_random_generator(self):
        assert model_effort_ab.Deps().rng is not model_effort_ab.Deps().rng

    def test_default_pricing_table_is_the_shipped_one(self):
        assert model_effort_ab.Deps().pricing_table == external.pricing().load_pricing(
            paths.PRICING_PATH
        )


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
                "graded_fail": 0,
                "pass": 6,
                "clean_fixture_false_positives": 0,
                "actual_cost_usd": pytest.approx(0.06),
                "unreported_trials_estimate_usd": 0.0,
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
                "graded_fail": 0,
                "pass": 4,
                "clean_fixture_false_positives": 0,
                "actual_cost_usd": pytest.approx(0.06),
                "unreported_trials_estimate_usd": 0.0,
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


class TestPreRunRefusals:
    def test_existing_artifact_path_exits_2_before_any_trial_and_stays_unchanged(
        self, world
    ):
        stub = StubClaude(world.stub_dir)
        world.artifact_path.write_text("sentinel", encoding="utf-8")

        code = _cli(world, stub, *SCOUT_HAIKU_ARGS)

        assert code == 2
        assert stub.calls == []
        assert world.artifact_path.read_text(encoding="utf-8") == "sentinel"

    def test_collision_message_says_what_is_wrong_and_how_to_fix_it(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)
        world.artifact_path.write_text("x", encoding="utf-8")

        _cli(world, stub, *SCOUT_HAIKU_ARGS)

        stderr = capsys.readouterr().err
        assert "already exists" in stderr and "rerun" in stderr

    def test_unknown_agent_exits_2_listing_valid_agents_and_writes_nothing(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "no-such-agent")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "no-such-agent" in stderr
        assert "scout" in stderr and "lonely" in stderr
        assert_nothing_ran(stub, world)

    def test_unknown_fixture_exits_2_naming_it_and_listing_valid_stems(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", "clean-form,nope")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "nope" in stderr
        assert "clean-form" in stderr and "layered-svc" in stderr
        assert_nothing_ran(stub, world)

    def test_a_fixtures_list_with_no_stems_exits_2_and_runs_nothing(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", ",")

        assert code == 2
        assert "named no stems" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_fixture_whose_expected_entry_names_another_agent_exits_2(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", "other-only")

        assert code == 2
        assert "other-only" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_agent_with_no_expected_entries_exits_2_stating_no_fixtures_found(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "lonely")

        assert code == 2
        assert "no fixtures were found" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_write_capable_agent_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "write-capable")

        assert code == 2
        assert "write-capable agents are not supported yet" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_missing_runs_directory_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        world.runs_dir.rmdir()

        code = _cli(world, stub, *SCOUT_HAIKU_ARGS)

        assert code == 2
        assert "runs directory" in capsys.readouterr().err
        assert stub.calls == []

    def test_malformed_expected_json_exits_2_naming_the_file(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        broken = world.expected_dir / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        code = _cli(world, stub, "scout")

        assert code == 2
        assert str(broken) in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_misspelled_candidate_effort_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--effort", "hgih")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "hgih" in stderr and "high" in stderr
        assert_nothing_ran(stub, world)

    def test_candidate_model_with_path_characters_exits_2_before_any_trial(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--model", "../../etc")

        assert code == 2
        assert "--model" in capsys.readouterr().err
        assert_nothing_ran(stub, world)


def _add_agent(world: World, name: str) -> None:
    """Add a read-only agent with one fixture, so a run over it has one fixture."""
    _write_agent(
        world.deps.eval_paths.agents_dir, name, "Read", model="sonnet", effort="high"
    )
    _write_expected(world.expected_dir, f"{name}-case", name, "pass")
    _make_file_fixture(world.deps.eval_paths.fixtures_dir, f"{name}-case.txt")


class TestTrialDefaults:
    @pytest.mark.parametrize(
        ("agent", "trials", "echo_label"),
        [
            ("naming-review", 5, "default"),
            ("security-review", 10, "high-stakes default"),
        ],
    )
    def test_each_arm_runs_the_default_trials_for_the_agent(
        self, world, capsys, agent, trials, echo_label
    ):
        _add_agent(world, agent)
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli(
            world, StubClaude(world.stub_dir), agent, "--model", "haiku", deps=deps
        )

        assert code == 0
        assert len(trial_calls) == ARM_COUNT * trials
        assert f"Trials per arm per fixture: {trials} ({echo_label})" in _stderr_lines(
            capsys
        )

    def test_explicit_trials_override_the_high_stakes_default(self, world, capsys):
        _add_agent(world, "security-review")
        deps, trial_calls = _deps_with_canned_trials(world.deps)

        code = _cli(
            world,
            StubClaude(world.stub_dir),
            "security-review",
            "--model",
            "haiku",
            "--trials",
            "3",
            deps=deps,
        )

        assert code == 0
        assert len(trial_calls) == ARM_COUNT * 3
        assert "Trials per arm per fixture: 3 (--trials)" in _stderr_lines(capsys)

    @pytest.mark.parametrize(
        "agent",
        ["security-review", "correctness-review", "architect", "security-engineer"],
    )
    def test_resolver_gives_every_high_stakes_agent_ten_trials(self, agent):
        assert trial_count.resolve_trials(None, agent) == trial_count.TrialCount(
            10, "high-stakes default"
        )

    def test_resolver_gives_other_agents_five_trials(self):
        assert trial_count.resolve_trials(None, "security-reviewer") == (
            trial_count.TrialCount(5, "default")
        )

    def test_resolver_prefers_the_flag_over_the_high_stakes_default(self):
        assert trial_count.resolve_trials(2, "architect") == trial_count.TrialCount(
            2, "--trials"
        )


class TestInvalidArgumentsAreRefusedBeforeTheEstimate:
    def _assert_refused(self, world, stub, capsys, code, fix_hint):
        err = capsys.readouterr().err
        assert code == 2
        assert fix_hint in err
        assert "Estimate" not in err
        assert_nothing_ran(stub, world)

    @pytest.mark.parametrize("trials", ["0", "-1", "abc", "2.5"])
    def test_non_positive_or_non_integer_trials_name_the_fix(
        self, world, capsys, trials
    ):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, *SCOUT_HAIKU_ARGS, "--trials", trials)

        self._assert_refused(
            world, stub, capsys, excinfo.value.code, "a whole number of 1 or more"
        )

    def test_rubric_grader_is_refused_as_not_implemented(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, *SCOUT_HAIKU_ARGS, "--grader", "rubric")

        self._assert_refused(
            world, stub, capsys, code, "not implemented yet; rubric grading is planned"
        )

    def test_unknown_grader_is_refused_listing_the_valid_ones(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, *SCOUT_HAIKU_ARGS, "--grader", "vibes")

        self._assert_refused(
            world, stub, capsys, excinfo.value.code, "expected-findings"
        )

    def test_the_default_grader_is_accepted(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *SCOUT_HAIKU_ARGS,
            "--grader",
            "expected-findings",
            "--trials",
            "1",
        )

        assert code == 0

    @pytest.mark.parametrize(
        "overrides",
        [
            [],
            ["--model", "sonnet", "--effort", "high"],
            ["--model", "sonnet"],
            ["--effort", "high"],
        ],
        ids=["no-overrides", "both-equal", "model-only-equal", "effort-only-equal"],
    )
    def test_candidate_equal_to_frontmatter_names_the_fix(
        self, world, capsys, overrides
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", *overrides)

        self._assert_refused(
            world, stub, capsys, code, "pass a different --model or --effort"
        )

    @pytest.mark.parametrize(
        ("model", "effort", "named_key", "bad_value"),
        [
            ("../evil", "high", "model", "../evil"),
            ("sonnet", "hgih", "effort", "hgih"),
        ],
        ids=["model", "effort"],
    )
    def test_malformed_frontmatter_value_is_refused_naming_the_key_and_value(
        self, world, capsys, model, effort, named_key, bad_value
    ):
        _write_agent(
            world.deps.eval_paths.agents_dir, "odd", "Read", model=model, effort=effort
        )
        _write_expected(world.expected_dir, "odd-case", "odd", "pass")
        _make_file_fixture(world.deps.eval_paths.fixtures_dir, "odd-case.txt")
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "odd", "--model", "haiku", "--effort", "low")

        err = capsys.readouterr().err
        assert code == 2
        assert f"frontmatter `{named_key}:`" in err
        assert repr(bad_value) in err
        assert "Estimate" not in err
        assert_nothing_ran(stub, world)

    def test_a_partial_override_that_changes_one_value_is_accepted(self, world):
        stub = _passing_stub(world)

        code = _cli(world, stub, "scout", "--effort", "low", "--trials", "1")

        assert code == 0


class TestArtifactReservationAndWrite:
    def test_run_that_fails_before_any_trial_starts_leaves_no_placeholder(self, world):
        stdin = RaisingStdin(RuntimeError("stdin closed"))

        with pytest.raises(RuntimeError):
            _gated_cli(world, _passing_stub(world), stdin)

        assert world.artifacts == []

    def test_failed_final_write_prints_the_artifact_to_stdout_exits_1_and_leaves_no_files(
        self, world, capsys, monkeypatch
    ):
        stub = _passing_stub(world)
        _store_with_failing_replace(monkeypatch)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        captured = capsys.readouterr()
        printed = json.loads(captured.out)
        assert code == 1
        assert printed["run_id"] == RUN_ID and printed["status"] == "complete"
        assert "stdout" in captured.err
        assert world.artifacts == []

    def test_failed_final_write_keeps_a_placeholder_that_gained_content(
        self, world, monkeypatch
    ):
        stub = _passing_stub(world, touch=str(world.artifact_path))
        _store_with_failing_replace(monkeypatch)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        assert code == 1
        assert world.artifact_path.read_text(encoding="utf-8") == (
            "created during the run"
        )
        assert world.artifacts == [world.artifact_path]


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
