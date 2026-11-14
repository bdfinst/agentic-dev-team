"""The harness's per-agent graders: the grader map, sandboxed write-capable trials,
dispatch-set grading, tests-pass grading and the pinned rubric judge.

Every `claude` process here is the stub CLI; no test reaches a model.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import model_effort_ab
import pytest
from _model_effort_support import (
    NOW,
    SONNET_MODEL_ID,
    TEST_PRICING,
    FixedRng,
    StubClaude,
    _eval_paths,
    _flag_value,
    _init_event,
    _result_event,
    _stream,
    _write_agent,
)
from model_effort import (
    fixtures,
    grader_config,
    invocation,
    outcome,
    process_record,
    rubric_judge,
    runner,
    tools,
    transcript,
    trial_count,
)
from model_effort.errors import UsageError
from model_effort.outcome import Outcome

OPUS_JUDGE = "claude-opus-5-5"
RUBRIC_TEXT = """# Rubric: thinker

A good answer decides.

## Criteria

- **commits**: Makes one recommendation.
- **grounded**: Cites the provided material.
"""
JUDGE_COST = 0.02
PRICING = {
    "models": {**TEST_PRICING["models"], "test-judge": {"input": 5.0, "output": 25.0}},
    "aliases": {**TEST_PRICING["aliases"], "opus": "test-judge", OPUS_JUDGE: "test-judge"},
}


@dataclasses.dataclass
class GraderWorld:
    root: Path
    deps: model_effort_ab.Deps

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def written(self) -> dict:
        (artifact,) = sorted(self.runs_dir.iterdir())
        return json.loads(artifact.read_text(encoding="utf-8"))


def _write_entry(expected: Path, stem: str, agent: str, block: dict) -> None:
    entry = {"fixture": stem, "applicableAgents": [agent], "agents": {agent: block}}
    (expected / f"{stem}.json").write_text(json.dumps(entry), encoding="utf-8")


@pytest.fixture
def gworld(tmp_path: Path) -> GraderWorld:
    agents, expected, fixtures, runs = (
        tmp_path / name for name in ("agents", "expected", "fixtures", "runs")
    )
    for directory in (agents, expected, fixtures, runs):
        directory.mkdir()
    _write_agent(agents, "thinker", "Read, Grep", model="sonnet", effort="high")
    _write_agent(agents, "builder", "Read, Edit, Bash", model="sonnet", effort="high")
    _write_agent(agents, "router", "Read, Agent, Skill", model="sonnet", effort="high")
    _write_agent(agents, "unmapped-writer", "Read, Write", model="sonnet", effort="high")
    graders = tmp_path / "graders"
    (graders / "rubrics").mkdir(parents=True)
    (graders / "rubrics" / "thinker.md").write_text(RUBRIC_TEXT, encoding="utf-8")
    (graders / "graders.json").write_text(
        json.dumps(
            {
                "agents": {
                    "thinker": {
                        "grader": "rubric",
                        "judge": {"model": OPUS_JUDGE, "effort": "high"},
                        "rubric": "rubrics/thinker.md",
                    },
                    "builder": {"grader": "tests-pass", "sandbox": True},
                    "router": {"grader": "dispatch-set"},
                }
            }
        ),
        encoding="utf-8",
    )
    _write_entry(
        expected,
        "design-q",
        "thinker",
        {
            "grader": "rubric",
            "task": "Decide using `{fixture}/brief.md`.",
            "rubricPoints": [{"id": "picks-queue", "requirement": "Picks the queue."}],
        },
    )
    (fixtures / "design-q").mkdir()
    (fixtures / "design-q" / "brief.md").write_text("brief", encoding="utf-8")
    _write_entry(
        expected,
        "tamper-proof",
        "builder",
        {
            "grader": "tests_pass",
            "task": "Fix `{fixture}`.",
            "testCommands": ["{python} check.py"],
            "protectedPaths": ["check.py"],
        },
    )
    (fixtures / "tamper-proof").mkdir()
    (fixtures / "tamper-proof" / "value.txt").write_text("start", encoding="utf-8")
    (fixtures / "tamper-proof" / "check.py").write_text(
        "import pathlib, sys\n"
        "sys.exit(0 if 'TAMPERED' in pathlib.Path('value.txt').read_text() else 3)\n",
        encoding="utf-8",
    )
    _write_entry(
        expected,
        "route-me",
        "router",
        {
            "grader": "dispatch_set",
            "task": "Route `{fixture}/REQUEST.md`.",
            "dispatch": {"include": ["architect"], "exclude": ["security-review"]},
        },
    )
    (fixtures / "route-me").mkdir()
    (fixtures / "route-me" / "REQUEST.md").write_text("request", encoding="utf-8")
    knowledge = tmp_path / "plugin" / "knowledge"
    knowledge.mkdir(parents=True)
    deps = model_effort_ab.Deps(
        clock=lambda: NOW,
        rng=FixedRng(),
        read_git_sha=lambda: "abc123",
        eval_paths=_eval_paths(
            agents_dir=agents,
            expected_dir=expected,
            fixtures_dir=fixtures,
            plugin_root=knowledge.parent,
            knowledge_dir=knowledge,
            grader_map=graders / "graders.json",
        ),
        pricing_table=PRICING,
    )
    return GraderWorld(tmp_path, deps)


def _run(gworld: GraderWorld, stub: StubClaude, *args: str) -> int:
    return model_effort_ab.main(
        [
            *args,
            "--trials",
            "1",
            "--yes",
            "--claude-bin",
            str(stub.path),
            "--runs-dir",
            str(gworld.runs_dir),
        ],
        deps=gworld.deps,
    )


def _answer_call(text: str, *events: dict) -> dict:
    result = _result_event(text, model_usage={SONNET_MODEL_ID: {}})
    return {"stdout": _stream(_init_event(SONNET_MODEL_ID), *events, result)}


def _judge_call(criteria: list[dict]) -> dict:
    result = _result_event(
        json.dumps({"criteria": criteria}),
        model_usage={OPUS_JUDGE: {}},
        total_cost_usd=JUDGE_COST,
    )
    return {"stdout": _stream(result)}


def _met(*ids: str) -> list[dict]:
    return [{"id": criterion, "met": True, "reason": "ok"} for criterion in ids]


def _dispatch_event(*agent_types: str) -> dict:
    blocks = [
        {"type": "tool_use", "name": "Agent", "input": {"subagent_type": name}}
        for name in agent_types
    ]
    return {"type": "assistant", "message": {"content": blocks}}


def _trial_outcomes(written: dict) -> list[str]:
    return [
        trial["outcome"]
        for arm in written["arms"]
        for fixture in arm["fixtures"]
        for trial in fixture["trials"]
    ]


class TestGraderMap:
    def test_an_agent_the_map_does_not_list_uses_the_expected_findings_grader(
        self, gworld
    ):
        grading = grader_config.resolve_agent_grading(
            "scout", gworld.deps.eval_paths.grader_map
        )

        assert grading == grader_config.DEFAULT_GRADING

    def test_a_rubric_agent_loads_its_pinned_judge_and_rubric_criteria(self, gworld):
        grading = grader_config.resolve_agent_grading(
            "thinker", gworld.deps.eval_paths.grader_map
        )

        assert grading.kind is grader_config.GraderKind.RUBRIC
        assert (grading.judge.model, grading.judge.effort) == (OPUS_JUDGE, "high")
        assert grading.judge.criterion_ids == ("commits", "grounded")

    def test_an_unknown_grader_name_is_refused_listing_the_known_ones(self, tmp_path):
        path = tmp_path / "graders.json"
        path.write_text(json.dumps({"agents": {"x": {"grader": "vibes"}}}))

        with pytest.raises(UsageError, match="expected-findings, tests-pass"):
            grader_config.resolve_agent_grading("x", path)

    def test_a_rubric_agent_without_a_rubric_file_is_refused(self, tmp_path):
        path = tmp_path / "graders.json"
        path.write_text(
            json.dumps(
                {
                    "agents": {
                        "x": {
                            "grader": "rubric",
                            "judge": {"model": OPUS_JUDGE, "effort": "high"},
                            "rubric": "missing.md",
                        }
                    }
                }
            )
        )

        with pytest.raises(UsageError, match="cannot read the rubric"):
            grader_config.resolve_agent_grading("x", path)

    def test_a_rubric_with_no_criterion_lines_is_refused(self, tmp_path):
        (tmp_path / "r.md").write_text("# Rubric\n\nNo criteria here.\n")
        path = tmp_path / "graders.json"
        path.write_text(
            json.dumps(
                {
                    "agents": {
                        "x": {
                            "grader": "rubric",
                            "judge": {"model": OPUS_JUDGE, "effort": "high"},
                            "rubric": "r.md",
                        }
                    }
                }
            )
        )

        with pytest.raises(UsageError, match="lists no criteria"):
            grader_config.resolve_agent_grading("x", path)


class TestJudgeTier:
    @pytest.mark.parametrize(
        ("model", "tier"),
        [
            ("haiku", 0),
            ("claude-sonnet-5-5", 1),
            ("opus", 2),
            ("claude-opus-4-8", 2),
            ("fable", None),
        ],
    )
    def test_model_tier_places_aliases_and_full_ids_on_the_ladder(self, model, tier):
        assert grader_config.model_tier(model) == tier

    @pytest.mark.parametrize(
        ("arms", "required"),
        [(["haiku", "haiku"], 1), (["sonnet", "haiku"], 2), (["opus", "sonnet"], 2)],
    )
    def test_the_judge_must_sit_one_tier_above_the_strongest_arm_capped_at_opus(
        self, arms, required
    ):
        assert grader_config.required_judge_tier(arms) == required

    def test_a_judge_on_the_same_tier_as_an_arm_below_opus_is_refused(self):
        judge = grader_config.Judge("claude-sonnet-5-5", "high", Path("r.md"), "", ("a",))

        with pytest.raises(UsageError, match="must be at least opus"):
            grader_config.check_judge_tier(judge, ["haiku", "sonnet"])

    def test_an_opus_judge_may_judge_an_opus_agent(self):
        judge = grader_config.Judge(OPUS_JUDGE, "high", Path("r.md"), "", ("a",))

        grader_config.check_judge_tier(judge, ["opus", "sonnet"])

    def test_an_unplaceable_arm_model_is_refused(self):
        judge = grader_config.Judge(OPUS_JUDGE, "high", Path("r.md"), "", ("a",))

        with pytest.raises(UsageError, match="cannot place"):
            grader_config.check_judge_tier(judge, ["fable", "sonnet"])


class TestTrialCounts:
    def test_rubric_judged_agents_default_to_ten_trials(self):
        count = trial_count.resolve_trials(None, "thinker", rubric_judged=True)

        assert (count.count, count.reason) == (10, "rubric-judged default")

    def test_an_explicit_trial_flag_overrides_the_rubric_default(self):
        assert trial_count.resolve_trials(3, "thinker", rubric_judged=True).count == 3

    @pytest.mark.parametrize(
        ("grader", "trials", "allowed"),
        [
            ("rubric", 10, True),
            ("rubric", 9, False),
            ("expected-findings", 3, True),
            ("tests-pass", 1, True),
        ],
    )
    def test_rubric_evidence_can_move_a_tier_only_with_ten_trials_per_arm(
        self, grader, trials, allowed
    ):
        assert trial_count.can_justify_tier_change(grader, trials) is allowed


class TestToolProfiles:
    def test_a_sandboxed_agent_gets_its_write_tools_enabled(self):
        profile = tools.resolve_tool_profile(
            "builder", {"tools": "Read, Edit, Bash, Skill"}, sandbox=True
        )

        assert profile.enabled_tools == ("Read", "Edit", "Bash")
        assert profile.withheld_tools == ("Skill",)
        assert profile.refused_tools == ()

    def test_a_dispatch_graded_agent_gets_its_agent_tool_enabled(self):
        profile = tools.resolve_tool_profile(
            "router", {"tools": "Read, Agent, Skill"}, dispatch=True
        )

        assert profile.enabled_tools == ("Read", "Agent")

    def test_without_the_dispatch_grader_the_agent_tool_is_withheld(self):
        profile = tools.resolve_tool_profile("router", {"tools": "Read, Agent"})

        assert profile.withheld_tools == ("Agent",)


class TestInvocation:
    def test_a_fixture_task_replaces_the_review_prompt_naming_the_staged_fixture(self):
        prompt = invocation.build_user_prompt("design-q", "Decide using `{fixture}/b.md`.")

        assert prompt == "Decide using `design-q/b.md`."

    def test_without_a_task_the_review_prompt_is_used(self):
        assert invocation.build_user_prompt("x.py").startswith("Review `x.py`")


class TestTranscriptDispatches:
    def test_the_agent_type_of_every_dispatch_tool_call_is_recorded(self):
        parsed = transcript.parse_stream(
            _stream(
                _dispatch_event("dev-team:architect"),
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Task",
                                "input": {"subagent_type": "qa-engineer"},
                            },
                            {"type": "tool_use", "name": "Read", "input": {}},
                        ]
                    },
                },
                _result_event("done"),
            )
        )

        assert parsed.dispatched_agents == ("dev-team:architect", "qa-engineer")


class TestOutcomeWithoutAgentJson:
    def _record(self) -> process_record.TrialProcessRecord:
        return process_record.TrialProcessRecord(
            exit_code=0, stdout="", stderr="", timed_out=False
        )

    def test_prose_is_graded_when_the_grader_does_not_need_json(self):
        parsed = transcript.parse_stream(_stream(_result_event("Plain prose answer.")))

        result = outcome.resolve_outcome(
            self._record(),
            parsed,
            ("Read",),
            lambda agent_json: (agent_json == {}, []),
            requires_agent_json=False,
        )

        assert result.outcome is Outcome.PASS

    def test_a_grader_that_cannot_reach_a_verdict_is_a_judge_error(self):
        parsed = transcript.parse_stream(_stream(_result_event("{}")))

        def unavailable(_agent_json):
            raise rubric_judge.JudgeError("judge down")

        result = outcome.resolve_outcome(self._record(), parsed, ("Read",), unavailable)

        assert (result.outcome, result.error) == (Outcome.JUDGE_ERROR, "judge down")


class TestSandboxRunner:
    def test_the_sandbox_copy_becomes_a_git_repo_with_the_fixture_committed(
        self, tmp_path
    ):
        (tmp_path / "a.txt").write_text("a")

        runner.init_sandbox_repo(tmp_path)

        listed = subprocess.run(
            ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True, check=True
        )
        assert listed.stdout.split() == ["a.txt"]

    def test_protected_paths_are_restored_from_the_pristine_fixture(self, tmp_path):
        pristine, work = tmp_path / "pristine", tmp_path / "work"
        (pristine / "tests").mkdir(parents=True)
        (pristine / "tests" / "t.py").write_text("original")
        (work / "tests").mkdir(parents=True)
        (work / "tests" / "t.py").write_text("weakened")
        (work / "tests" / "extra.py").write_text("added by the agent")

        runner.restore_protected_paths(pristine, work, ("tests",))

        assert sorted(p.name for p in (work / "tests").iterdir()) == ["t.py"]
        assert (work / "tests" / "t.py").read_text() == "original"

    def test_a_check_command_runs_with_this_interpreter_and_reports_its_failure_line(
        self, tmp_path
    ):
        (tmp_path / "fail.py").write_text("import sys\nprint('3 failed')\nsys.exit(1)\n")

        result = runner.run_check_command("{python} fail.py", tmp_path, 30, None)

        assert result == {
            "command": "{python} fail.py",
            "exit_code": 1,
            "stderr_first_line": "3 failed",
        }


class TestRubricJudge:
    def _judge(self) -> grader_config.Judge:
        return grader_config.Judge(
            OPUS_JUDGE, "high", Path("r.md"), RUBRIC_TEXT, ("commits", "grounded")
        )

    def test_the_judge_runs_the_pinned_model_and_effort_with_no_tools(self):
        argv = rubric_judge.build_judge_argv(self._judge(), "claude", "prompt")

        assert _flag_value(argv, "--model") == OPUS_JUDGE
        assert _flag_value(argv, "--effort") == "high"
        assert _flag_value(argv, "--tools") == ""
        assert "--restricted" in argv

    def test_the_judge_prompt_carries_rubric_points_task_and_answer(self):
        prompt = rubric_judge.build_judge_prompt(
            self._judge(),
            [{"id": "picks-queue", "requirement": "Picks the queue."}],
            "Decide.",
            "Use the queue.",
        )

        assert "- **commits**" in prompt
        assert "- **picks-queue**: Picks the queue." in prompt
        assert "Decide." in prompt and "<answer>\nUse the queue.\n</answer>" in prompt

    def test_a_judge_answer_without_criteria_raises_judge_error(self):
        def run_process(argv, cwd, timeout, env):
            return process_record.TrialProcessRecord(
                exit_code=0, stdout=_stream(_result_event("no json")), stderr="", timed_out=False
            )

        with pytest.raises(rubric_judge.JudgeError, match="no `criteria` list"):
            rubric_judge.run_judge(
                self._judge(),
                [],
                "task",
                "answer",
                claude_bin="claude",
                timeout_seconds=5,
                env=None,
                run_process=run_process,
            )


class TestRubricRun:
    def test_a_rubric_run_judges_each_trial_and_records_grader_judge_and_cost(
        self, gworld
    ):
        (gworld.root / "stub-dir").mkdir()
        stub = StubClaude(gworld.root / "stub-dir")
        everything = _met("commits", "grounded", "picks-queue")
        stub.queue(
            _answer_call("Use the queue."),
            _judge_call(everything),
            _answer_call("Maybe a queue, maybe not."),
            _judge_call([*_met("commits", "grounded"), {"id": "picks-queue", "met": False, "reason": "hedges"}]),
        )

        code = _run(gworld, stub, "thinker", "--model", "opus")

        written = gworld.written()
        assert code == 0
        assert written["grader"] == "rubric"
        assert written["judge"]["model"] == OPUS_JUDGE
        assert written["judge"]["criteria"] == ["commits", "grounded"]
        assert _trial_outcomes(written) == ["pass", "graded_fail"]
        candidate_trial = written["arms"][1]["fixtures"][0]["trials"][0]
        assert any("picks-queue" in m for m in candidate_trial["grader_messages"])
        assert candidate_trial["judge_cost_usd"] == JUDGE_COST
        judge_argv = stub.calls[1]["argv"]
        assert _flag_value(judge_argv, "--model") == OPUS_JUDGE
        assert "Use the queue." in _flag_value(judge_argv, "-p")

    def test_a_candidate_on_the_judges_tier_below_opus_is_refused_before_any_trial(
        self, gworld, tmp_path, capsys
    ):
        stub_dir = tmp_path / "s"
        stub_dir.mkdir()
        path = gworld.deps.eval_paths.grader_map
        data = json.loads(path.read_text())
        data["agents"]["thinker"]["judge"]["model"] = "claude-sonnet-5-5"
        path.write_text(json.dumps(data))
        stub = StubClaude(stub_dir)

        code = _run(gworld, stub, "thinker", "--effort", "low")

        assert code == 2
        assert "must be at least opus" in capsys.readouterr().err
        assert stub.calls == []

    def test_a_failed_judge_is_recorded_as_a_judge_error_not_a_graded_fail(
        self, gworld, tmp_path
    ):
        stub_dir = tmp_path / "s"
        stub_dir.mkdir()
        stub = StubClaude(stub_dir)
        stub.queue(
            _answer_call("Use the queue."),
            {"stdout": "", "stderr": "overloaded", "exit_code": 1},
            _answer_call("Use the queue."),
            {"stdout": "", "stderr": "overloaded", "exit_code": 1},
        )

        code = _run(gworld, stub, "thinker", "--model", "opus")

        written = gworld.written()
        trial = written["arms"][0]["fixtures"][0]["trials"][0]
        assert code == 1
        assert written["abort_reason"] == "infra-failure"
        assert trial["outcome"] == "judge_error"
        assert "overloaded" in trial["error"]


class TestTestsPassRun:
    def test_tests_run_after_the_agent_with_protected_files_restored(
        self, gworld, tmp_path
    ):
        stub_dir = tmp_path / "s"
        stub_dir.mkdir()
        # `tamper` rewrites every staged file, the checker included: the run passes
        # only if the checker is restored before the test command runs.
        stub = StubClaude(stub_dir, tamper=True, **_answer_call("Done."))

        code = _run(gworld, stub, "builder", "--model", "haiku")

        written = gworld.written()
        assert code == 0
        assert written["grader"] == "tests-pass"
        assert written["fidelity"] == "sandboxed-write-profile"
        assert _trial_outcomes(written) == ["pass", "pass"]
        assert written["arms"][0]["tools_enabled"] == ["Read", "Edit", "Bash"]

    def test_a_failing_test_command_grades_the_trial_failed_naming_its_exit_code(
        self, gworld, tmp_path
    ):
        stub_dir = tmp_path / "s"
        stub_dir.mkdir()
        stub = StubClaude(stub_dir, **_answer_call("Done."))

        _run(gworld, stub, "builder", "--model", "haiku")

        trial = gworld.written()["arms"][0]["fixtures"][0]["trials"][0]
        assert trial["outcome"] == "graded_fail"
        assert trial["grader_messages"] == [
            "tests_pass: command '{python} check.py' exited 3"
        ]

    def test_a_write_capable_agent_the_map_does_not_sandbox_is_refused(
        self, gworld, tmp_path, capsys
    ):
        stub_dir = tmp_path / "s"
        stub_dir.mkdir()
        stub = StubClaude(stub_dir)

        code = _run(gworld, stub, "unmapped-writer", "--model", "haiku")

        assert code == 2
        assert "sandbox: true" in capsys.readouterr().err


class TestDispatchSetRun:
    def test_dispatches_are_graded_from_the_transcript_and_stub_agents_are_supplied(
        self, gworld, tmp_path
    ):
        stub_dir = tmp_path / "s"
        stub_dir.mkdir()
        stub = StubClaude(stub_dir)
        stub.queue(
            _answer_call('{"status": "pass"}', _dispatch_event("dev-team:architect")),
            _answer_call('{"status": "pass"}', _dispatch_event("architect", "security-review")),
        )

        code = _run(gworld, stub, "router", "--model", "haiku")

        written = gworld.written()
        assert code == 0
        assert written["grader"] == "dispatch-set"
        assert _trial_outcomes(written) == ["pass", "graded_fail"]
        argv = stub.calls[0]["argv"]
        assert _flag_value(argv, "--tools") == "Read,Agent"
        stubs = json.loads(_flag_value(argv, "--agents"))
        assert set(stubs) == {"builder", "router", "thinker", "unmapped-writer"}
        assert _flag_value(argv, "-p") == "Route `route-me/REQUEST.md`."



class TestCleanFixtures:
    def test_an_entry_marked_clean_counts_as_a_clean_fixture(self):
        entry = {"agents": {"critic": {"expectedStatus": "approve", "clean": True}}}

        assert fixtures.is_expected_clean(entry, "critic") is True

    def test_an_approve_status_alone_is_not_a_clean_fixture(self):
        entry = {"agents": {"critic": {"expectedStatus": "approve"}}}

        assert fixtures.is_expected_clean(entry, "critic") is False
