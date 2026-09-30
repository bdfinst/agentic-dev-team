"""The retained `between-steps` build-phase record (#2240, part of #2177).

`/build` rewrites build-phase.json at step completion instead of deleting it,
so a compaction between steps still restores the plan and next step. The
crashed-/build rule in `test_file_classify` and the three refactor guards must
be unaffected by the retained file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
sys.path.insert(0, str(_HOOKS))
sys.path.insert(0, str(_HOOKS / "lib"))

import post_compact_state_reinject as reinject
import refactor_test_bash_guard as bash_guard
import refactor_test_freeze_guard as freeze_guard
import refactor_test_revert_guard as revert_guard
from build_state import BETWEEN_STEPS, read_active_build_state
from test_file_classify import STALE_AFTER_SECONDS, read_build_phase

_WRITTEN_AT = "2026-07-04T10:00:00+00:00"
_EPOCH = 1783159200.0
_TEST_FILE = "src/thing.test.ts"


def _write(root: Path, phase: str, **over) -> None:
    record = {
        "phase": phase,
        "step": "2.4",
        "written_at": _WRITTEN_AT,
        "test_files_staged": [_TEST_FILE] if phase == "refactor" else [],
        "plan_path": "plans/foo.md",
    }
    record.update(over)
    path = root / ".claude" / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "foo.md").write_text(
        "# Plan\n\n## Build Progress\n\n- [x] 2.3\n- [ ] 2.4\n- [ ] 2.5\n",
        encoding="utf-8",
    )
    return tmp_path


# --- classifier / crashed-/build rule -----------------------------------------


def test_classifier_reads_a_fresh_between_steps_record(proj):
    _write(proj, BETWEEN_STEPS)
    state, error = read_build_phase(proj, now=_EPOCH + 60)
    assert error is None and state["phase"] == BETWEEN_STEPS


def test_an_old_between_steps_record_is_ignored_by_the_staleness_rule(proj):
    _write(proj, BETWEEN_STEPS)
    state, error = read_build_phase(proj, now=_EPOCH + STALE_AFTER_SECONDS + 1)
    assert (state, error) == (None, None)
    assert read_active_build_state(proj, now=_EPOCH + STALE_AFTER_SECONDS + 1) is None


# --- the three refactor guards stay inert between steps ----------------------


def test_freeze_guard_blocks_refactor_but_not_between_steps(proj):
    _write(proj, "refactor")
    assert freeze_guard.evaluate(_TEST_FILE, proj, now=_EPOCH + 60)[0] == 2
    _write(proj, BETWEEN_STEPS)
    assert freeze_guard.evaluate(_TEST_FILE, proj, now=_EPOCH + 60) == (0, [])


def test_bash_guard_blocks_refactor_but_not_between_steps(proj):
    command = f"echo x > {_TEST_FILE}"
    _write(proj, "refactor")
    assert bash_guard.evaluate(command, proj, now=_EPOCH + 60)[0] == 2
    _write(proj, BETWEEN_STEPS)
    assert bash_guard.evaluate(command, proj, now=_EPOCH + 60) == (0, [], None)


def test_revert_guard_is_inert_between_steps(proj):
    _write(proj, BETWEEN_STEPS)
    assert revert_guard.evaluate(proj, now=_EPOCH + 60) == (0, [])


# --- restore ----------------------------------------------------------------


def _fresh(proj, phase, **over):
    _write(proj, phase, written_at=datetime.now(timezone.utc).isoformat(), **over)


def test_reader_restores_plan_path_and_next_step(proj):
    _fresh(proj, BETWEEN_STEPS)
    state = read_active_build_state(proj)
    assert (state.phase, state.step, state.plan_path) == (
        BETWEEN_STEPS,
        "2.4",
        "plans/foo.md",
    )


def test_hook_restored_line_names_the_next_step_and_unchecked_items(proj):
    _fresh(proj, BETWEEN_STEPS)
    out = json.loads(reinject.build_output({"source": "compact", "cwd": str(proj)}))
    text = out["hookSpecificOutput"]["additionalContext"]
    assert text.startswith(
        "Restored after compaction: between steps, next step=2.4 plan=plans/foo.md"
    )
    assert "2.4, 2.5" in text and "2.3" not in text
    assert (
        out["systemMessage"]
        == "dev-team: restored build state (step 2.4) after compaction"
    )


def test_between_steps_hook_end_to_end_subprocess(proj):
    _fresh(proj, BETWEEN_STEPS)
    result = subprocess.run(
        [sys.executable, str(_HOOKS / "post_compact_state_reinject.py")],
        input=json.dumps({"source": "compact", "cwd": str(proj)}),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(proj)},
    )
    assert result.returncode == 0
    assert "between steps, next step=2.4" in result.stdout


def test_no_plan_file_is_ever_globbed(proj):
    _fresh(proj, BETWEEN_STEPS, plan_path=None)
    (proj / "plans" / "other.md").write_text(
        "## Build Progress\n- [ ] 9.9\n", encoding="utf-8"
    )
    text = json.loads(reinject.build_output({"source": "compact", "cwd": str(proj)}))[
        "hookSpecificOutput"
    ]["additionalContext"]
    assert (
        "9.9" not in text
        and text == "Restored after compaction: between steps, next step=2.4"
    )
