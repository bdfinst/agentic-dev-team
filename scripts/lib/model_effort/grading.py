"""Grade one trial's recorded output against its `evals/expected` entry.

Delegates to the repo's deterministic grader (`scripts/eval_grade.py`) so the
harness and the CI agent-eval gate apply identical rules.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from . import external
from .errors import UsageError
from .paths import EvalPaths

TEMP_DIR_PREFIX = "model-effort-grade-"
# What the grader raises on agent JSON of an unexpected shape. Any other error is a
# harness fault and propagates, so it is not recorded as the agent's answer failing.
AGENT_ANSWER_ERRORS = (TypeError, KeyError, AttributeError, ValueError)
# Well-formed answers, one empty and one with a value in every field a registered
# grader reads. The grader handles either without raising against a sound
# expected entry, so a raise on one of them is a fault in the entry.
PROBE_ANSWERS: tuple[dict, ...] = (
    {},
    {
        "status": "warn",
        "issues": [
            {
                "severity": "suggestion",
                "confidence": "high",
                "category": "probe",
                "message": "probe",
            }
        ],
        "summary": "probe",
        "dispatched": ["probe"],
        "output": {"status": "pass"},
        "results": [{"command": "probe", "exit_code": 0, "stderr_first_line": ""}],
        "criterionIds": ["probe"],
        "judgement": {"criteria": [{"id": "probe", "met": True, "reason": ""}]},
    },
)


class MalformedExpectedEntryError(RuntimeError):
    """The grader cannot grade even a well-formed answer against the expected entry."""


def check_expected_entries(agent: str, stems: Iterable[str], expected_dir: Path) -> None:
    """Refuse an expected entry for `agent` that the grader raises on, before any trial is paid for.

    Raises:
        UsageError: grading a well-formed answer against an entry raises.
    """
    for stem in stems:
        fault = _entry_fault(agent, stem, expected_dir)
        if fault is not None:
            raise UsageError(
                f"evals/expected/{stem}.json: the {agent!r} entry cannot be graded "
                f"({fault}): fix the entry, then run "
                "`python3 scripts/eval_grade.py --check-corpus`"
            )


def grade_trial(
    agent: str,
    stem: str,
    actual: dict,
    eval_paths: EvalPaths,
) -> tuple[bool, list[str]]:
    """Grade the recorded output `actual` for `agent` on fixture `stem`; return (passed, failure messages).

    Only the one expected file is copied into the grading dir, so the grader
    never sees other fixtures' entries. Agent JSON the grader cannot handle fails
    the trial; an error from staging or any other part of grading propagates.

    Raises:
        MalformedExpectedEntryError: the grader raised, and raises on a well-formed
            answer too, so the expected entry is at fault, not the agent.
    """
    with _staged_entry(eval_paths.expected_dir, stem) as grading_dir:
        try:
            results = external.grade_against_expected(grading_dir, stem, agent, actual)
        except AGENT_ANSWER_ERRORS as error:
            answer_error = error
        else:
            answer_error = None
    if answer_error is not None:
        fault = _entry_fault(agent, stem, eval_paths.expected_dir)
        if fault is not None:
            raise MalformedExpectedEntryError(
                f"{stem}.json: the {agent!r} entry cannot be graded ({fault})"
            ) from answer_error
        return False, [f"grader raised {type(answer_error).__name__}: {answer_error}"]
    if not results:
        return False, [f"expected entry for {agent!r} not found in {stem}.json"]
    messages = [message for _, _, fails in results for message in fails]
    return all(passed for _, passed, _ in results), messages


def _entry_fault(agent: str, stem: str, expected_dir: Path) -> str | None:
    """What the grader raised on a well-formed answer, or None when it raised on none."""
    for probe in PROBE_ANSWERS:
        try:
            with _staged_entry(expected_dir, stem) as grading_dir:
                external.grade_against_expected(grading_dir, stem, agent, probe)
        except AGENT_ANSWER_ERRORS as error:
            return f"grader raised {type(error).__name__}: {error}"
    return None


@contextmanager
def _staged_entry(expected_dir: Path, stem: str) -> Iterator[Path]:
    """A temp grading dir holding only `stem`'s expected file."""
    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as grading_dir:
        shutil.copy2(expected_dir / f"{stem}.json", grading_dir)
        yield Path(grading_dir)
