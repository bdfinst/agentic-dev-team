"""#224 — the /build skill + orchestrator + CLAUDE.md must document
wave-aware concurrent build: worktree fan-out, the configurable bound,
sequential fallback, the barrier+reconcile, the loud halt, and the cost
caveat. Documentation gate.

Ported from tests/commands/build_parallel_doc_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"
ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"
CLAUDEMD = REPO_ROOT / "plugins" / "dev-team" / "CLAUDE.md"


@pytest.fixture(scope="module")
def build_text() -> str:
    return BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def orch_text() -> str:
    return ORCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def claude_md_text() -> str:
    return CLAUDEMD.read_text(encoding="utf-8")


def test_build_skill_no_longer_says_slice_by_slice_in_order(build_text: str) -> None:
    assert "slice by slice, in order" not in build_text


def test_build_skill_drives_wave_schedule_and_jobs_scripts(build_text: str) -> None:
    assert "build_wave.py" in build_text
    assert "build_jobs.py" in build_text
    assert "build_wave_reconcile.py" in build_text


def test_build_skill_documents_configurable_bound_and_sequential_fallback(
    build_text: str,
) -> None:
    assert "DEV_TEAM_MAX_PARALLEL_BUILDS" in build_text
    assert "sequential fallback" in build_text.lower()


def test_build_skill_documents_barrier_reconcile_and_loud_halt(
    build_text: str,
) -> None:
    assert "reconcile" in build_text.lower()
    assert "no next-wave slice" in build_text.lower()


def test_build_skill_surfaces_concurrency_and_cost_caveat(build_text: str) -> None:
    assert "budget faster" in build_text.lower()


def test_build_skill_keeps_per_slice_worktree_isolation(build_text: str) -> None:
    assert 'isolation: "worktree"' in build_text


def test_orchestrator_documents_wave_dispatch_worktree_reconcile(
    orch_text: str,
) -> None:
    assert "wave-aware build dispatch" in orch_text.lower()
    assert "build_wave_reconcile.py" in orch_text


def test_claude_md_documents_max_parallel_builds_env_var(
    claude_md_text: str,
) -> None:
    assert "DEV_TEAM_MAX_PARALLEL_BUILDS" in claude_md_text
