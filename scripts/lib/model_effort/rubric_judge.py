"""Ask the pinned rubric judge whether one trial's answer meets each criterion.

The judge is a `claude -p` call with no tools: it sees the agent-level rubric,
the fixture's rubric points, the task the agent was given and the agent's final
answer, never the fixture or the expected entry. It returns one met/not-met
verdict per criterion; whether the trial passes is decided afterwards by the
deterministic `rubric` grader in `scripts/eval_graders/`, not by the judge.

A judge that cannot be run or whose answer has no verdict JSON raises
`JudgeError`, which the outcome records as a judge failure, never as the agent's
answer failing.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .grader_config import Judge
from .outcome import GraderUnavailableError
from .process_record import TrialProcessRecord
from .transcript import extract_agent_json, parse_stream

JUDGE_TEMP_DIR_PREFIX = "model-effort-judge-"
JUDGE_SYSTEM_PROMPT = (
    "You are a strict grader. You judge one answer against a list of criteria. "
    "Mark a criterion met only when the answer clearly satisfies it; when in doubt, "
    "mark it not met. Judge only the answer text you are given. Respond with only "
    'this JSON object: {"criteria": [{"id": "<criterion id>", "met": true|false, '
    '"reason": "<one sentence>"}]}, with one entry for every criterion id listed.'
)

# Runs one CLI process: (argv, cwd, timeout seconds, env) -> record.
ProcessRunner = Callable[
    [Sequence[str], Path, float, Mapping[str, str] | None], TrialProcessRecord
]


class JudgeError(GraderUnavailableError):
    """The judge could not be run or gave no usable verdict."""


@dataclass(frozen=True)
class Judgement:
    criteria: list[dict]
    cost_usd: float | None


def build_judge_prompt(
    judge: Judge, rubric_points: Sequence[dict], task: str, answer: str
) -> str:
    """The judge's user prompt: the criteria to mark, the task and the answer."""
    points = "\n".join(
        f"- **{point['id']}**: {point['requirement']}" for point in rubric_points
    )
    return (
        "## Rubric\n\n"
        f"{judge.rubric_text.strip()}\n\n"
        "## Task-specific criteria\n\n"
        f"{points or '(none)'}\n\n"
        "## Task the agent was given\n\n"
        f"{task.strip()}\n\n"
        "## The agent's answer\n\n"
        f"<answer>\n{answer.strip()}\n</answer>\n\n"
        "Mark every criterion id from the Rubric's Criteria list and from the "
        "task-specific criteria."
    )


def build_judge_argv(judge: Judge, claude_bin: str, prompt: str) -> list[str]:
    """The judge's CLI argv: pinned model and effort, no tools, no project config."""
    return [
        claude_bin,
        "-p",
        prompt,
        "--model",
        judge.model,
        "--effort",
        judge.effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--tools",
        "",
        "--restricted",
        "--system-prompt",
        JUDGE_SYSTEM_PROMPT,
    ]


def run_judge(
    judge: Judge,
    rubric_points: Sequence[dict],
    task: str,
    answer: str,
    *,
    claude_bin: str,
    timeout_seconds: float,
    env: Mapping[str, str] | None,
    run_process: ProcessRunner,
) -> Judgement:
    """Run the judge once in an empty temp dir and return its per-criterion verdicts.

    Raises:
        JudgeError: the process failed or timed out, or its answer has no
            `criteria` list.
    """
    argv = build_judge_argv(
        judge, claude_bin, build_judge_prompt(judge, rubric_points, task, answer)
    )
    with tempfile.TemporaryDirectory(prefix=JUDGE_TEMP_DIR_PREFIX) as cwd:
        record = run_process(argv, Path(cwd), timeout_seconds, env)
    parsed = parse_stream(record.stdout)
    if record.timed_out:
        raise JudgeError("rubric judge exceeded the time limit")
    if record.exit_code != 0 or parsed.is_error or not parsed.has_result:
        detail = record.stderr.strip() or parsed.result_text or "no result event"
        raise JudgeError(f"rubric judge failed (exit {record.exit_code}): {detail}")
    verdict = extract_agent_json(parsed.result_text)
    criteria = verdict.get("criteria") if verdict is not None else None
    if not isinstance(criteria, list):
        raise JudgeError("rubric judge answer has no `criteria` list")
    return Judgement(criteria=criteria, cost_usd=parsed.cost_usd)


def judgement_actual(judge: Judge, judgement: Judgement) -> dict:
    """The recorded output the `rubric` grader reads."""
    return {
        "criterionIds": list(judge.criterion_ids),
        "judgement": {"criteria": judgement.criteria},
    }

