"""Slice 6 — plugins/dev-team/scripts/orchestrator.py CLI integration tests.

Covers task classification, fast-path branch, --resume flag, phase state,
concurrent persona dispatch, and wave barrier — driven through the CLI
entry point (subprocess), not the internal functions. See
tests/scripts/test_orchestrator.py for unit-level async coverage of the
same behaviors.

Ported from tests/scripts/orchestrator_tests.bats (issue #676).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

ORCH = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "orchestrator.py"


def _run(
    memory_dir: Path, *args: str, stdin_text: str = "a task"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ORCH), *args, "--memory-dir", str(memory_dir)],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Step 6.1 — Task classification and fast-path branch
# ---------------------------------------------------------------------------


def test_6_1a_skip_llm_with_classify_trivial_exits_0_and_stderr_shows_fast_path(
    tmp_path: Path,
) -> None:
    result = _run(
        tmp_path,
        "--skip-llm",
        "--classify",
        "trivial",
        stdin_text="do something trivial",
    )
    assert result.returncode == 0
    assert "fast path" in result.stdout or "fast path" in result.stderr


def test_6_1b_resume_with_no_prior_state_exits_1_with_message(tmp_path: Path) -> None:
    result = _run(tmp_path, "--resume", "--skip-llm", stdin_text="some task")
    assert result.returncode == 1
    assert (
        "No prior phase state found" in result.stdout
        or "No prior phase state found" in result.stderr
    )


def test_6_1c_skip_llm_with_default_classify_standard_exits_0(tmp_path: Path) -> None:
    result = _run(tmp_path, "--skip-llm", stdin_text="a standard task")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Step 6.2 — Phase state machine and --resume flag
# ---------------------------------------------------------------------------


def test_6_2a_after_skip_llm_run_at_least_one_phase_state_file_exists(
    tmp_path: Path,
) -> None:
    _run(tmp_path, "--skip-llm", stdin_text="a task")
    state_files = list(tmp_path.glob("orchestrator-*.json"))
    assert len(state_files) > 0


def test_6_2b_resume_with_prior_research_state_skips_research_and_exits_0(
    tmp_path: Path,
) -> None:
    (tmp_path / "orchestrator-research.json").write_text(
        '{"result":"prior research","files":[]}'
    )
    result = _run(tmp_path, "--resume", "--skip-llm", stdin_text="a task")
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Step 6.3 — Concurrent persona dispatch and wave barrier
# ---------------------------------------------------------------------------


def test_6_3a_wave_barrier_failure_prints_resume_hint_to_stderr(tmp_path: Path) -> None:
    result = _run(tmp_path, "--skip-llm", "--fail-wave", stdin_text="a task")
    assert result.returncode == 1
    hint = f"Resume with: python3 {ORCH} --resume"
    assert hint in result.stdout or hint in result.stderr


def test_6_3b_skip_llm_dispatches_personas_and_prints_startup_line_per_persona(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, "--skip-llm", "--dispatch-personas", stdin_text="a task")
    assert result.returncode == 0
    marker = "dispatching persona"
    assert marker in result.stdout or marker in result.stderr
    assert "dispatching plan-review persona" not in result.stderr
