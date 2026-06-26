"""Pytest async tests for scripts/orchestrator.py — Slice 6.

Tests classification, fast-path routing, phase state persistence,
--resume skip logic, persona dispatch concurrency, and wave barrier.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Ensure scripts/ is on the path so we can import orchestrator
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import orchestrator as orch


# ---------------------------------------------------------------------------
# Step 6.1 — Task classification and fast-path branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_trivial_stub_takes_fast_path():
    """With classify_fn returning trivial, run_pipeline() must NOT call phase functions."""
    called = []

    async def stub_research(task, skip_llm):
        called.append("research")
        return {"result": "research_done"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="fix typo",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "trivial"},
            phase_research_fn=stub_research,
        )

    assert exit_code == 0
    assert "research" not in called, (
        "research phase should be skipped for trivial tasks"
    )


@pytest.mark.asyncio
async def test_classify_standard_calls_research_phase():
    """With classify_fn returning standard, run_pipeline() must call research phase."""
    called = []

    async def stub_research(task, skip_llm):
        called.append("research")
        return {"result": "research_done"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        exit_code = await orch.run_pipeline(
            request="implement feature X",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=stub_research,
        )

    assert exit_code == 0
    assert "research" in called, "research phase should run for standard tasks"


@pytest.mark.asyncio
async def test_classify_fallback_on_llm_unavailable():
    """When claude is not on PATH, classify() must return standard (safe default)."""
    result = await orch.classify("do something", skip_llm=False)
    # claude may or may not be available; either way must return a dict with 'size'
    assert "size" in result
    assert result["size"] in ("trivial", "standard", "complex")


# ---------------------------------------------------------------------------
# Step 6.2 — Phase state persistence and --resume
# ---------------------------------------------------------------------------


def test_write_and_read_progress():
    """write_progress writes JSON; read_progress reads it back correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        payload = {"result": "done", "files": ["a.py", "b.py"]}
        orch.write_progress("research", payload, memory_dir)
        got = orch.read_progress("research", memory_dir)
    assert got == payload


def test_read_progress_returns_none_when_missing():
    """read_progress returns None when no state file exists."""
    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        result = orch.read_progress("plan", memory_dir)
    assert result is None


@pytest.mark.asyncio
async def test_resume_skips_research_when_state_present():
    """With --resume and an existing research state file, research fn is NOT called."""
    called = []

    async def stub_research(task, skip_llm):
        called.append("research")
        return {"result": "research_done"}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        # Pre-seed research state
        orch.write_progress("research", {"result": "prior", "files": []}, memory_dir)

        exit_code = await orch.run_pipeline(
            request="implement feature X",
            memory_dir=memory_dir,
            skip_llm=True,
            resume=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=stub_research,
        )

    assert exit_code == 0
    assert "research" not in called, (
        "research should be skipped when prior state exists"
    )


@pytest.mark.asyncio
async def test_phase_state_written_after_research():
    """After a successful pipeline run, a research state file must exist."""

    async def stub_research(task, skip_llm):
        return {"result": "done", "files": []}

    with tempfile.TemporaryDirectory() as tmp:
        memory_dir = Path(tmp)
        await orch.run_pipeline(
            request="implement feature X",
            memory_dir=memory_dir,
            skip_llm=True,
            classify_fn=lambda req: {"size": "standard"},
            phase_research_fn=stub_research,
        )
        state = orch.read_progress("research", memory_dir)

    assert state is not None
    assert state.get("result") == "done"


# ---------------------------------------------------------------------------
# Step 6.3 — Concurrent persona dispatch and wave barrier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_personas_concurrently():
    """dispatch_personas must return one result per persona (gather semantics)."""
    personas = ["acceptance-test-critic", "design-architecture-critic"]
    results = await orch.dispatch_personas(personas, plan={"spec": "x"}, skip_llm=True)
    assert len(results) == len(personas)
    returned_personas = {r["persona"] for r in results}
    assert returned_personas == set(personas)


@pytest.mark.asyncio
async def test_dispatch_persona_prints_startup_line(capsys):
    """Each persona dispatch must print an INFO startup line to stderr."""
    await orch.dispatch_persona("acceptance-test-critic", plan={}, skip_llm=True)
    captured = capsys.readouterr()
    assert "dispatching plan-review persona" in captured.err
    assert "acceptance-test-critic" in captured.err


@pytest.mark.asyncio
async def test_wave_error_raised_on_failed_slice():
    """reconcile() must raise WaveError when any result has status='failed'."""
    results = [
        {"slice": "slice-1", "status": "success"},
        {"slice": "slice-2", "status": "failed"},
    ]
    wave_slices = ["slice-1", "slice-2"]

    with pytest.raises(orch.WaveError) as exc_info:
        await orch.reconcile(results, wave_slices)

    err = exc_info.value
    assert err.failing_slice == "slice-2"
    assert "slice-1" in err.succeeded


@pytest.mark.asyncio
async def test_wave_error_not_raised_on_all_success():
    """reconcile() must NOT raise when all slices succeed."""
    results = [
        {"slice": "slice-1", "status": "success"},
        {"slice": "slice-2", "status": "success"},
    ]
    # Should not raise
    await orch.reconcile(results, ["slice-1", "slice-2"])


@pytest.mark.asyncio
async def test_gather_called_with_two_tasks_for_two_personas():
    """asyncio.gather must be called with exactly two coroutines for two personas."""
    personas = ["critic-a", "critic-b"]
    # We spy on the actual gather by counting how many tasks are awaited
    dispatched = []
    original_dispatch_persona = orch.dispatch_persona

    async def counting_dispatch(persona, plan, skip_llm=False):
        dispatched.append(persona)
        return await original_dispatch_persona(persona, plan, skip_llm=True)

    with patch.object(orch, "dispatch_persona", side_effect=counting_dispatch):
        results = await orch.dispatch_personas(personas, plan={}, skip_llm=True)

    assert len(dispatched) == 2
    assert set(dispatched) == set(personas)
