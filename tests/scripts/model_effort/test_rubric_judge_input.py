"""The rubric judge's input: the prompt goes on stdin, the answer is capped, and a
judge that ran but gave no usable verdict counts against the agent, not as infra.

Every `claude` process here is a fake; no test reaches a model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import pytest
from _model_effort_support import _result_event, _stream
from model_effort import process_record, rubric_file, rubric_judge, runner

OPUS_JUDGE = "claude-opus-5-5"
# Linux's limit on one argv string (MAX_ARG_STRLEN); a longer one fails with E2BIG.
LINUX_MAX_ARG_STRLEN = 128 * 1024
JUDGE_COST = 0.07


def _judge() -> rubric_file.Judge:
    return rubric_file.Judge(
        OPUS_JUDGE, "high", Path("r.md"), "# Rubric\n", ("commits",)
    )


class _Capture:
    """A judge process runner that records its input and replies with `stdout`."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.calls: list[dict] = []

    def __call__(self, argv, cwd, timeout, env, *, stdin_text=None):
        self.calls.append({"argv": list(argv), "stdin_text": stdin_text})
        return process_record.TrialProcessRecord(
            exit_code=0, stdout=self.stdout, stderr="", timed_out=False
        )


def _verdict_stdout(text: str) -> str:
    return _stream(_result_event(text, total_cost_usd=JUDGE_COST))


def _run(capture: _Capture, answer: str = "Use the queue.", material: str = ""):
    return rubric_judge.run_judge(
        _judge(),
        [],
        "task",
        answer,
        material=material,
        claude_bin="claude",
        timeout_seconds=5,
        parent_env={},
        run_process=capture,
    )


class TestPromptOnStdin:
    def test_run_cli_process_feeds_stdin_text_to_the_process(self, tmp_path):
        text = "é" * 200_000

        record = runner.run_cli_process(
            [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
            tmp_path,
            30,
            stdin_text=text,
        )

        assert record.exit_code == 0
        assert record.stdout == text

    def test_a_large_prompt_goes_on_stdin_and_no_argv_string_nears_the_linux_limit(
        self,
    ):
        capture = _Capture(_verdict_stdout(json.dumps({"criteria": []})))
        # Four UTF-8 bytes per character: the capped material alone is well over 128 KiB.
        material = "\U0001d11e" * rubric_judge.MATERIAL_MAX_CHARS

        _run(capture, answer="Use the queue.", material=material)

        argv, stdin_text = capture.calls[0]["argv"], capture.calls[0]["stdin_text"]
        assert "-p" in argv
        assert max(len(arg.encode("utf-8")) for arg in argv) < LINUX_MAX_ARG_STRLEN
        assert "Use the queue." in stdin_text and material[:100] in stdin_text
        assert not any("Use the queue." in arg for arg in argv)


class TestAnswerCap:
    def test_the_prompt_caps_the_answer_with_a_truncation_note(self):
        answer = "x" * (rubric_judge.ANSWER_MAX_CHARS + 50)

        prompt = rubric_judge.build_judge_prompt(_judge(), [], "t", answer)

        assert rubric_judge.ANSWER_TRUNCATED_NOTE in prompt
        assert "x" * (rubric_judge.ANSWER_MAX_CHARS + 1) not in prompt

    def test_an_over_cap_answer_fails_without_a_judge_call(self):
        capture = _Capture(_verdict_stdout(json.dumps({"criteria": []})))

        judgement = _run(capture, answer="x" * (rubric_judge.ANSWER_MAX_CHARS + 1))

        assert capture.calls == []
        assert judgement.failure is not None and "limit" in judgement.failure
        assert judgement.cost_usd is None


class TestUnusableVerdict:
    @pytest.mark.parametrize(
        "text",
        ["no json here", '{"criteria": "all met"}'],
        ids=["no-json", "not-a-list"],
    )
    def test_a_completed_judge_with_no_criteria_list_fails_the_answer_with_its_cost(
        self, text
    ):
        judgement = _run(_Capture(_verdict_stdout(text)))

        assert judgement.failure is not None and "criteria" in judgement.failure
        assert judgement.cost_usd == JUDGE_COST

    def test_a_usable_verdict_has_no_failure(self):
        criteria = [{"id": "commits", "met": True, "reason": "ok"}]

        judgement = _run(_Capture(_verdict_stdout(json.dumps({"criteria": criteria}))))

        assert judgement.failure is None
        assert judgement.criteria == criteria
