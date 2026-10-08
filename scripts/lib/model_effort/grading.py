"""Grade one trial's parsed agent output against its `evals/expected` entry.

Delegates to the repo's deterministic grader (`scripts/eval_grade.py`) so the
harness and the CI agent-eval gate apply identical rules.

Requires `scripts/` on sys.path (for `eval_grade`); the CLI and the tests set it up.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from eval_grade import run_grading

from .paths import EXPECTED_DIR

TEMP_DIR_PREFIX = "model-effort-grade-"
# What the grader raises on agent JSON of an unexpected shape. Any other error is a
# harness fault and propagates, so it is not recorded as the agent's answer failing.
AGENT_ANSWER_ERRORS = (TypeError, KeyError, AttributeError, ValueError)


def grade_trial(
    agent: str,
    stem: str,
    parsed: dict,
    expected_dir: Path = EXPECTED_DIR,
) -> tuple[bool, list[str]]:
    """Grade `parsed` for `agent` on fixture `stem`; return (passed, failure messages).

    Only the one expected file is copied into the grading dir, so the grader
    never sees other fixtures' entries. Agent JSON the grader cannot handle fails
    the trial; an error from staging or any other part of grading propagates.
    """
    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as grading_dir:
        shutil.copy2(expected_dir / f"{stem}.json", grading_dir)
        try:
            results, _ = run_grading(
                expected_dir=Path(grading_dir),
                actuals={stem: {"agents": {agent: parsed}}},
                baseline=None,
                only={agent},
            )
        except AGENT_ANSWER_ERRORS as error:
            return False, [f"grader raised {type(error).__name__}: {error}"]
    if not results:
        return False, [f"expected entry for {agent!r} not found in {stem}.json"]
    messages = [message for _, _, fails in results for message in fails]
    return all(passed for _, passed, _ in results), messages
