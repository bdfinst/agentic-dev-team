"""Fixtures shared by the model/effort A/B harness tests. Importing the support module first puts the harness on `sys.path`."""

from __future__ import annotations

import signal
import tempfile
from collections.abc import Iterator
from pathlib import Path

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import model_effort_ab
import pytest
from _model_effort_support import (
    GRADED_AGENT,
    GRADED_STEM,
    NOW,
    PINNED_OUTPUT_TOKENS,
    PINNED_TURN_MULTIPLIER,
    SCOUT_TOOLS,
    TERMINATION_SIGNALS,
    TEST_PRICING,
    WORLD_KNOWLEDGE_NOTE,
    FixedRng,
    World,
    _eval_paths,
    _make_file_fixture,
    _note_signal,
    _write_agent,
    _write_expected,
)
from model_effort import estimate, plan


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "agents"
    directory.mkdir()
    return directory


@pytest.fixture
def expected_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "expected"
    directory.mkdir()
    return directory


@pytest.fixture
def stub_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "stub"
    directory.mkdir()
    return directory


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    directory = tmp_path / "fixtures"
    directory.mkdir()
    return directory


@pytest.fixture
def graded_expected_dir(expected_dir: Path) -> Path:
    _write_expected(expected_dir, GRADED_STEM, GRADED_AGENT, "pass")
    return expected_dir


@pytest.fixture
def world(tmp_path: Path, monkeypatch) -> World:
    monkeypatch.setattr(estimate, "TOOL_TURN_MULTIPLIER", PINNED_TURN_MULTIPLIER)
    monkeypatch.setattr(estimate, "OUTPUT_TOKENS_PER_TRIAL", PINNED_OUTPUT_TOKENS)
    agents, expected, fixtures = (
        tmp_path / name for name in ("agents", "expected", "fixtures")
    )
    for directory in (agents, expected, fixtures, tmp_path / "runs", tmp_path / "stub"):
        directory.mkdir()
    for name, tools_line in (
        ("scout", SCOUT_TOOLS),
        ("write-capable", "Read, Edit"),
        ("lonely", "Read"),
        ("other", "Read"),
    ):
        _write_agent(
            agents,
            name,
            tools_line,
            model="sonnet",
            effort="high",
            body=f"You are {name}.",
        )
    _write_expected(expected, "clean-form", "scout", "pass")
    _write_expected(expected, "layered-svc", "scout", "fail")
    _write_expected(expected, "other-only", "other", "pass")
    _make_file_fixture(fixtures, "clean-form.html")
    (fixtures / "layered-svc" / "src").mkdir(parents=True)
    (fixtures / "layered-svc" / "src" / "app.py").write_text("app", encoding="utf-8")
    _make_file_fixture(fixtures, "other-only.txt", "other")
    knowledge = tmp_path / "plugin" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "note.md").write_text(WORLD_KNOWLEDGE_NOTE, encoding="utf-8")
    deps = model_effort_ab.Deps(
        clock=lambda: NOW,
        rng=FixedRng(),
        read_git_sha=lambda: "abc123",
        eval_paths=_eval_paths(
            agents_dir=agents,
            expected_dir=expected,
            fixtures_dir=fixtures,
            plugin_root=knowledge.parent,
            knowledge_dir=knowledge,
        ),
        pricing_table=TEST_PRICING,
    )
    return World(tmp_path, deps)


@pytest.fixture
def harmless_termination_signals():
    """Swap in a no-op SIGTERM/SIGHUP handler so a signal a test sends cannot end pytest."""
    originals = {
        signum: signal.signal(signum, _note_signal) for signum in TERMINATION_SIGNALS
    }
    yield
    for signum, handler in originals.items():
        signal.signal(signum, handler)


@pytest.fixture
def scout_plan(world: World) -> Iterator[plan.RunPlan]:
    """The planned `scout` run; its snapshot is removed when the test ends."""
    with plan.plan_run(
        "scout",
        candidate_model="haiku",
        candidate_effort=None,
        fixture_stems=None,
        runs_dir=world.runs_dir,
        now=NOW,
        rng=FixedRng(),
        git_sha=None,
        eval_paths=world.deps.eval_paths,
    ) as planned:
        yield planned


@pytest.fixture
def private_tmp(tmp_path: Path, monkeypatch) -> Path:
    """A temp directory only this test writes to, so a leftover directory shows."""
    directory = tmp_path / "private-tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory
