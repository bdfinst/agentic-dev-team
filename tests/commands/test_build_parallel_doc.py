"""#224 — the /build skill + orchestrator + CLAUDE.md must document
wave-aware concurrent build: worktree fan-out, the configurable bound,
sequential fallback, the barrier+reconcile, the loud halt, and the cost
caveat. Documentation gate.

Ported from tests/commands/build_parallel_doc_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Any bare-integer default phrasing tied to a concurrency cap, e.g.
# "default 3", "default max **2**", "defaults to 2", "default of **2**".
# Broader than three frozen literals so an equivalently-worded revert is
# still caught (#1170).
_FIXED_DEFAULT_RE = re.compile(r"default(s)?\s+(max\s+|of\s+|to\s+)?\*{0,2}\d")

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"
ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"
CLAUDEMD = REPO_ROOT / "plugins" / "dev-team" / "CLAUDE.md"
REQFLOW = (
    REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "request-processing-flow.md"
)


@pytest.fixture(scope="module")
def build_text() -> str:
    return BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def orch_text() -> str:
    return ORCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def claude_md_text() -> str:
    return CLAUDEMD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def req_flow_text() -> str:
    return REQFLOW.read_text(encoding="utf-8")


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


def test_docs_document_cores_derived_default(
    build_text: str, claude_md_text: str, req_flow_text: str
) -> None:
    """#1170 — the default is now the per-host ceiling min(16, cores-2), not a
    fixed number. Each doc must describe the cores-derived default. Pin the
    full token including the operator (ASCII hyphen, matching the code) so a
    later dash normalization or truncation can't slip past the gate."""
    assert "min(16, cores-2)" in build_text
    assert "min(16, cores-2)" in claude_md_text
    assert "min(16, cores-2)" in req_flow_text


def test_docs_no_longer_state_a_fixed_default(
    build_text: str, claude_md_text: str, req_flow_text: str
) -> None:
    """#1170 negative gate — no doc may reintroduce a fixed integer default for
    DEV_TEAM_MAX_PARALLEL_BUILDS. Uses a pattern (not three frozen literals) so
    an equivalently-worded revert ("defaults to 2", "default of 3") is caught
    too, not only a byte-for-byte revert of the pre-change text."""
    for name, text in (
        ("build/SKILL.md", build_text),
        ("CLAUDE.md", claude_md_text),
        ("request-processing-flow.md", req_flow_text),
    ):
        assert not _FIXED_DEFAULT_RE.search(text), (
            f"{name} states a fixed integer default for the build concurrency "
            f"cap; #1170 requires the cores-derived default only"
        )
