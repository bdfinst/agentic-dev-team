"""Grade one trial's parsed agent output against its `evals/expected` entry.

Delegates to the repo's deterministic grader (`scripts/eval_grade.py`) so the
harness and the CI agent-eval gate apply identical rules.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from eval_grade import run_grading

REPO_ROOT = _SCRIPTS_DIR.parent
EXPECTED_DIR = REPO_ROOT / "evals" / "expected"
EXPECTED_STATUS_CLEAN = "pass"
TEMP_DIR_PREFIX = "model-effort-grade-"


def grade_trial(
    agent: str,
    stem: str,
    parsed: dict,
    expected_dir: Path = EXPECTED_DIR,
) -> tuple[bool, list[str]]:
    """Grade `parsed` for `agent` on fixture `stem`; return (passed, failure messages).

    Only the one expected file is copied into the grading dir, so the grader
    never sees other fixtures' entries.
    """
    with tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX) as grading_dir:
        shutil.copy2(expected_dir / f"{stem}.json", grading_dir)
        results, _ = run_grading(
            Path(grading_dir), {stem: {"agents": {agent: parsed}}}, None, {agent}
        )
    if not results:
        return False, [f"expected entry for {agent!r} not found in {stem}.json"]
    messages = [message for _, _, fails in results for message in fails]
    return all(passed for _, passed, _ in results), messages


def is_expected_clean(expected_entry: dict, agent: str) -> bool:
    """True when the expected entry says `agent` should report no problems."""
    agent_spec = expected_entry.get("agents", {}).get(agent, {})
    return agent_spec.get("expectedStatus") == EXPECTED_STATUS_CLEAN
