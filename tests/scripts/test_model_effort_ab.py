"""Tests for the model/effort A/B harness (scripts/model_effort_ab.py, scripts/lib/model_effort/).

Tool resolution: an agent's `tools:` frontmatter line is split into the
read-only built-ins the harness enables, the entries it withholds, and the
write-capable entries that make it refuse the agent.

Trial runner: a fixture is staged into a fresh temp dir per trial and the CLI
is invoked with an exact, isolating argv. A stub executable stands in for
`claude` and records its argv, cwd and the files it saw.

Unit tests build their own agents, expected entries and fixtures in temp dirs.
Each shipped asset (an agent file, an expected entry, the recorded transcripts)
has one named smoke test; the transcripts are the harness's parser fixtures.
"""

from __future__ import annotations

import dataclasses
import io
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT

for _path in (
    REPO_ROOT / "scripts",
    REPO_ROOT / "scripts" / "lib",
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import model_effort_ab
import pricing
from model_effort import (
    agent_file,
    agent_spec,
    artifact,
    artifact_store,
    estimate,
    execution,
    external,
    grading,
    interrupts,
    invocation,
    outcome,
    path_scrub,
    paths,
    plan,
    process_record,
    run_types,
    runner,
    session,
    stop_rules,
    tools,
    transcript,
)
from model_effort import fixtures as fixture_resolution
from model_effort.arm import (
    BASELINE_LABEL,
    CANDIDATE_LABEL,
    Arm,
)
from model_effort.cost import total_cost_usd
from model_effort.errors import UsageError
from model_effort.formatting import format_usd
from model_effort.outcome import Outcome
from model_effort.run_status import AbortReason, RunStatus
from model_effort.stop_rules import SpendLimit

TRANSCRIPT_FIXTURES = Path(__file__).parent / "fixtures" / "model_effort_ab"
HAIKU_MODEL_ID = "claude-haiku-5-5"
SONNET_MODEL_ID = "claude-sonnet-5-5"
NOW = datetime(2026, 10, 8, 12, 30, 45, tzinfo=timezone.utc)
RUN_ID = "20261008T123045Z-scout-haiku-high-0ab3"
SCOUT_TOOLS = "Read, Grep, mcp__x__y, Bash(graphify *)"
PASS_VERDICT = {"status": "pass", "issues": [], "summary": "Nothing to report."}
FAIL_VERDICT = {"status": "fail", "issues": [], "summary": "Layer violation."}
TRIAL_COST = 0.01
# Dollars per million tokens. Aliases mirror the agent files' `sonnet` and the
# candidate `haiku`; `opus` is deliberately absent so it is unpriced.
PRICEY_RATE = {"input": 4.0, "output": 20.0}
CHEAP_RATE = {"input": 1.0, "output": 5.0}
TEST_PRICING = {
    "models": {"test-pricey": PRICEY_RATE, "test-cheap": CHEAP_RATE},
    "aliases": {"sonnet": "test-pricey", "haiku": "test-cheap"},
}
# Pinned so CLI estimates do not move when the shipped calibration is retuned.
PINNED_TURN_MULTIPLIER = 2
PINNED_OUTPUT_TOKENS = 100
# The `scout` world run over both fixtures with 3 trials per arm. Per trial, the
# two fixtures send (15+13+145 + 15+3+141) chars / 4 * 2 = 166 input tokens and
# write 2 * 100 output tokens: pricey (166*4 + 200*20) / 1e6 = 0.004664,
# cheap (166*1 + 200*5) / 1e6 = 0.001166.
BASELINE_TWO_ARM_ESTIMATE = 0.004664 * 3
CANDIDATE_TWO_ARM_ESTIMATE = 0.001166 * 3
TWO_ARM_ESTIMATE = BASELINE_TWO_ARM_ESTIMATE + CANDIDATE_TWO_ARM_ESTIMATE
# A `--max-cost` under the estimate, so the startup refusal applies.
MAX_COST_BELOW_ESTIMATE = TWO_ARM_ESTIMATE / 2
ARM_COUNT = 2
TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP)
# The `scout` world resolves two fixtures: clean-form and layered-svc.
SCOUT_FIXTURE_COUNT = 2
SCOUT_TRIALS = 3
# Calls and cost of one arm, and of both, when every planned trial runs.
ARM_RUN_CALLS = SCOUT_FIXTURE_COUNT * SCOUT_TRIALS
FULL_RUN_CALLS = ARM_COUNT * ARM_RUN_CALLS
FULL_RUN_COST = FULL_RUN_CALLS * TRIAL_COST
MAX_COST_ABOVE_FULL_RUN = 2 * FULL_RUN_COST
SINGLE_TRIAL_RUN_CALLS = ARM_COUNT * SCOUT_FIXTURE_COUNT
# A spend limit of two and a half trials' cost: the third trial takes the total past it.
LIMIT_IN_TRIALS = 2.5
MAX_COST_MID_RUN = LIMIT_IN_TRIALS * TRIAL_COST
TRIALS_BEFORE_STOP = math.ceil(LIMIT_IN_TRIALS)
ENABLED = ("Read", "Grep")
# The most characters of a trial's error text (and of its grader messages) that are kept.
CAUSE_LIMIT = 500
# A spend limit just above the run's estimate, so the startup refusal allows it.
MAX_COST_ESTIMATE_FACTOR = 1.1
# Calls alternate baseline, candidate; the baseline's every second trial reports no
# cost, which is one call in four of the full run.
UNREPORTED_CALLS = FULL_RUN_CALLS // 4
REPORTED_CALLS = FULL_RUN_CALLS - UNREPORTED_CALLS
# Each reported trial costs a share of the limit that leaves half a share spare, so
# the reported trials alone stay under the limit.
SPARE_TRIAL_SHARE = 0.5
# Long enough that a slow interpreter start still reaches the stub before the kill.
TIMEOUT_SECONDS = 3


def _write_agent(
    agents_dir: Path,
    name: str,
    tools_line: str | None = None,
    *,
    model: str | None = None,
    effort: str | None = None,
    body: str = "Body.",
) -> None:
    lines = ["---", f"name: {name}"]
    for key, value in (("tools", tools_line), ("model", model), ("effort", effort)):
        if value is not None:
            lines.append(f"{key}: {value}")
    lines += ["---", "", body, ""]
    (agents_dir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def _write_expected(expected_dir: Path, stem: str, agent: str, status: str) -> None:
    entry = {
        "fixture": stem,
        "applicableAgents": [agent],
        "agents": {agent: {"expectedStatus": status}},
    }
    (expected_dir / f"{stem}.json").write_text(json.dumps(entry), encoding="utf-8")


def _make_file_fixture(
    root: Path, name: str = "form.html", content: str = "<form></form>"
) -> Path:
    fixture = root / name
    fixture.write_text(content, encoding="utf-8")
    return fixture


def _make_directory_fixture(root: Path) -> Path:
    fixture = root / "service"
    (fixture / "src" / "deep").mkdir(parents=True)
    (fixture / "README.md").write_text("readme", encoding="utf-8")
    (fixture / "src" / "app.py").write_text("print('app')", encoding="utf-8")
    (fixture / "src" / "deep" / "util.py").write_text("print('util')", encoding="utf-8")
    return fixture


def _snapshot(path: Path) -> dict[str, str]:
    files = (
        [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    )
    return {str(p): p.read_text(encoding="utf-8") for p in files}


def _flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


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


# --- Tool resolution ---------------------------------------------------------


class TestClassifyTools:
    def test_read_grep_enabled_mcp_and_scoped_bash_withheld(self):
        profile = tools.classify_tools(
            "Read, Grep, mcp__codegraph__*, Bash(graphify *)"
        )

        assert profile.enabled_tools == ("Read", "Grep")
        assert profile.withheld_tools == ("mcp__codegraph__*", "Bash(graphify *)")
        assert profile.refused_tools == ()

    def test_unlisted_builtin_is_withheld_not_enabled(self):
        profile = tools.classify_tools("Read, WebFetch")

        assert profile.enabled_tools == ("Read",)
        assert profile.withheld_tools == ("WebFetch",)

    def test_skill_and_agent_are_withheld(self):
        profile = tools.classify_tools("Read, Skill, Agent")

        assert profile.enabled_tools == ("Read",)
        assert profile.withheld_tools == ("Skill", "Agent")

    def test_glob_is_enabled(self):
        assert tools.classify_tools("Glob").enabled_tools == ("Glob",)

    @pytest.mark.parametrize(
        "write_tool", ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"]
    )
    def test_write_capable_tool_is_refused(self, write_tool):
        profile = tools.classify_tools(f"Read, {write_tool}")

        assert profile.refused_tools == (write_tool,)
        assert write_tool not in profile.enabled_tools
        assert write_tool not in profile.withheld_tools

    def test_scoped_bash_is_withheld_not_refused(self):
        profile = tools.classify_tools("Bash(git log *)")

        assert profile.refused_tools == ()
        assert profile.withheld_tools == ("Bash(git log *)",)

    @pytest.mark.parametrize("tools_line", [None, ""])
    def test_missing_or_blank_tools_line_yields_empty_profile(self, tools_line):
        profile = tools.classify_tools(tools_line)

        assert profile == tools.ToolProfile(
            enabled_tools=(), withheld_tools=(), refused_tools=()
        )

    def test_whitespace_and_empty_entries_are_dropped(self):
        profile = tools.classify_tools("  Read ,, Grep  ,")

        assert profile.enabled_tools == ("Read", "Grep")

    def test_tool_names_are_matched_case_sensitively(self):
        profile = tools.classify_tools("read, bash")

        assert profile.enabled_tools == ()
        assert profile.refused_tools == ()
        assert profile.withheld_tools == ("read", "bash")

    def test_agent_with_only_withheld_tools_has_no_enabled_tools(self):
        profile = tools.classify_tools("mcp__codegraph__*, WebFetch")

        assert profile.enabled_tools == ()
        assert profile.withheld_tools == ("mcp__codegraph__*", "WebFetch")


class TestResolveToolProfile:
    def test_reads_tools_from_parsed_frontmatter(self):
        profile = tools.resolve_tool_profile("scout", {"tools": SCOUT_TOOLS})

        assert profile.enabled_tools == ("Read", "Grep")
        assert profile.withheld_tools == ("mcp__x__y", "Bash(graphify *)")

    def test_agent_without_tools_key_has_no_tools(self):
        assert tools.resolve_tool_profile("bare", {}).enabled_tools == ()

    def test_write_capable_agent_raises_naming_agent_and_tools(self):
        with pytest.raises(tools.WriteCapableAgentError) as excinfo:
            tools.resolve_tool_profile("editor", {"tools": "Read, Edit, Write"})

        message = str(excinfo.value)
        assert "editor" in message
        assert "Edit" in message and "Write" in message
        assert "write-capable agents are not supported yet" in message

    def test_tools_given_as_a_yaml_list_raises_clear_error(self):
        with pytest.raises(agent_file.AgentFrontmatterError) as excinfo:
            tools.resolve_tool_profile("listy", {"tools": ["Read", "Grep"]})

        assert "listy" in str(excinfo.value)
        assert "comma-separated" in str(excinfo.value)


class TestLoadAgentFile:
    def test_returns_frontmatter_and_body_from_one_read(self, agents_dir):
        _write_agent(agents_dir, "scout", "Read, Grep", body="You are scout.")

        loaded = agent_file.load_agent_file("scout", agents_dir)

        assert loaded.frontmatter == {"name": "scout", "tools": "Read, Grep"}
        assert loaded.body == "You are scout.\n"
        assert loaded.path == agents_dir / "scout.md"

    def test_body_may_contain_delimiter_lines_without_ending_the_frontmatter(
        self, agents_dir
    ):
        (agents_dir / "scout.md").write_text(
            "---\nname: scout\n---\n\nIntro\n\n---\n\nAfter the rule\n",
            encoding="utf-8",
        )

        loaded = agent_file.load_agent_file("scout", agents_dir)

        assert loaded.frontmatter == {"name": "scout"}
        assert loaded.body == "Intro\n\n---\n\nAfter the rule\n"

    def test_unknown_agent_raises_listing_valid_names(self, agents_dir):
        _write_agent(agents_dir, "alpha")
        _write_agent(agents_dir, "beta")

        with pytest.raises(agent_file.UnknownAgentError) as excinfo:
            agent_file.load_agent_file("gamma", agents_dir)

        message = str(excinfo.value)
        assert "gamma" in message
        assert "alpha" in message and "beta" in message

    def test_agent_name_with_path_separator_is_unknown(self, agents_dir):
        _write_agent(agents_dir, "alpha")
        (agents_dir.parent / "outside.md").write_text(
            "---\ntools: Read\n---\n", encoding="utf-8"
        )

        with pytest.raises(agent_file.UnknownAgentError):
            agent_file.load_agent_file("../outside", agents_dir)

    def test_agent_file_without_frontmatter_raises_clear_error(self, agents_dir):
        (agents_dir / "broken.md").write_text("no frontmatter here", encoding="utf-8")

        with pytest.raises(agent_file.AgentFrontmatterError) as excinfo:
            agent_file.load_agent_file("broken", agents_dir)

        assert "broken" in str(excinfo.value)

    def test_unterminated_frontmatter_raises_clear_error(self, agents_dir):
        (agents_dir / "open.md").write_text("---\nname: open\nbody", encoding="utf-8")

        with pytest.raises(agent_file.AgentFrontmatterError):
            agent_file.load_agent_file("open", agents_dir)

    def test_frontmatter_that_is_not_a_mapping_raises_clear_error(self, agents_dir):
        (agents_dir / "listy.md").write_text("---\n- a\n- b\n---\n", encoding="utf-8")

        with pytest.raises(agent_file.AgentFrontmatterError) as excinfo:
            agent_file.load_agent_file("listy", agents_dir)

        assert "mapping" in str(excinfo.value)

    def test_undecodable_file_raises_frontmatter_error_not_a_raw_error(
        self, agents_dir
    ):
        (agents_dir / "binary.md").write_bytes(b"---\n\xff\xfe\n---\n")

        with pytest.raises(agent_file.AgentFrontmatterError):
            agent_file.load_agent_file("binary", agents_dir)


class TestAgentSpec:
    def test_reads_baseline_model_effort_and_body_as_system_prompt(self, agents_dir):
        _write_agent(
            agents_dir,
            "scout",
            model="sonnet",
            effort="high",
            body="You are scout.",
        )
        loaded = agent_file.load_agent_file("scout", agents_dir)

        built = agent_spec.build_agent_spec("scout", loaded)

        assert (built.model, built.effort) == ("sonnet", "high")
        assert built.system_prompt == "You are scout.\n"

    def test_missing_model_raises_naming_the_key(self, agents_dir):
        _write_agent(agents_dir, "scout", effort="high")
        loaded = agent_file.load_agent_file("scout", agents_dir)

        with pytest.raises(agent_file.AgentFrontmatterError) as excinfo:
            agent_spec.build_agent_spec("scout", loaded)

        assert "model" in str(excinfo.value)


class TestShippedAgentSmoke:
    def test_data_flow_tracer_enables_read_tools_and_withholds_mcp_and_scoped_bash(
        self,
    ):
        loaded = agent_file.load_agent_file("data-flow-tracer", paths.AGENTS_DIR)

        profile = tools.resolve_tool_profile("data-flow-tracer", loaded.frontmatter)

        assert profile.enabled_tools == ("Read", "Grep", "Glob")
        assert "Bash(graphify *)" in profile.withheld_tools
        assert any(entry.startswith("mcp__") for entry in profile.withheld_tools)

    def test_shipped_pricing_table_prices_the_smoke_agents_model(self):
        loaded = agent_file.load_agent_file("data-flow-tracer", paths.AGENTS_DIR)
        model = agent_spec.build_agent_spec("data-flow-tracer", loaded).model

        rate = pricing.rate(pricing.load_pricing(paths.PRICING_PATH), model)

        assert rate is not None
        assert rate["input"] > 0 and rate["output"] > 0


# --- Trial runner ------------------------------------------------------------

STUB_TEMPLATE = """#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
from pathlib import Path

RECORD = Path(__RECORD__)
QUEUE = Path(__QUEUE__)
BEHAVIOR = json.loads(__BEHAVIOR__)
if QUEUE.exists():
    queued = json.loads(QUEUE.read_text())
    if queued:
        BEHAVIOR = {**BEHAVIOR, **queued.pop(0)}
        QUEUE.write_text(json.dumps(queued))
cwd = Path(os.getcwd())
files_before = {
    str(p.relative_to(cwd)): p.read_text()
    for p in sorted(cwd.rglob("*"))
    if p.is_file()
}
symlinks = [str(p.relative_to(cwd)) for p in sorted(cwd.rglob("*")) if p.is_symlink()]
observed = None
if BEHAVIOR.get("observe"):
    target = Path(BEHAVIOR["observe"])
    observed = {
        "exists": target.exists(),
        "size": target.stat().st_size if target.exists() else None,
    }
calls = json.loads(RECORD.read_text()) if RECORD.exists() else []
calls.append({
    "pid": os.getpid(),
    "argv": sys.argv[1:],
    "cwd": str(cwd),
    "files_before": files_before,
    "symlinks": symlinks,
    "env_names": sorted(os.environ),
    "blocked_signals": sorted(
        s.name for s in signal.pthread_sigmask(signal.SIG_BLOCK, [])
    ),
    "observed": observed,
})
RECORD.write_text(json.dumps(calls))
if BEHAVIOR.get("tamper"):
    for p in cwd.rglob("*"):
        if p.is_file():
            p.write_text(p.read_text() + "TAMPERED")
if BEHAVIOR.get("touch"):
    Path(BEHAVIOR["touch"]).write_text("created during the run")
if BEHAVIOR.get("lock_subdir"):
    locked = cwd / "locked"
    locked.mkdir()
    (locked / "inner.txt").write_text("x")
    locked.chmod(0o500)
if BEHAVIOR.get("grandchild_marker"):
    code = "import pathlib, time; time.sleep(%s); pathlib.Path(%r).write_text('late')" % (
        BEHAVIOR["grandchild_delay"],
        BEHAVIOR["grandchild_marker"],
    )
    subprocess.Popen([sys.executable, "-c", code])
    Path(BEHAVIOR["grandchild_spawned"]).write_text("spawned")
if BEHAVIOR.get("stdout_hex"):
    sys.stdout.buffer.write(bytes.fromhex(BEHAVIOR["stdout_hex"]))
    sys.stdout.flush()
time.sleep(BEHAVIOR.get("sleep", 0))
sys.stdout.write(BEHAVIOR.get("stdout", ""))
sys.stderr.write(BEHAVIOR.get("stderr", ""))
if BEHAVIOR.get("stderr_cwd"):
    sys.stderr.write("cannot read " + str(cwd) + "/form.html")
sys.exit(BEHAVIOR.get("exit_code", 0))
"""


class StubClaude:
    """A stand-in `claude` executable that records every invocation."""

    def __init__(self, directory: Path, **behavior):
        self.path = directory / "claude-stub"
        self._record = directory / "calls.json"
        self._queue = directory / "queue.json"
        self.path.write_text(
            STUB_TEMPLATE.replace("__RECORD__", repr(str(self._record)))
            .replace("__QUEUE__", repr(str(self._queue)))
            .replace("__BEHAVIOR__", repr(json.dumps(behavior))),
            encoding="utf-8",
        )
        self.path.chmod(0o755)

    def queue(self, *per_call_behaviors: dict) -> None:
        """Make call N use the Nth behavior (merged over the defaults); later calls use the defaults."""
        self._queue.write_text(json.dumps(list(per_call_behaviors)), encoding="utf-8")

    @property
    def calls(self) -> list[dict]:
        if not self._record.exists():
            return []
        return json.loads(self._record.read_text(encoding="utf-8"))


def _config(
    stub: StubClaude | None = None,
    *,
    model: str = "haiku",
    effort: str = "low",
    enabled_tools: tuple[str, ...] = ENABLED,
    system_prompt: str = "You are a reviewer.",
    claude_bin: str | None = None,
    **config_fields,
) -> invocation.TrialConfig:
    profile = tools.ToolProfile(
        enabled_tools=tuple(enabled_tools), withheld_tools=(), refused_tools=()
    )
    return invocation.TrialConfig(
        arm=Arm(label=CANDIDATE_LABEL, model=model, effort=effort, profile=profile),
        system_prompt=system_prompt,
        claude_bin=claude_bin if claude_bin is not None else str(stub.path),
        **config_fields,
    )


class TestStagingFixtures:
    def test_file_fixture_is_staged_under_its_own_name(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root)

        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["files_before"] == {"form.html": "<form></form>"}

    def test_directory_fixture_is_staged_with_nested_files(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir)
        fixture = _make_directory_fixture(fixture_root)

        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["files_before"] == {
            "service/README.md": "readme",
            "service/src/app.py": "print('app')",
            "service/src/deep/util.py": "print('util')",
        }

    @pytest.mark.parametrize(
        "make_fixture",
        [_make_file_fixture, _make_directory_fixture],
        ids=["file", "directory"],
    )
    def test_two_trials_each_see_a_pristine_copy_and_source_is_unchanged(
        self, make_fixture, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, tamper=True)
        fixture = make_fixture(fixture_root)
        source_before = _snapshot(fixture)

        runner.run_trial(fixture, _config(stub))
        runner.run_trial(fixture, _config(stub))

        first, second = stub.calls
        assert first["files_before"] == second["files_before"]
        assert not any("TAMPERED" in text for text in second["files_before"].values())
        assert _snapshot(fixture) == source_before

    def test_trials_run_in_distinct_temp_dirs(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))
        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["cwd"] != stub.calls[1]["cwd"]

    def test_temp_dir_is_removed_after_the_trial(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))

        assert not Path(stub.calls[0]["cwd"]).exists()

    def test_temp_dir_is_removed_after_a_timeout(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS)

        assert stub.calls, "the stub never started, so the timeout proved nothing"
        assert not Path(stub.calls[0]["cwd"]).exists()

    def test_symlinks_in_a_directory_fixture_are_copied_as_links(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir)
        fixture = _make_directory_fixture(fixture_root)
        outside = _make_file_fixture(fixture_root, "outside.txt", "outside")
        (fixture / "link.txt").symlink_to(outside)

        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["symlinks"] == ["service/link.txt"]

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
    def test_temp_dir_that_cannot_be_removed_is_reported_on_stderr(
        self, stub_dir, fixture_root, capsys
    ):
        stub = StubClaude(stub_dir, lock_subdir=True)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))

        leftover = Path(stub.calls[0]["cwd"])
        try:
            assert "could not remove" in capsys.readouterr().err
        finally:
            (leftover / "locked").chmod(0o700)
            shutil.rmtree(leftover)


def _raise_keyboard_interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


INTERRUPT_SIGNALS = (signal.SIGINT, *TERMINATION_SIGNALS)


def _blocked_signals() -> set[signal.Signals]:
    return set(signal.pthread_sigmask(signal.SIG_BLOCK, []))


class TestSignalsAroundSpawn:
    def test_interrupt_signals_are_blocked_while_the_process_starts_and_free_afterwards(
        self, stub_dir, fixture_root, monkeypatch
    ):
        blocked_during_spawn = []
        real_popen = subprocess.Popen

        def record_mask_then_spawn(*args, **kwargs):
            blocked_during_spawn.append(_blocked_signals())
            return real_popen(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", record_mask_then_spawn)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(StubClaude(stub_dir)))

        assert set(INTERRUPT_SIGNALS) <= blocked_during_spawn[0]
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_signals_are_free_again_when_the_binary_cannot_start(self, fixture_root):
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(claude_bin="/no/such/claude"))

        assert record.exit_code == runner.COMMAND_NOT_RUNNABLE_EXIT_CODE
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_the_cli_process_starts_with_the_interrupt_signals_unblocked(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))

        blocked_in_child = set(stub.calls[0]["blocked_signals"])
        assert not {signum.name for signum in INTERRUPT_SIGNALS} & blocked_in_child

    def test_signal_arriving_during_the_spawn_still_kills_the_new_process_group(
        self, stub_dir, fixture_root, monkeypatch
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        children = []
        real_popen = subprocess.Popen

        def spawn_then_terminate(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        monkeypatch.setattr(subprocess, "Popen", spawn_then_terminate)
        previous = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        try:
            with pytest.raises(KeyboardInterrupt):
                runner.run_trial(fixture, _config(stub))
            assert children[0].poll() is not None, "the child outlived the interrupt"
        finally:
            signal.signal(signal.SIGTERM, previous)
            for child in children:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_interrupt_signals_are_blocked_while_the_group_is_killed_and_free_afterwards(
        self, stub_dir, fixture_root, monkeypatch
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        blocked_during_kill = []
        # Call-through spy on `_kill_process_group`: it records the signal mask at
        # the kill. The mask is not visible from outside the process.
        real_kill = runner._kill_process_group
        real_popen = subprocess.Popen

        def record_mask_then_kill(process):
            blocked_during_kill.append(_blocked_signals())
            real_kill(process)

        def spawn_then_terminate(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        monkeypatch.setattr(runner, "_kill_process_group", record_mask_then_kill)
        monkeypatch.setattr(subprocess, "Popen", spawn_then_terminate)
        previous = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        try:
            with pytest.raises(KeyboardInterrupt):
                runner.run_trial(fixture, _config(stub))
        finally:
            signal.signal(signal.SIGTERM, previous)

        assert blocked_during_kill, "the process group was never killed"
        assert set(INTERRUPT_SIGNALS) <= blocked_during_kill[0]
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()


class TestTrialArgv:
    def _run(self, stub_dir, fixture_root, **config_overrides) -> dict:
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root)
        runner.run_trial(fixture, _config(stub, **config_overrides))
        return stub.calls[0]

    def test_tools_flag_carries_the_enabled_tools_comma_joined(
        self, stub_dir, fixture_root
    ):
        call = self._run(stub_dir, fixture_root, enabled_tools=("Read", "Grep", "Glob"))

        assert _flag_value(call["argv"], "--tools") == "Read,Grep,Glob"

    def test_no_enabled_tools_passes_an_empty_tools_value(self, stub_dir, fixture_root):
        call = self._run(stub_dir, fixture_root, enabled_tools=())

        assert _flag_value(call["argv"], "--tools") == ""

    def test_argv_enables_no_mcp_tools(self, stub_dir, fixture_root):
        call = self._run(stub_dir, fixture_root)

        assert not any("mcp__" in arg for arg in call["argv"])

    def test_argv_carries_every_isolation_and_output_flag(self, stub_dir, fixture_root):
        call = self._run(stub_dir, fixture_root)

        argv = call["argv"]
        for flag in (
            "--restricted",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--verbose",
        ):
            assert flag in argv
        assert _flag_value(argv, "--output-format") == "stream-json"

    def test_model_and_effort_are_passed(self, stub_dir, fixture_root):
        call = self._run(stub_dir, fixture_root, model="sonnet", effort="high")

        assert _flag_value(call["argv"], "--model") == "sonnet"
        assert _flag_value(call["argv"], "--effort") == "high"

    def test_add_dir_is_only_the_plugin_knowledge_dir_and_never_answer_files(
        self, stub_dir, fixture_root
    ):
        knowledge = REPO_ROOT / "plugins" / "dev-team" / "knowledge"

        call = self._run(stub_dir, fixture_root)

        add_dirs = [
            call["argv"][i + 1]
            for i, arg in enumerate(call["argv"])
            if arg == "--add-dir"
        ]
        assert add_dirs == [str(knowledge)]
        assert knowledge.is_dir()
        assert paths.EXPECTED_DIR != knowledge
        assert knowledge not in paths.EXPECTED_DIR.parents

    def test_cwd_is_the_staged_dir_outside_the_repo(self, stub_dir, fixture_root):
        call = self._run(stub_dir, fixture_root)

        cwd = Path(call["cwd"]).resolve()
        assert REPO_ROOT.resolve() not in (cwd, *cwd.parents)
        assert cwd.name.startswith(runner.TEMP_DIR_PREFIX)

    def test_plugin_root_placeholder_is_substituted_in_the_system_prompt(
        self, stub_dir, fixture_root, tmp_path
    ):
        plugin_root = tmp_path / "plugin-root"
        call = self._run(
            stub_dir,
            fixture_root,
            system_prompt="Read ${CLAUDE_PLUGIN_ROOT}/knowledge/x.md then ${CLAUDE_PLUGIN_ROOT}/y.md",
            plugin_root=plugin_root,
        )

        assert _flag_value(call["argv"], "--system-prompt") == (
            f"Read {plugin_root}/knowledge/x.md then {plugin_root}/y.md"
        )

    def test_user_prompt_names_the_staged_fixture_relative_to_cwd(
        self, stub_dir, fixture_root
    ):
        call = self._run(stub_dir, fixture_root)

        prompt = _flag_value(call["argv"], "-p")
        assert "`form.html`" in prompt
        assert str(fixture_root) not in prompt
        assert "only the JSON object" in prompt

    def test_argv_starts_with_the_injected_binary(self):
        config = _config(claude_bin="/opt/bin/claude-x")

        argv = invocation.build_argv(config, "go")

        assert argv[:3] == ["/opt/bin/claude-x", "-p", "go"]


class TestExternalScriptWrappers:
    """These fail when an upstream script renames the private helper the wrapper reaches."""

    def test_session_identity_variable_is_scrubbed_and_home_is_kept(self):
        assert external.should_scrub_env_var("CLAUDE_CODE_SESSION_ID") is True
        assert external.should_scrub_env_var("HOME") is False

    @pytest.mark.parametrize(
        ("value", "valid"),
        [("haiku", True), ("claude-opus-4-8", True), ("gpt-4", False), ("", False)],
    )
    def test_model_is_valid_against_the_contract_enum(self, value, valid):
        assert external.model_is_valid(value, ["haiku", "sonnet", "opus"]) is valid


class TestTrialEnvironment:
    def test_parent_session_identity_variables_are_removed_and_the_rest_kept(self):
        parent = {
            "CLAUDE_CODE_SESSION_ID": "parent-session",
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            "HOME": "/home/me",
            "ANTHROPIC_API_KEY": "key",
        }

        env = invocation.build_trial_env(parent)

        assert env == {"HOME": "/home/me", "ANTHROPIC_API_KEY": "key"}

    def test_the_cli_process_receives_the_scrubbed_environment(
        self, stub_dir, fixture_root, monkeypatch
    ):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
        monkeypatch.setenv("KEEP_ME", "1")
        stub = StubClaude(stub_dir)

        runner.run_trial(_make_file_fixture(fixture_root), _config(stub))

        env_names = stub.calls[0]["env_names"]
        assert "CLAUDE_CODE_SESSION_ID" not in env_names
        assert "KEEP_ME" in env_names and "HOME" in env_names


GRANDCHILD_DELAY_SECONDS = 4


def _wait_until_after(started: float, delay: float) -> None:
    """Sleep until a grandchild started after `started` would have written its marker."""
    margin = 1.5
    remaining = started + delay + margin - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


class TestExecution:
    def test_exit_code_stdout_and_stderr_are_captured_for_a_failing_run(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(
            stub_dir, exit_code=3, stdout="out-line", stderr="boom: bad model"
        )
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout, record.stderr, record.timed_out) == (
            3,
            "out-line",
            "boom: bad model",
            False,
        )

    def test_successful_run_reports_zero_exit_and_not_timed_out(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, stdout="ok")
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout, record.timed_out) == (0, "ok", False)

    def test_output_that_is_not_utf8_is_decoded_with_replacement_characters(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, stdout_hex="6f6bff")
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout) == (0, "ok�")

    def test_run_exceeding_the_time_limit_is_marked_timed_out(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS
        )

        assert stub.calls, "the stub never started, so the timeout proved nothing"
        assert record.timed_out is True
        assert record.exit_code is None

    def test_timeout_kills_the_whole_process_group_not_just_the_child(
        self, stub_dir, fixture_root
    ):
        marker, spawned = stub_dir / "late.txt", stub_dir / "spawned.txt"
        stub = StubClaude(
            stub_dir,
            sleep=30,
            grandchild_marker=str(marker),
            grandchild_delay=GRANDCHILD_DELAY_SECONDS,
            grandchild_spawned=str(spawned),
        )
        started = time.monotonic()

        runner.run_trial(
            _make_file_fixture(fixture_root, "a.txt", "a"),
            _config(stub),
            trial_timeout_seconds=TIMEOUT_SECONDS,
        )
        _wait_until_after(started, GRANDCHILD_DELAY_SECONDS)

        assert spawned.exists(), (
            "the grandchild never started, so the kill proved nothing"
        )
        assert not marker.exists()

    def test_interrupt_kills_the_whole_process_group_before_propagating(
        self, stub_dir, fixture_root
    ):
        marker, spawned = stub_dir / "late.txt", stub_dir / "spawned.txt"
        delay = GRANDCHILD_DELAY_SECONDS - 2
        stub = StubClaude(
            stub_dir,
            sleep=30,
            grandchild_marker=str(marker),
            grandchild_delay=delay,
            grandchild_spawned=str(spawned),
        )
        started = time.monotonic()
        cancelled = threading.Event()

        def interrupt_once_spawned() -> None:
            deadline = time.monotonic() + 10
            while not spawned.exists() and time.monotonic() < deadline:
                if cancelled.wait(0.05):
                    return
            if spawned.exists() and not cancelled.is_set():
                signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)

        interrupter = threading.Thread(target=interrupt_once_spawned, daemon=True)
        interrupter.start()
        try:
            with pytest.raises(KeyboardInterrupt):
                runner.run_trial(
                    _make_file_fixture(fixture_root, "a.txt", "a"),
                    _config(stub),
                    trial_timeout_seconds=60,
                )
        finally:
            cancelled.set()
            interrupter.join()
        _wait_until_after(started, delay)

        assert spawned.exists()
        assert not marker.exists()

    def test_missing_claude_binary_yields_exit_127_with_the_os_error_as_stderr(
        self, tmp_path, fixture_root
    ):
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        missing = tmp_path / "no-such-claude"

        record = runner.run_trial(fixture, _config(claude_bin=str(missing)))

        assert (record.exit_code, record.timed_out) == (127, False)
        assert "no-such-claude" in record.stderr

    def test_non_executable_claude_binary_yields_exit_127(self, tmp_path, fixture_root):
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        not_executable = tmp_path / "claude-plain-file"
        not_executable.write_text("not a program", encoding="utf-8")
        not_executable.chmod(0o644)

        record = runner.run_trial(fixture, _config(claude_bin=str(not_executable)))

        assert record.exit_code == 127
        assert record.stderr != ""


# --- Transcript parsing ------------------------------------------------------


def _fixture_text(filename: str) -> str:
    return (TRANSCRIPT_FIXTURES / filename).read_text(encoding="utf-8")


def _read_transcript(name: str) -> transcript.ParsedTranscript:
    return transcript.parse_stream(_fixture_text(f"{name}.jsonl"))


def _stream(*events: dict | str) -> str:
    return "\n".join(e if isinstance(e, str) else json.dumps(e) for e in events)


def _result_event(text="ok", model_usage=None, **fields) -> dict:
    usage = {HAIKU_MODEL_ID: {}} if model_usage is None else model_usage
    return {
        "type": "result",
        "result": text,
        "is_error": False,
        "total_cost_usd": TRIAL_COST,
        "modelUsage": usage,
        **fields,
    }


def _tool_use_event(*names: str) -> dict:
    blocks = [{"type": "tool_use", "name": n, "input": {}} for n in names]
    return {"type": "assistant", "message": {"content": blocks}}


def _init_event(model_id: str = HAIKU_MODEL_ID, **fields) -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "cwd": "/private/var/folders/XX/T/model-effort-ab-abc123",
        "session_id": "11111111-1111-1111-1111-111111111111",
        "model": model_id,
        "permissionMode": "default",
        "tools": ["Read", "Grep"],
        "mcp_servers": [],
        "plugins": [{"name": "builtin-a", "path": "/home/someone/.claude/plugins/a"}],
        **fields,
    }


def _expected_session_config(model_id: str) -> dict:
    return {
        "model": model_id,
        "permissionMode": "default",
        "tools": ["Read", "Grep"],
        "mcp_servers": [],
        "plugins": ["builtin-a"],
        "cwd": "<staged>",
    }


class TestParseStream:
    def test_real_read_only_run_yields_result_cost_model_and_tool_names(self):
        parsed = _read_transcript("pass-readonly")

        assert parsed.has_result is True
        assert parsed.is_error is False
        assert parsed.result_text == '{"status": "ok", "knowledge_read": true}'
        assert parsed.cost_usd == pytest.approx(0.00041539)
        assert parsed.model_id == HAIKU_MODEL_ID
        assert parsed.model_id_note is None
        assert parsed.called_tool_names == ("Read", "Read")

    def test_real_run_with_a_denied_read_shows_the_attempt_and_the_denial(self):
        parsed = _read_transcript("read-outside-denied")

        assert parsed.has_result is True
        assert parsed.called_tool_names == ("Read",)
        assert parsed.permission_denial_count == 1

    def test_real_run_with_allowed_reads_has_no_permission_denials(self):
        assert _read_transcript("pass-readonly").permission_denial_count == 0

    def test_real_bad_model_run_is_an_error_with_no_model_id_and_a_note(self):
        parsed = _read_transcript("bad-model")

        assert parsed.has_result is True
        assert parsed.is_error is True
        assert parsed.cost_usd == 0
        assert parsed.model_id is None
        assert parsed.model_id_note

    def test_real_run_where_the_model_declines_bash_has_no_tool_use(self):
        parsed = _read_transcript("tool-denied-bash")

        assert parsed.called_tool_names == ()
        assert parsed.model_id == HAIKU_MODEL_ID

    def test_real_run_with_no_tools_has_no_tool_use(self):
        parsed = _read_transcript("no-tools")

        assert parsed.called_tool_names == ()
        assert parsed.result_text == "ok"
        assert parsed.has_result is True

    def test_blank_and_unparseable_lines_are_skipped(self):
        parsed = transcript.parse_stream(
            _stream("", "not json", "[1, 2]", _result_event("hi"), "   ")
        )

        assert (parsed.has_result, parsed.result_text) == (True, "hi")

    def test_rate_limit_and_system_events_are_ignored(self):
        parsed = transcript.parse_stream(
            _stream(
                {"type": "system", "subtype": "init", "tools": ["Read"]},
                {"type": "rate_limit_event", "rate_limit_info": {}},
                _tool_use_event("Read"),
                {"type": "rate_limit_event", "rate_limit_info": {}},
                _result_event("done"),
            )
        )

        assert parsed.called_tool_names == ("Read",)
        assert parsed.result_text == "done"

    def test_missing_result_event_reports_has_result_false(self):
        parsed = transcript.parse_stream(_stream(_tool_use_event("Grep")))

        assert parsed.has_result is False
        assert parsed.result_text is None
        assert parsed.called_tool_names == ("Grep",)
        assert parsed.cost_usd is None

    def test_zero_cost_is_reported_not_unknown(self):
        parsed = transcript.parse_stream(_stream(_result_event(total_cost_usd=0)))

        assert parsed.cost_usd == 0

    @pytest.mark.parametrize(
        "cost",
        [float("nan"), float("inf"), float("-inf"), -0.01, "0.01", True, None],
        ids=["nan", "inf", "-inf", "negative", "string", "bool", "null"],
    )
    def test_cost_that_is_not_a_finite_non_negative_number_is_unreported(self, cost):
        parsed = transcript.parse_stream(_stream(_result_event(total_cost_usd=cost)))

        assert parsed.has_result is True
        assert parsed.cost_usd is None

    def test_result_event_without_a_cost_field_is_unreported(self):
        event = _result_event()
        del event["total_cost_usd"]

        assert transcript.parse_stream(_stream(event)).cost_usd is None

    def test_empty_stdout_has_no_result(self):
        assert transcript.parse_stream("").has_result is False

    def test_missing_model_usage_gives_no_model_id_and_a_note(self):
        event = _result_event()
        del event["modelUsage"]

        parsed = transcript.parse_stream(_stream(event))

        assert parsed.model_id is None
        assert parsed.model_id_note

    def test_multiple_models_in_model_usage_are_ambiguous_and_noted(self):
        usage = {"claude-haiku-5-5": {}, "claude-sonnet-5-5": {}}

        parsed = transcript.parse_stream(_stream(_result_event(model_usage=usage)))

        assert parsed.model_id is None
        assert "claude-haiku-5-5" in parsed.model_id_note
        assert "claude-sonnet-5-5" in parsed.model_id_note

    def test_tool_names_from_several_assistant_events_keep_order_and_skip_text(self):
        text_block = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "thinking"}]},
        }

        parsed = transcript.parse_stream(
            _stream(
                _tool_use_event("Read", "Grep"),
                text_block,
                _tool_use_event("WebFetch"),
                _result_event(),
            )
        )

        assert parsed.called_tool_names == ("Read", "Grep", "WebFetch")


class TestSessionConfig:
    def test_real_run_session_config_names_what_loaded_without_paths_or_ids(self):
        config = _read_transcript("pass-readonly").session_config

        assert config["model"] == HAIKU_MODEL_ID
        assert config["permissionMode"] == "default"
        assert config["tools"] == ["Glob", "Grep", "Read"]
        assert config["mcp_servers"] == []
        assert config["cwd"] == "<staged>"
        assert config["plugins"] and all(
            isinstance(name, str) and "/" not in name for name in config["plugins"]
        )
        assert set(config) == {
            "model",
            "permissionMode",
            "tools",
            "mcp_servers",
            "plugins",
            "cwd",
        }
        dumped = json.dumps(config)
        assert "/private" not in dumped and "/Users" not in dumped

    def test_init_event_is_scrubbed_of_cwd_session_id_and_plugin_paths(self):
        parsed = transcript.parse_stream(_stream(_init_event(), _result_event()))

        assert parsed.session_config == _expected_session_config(HAIKU_MODEL_ID)
        dumped = json.dumps(parsed.session_config)
        assert "/home/someone" not in dumped and "1111" not in dumped

    def test_mcp_servers_are_reported_by_name_only(self):
        init = _init_event(
            mcp_servers=[{"name": "codegraph", "status": "connected"}, "plain"]
        )

        parsed = transcript.parse_stream(_stream(init, _result_event()))

        assert parsed.session_config["mcp_servers"] == ["codegraph", "plain"]

    def test_stream_without_an_init_event_has_no_session_config(self):
        parsed = transcript.parse_stream(_stream(_result_event()))

        assert parsed.session_config is None

    def test_a_stream_cut_off_after_init_still_reports_the_session_config(self):
        parsed = transcript.parse_stream(_stream(_init_event()))

        assert parsed.has_result is False
        assert parsed.session_config == _expected_session_config(HAIKU_MODEL_ID)


TRUNCATED_OUTER_OBJECT = '{"status":"fail","issues":[{"severity":"error","message":"x"}'


class TestExtractAgentJson:
    def test_bare_object_is_parsed(self):
        assert transcript.extract_agent_json('{"status": "pass"}') == {"status": "pass"}

    def test_fenced_json_block_is_preferred_over_earlier_bare_object(self):
        text = 'Draft {"status": "fail"}\n```json\n{"status": "pass"}\n```'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_two_objects_without_a_fence_first_wins(self):
        text = '{"status": "pass"} then {"status": "fail"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_prose_around_the_object_is_ignored(self):
        text = 'Here is my review:\n{"status": "warn", "issues": []}\nHope it helps.'

        assert transcript.extract_agent_json(text) == {"status": "warn", "issues": []}

    def test_braces_inside_strings_do_not_break_balancing(self):
        text = 'x {"summary": "uses } and { inside", "status": "pass"} y'

        assert transcript.extract_agent_json(text) == {
            "summary": "uses } and { inside",
            "status": "pass",
        }

    def test_nested_objects_are_returned_whole(self):
        text = '{"issues": [{"severity": "error"}], "status": "fail"}'

        assert transcript.extract_agent_json(text)["issues"] == [{"severity": "error"}]

    def test_invalid_fenced_block_falls_back_to_a_bare_object(self):
        text = '```json\n{broken\n```\n{"status": "pass"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    @pytest.mark.parametrize(
        "text", ["", "no json here", "{not: json}", "[1, 2]", None]
    )
    def test_text_without_a_json_object_gives_none(self, text):
        assert transcript.extract_agent_json(text) is None

    def test_truncated_outer_object_does_not_yield_its_inner_object(self):
        assert transcript.extract_agent_json(TRUNCATED_OUTER_OBJECT) is None

    def test_object_inside_an_unclosed_outer_with_escaped_quote_is_not_top_level(self):
        text = r'{"summary": "say \"hi\" {", "issues": [{"severity": "error"}]'

        assert transcript.extract_agent_json(text) is None

    def test_top_level_object_after_a_closed_invalid_one_is_returned(self):
        text = '{not: json} then {"status": "pass"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}

    def test_apostrophe_or_quote_in_prose_before_the_object_is_ignored(self):
        text = 'It said "hello and then: {"status": "pass"}'

        assert transcript.extract_agent_json(text) == {"status": "pass"}


# --- Grading and outcomes ----------------------------------------------------

GRADED_AGENT = "x-review"
GRADED_STEM = "clean-form"


@pytest.fixture
def graded_expected_dir(expected_dir: Path) -> Path:
    _write_expected(expected_dir, GRADED_STEM, GRADED_AGENT, "pass")
    return expected_dir


class TestGradeTrial:
    def test_verdict_matching_the_expected_entry_passes(self, graded_expected_dir):
        passed, messages = grading.grade_trial(
            GRADED_AGENT, GRADED_STEM, PASS_VERDICT, expected_dir=graded_expected_dir
        )

        assert (passed, messages) == (True, [])

    def test_verdict_with_the_wrong_status_fails_with_a_status_message(
        self, graded_expected_dir
    ):
        wrong = {"status": "fail", "issues": [], "summary": ""}

        passed, messages = grading.grade_trial(
            GRADED_AGENT, GRADED_STEM, wrong, expected_dir=graded_expected_dir
        )

        assert passed is False
        assert any("status" in message for message in messages)

    def test_only_the_named_expected_file_reaches_the_grader(self, graded_expected_dir):
        # A malformed sibling would crash the grader if it were copied too.
        (graded_expected_dir / "two.json").write_text("{not json", encoding="utf-8")

        passed, _ = grading.grade_trial(
            GRADED_AGENT, GRADED_STEM, PASS_VERDICT, expected_dir=graded_expected_dir
        )

        assert passed is True

    def test_agent_absent_from_the_expected_entry_fails_with_a_message(
        self, graded_expected_dir
    ):
        passed, messages = grading.grade_trial(
            "no-such-agent", GRADED_STEM, {}, expected_dir=graded_expected_dir
        )

        assert passed is False
        assert messages

    @pytest.mark.parametrize(
        "error",
        [TypeError, KeyError, AttributeError, ValueError],
        ids=lambda e: e.__name__,
    )
    def test_agent_answer_shaped_errors_from_the_grader_fail_the_trial_naming_the_error(
        self, graded_expected_dir, monkeypatch, error
    ):
        def raising_grader(**_kwargs):
            raise error("bad shape")

        monkeypatch.setattr(grading, "run_grading", raising_grader)

        passed, messages = grading.grade_trial(
            GRADED_AGENT, GRADED_STEM, {}, expected_dir=graded_expected_dir
        )

        assert passed is False
        assert len(messages) == 1 and error.__name__ in messages[0]

    def test_other_errors_from_the_grader_propagate(
        self, graded_expected_dir, monkeypatch
    ):
        def failing_grader(**_kwargs):
            raise OSError("disk gone")

        monkeypatch.setattr(grading, "run_grading", failing_grader)

        with pytest.raises(OSError, match="disk gone"):
            grading.grade_trial(
                GRADED_AGENT, GRADED_STEM, {}, expected_dir=graded_expected_dir
            )

    @pytest.mark.parametrize("error", [OSError, ValueError], ids=lambda e: e.__name__)
    def test_errors_while_staging_the_expected_entry_propagate(
        self, graded_expected_dir, monkeypatch, error
    ):
        def failing_copy(*_args, **_kwargs):
            raise error("cannot stage")

        monkeypatch.setattr(grading, "shutil", SimpleNamespace(copy2=failing_copy))

        with pytest.raises(error, match="cannot stage"):
            grading.grade_trial(
                GRADED_AGENT,
                GRADED_STEM,
                PASS_VERDICT,
                expected_dir=graded_expected_dir,
            )

    def test_grading_leaves_no_temp_dir_behind(
        self, graded_expected_dir, tmp_path, monkeypatch
    ):
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr(grading.tempfile, "tempdir", str(scratch))

        grading.grade_trial(
            GRADED_AGENT, GRADED_STEM, PASS_VERDICT, expected_dir=graded_expected_dir
        )

        assert list(scratch.iterdir()) == []


class TestIsExpectedClean:
    def test_expected_status_pass_is_clean(self):
        entry = {"agents": {"a": {"expectedStatus": "pass"}}}

        assert grading.is_expected_clean(entry, "a") is True

    def test_expected_status_fail_is_not_clean(self):
        entry = {"agents": {"a": {"expectedStatus": "fail"}}}

        assert grading.is_expected_clean(entry, "a") is False

    def test_agent_missing_from_entry_is_not_clean(self):
        assert grading.is_expected_clean({"agents": {}}, "a") is False


class TestShippedExpectedEntrySmoke:
    def test_clean_form_verdict_grades_as_pass_against_the_shipped_entry(self):
        passed, messages = grading.grade_trial(
            "a11y-review", "a11y-clean-form", PASS_VERDICT
        )

        assert (passed, messages) == (True, [])


def _record(
    exit_code=0, stdout="", stderr="", timed_out=False, cwd=None
) -> process_record.TrialProcessRecord:
    return process_record.TrialProcessRecord(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        cwd=cwd,
    )


def _resolve(stdout: str, grader=None, **record_fields) -> outcome.TrialResult:
    record = _record(stdout=stdout, **record_fields)
    parsed = transcript.parse_stream(stdout)
    grader = grader or (lambda agent_json: (True, []))
    return outcome.resolve_outcome(record, parsed, ENABLED, grader)


@pytest.fixture
def real_grader(graded_expected_dir):
    def grade(agent_json: dict) -> tuple[bool, list[str]]:
        return grading.grade_trial(
            GRADED_AGENT, GRADED_STEM, agent_json, expected_dir=graded_expected_dir
        )

    return grade


def _verdict_stream(verdict: dict, *tool_names: str) -> str:
    events = [_tool_use_event(*tool_names)] if tool_names else []
    return _stream(*events, _result_event(json.dumps(verdict)))


class TestOutcomeEnum:
    def test_outcomes_are_declared_in_precedence_order(self):
        assert [member.value for member in Outcome] == [
            "timeout",
            "cli_error",
            "tool_violation",
            "parse_failure",
            "graded_fail",
            "pass",
        ]

    def test_infrastructure_outcomes_are_cli_error_and_timeout(self):
        assert outcome.INFRA_OUTCOMES == {Outcome.CLI_ERROR, Outcome.TIMEOUT}


class TestTrialOutcomes:
    def test_json_satisfying_the_expected_entry_is_pass(self, real_grader):
        result = _resolve(_verdict_stream(PASS_VERDICT), real_grader)

        assert result.outcome == Outcome.PASS
        assert result.error is None
        assert result.grader_messages == ()

    def test_json_with_the_wrong_status_is_graded_fail_with_grader_messages(
        self, real_grader
    ):
        wrong = {"status": "fail", "issues": [], "summary": ""}

        result = _resolve(_verdict_stream(wrong), real_grader)

        assert result.outcome == Outcome.GRADED_FAIL
        assert any("status" in m for m in result.grader_messages)

    @pytest.mark.parametrize(
        ("malformed", "error_type"),
        [({"issues": ["text"]}, "AttributeError"), ({"issues": 3}, "TypeError")],
        ids=["issues-as-strings", "issues-as-number"],
    )
    def test_json_shaped_so_the_real_grader_raises_is_graded_fail_naming_the_error(
        self, real_grader, malformed, error_type
    ):
        result = _resolve(_verdict_stream(malformed), real_grader)

        assert result.outcome == Outcome.GRADED_FAIL
        assert len(result.grader_messages) == 1
        assert error_type in result.grader_messages[0]

    def test_error_raised_by_the_grader_is_not_a_verdict_and_propagates(self):
        def failing_grader(_agent_json):
            raise OSError("grading disk gone")

        with pytest.raises(OSError, match="grading disk gone"):
            _resolve(_verdict_stream(PASS_VERDICT), failing_grader)

    def test_text_with_no_json_object_is_parse_failure(self):
        result = _resolve(_stream(_result_event("I found nothing to report.")))

        assert result.outcome == Outcome.PARSE_FAILURE
        assert result.error

    def test_truncated_outer_object_is_parse_failure_not_its_inner_object(self):
        result = _resolve(_stream(_result_event(TRUNCATED_OUTER_OBJECT)))

        assert result.outcome == Outcome.PARSE_FAILURE

    def test_call_to_a_tool_outside_the_enabled_set_is_tool_violation_naming_it(self):
        result = _resolve(_verdict_stream(PASS_VERDICT, "Read", "Bash"))

        assert result.outcome == Outcome.TOOL_VIOLATION
        assert "Bash" in result.error
        assert "Read" not in result.error

    def test_webfetch_call_with_passing_json_is_tool_violation(self, real_grader):
        result = _resolve(_verdict_stream(PASS_VERDICT, "WebFetch"), real_grader)

        assert result.outcome == Outcome.TOOL_VIOLATION
        assert "WebFetch" in result.error

    @pytest.mark.parametrize("tool_name", ["Bash", "WebFetch"])
    def test_tool_violation_outranks_parse_failure(self, tool_name):
        stdout = _stream(_tool_use_event(tool_name), _result_event("no json here"))

        result = _resolve(stdout)

        assert result.outcome == Outcome.TOOL_VIOLATION

    def test_non_zero_exit_is_cli_error_carrying_stderr(self):
        result = _resolve(
            _verdict_stream(PASS_VERDICT), exit_code=1, stderr="model not found"
        )

        assert result.outcome == Outcome.CLI_ERROR
        assert "model not found" in result.error

    def test_webfetch_call_with_non_zero_exit_is_cli_error(self):
        result = _resolve(_verdict_stream(PASS_VERDICT, "WebFetch"), exit_code=1)

        assert result.outcome == Outcome.CLI_ERROR

    def test_exit_zero_with_no_result_event_is_cli_error(self):
        result = _resolve(_stream(_tool_use_event("Read")))

        assert result.outcome == Outcome.CLI_ERROR
        assert "result" in result.error

    def test_result_event_flagged_is_error_is_cli_error_even_with_exit_zero(self):
        stdout = _stream(_result_event("model gone", is_error=True))

        result = _resolve(stdout)

        assert result.outcome == Outcome.CLI_ERROR
        assert "model gone" in result.error

    def test_timed_out_run_is_timeout_even_with_other_failures(self):
        result = _resolve(
            _stream(_tool_use_event("WebFetch")),
            exit_code=None,
            timed_out=True,
        )

        assert result.outcome == Outcome.TIMEOUT

    def test_recorded_successful_run_resolves_to_pass_with_a_passing_grader(self):
        result = _resolve(_fixture_text("pass-readonly.jsonl"))

        assert result.outcome == Outcome.PASS

    def test_recorded_bad_model_run_resolves_to_cli_error_carrying_stderr(self):
        result = _resolve(
            _fixture_text("bad-model.jsonl"),
            exit_code=1,
            stderr=_fixture_text("bad-model.stderr.txt"),
        )

        assert result.outcome == Outcome.CLI_ERROR
        assert "unrecognized_model" in result.error

    @pytest.mark.parametrize(
        ("stdout", "record_fields"),
        [
            pytest.param(
                _verdict_stream(PASS_VERDICT, "WebFetch"), {}, id="tool-violation"
            ),
            pytest.param(_stream(_result_event("no json")), {}, id="parse-failure"),
            pytest.param(
                _verdict_stream(PASS_VERDICT), {"exit_code": 1}, id="cli-error"
            ),
            pytest.param(
                _verdict_stream(PASS_VERDICT),
                {"exit_code": None, "timed_out": True},
                id="timeout",
            ),
        ],
    )
    def test_grader_is_not_called_when_an_earlier_check_decides_the_outcome(
        self, stdout, record_fields
    ):
        calls = []

        def spy(agent_json):
            calls.append(agent_json)
            return True, []

        _resolve(stdout, spy, **record_fields)

        assert calls == []

    def test_cost_and_model_id_come_from_the_transcript(self):
        result = _resolve(_verdict_stream(PASS_VERDICT))

        assert result.cost_usd == pytest.approx(TRIAL_COST)
        assert result.model_id == HAIKU_MODEL_ID
        assert result.model_id_note is None

    def test_cost_is_kept_for_a_failed_trial(self):
        result = _resolve(_verdict_stream(PASS_VERDICT, "WebFetch"))

        assert result.cost_usd == pytest.approx(TRIAL_COST)

    def test_trial_with_a_reported_cost_is_marked_reported(self):
        assert _resolve(_verdict_stream(PASS_VERDICT)).cost_reported is True

    def test_trial_with_no_result_event_has_zero_cost_marked_unreported(self):
        result = _resolve(_stream(_tool_use_event("Read")), exit_code=1)

        assert (result.cost_usd, result.cost_reported) == (0.0, False)

    def test_trial_with_a_non_finite_cost_has_zero_cost_marked_unreported(self):
        stdout = _stream(
            _result_event(json.dumps(PASS_VERDICT), total_cost_usd=float("nan"))
        )

        result = _resolve(stdout)

        assert (result.cost_usd, result.cost_reported) == (0.0, False)

    def test_session_config_comes_from_the_transcript_init_event(self):
        stdout = _stream(_init_event(), _result_event(json.dumps(PASS_VERDICT)))

        result = _resolve(stdout)

        assert result.session_config == _expected_session_config(HAIKU_MODEL_ID)


class TestErrorTextIsScrubbed:
    def test_the_staged_directory_in_a_cli_error_becomes_a_placeholder(self):
        staged = Path(tempfile.mkdtemp(prefix=runner.TEMP_DIR_PREFIX))
        try:
            result = _resolve(
                "",
                exit_code=1,
                stderr=f"cannot read {staged}/form.html",
                cwd=staged,
            )
        finally:
            staged.rmdir()

        assert "<staged>/form.html" in result.error
        assert str(staged) not in result.error

    def test_a_real_failed_trial_reports_no_part_of_its_temp_directory(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, exit_code=1, stderr_cwd=True)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))
        result = outcome.resolve_outcome(
            record,
            transcript.parse_stream(record.stdout),
            ENABLED,
            lambda agent_json: (True, []),
        )

        ran_in = stub.calls[0]["cwd"]
        assert "<staged>/form.html" in result.error
        assert ran_in not in result.error
        assert str(record.cwd) not in result.error


class TestScrubPaths:
    def test_home_directory_becomes_a_tilde(self, tmp_path, monkeypatch):
        home = tmp_path / "alice"
        monkeypatch.setenv("HOME", str(home))

        scrubbed = path_scrub.scrub_paths(f"cannot open {home}/bin/claude", None)

        assert scrubbed == "cannot open ~/bin/claude"

    def test_temp_directory_becomes_a_placeholder(self, monkeypatch):
        monkeypatch.setenv("HOME", "/nowhere/home")
        temp = tempfile.gettempdir()

        scrubbed = path_scrub.scrub_paths(f"cannot write {temp}/x.json", None)

        assert scrubbed == "cannot write <tmp>/x.json"

    def test_staged_directory_becomes_a_placeholder_even_inside_the_temp_directory(
        self,
    ):
        staged = Path(tempfile.mkdtemp(prefix=runner.TEMP_DIR_PREFIX))
        try:
            scrubbed = path_scrub.scrub_paths(f"cannot read {staged}/form.html", staged)
        finally:
            staged.rmdir()

        assert scrubbed == "cannot read <staged>/form.html"

    def test_the_resolved_spelling_of_a_directory_is_scrubbed_too(self, tmp_path):
        link = tmp_path / "link"
        target = tmp_path / "target"
        target.mkdir()
        link.symlink_to(target)

        scrubbed = path_scrub.scrub_paths(f"in {target.resolve()}/x", link)

        assert scrubbed == "in <staged>/x"

    def test_home_inside_the_temp_directory_is_scrubbed_as_home(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "alice"
        monkeypatch.setenv("HOME", str(home))

        scrubbed = path_scrub.scrub_paths(f"{home}/bin and {tmp_path}/other", None)

        assert scrubbed.startswith("~/bin and <tmp>")

    def test_a_root_home_directory_leaves_the_text_alone(self, monkeypatch):
        monkeypatch.setenv("HOME", "/")

        assert path_scrub.scrub_paths("/usr/bin/claude", None) == "/usr/bin/claude"


class TestFormatUsd:
    @pytest.mark.parametrize(
        ("amount", "text"),
        [(0.004664, "$0.0047"), (0, "$0.0000"), (12.5, "$12.5000")],
    )
    def test_amounts_show_four_decimals(self, amount, text):
        assert format_usd(amount) == text


class TestTotalCost:
    def test_ten_tenths_sum_to_exactly_one(self):
        assert total_cost_usd([0.1] * 10) == 1.0

    def test_no_amounts_sum_to_zero(self):
        assert total_cost_usd([]) == 0.0


class TestMessageCaps:
    def test_error_is_capped_at_the_cause_limit(self):
        errored = _resolve(_verdict_stream(PASS_VERDICT), exit_code=1, stderr="e" * 900)

        assert len(errored.error) == CAUSE_LIMIT

    def test_a_single_long_grader_message_is_capped_at_the_cause_limit(self):
        long_message = "m" * (2 * CAUSE_LIMIT)
        graded = _resolve(
            _verdict_stream(PASS_VERDICT), lambda j: (False, [long_message])
        )

        assert [len(m) for m in graded.grader_messages] == [CAUSE_LIMIT]

    def test_combined_grader_messages_are_capped_at_the_cause_limit(self):
        first_length = CAUSE_LIMIT * 3 // 5
        messages = ["a" * first_length, "b" * CAUSE_LIMIT, "c" * CAUSE_LIMIT]

        graded = _resolve(_verdict_stream(PASS_VERDICT), lambda j: (False, messages))

        assert graded.grader_messages == (
            "a" * first_length,
            "b" * (CAUSE_LIMIT - first_length),
        )

    def test_messages_that_fit_the_cap_are_kept_whole(self):
        messages = ["a" * 100, "b" * 100]

        graded = _resolve(_verdict_stream(PASS_VERDICT), lambda j: (False, messages))

        assert graded.grader_messages == tuple(messages)


# --- Artifact assembly -------------------------------------------------------


class FixedRng:
    """Stands in for `random.Random`: always returns the same bits."""

    def getrandbits(self, bits: int) -> int:
        assert bits == 16
        return 0x0AB3


def _trial_result(
    outcome_value: Outcome,
    cost=TRIAL_COST,
    model_id=None,
    note=None,
    session_config=None,
    cost_reported=True,
) -> outcome.TrialResult:
    return outcome.TrialResult(
        outcome=outcome_value,
        cost_usd=cost,
        model_id=model_id,
        model_id_note=note,
        grader_messages=(),
        error=None,
        session_config=session_config,
        cost_reported=cost_reported,
    )


def _arm(label: str = CANDIDATE_LABEL) -> Arm:
    profile = tools.ToolProfile(
        enabled_tools=("Read",), withheld_tools=(), refused_tools=()
    )
    return Arm(label=label, model="haiku", effort="high", profile=profile)


def _arm_run(
    label: str, results: list[outcome.TrialResult], expected_clean: bool = False
) -> run_types.ArmRun:
    fixture = run_types.FixtureTrials(
        stem="f",
        kind=fixture_resolution.FixtureKind.FILE,
        expected_clean=expected_clean,
        results=results,
    )
    return run_types.ArmRun(
        arm=_arm(label), trials_per_fixture=1, fixture_trials=[fixture]
    )


def _metadata() -> run_types.RunMetadata:
    return run_types.RunMetadata(
        run_id=RUN_ID,
        created=NOW,
        git_sha=None,
        agent="scout",
        knowledge_dir="knowledge",
    )


# One planned trial per arm, so an arm's per-trial estimate is its whole estimate.
ARM_ESTIMATE = 0.005


def _run_estimate(trials_per_arm: int = 1) -> estimate.RunEstimate:
    return estimate.RunEstimate(
        by_arm=(
            (BASELINE_LABEL, ARM_ESTIMATE * trials_per_arm),
            (CANDIDATE_LABEL, ARM_ESTIMATE * trials_per_arm),
        ),
        trials_per_arm=trials_per_arm,
    )


def _built_arm(
    results: list[outcome.TrialResult],
    expected_clean: bool = False,
    trials_per_arm: int = 1,
) -> dict:
    run = _arm_run(CANDIDATE_LABEL, results, expected_clean)
    built = artifact.build_artifact(
        _metadata(), [run], _run_estimate(trials_per_arm), None
    )
    return built["arms"][0]


class TestRunId:
    def test_run_id_joins_utc_time_agent_candidate_model_effort_and_four_hex(self):
        run_id = run_types.make_run_id(NOW, "scout", "haiku", "high", FixedRng())

        assert run_id == RUN_ID


class TestArtifactStatus:
    def test_run_without_an_abort_reason_is_complete(self):
        built = artifact.build_artifact(_metadata(), [], _run_estimate(), None)

        assert (built["status"], built["abort_reason"]) == ("complete", None)

    @pytest.mark.parametrize(
        "reason", list(AbortReason), ids=lambda reason: reason.value
    )
    def test_run_with_an_abort_reason_is_incomplete_and_names_it(self, reason):
        built = artifact.build_artifact(_metadata(), [], _run_estimate(), reason)

        assert (built["status"], built["abort_reason"]) == ("incomplete", reason.value)

    def test_abort_reasons_use_the_contract_strings(self):
        assert [reason.value for reason in AbortReason] == [
            "max-cost",
            "infra-failure",
            "interrupt",
            "harness-error",
        ]


class TestArmTotals:
    def test_every_outcome_is_counted_with_zeros_included(self):
        arm = _built_arm(
            [_trial_result(Outcome.PASS), _trial_result(Outcome.PARSE_FAILURE)]
        )

        assert arm["totals"] == {
            "pass": 1,
            "graded_fail": 0,
            "parse_failure": 1,
            "tool_violation": 0,
            "cli_error": 0,
            "timeout": 0,
            "clean_fixture_failures": 0,
            "actual_cost_usd": pytest.approx(0.02),
            "estimated_cost_charged_usd": 0.0,
        }

    def test_trial_without_a_reported_cost_is_flagged_and_charged_the_arms_per_trial_estimate(
        self,
    ):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS),
                _trial_result(Outcome.TIMEOUT, cost=0.0, cost_reported=False),
                _trial_result(Outcome.CLI_ERROR, cost=0.0, cost_reported=False),
            ],
            trials_per_arm=3,
        )

        trials = arm["fixtures"][0]["trials"]
        assert [trial["cost_reported"] for trial in trials] == [True, False, False]
        assert arm["totals"]["actual_cost_usd"] == pytest.approx(TRIAL_COST)
        assert arm["totals"]["estimated_cost_charged_usd"] == pytest.approx(
            2 * ARM_ESTIMATE
        )

    def test_arm_records_its_estimated_cost_from_the_run_estimate(self):
        arm = _built_arm([_trial_result(Outcome.PASS)], trials_per_arm=4)

        assert arm["estimated_cost_usd"] == pytest.approx(4 * ARM_ESTIMATE)

    def test_clean_fixture_failures_count_every_non_pass_on_clean_fixtures(self):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS),
                _trial_result(Outcome.GRADED_FAIL),
                _trial_result(Outcome.CLI_ERROR),
            ],
            expected_clean=True,
        )

        assert arm["totals"]["clean_fixture_failures"] == 2

    def test_non_clean_fixtures_never_count_as_clean_fixture_failures(self):
        arm = _built_arm([_trial_result(Outcome.GRADED_FAIL)], expected_clean=False)

        assert arm["totals"]["clean_fixture_failures"] == 0

    def test_model_id_is_reported_when_every_reporting_trial_agrees(self):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS, model_id="m-1"),
                _trial_result(Outcome.CLI_ERROR, note="no result"),
            ]
        )

        assert (arm["model_id"], arm["model_id_note"]) == ("m-1", None)

    def test_conflicting_model_ids_yield_null_with_a_note_naming_them(self):
        arm = _built_arm(
            [
                _trial_result(Outcome.PASS, model_id="m-1"),
                _trial_result(Outcome.PASS, model_id="m-2"),
            ]
        )

        assert arm["model_id"] is None
        assert "m-1" in arm["model_id_note"] and "m-2" in arm["model_id_note"]

    def test_no_reported_model_id_yields_null_with_the_trial_note(self):
        arm = _built_arm([_trial_result(Outcome.CLI_ERROR, note="no result event")])

        assert (arm["model_id"], arm["model_id_note"]) == (None, "no result event")


class TestArtifactSessionConfig:
    def test_arm_session_config_comes_from_its_first_trial_with_an_init_event(self):
        first = {"model": "first"}
        arm = _built_arm(
            [
                _trial_result(Outcome.CLI_ERROR),
                _trial_result(Outcome.PASS, session_config=first),
                _trial_result(Outcome.PASS, session_config={"model": "later"}),
            ]
        )

        assert arm["session_config"] == first

    def test_arm_without_any_init_event_has_null_session_config(self):
        assert _built_arm([_trial_result(Outcome.CLI_ERROR)])["session_config"] is None

    def test_run_level_session_config_is_the_baseline_arms_whatever_the_arm_order(
        self,
    ):
        baseline = _arm_run(
            BASELINE_LABEL,
            [_trial_result(Outcome.PASS, session_config={"model": "base"})],
        )
        candidate = _arm_run(
            CANDIDATE_LABEL,
            [_trial_result(Outcome.PASS, session_config={"model": "cand"})],
        )

        built = artifact.build_artifact(
            _metadata(), [candidate, baseline], _run_estimate(), None
        )

        assert built["session_config"] == {"model": "base"}


# --- Fixture resolution and candidate validation -----------------------------


class TestDescribeFixture:
    def test_file_stem_drops_one_extension_and_kind_is_file(self, fixture_root):
        path = _make_file_fixture(fixture_root, "a.b.html")

        assert fixture_resolution.describe_fixture(path) == (
            "a.b",
            fixture_resolution.FixtureKind.FILE,
        )

    def test_directory_stem_is_its_name_and_kind_is_directory(self, fixture_root):
        path = _make_directory_fixture(fixture_root)

        assert fixture_resolution.describe_fixture(path) == (
            "service",
            fixture_resolution.FixtureKind.DIRECTORY,
        )


class TestResolveFixtures:
    def test_agent_named_by_no_expected_entry_is_refused_saying_so(
        self, expected_dir, fixture_root
    ):
        _write_expected(expected_dir, "other-case", "other", "pass")

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures(
                "scout", None, expected_dir, fixture_root
            )

        assert "no evals/expected entry names it" in str(excinfo.value)

    def test_entries_without_a_matching_fixture_are_refused_listing_the_stems(
        self, expected_dir, fixture_root
    ):
        _write_expected(expected_dir, "ghost-case", "scout", "pass")
        _write_expected(expected_dir, "phantom-case", "scout", "fail")

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures(
                "scout", None, expected_dir, fixture_root
            )

        message = str(excinfo.value)
        assert "entries exist but no fixture matches" in message
        assert "ghost-case" in message and "phantom-case" in message
        assert "no evals/expected entry names it" not in message

    def test_runnable_fixtures_carry_kind_path_and_expected_clean(
        self, expected_dir, fixture_root
    ):
        _write_expected(expected_dir, "clean-form", "scout", "pass")
        _write_expected(expected_dir, "layered-svc", "scout", "fail")
        form = _make_file_fixture(fixture_root, "clean-form.html")
        service = fixture_root / "layered-svc"
        service.mkdir()

        resolved = fixture_resolution.resolve_fixtures(
            "scout", None, expected_dir, fixture_root
        )

        assert resolved == [
            fixture_resolution.ResolvedFixture(
                stem="clean-form",
                path=form,
                kind=fixture_resolution.FixtureKind.FILE,
                expected_clean=True,
            ),
            fixture_resolution.ResolvedFixture(
                stem="layered-svc",
                path=service,
                kind=fixture_resolution.FixtureKind.DIRECTORY,
                expected_clean=False,
            ),
        ]

    def test_missing_fixtures_directory_is_refused_naming_it(
        self, expected_dir, tmp_path
    ):
        _write_expected(expected_dir, "clean-form", "scout", "pass")
        missing = tmp_path / "no-fixtures"

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures("scout", None, expected_dir, missing)

        assert str(missing) in str(excinfo.value)

    def test_malformed_expected_json_is_refused_naming_the_file(
        self, expected_dir, fixture_root
    ):
        (expected_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures(
                "scout", None, expected_dir, fixture_root
            )

        assert str(expected_dir / "broken.json") in str(excinfo.value)


class TestValidateCandidate:
    @pytest.mark.parametrize(
        ("model", "effort"),
        [
            (None, None),
            ("haiku", "low"),
            ("claude-opus-4-8", "max"),
            ("sonnet", None),
            (None, "xhigh"),
        ],
    )
    def test_values_in_the_agent_contract_are_accepted(self, model, effort):
        plan.validate_candidate(model, effort)

    @pytest.mark.parametrize("model", ["gpt-4", "../evil", "", "Haiku"])
    def test_model_outside_the_contract_is_refused_listing_valid_values(self, model):
        with pytest.raises(UsageError) as excinfo:
            plan.validate_candidate(model, None)

        message = str(excinfo.value)
        assert "--model" in message
        assert "haiku" in message and "sonnet" in message

    @pytest.mark.parametrize("effort", ["hgih", "ultracode", ""])
    def test_effort_outside_the_contract_is_refused_listing_valid_values(self, effort):
        with pytest.raises(UsageError) as excinfo:
            plan.validate_candidate(None, effort)

        message = str(excinfo.value)
        assert "--effort" in message
        assert "low" in message and "high" in message


# --- Artifact store ----------------------------------------------------------


def _failing_replace(*_args, **_kwargs):
    raise OSError("disk full")


def _store_with_failing_replace(monkeypatch) -> None:
    """Make the final move fail while leaving every other os call working."""
    monkeypatch.setattr(artifact_store.os, "replace", _failing_replace)


class TestArtifactStore:
    def test_reservation_creates_an_empty_placeholder(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        assert path == tmp_path / f"{RUN_ID}.json"
        assert path.read_text(encoding="utf-8") == ""

    def test_reserving_an_existing_artifact_is_refused_and_leaves_it_unchanged(
        self, tmp_path
    ):
        existing = tmp_path / f"{RUN_ID}.json"
        existing.write_text("sentinel", encoding="utf-8")

        with pytest.raises(UsageError) as excinfo:
            artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        assert "already exists" in str(excinfo.value)
        assert existing.read_text(encoding="utf-8") == "sentinel"

    def test_reserving_in_a_missing_directory_is_refused(self, tmp_path):
        with pytest.raises(UsageError) as excinfo:
            artifact_store.reserve_artifact_path(tmp_path / "nope", RUN_ID)

        assert "runs directory" in str(excinfo.value)

    def test_write_replaces_the_placeholder_with_the_full_text(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        artifact_store.write_artifact(path, '{"a": 1}\n')

        assert path.read_text(encoding="utf-8") == '{"a": 1}\n'
        assert [p.name for p in tmp_path.iterdir()] == [path.name]

    def test_failed_write_leaves_the_destination_untouched_and_no_temp_file(
        self, tmp_path, monkeypatch
    ):
        path = tmp_path / "a.json"
        path.write_text("original", encoding="utf-8")
        _store_with_failing_replace(monkeypatch)

        with pytest.raises(OSError, match="disk full"):
            artifact_store.write_artifact(path, "replacement")

        assert path.read_text(encoding="utf-8") == "original"
        assert [p.name for p in tmp_path.iterdir()] == ["a.json"]

    def test_unwritten_placeholder_is_removed_when_the_block_exits(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        with artifact_store.release_if_unwritten(path):
            pass

        assert not path.exists()

    def test_written_artifact_is_kept_when_the_block_exits(self, tmp_path):
        path = artifact_store.reserve_artifact_path(tmp_path, RUN_ID)

        with artifact_store.release_if_unwritten(path):
            artifact_store.write_artifact(path, "{}\n")

        assert path.read_text(encoding="utf-8") == "{}\n"


# --- The CLI, end to end through a stub binary -------------------------------


def _verdict_call(
    verdict: dict, model_id: str, *tool_names: str, cost: float = TRIAL_COST
) -> dict:
    events = [_tool_use_event(*tool_names)] if tool_names else []
    result = _result_event(
        json.dumps(verdict), model_usage={model_id: {}}, total_cost_usd=cost
    )
    return {"stdout": _stream(_init_event(model_id), *events, result)}


def _unparseable_call(model_id: str) -> dict:
    result = _result_event("No JSON here.", model_usage={model_id: {}})
    return {"stdout": _stream(_init_event(model_id), result)}


@dataclass
class World:
    """A throwaway repo slice: agents, expected entries, fixtures and a runs dir."""

    root: Path
    deps: model_effort_ab.Deps

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def expected_dir(self) -> Path:
        return self.root / "expected"

    @property
    def stub_dir(self) -> Path:
        return self.root / "stub"

    @property
    def artifacts(self) -> list[Path]:
        return sorted(self.runs_dir.iterdir())

    @property
    def artifact_path(self) -> Path:
        return self.runs_dir / f"{RUN_ID}.json"


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
    deps = model_effort_ab.Deps(
        clock=lambda: NOW,
        rng=FixedRng(),
        read_git_sha=lambda: "abc123",
        agents_dir=agents,
        expected_dir=expected,
        fixtures_dir=fixtures,
        pricing_table=TEST_PRICING,
    )
    return World(tmp_path, deps)


def _cli(
    world: World,
    stub: StubClaude,
    *args: str,
    yes: bool = True,
    deps: model_effort_ab.Deps | None = None,
) -> int:
    """Run the CLI; `yes` passes the approval gate unless a test exercises the gate itself."""
    argv = [
        *args,
        *(["--yes"] if yes else []),
        "--claude-bin",
        str(stub.path),
        "--runs-dir",
        str(world.runs_dir),
    ]
    return model_effort_ab.main(argv, deps=deps or world.deps)


def assert_nothing_ran(stub: StubClaude, world: World) -> None:
    assert stub.calls == [], "a trial ran"
    assert world.artifacts == [], "an artifact or placeholder was left behind"


def _run_over_max_cost(world: World, stub: StubClaude, **cli_options) -> int:
    """Run the CLI with a spend limit under the run's estimate, so startup refuses it."""
    return _cli(
        world,
        stub,
        "scout",
        "--model",
        "haiku",
        "--trials",
        str(SCOUT_TRIALS),
        "--max-cost",
        str(MAX_COST_BELOW_ESTIMATE),
        **cli_options,
    )


def _written(world: World) -> dict:
    return json.loads(world.artifacts[0].read_text(encoding="utf-8"))


def _arm_block(written: dict, label: str) -> dict:
    return {arm["label"]: arm for arm in written["arms"]}[label]


def _passing_stub(world: World, **behavior) -> StubClaude:
    return StubClaude(
        world.stub_dir, **_verdict_call(PASS_VERDICT, SONNET_MODEL_ID), **behavior
    )


def _two_arm_stub(world: World) -> StubClaude:
    """Calls alternate baseline, candidate over clean-form x3 then layered-svc x3.

    The candidate's second clean-form trial returns no JSON and its first
    layered-svc trial calls WebFetch.
    """
    stub = StubClaude(world.stub_dir)
    baseline_pass = _verdict_call(PASS_VERDICT, SONNET_MODEL_ID)
    baseline_fail = _verdict_call(FAIL_VERDICT, SONNET_MODEL_ID)
    candidate_pass = _verdict_call(PASS_VERDICT, HAIKU_MODEL_ID)
    candidate_fail = _verdict_call(FAIL_VERDICT, HAIKU_MODEL_ID)
    stub.queue(
        baseline_pass,
        candidate_pass,
        baseline_pass,
        _unparseable_call(HAIKU_MODEL_ID),
        baseline_pass,
        candidate_pass,
        baseline_fail,
        _verdict_call(FAIL_VERDICT, HAIKU_MODEL_ID, "WebFetch"),
        baseline_fail,
        candidate_fail,
        baseline_fail,
        candidate_fail,
    )
    return stub


def _run_two_arm_scenario(world: World) -> tuple[int, dict, StubClaude]:
    stub = _two_arm_stub(world)
    code = _cli(world, stub, "scout", "--model", "haiku", "--trials", str(SCOUT_TRIALS))
    return code, _written(world), stub


def _trial(outcome_name: str, error: str | None = None) -> dict:
    return {
        "outcome": outcome_name,
        "cost_usd": TRIAL_COST,
        "cost_reported": True,
        "grader_messages": [],
        "error": error,
    }


def _fixture_block(stem: str, kind: str, clean: bool, trials: list[dict]) -> dict:
    return {"stem": stem, "kind": kind, "expected_clean": clean, "trials": trials}


class TestReadGitHeadSha:
    @pytest.mark.parametrize(
        "error",
        [OSError("git missing"), subprocess.CalledProcessError(128, "git")],
        ids=["git-not-installed", "not-a-repository"],
    )
    def test_a_failing_git_yields_none(self, monkeypatch, error):
        def failing_run(*_args, **_kwargs):
            raise error

        monkeypatch.setattr(model_effort_ab.subprocess, "run", failing_run)

        assert model_effort_ab._read_git_head_sha() is None

    def test_the_real_repository_yields_a_full_commit_hash(self):
        sha = model_effort_ab._read_git_head_sha()

        assert sha is not None and re.fullmatch(r"[0-9a-f]{40}", sha)


class TestDepsDefaults:
    def test_default_deps_use_the_shipped_directories_and_collaborators(self):
        deps = model_effort_ab.Deps()

        assert (deps.agents_dir, deps.expected_dir, deps.fixtures_dir) == (
            paths.AGENTS_DIR,
            paths.EXPECTED_DIR,
            paths.FIXTURES_DIR,
        )
        assert deps.run_trial is runner.run_trial
        assert deps.read_git_sha is model_effort_ab._read_git_head_sha

    def test_default_stdin_is_the_process_stdin(self, monkeypatch):
        stream = io.StringIO()
        monkeypatch.setattr(sys, "stdin", stream)

        assert model_effort_ab.Deps().stdin is stream

    @pytest.mark.parametrize("is_tty", [True, False])
    def test_default_tty_check_follows_the_process_stdin(self, monkeypatch, is_tty):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: is_tty))

        assert model_effort_ab.Deps().stdin_is_tty() is is_tty

    def test_default_clock_reads_a_timezone_aware_time(self):
        assert model_effort_ab.Deps().clock().tzinfo is not None

    def test_each_default_deps_has_its_own_random_generator(self):
        assert model_effort_ab.Deps().rng is not model_effort_ab.Deps().rng

    def test_default_pricing_table_is_the_shipped_one(self):
        assert model_effort_ab.Deps().pricing_table == pricing.load_pricing(
            paths.PRICING_PATH
        )


class TestTwoArmRun:
    def test_run_metadata_records_identity_status_and_the_baseline_session_config(
        self, world
    ):
        code, written, _ = _run_two_arm_scenario(world)

        assert code == 0
        assert [path.name for path in world.artifacts] == [f"{RUN_ID}.json"]
        assert {key: value for key, value in written.items() if key != "arms"} == {
            "run_id": RUN_ID,
            "status": "complete",
            "abort_reason": None,
            "created": "2026-10-08T12:30:45Z",
            "git_sha": "abc123",
            "agent": "scout",
            "grader": "expected-findings",
            "fidelity": "read-only-profile",
            "knowledge_dir": "plugins/dev-team/knowledge",
            "session_config": _expected_session_config(SONNET_MODEL_ID),
        }

    def test_artifact_git_sha_is_null_when_the_repository_has_no_head(self, world):
        deps = dataclasses.replace(world.deps, read_git_sha=lambda: None)

        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=deps,
        )

        assert _written(world)["git_sha"] is None

    def test_baseline_arm_records_configuration_trials_and_totals(self, world):
        _, written, _ = _run_two_arm_scenario(world)

        assert _arm_block(written, BASELINE_LABEL) == {
            "label": "baseline",
            "model": "sonnet",
            "model_id": SONNET_MODEL_ID,
            "model_id_note": None,
            "effort": "high",
            "tools_enabled": ["Read", "Grep"],
            "tools_withheld": ["mcp__x__y", "Bash(graphify *)"],
            "trials": SCOUT_TRIALS,
            "estimated_cost_usd": pytest.approx(BASELINE_TWO_ARM_ESTIMATE),
            "session_config": _expected_session_config(SONNET_MODEL_ID),
            "fixtures": [
                _fixture_block("clean-form", "file", True, [_trial("pass")] * 3),
                _fixture_block("layered-svc", "directory", False, [_trial("pass")] * 3),
            ],
            "totals": {
                "timeout": 0,
                "cli_error": 0,
                "tool_violation": 0,
                "parse_failure": 0,
                "graded_fail": 0,
                "pass": 6,
                "clean_fixture_failures": 0,
                "actual_cost_usd": pytest.approx(0.06),
                "estimated_cost_charged_usd": 0.0,
            },
        }

    def test_candidate_arm_records_its_parse_failure_and_tool_violation(self, world):
        _, written, _ = _run_two_arm_scenario(world)

        assert _arm_block(written, CANDIDATE_LABEL) == {
            "label": "candidate",
            "model": "haiku",
            "model_id": HAIKU_MODEL_ID,
            "model_id_note": None,
            "effort": "high",
            "tools_enabled": ["Read", "Grep"],
            "tools_withheld": ["mcp__x__y", "Bash(graphify *)"],
            "trials": SCOUT_TRIALS,
            "estimated_cost_usd": pytest.approx(CANDIDATE_TWO_ARM_ESTIMATE),
            "session_config": _expected_session_config(HAIKU_MODEL_ID),
            "fixtures": [
                _fixture_block(
                    "clean-form",
                    "file",
                    True,
                    [
                        _trial("pass"),
                        _trial("parse_failure", "no JSON object in the result text"),
                        _trial("pass"),
                    ],
                ),
                _fixture_block(
                    "layered-svc",
                    "directory",
                    False,
                    [
                        _trial(
                            "tool_violation", "tools outside the enabled set: WebFetch"
                        ),
                        _trial("pass"),
                        _trial("pass"),
                    ],
                ),
            ],
            "totals": {
                "timeout": 0,
                "cli_error": 0,
                "tool_violation": 1,
                "parse_failure": 1,
                "graded_fail": 0,
                "pass": 4,
                "clean_fixture_failures": 1,
                "actual_cost_usd": pytest.approx(0.06),
                "estimated_cost_charged_usd": 0.0,
            },
        }

    def test_arms_alternate_trial_by_trial_fixture_by_fixture(self, world):
        _, _, stub = _run_two_arm_scenario(world)

        calls = stub.calls
        assert [_flag_value(c["argv"], "--model") for c in calls] == [
            "sonnet",
            "haiku",
        ] * 6
        staged = [sorted(c["files_before"]) for c in calls]
        assert staged[:6] == [["clean-form.html"]] * 6
        assert staged[6:] == [["layered-svc/src/app.py"]] * 6

    def test_candidate_inherits_baseline_values_for_omitted_flags(self, world):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            "scout",
            "--fixtures",
            "clean-form",
            "--effort",
            "low",
            "--trials",
            "1",
        )

        written = _written(world)
        baseline = _arm_block(written, BASELINE_LABEL)
        candidate = _arm_block(written, CANDIDATE_LABEL)
        assert (baseline["model"], baseline["effort"]) == ("sonnet", "high")
        assert (candidate["model"], candidate["effort"]) == ("sonnet", "low")

    def test_fixtures_flag_restricts_the_run_to_the_named_stems(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "layered-svc",
            "--trials",
            "1",
        )

        assert code == 0
        assert len(stub.calls) == 2
        assert all("layered-svc/src/app.py" in c["files_before"] for c in stub.calls)

    def test_enabled_tools_reach_the_cli_and_withheld_tools_only_the_artifact(
        self, world
    ):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "clean-form",
            "--trials",
            "1",
        )

        for call in stub.calls:
            assert _flag_value(call["argv"], "--tools") == "Read,Grep"
            assert not any("mcp__" in arg for arg in call["argv"])
        for arm in _written(world)["arms"]:
            assert arm["tools_withheld"] == ["mcp__x__y", "Bash(graphify *)"]

    def test_artifact_path_is_reserved_empty_before_the_first_trial(self, world):
        stub = _passing_stub(world, observe=str(world.artifact_path))

        _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "clean-form",
            "--trials",
            "1",
        )

        assert stub.calls[0]["observed"] == {"exists": True, "size": 0}

    def test_trial_that_times_out_is_recorded_as_a_timeout_in_the_artifact(self, world):
        _cli(
            world,
            StubClaude(world.stub_dir),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=_deps_timing_out(world),
        )

        baseline = _arm_block(_written(world), BASELINE_LABEL)
        trial = baseline["fixtures"][0]["trials"][0]
        assert baseline["totals"]["timeout"] == 1
        assert (trial["outcome"], trial["error"]) == (
            "timeout",
            "trial exceeded the time limit",
        )


class TestPreRunRefusals:
    def test_existing_artifact_path_exits_2_before_any_trial_and_stays_unchanged(
        self, world
    ):
        stub = StubClaude(world.stub_dir)
        world.artifact_path.write_text("sentinel", encoding="utf-8")

        code = _cli(world, stub, "scout", "--model", "haiku")

        assert code == 2
        assert stub.calls == []
        assert world.artifact_path.read_text(encoding="utf-8") == "sentinel"

    def test_collision_message_says_what_is_wrong_and_how_to_fix_it(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)
        world.artifact_path.write_text("x", encoding="utf-8")

        _cli(world, stub, "scout", "--model", "haiku")

        stderr = capsys.readouterr().err
        assert "already exists" in stderr and "rerun" in stderr

    def test_unknown_agent_exits_2_listing_valid_agents_and_writes_nothing(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "no-such-agent")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "no-such-agent" in stderr
        assert "scout" in stderr and "lonely" in stderr
        assert_nothing_ran(stub, world)

    def test_unknown_fixture_exits_2_naming_it_and_listing_valid_stems(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", "clean-form,nope")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "nope" in stderr
        assert "clean-form" in stderr and "layered-svc" in stderr
        assert_nothing_ran(stub, world)

    def test_fixture_whose_expected_entry_names_another_agent_exits_2(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", "other-only")

        assert code == 2
        assert "other-only" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_agent_with_no_expected_entries_exits_2_stating_no_fixtures_found(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "lonely")

        assert code == 2
        assert "no fixtures were found" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_write_capable_agent_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "write-capable")

        assert code == 2
        assert "write-capable agents are not supported yet" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_missing_runs_directory_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        world.runs_dir.rmdir()

        code = _cli(world, stub, "scout", "--model", "haiku")

        assert code == 2
        assert "runs directory" in capsys.readouterr().err
        assert stub.calls == []

    def test_malformed_expected_json_exits_2_naming_the_file(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        broken = world.expected_dir / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        code = _cli(world, stub, "scout")

        assert code == 2
        assert str(broken) in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_misspelled_candidate_effort_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--effort", "hgih")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "hgih" in stderr and "high" in stderr
        assert_nothing_ran(stub, world)

    def test_candidate_model_with_path_characters_exits_2_before_any_trial(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--model", "../../etc")

        assert code == 2
        assert "--model" in capsys.readouterr().err
        assert_nothing_ran(stub, world)


def _add_agent(world: World, name: str) -> None:
    """Add a read-only agent with one fixture, so a run over it has one fixture."""
    _write_agent(world.deps.agents_dir, name, "Read", model="sonnet", effort="high")
    _write_expected(world.expected_dir, f"{name}-case", name, "pass")
    _make_file_fixture(world.deps.fixtures_dir, f"{name}-case.txt")


class TestTrialDefaults:
    @pytest.mark.parametrize(
        ("agent", "trials"),
        [
            ("naming-review", 5),
            ("security-review", 10),
            ("correctness-review", 10),
            ("security-reviewer", 5),
        ],
    )
    def test_each_arm_runs_the_default_trials_for_the_agent(
        self, world, capsys, agent, trials
    ):
        _add_agent(world, agent)
        stub = _passing_stub(world)

        code = _cli(world, stub, agent, "--model", "haiku")

        assert code == 0
        assert len(stub.calls) == ARM_COUNT * trials
        assert (
            f"Trials per arm per fixture: {trials} "
            f"({'high-stakes default' if trials == 10 else 'default'})"
        ) in _stderr_lines(capsys)

    def test_explicit_trials_override_the_high_stakes_default(self, world, capsys):
        _add_agent(world, "security-review")
        stub = _passing_stub(world)

        code = _cli(world, stub, "security-review", "--model", "haiku", "--trials", "3")

        assert code == 0
        assert len(stub.calls) == ARM_COUNT * 3
        assert "Trials per arm per fixture: 3 (--trials)" in _stderr_lines(capsys)

    @pytest.mark.parametrize(
        "agent",
        ["security-review", "correctness-review", "architect", "security-engineer"],
    )
    def test_resolver_gives_every_high_stakes_agent_ten_trials(self, agent):
        assert run_types.resolve_trials(None, agent) == run_types.TrialCount(
            10, "high-stakes default"
        )

    def test_resolver_gives_other_agents_five_trials(self):
        assert run_types.resolve_trials(None, "security-reviewer") == (
            run_types.TrialCount(5, "default")
        )

    def test_resolver_prefers_the_flag_over_the_high_stakes_default(self):
        assert run_types.resolve_trials(2, "architect") == run_types.TrialCount(
            2, "--trials"
        )


class TestInvalidArgumentsAreRefusedBeforeTheEstimate:
    def _assert_refused(self, world, stub, capsys, code, fix_hint):
        err = capsys.readouterr().err
        assert code == 2
        assert fix_hint in err
        assert "Estimate" not in err
        assert_nothing_ran(stub, world)

    @pytest.mark.parametrize("trials", ["0", "-1", "abc", "2.5"])
    def test_non_positive_or_non_integer_trials_name_the_fix(
        self, world, capsys, trials
    ):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, "scout", "--model", "haiku", "--trials", trials)

        self._assert_refused(
            world, stub, capsys, excinfo.value.code, "a whole number of 1 or more"
        )

    def test_rubric_grader_is_refused_as_not_implemented(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--model", "haiku", "--grader", "rubric")

        self._assert_refused(
            world, stub, capsys, code, "not implemented yet; rubric grading is planned"
        )

    def test_unknown_grader_is_refused_listing_the_valid_ones(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, "scout", "--model", "haiku", "--grader", "vibes")

        self._assert_refused(
            world, stub, capsys, excinfo.value.code, "expected-findings"
        )

    def test_the_default_grader_is_accepted(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--grader",
            "expected-findings",
            "--trials",
            "1",
        )

        assert code == 0

    @pytest.mark.parametrize(
        "overrides",
        [
            [],
            ["--model", "sonnet", "--effort", "high"],
            ["--model", "sonnet"],
            ["--effort", "high"],
        ],
        ids=["no-overrides", "both-equal", "model-only-equal", "effort-only-equal"],
    )
    def test_candidate_equal_to_frontmatter_names_the_fix(
        self, world, capsys, overrides
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", *overrides)

        self._assert_refused(
            world, stub, capsys, code, "pass a different --model or --effort"
        )

    def test_a_partial_override_that_changes_one_value_is_accepted(self, world):
        stub = _passing_stub(world)

        code = _cli(world, stub, "scout", "--effort", "low", "--trials", "1")

        assert code == 0


class TestArtifactReservationAndWrite:
    def test_run_that_fails_before_any_trial_starts_leaves_no_placeholder(self, world):
        stdin = RaisingStdin(RuntimeError("stdin closed"))

        with pytest.raises(RuntimeError):
            _gated_cli(world, _passing_stub(world), stdin)

        assert world.artifacts == []

    def test_failed_final_write_prints_the_artifact_to_stdout_exits_1_and_leaves_no_files(
        self, world, capsys, monkeypatch
    ):
        stub = _passing_stub(world)
        _store_with_failing_replace(monkeypatch)

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "clean-form",
            "--trials",
            "1",
        )

        captured = capsys.readouterr()
        printed = json.loads(captured.out)
        assert code == 1
        assert printed["run_id"] == RUN_ID and printed["status"] == "complete"
        assert "stdout" in captured.err
        assert world.artifacts == []

    def test_failed_final_write_keeps_a_placeholder_that_gained_content(
        self, world, monkeypatch
    ):
        stub = _passing_stub(world, touch=str(world.artifact_path))
        _store_with_failing_replace(monkeypatch)

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "clean-form",
            "--trials",
            "1",
        )

        assert code == 1
        assert world.artifact_path.read_text(encoding="utf-8") == (
            "created during the run"
        )
        assert world.artifacts == [world.artifact_path]


def _file_fixture_of_size(
    root: Path, name: str, size: int
) -> fixture_resolution.ResolvedFixture:
    path = root / name
    path.write_bytes(b"x" * size)
    return fixture_resolution.ResolvedFixture(
        stem=path.stem,
        path=path,
        kind=fixture_resolution.FixtureKind.FILE,
        expected_clean=False,
    )


def _priced_arm(label: str, model: str) -> Arm:
    profile = tools.ToolProfile(
        enabled_tools=("Read",), withheld_tools=(), refused_tools=()
    )
    return Arm(label=label, model=model, effort="high", profile=profile)


class TestFixtureSize:
    def test_file_size_is_its_byte_count(self, tmp_path):
        fixture = _make_file_fixture(tmp_path, "form.html", "<form></form>")

        assert estimate.fixture_size_bytes(fixture) == 13

    def test_directory_size_sums_every_file_in_nested_directories(self, tmp_path):
        fixture = _make_directory_fixture(tmp_path)

        assert estimate.fixture_size_bytes(fixture) == 6 + 12 + 13


class TestEstimateRun:
    @pytest.fixture(autouse=True)
    def pinned_constants(self, monkeypatch):
        monkeypatch.setattr(estimate, "TOOL_TURN_MULTIPLIER", PINNED_TURN_MULTIPLIER)
        monkeypatch.setattr(estimate, "OUTPUT_TOKENS_PER_TRIAL", PINNED_OUTPUT_TOKENS)

    def _estimate(
        self, tmp_path, fixtures, arms=None, trials=3, pricing_table=TEST_PRICING
    ):
        # Each trial sends 865 system + 3000 fixture + 135 prompt chars = 1000 tokens,
        # doubled by the pinned turn multiplier.
        arms = arms or [
            _priced_arm("baseline", "sonnet"),
            _priced_arm("candidate", "haiku"),
        ]
        return estimate.estimate_run(arms, "s" * 865, fixtures, trials, pricing_table)

    def test_each_arm_costs_input_plus_output_priced_times_fixtures_times_trials(
        self, tmp_path
    ):
        fixtures = [
            _file_fixture_of_size(tmp_path, "a.txt", 3000),
            _file_fixture_of_size(tmp_path, "b.txt", 3000),
        ]

        result = self._estimate(tmp_path, fixtures)

        # Per trial across both fixtures: 4000 input tokens, 200 output tokens.
        # pricey: (4000*4 + 200*20) / 1e6 = 0.02, x3 trials. cheap: (4000*1 + 200*5) / 1e6 = 0.005, x3.
        assert result.cost_usd_for_arm("baseline") == pytest.approx(0.06)
        assert result.cost_usd_for_arm("candidate") == pytest.approx(0.015)
        assert result.estimated_total_usd == pytest.approx(0.075)

    def test_directory_fixture_counts_the_summed_size_of_its_files(self, tmp_path):
        directory = tmp_path / "d" / "service"
        (directory / "src").mkdir(parents=True)
        (directory / "a.txt").write_bytes(b"x" * 1000)
        (directory / "src" / "b.txt").write_bytes(b"x" * 2000)
        as_directory = fixture_resolution.ResolvedFixture(
            "service", directory, fixture_resolution.FixtureKind.DIRECTORY, False
        )
        (tmp_path / "f").mkdir()
        as_file = _file_fixture_of_size(tmp_path / "f", "service", 3000)

        assert self._estimate(
            tmp_path, [as_directory]
        ).estimated_total_usd == pytest.approx(
            self._estimate(tmp_path, [as_file]).estimated_total_usd
        )

    def test_per_trial_estimate_is_the_arm_estimate_over_its_planned_trials(
        self, tmp_path
    ):
        fixtures = [
            _file_fixture_of_size(tmp_path, "a.txt", 3000),
            _file_fixture_of_size(tmp_path, "b.txt", 3000),
        ]

        result = self._estimate(tmp_path, fixtures, trials=3)

        assert result.trials_per_arm == 2 * 3
        assert result.per_trial_usd("baseline") == pytest.approx(0.06 / (2 * 3))

    def test_unpriced_model_is_refused_naming_the_model_and_its_arm(self, tmp_path):
        fixtures = [_file_fixture_of_size(tmp_path, "a.txt", 3000)]
        arms = [_priced_arm("baseline", "sonnet"), _priced_arm("candidate", "opus")]

        with pytest.raises(UsageError) as excinfo:
            self._estimate(tmp_path, fixtures, arms)

        message = str(excinfo.value)
        assert "'opus' (candidate arm)" in message
        assert "sonnet" not in message
        assert "model-pricing.json" in message

    def test_empty_pricing_table_refuses_every_model(self, tmp_path):
        fixtures = [_file_fixture_of_size(tmp_path, "a.txt", 3000)]

        with pytest.raises(UsageError) as excinfo:
            self._estimate(tmp_path, fixtures, pricing_table={})

        assert "'sonnet' (baseline arm), 'haiku' (candidate arm)" in str(excinfo.value)


class TestChargedCost:
    def test_trial_with_a_reported_cost_is_charged_that_cost(self):
        result = _trial_result(Outcome.PASS, cost=0.0123)

        assert _run_estimate().charged_usd(BASELINE_LABEL, result) == 0.0123

    def test_trial_with_no_reported_cost_is_charged_its_arms_per_trial_estimate(self):
        result = _trial_result(Outcome.CLI_ERROR, cost=0.0, cost_reported=False)
        run_estimate = estimate.RunEstimate(
            by_arm=((BASELINE_LABEL, 0.06), (CANDIDATE_LABEL, 0.015)), trials_per_arm=3
        )

        assert run_estimate.charged_usd(CANDIDATE_LABEL, result) == pytest.approx(0.005)


def _stderr_lines(capsys) -> list[str]:
    return capsys.readouterr().err.splitlines()


class TestConfigurationEcho:
    def test_stderr_shows_agent_arms_tools_fixtures_trials_timeout_and_estimate(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        _cli(world, stub, "scout", "--model", "haiku", "--trials", str(SCOUT_TRIALS))

        assert _stderr_lines(capsys)[:9] == [
            "Agent: scout",
            "Arms:",
            "  baseline: model sonnet, effort high",
            "  candidate: model haiku, effort high",
            "Tools: Read, Grep",
            "Withheld tools: mcp__x__y, Bash(graphify *)",
            "Fixtures: clean-form, layered-svc",
            "Trials per arm per fixture: 3 (--trials)",
            "Trial timeout: 600 s",
        ]

    def test_estimate_line_labels_the_figure_rough_and_lists_each_arm_and_the_total(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        _cli(world, stub, "scout", "--model", "haiku", "--trials", str(SCOUT_TRIALS))

        assert (
            "Estimate (rough; real cost may be higher): "
            f"baseline {format_usd(BASELINE_TWO_ARM_ESTIMATE)}, "
            f"candidate {format_usd(CANDIDATE_TWO_ARM_ESTIMATE)}, "
            f"total {format_usd(TWO_ARM_ESTIMATE)}"
        ) in _stderr_lines(capsys)

    def test_trials_line_says_default_when_the_flag_is_absent(self, world, capsys):
        stub = _passing_stub(world)

        _cli(world, stub, "scout", "--model", "haiku", "--fixtures", "clean-form")

        assert "Trials per arm per fixture: 5 (default)" in _stderr_lines(capsys)

    def test_agent_without_tools_prints_no_tools_enabled_and_withheld_none(
        self, world, capsys
    ):
        _write_agent(world.deps.agents_dir, "bare", None, model="sonnet", effort="high")
        _write_expected(world.expected_dir, "bare-fixture", "bare", "pass")
        _make_file_fixture(world.deps.fixtures_dir, "bare-fixture.txt")
        stub = _passing_stub(world)

        _cli(world, stub, "bare", "--model", "haiku", "--trials", "1")

        lines = _stderr_lines(capsys)
        assert "Tools: no tools enabled" in lines
        assert "Withheld tools: none" in lines

    def test_echo_is_already_printed_when_the_first_trial_starts(self, world, capsys):
        stderr_when_trials_start = []

        def snapshot_then_run(*args, **kwargs):
            stderr_when_trials_start.append(capsys.readouterr().err)
            return runner.run_trial(*args, **kwargs)

        _cli(
            world,
            _passing_stub(world),
            "scout",
            "--model",
            "haiku",
            "--fixtures",
            "clean-form",
            "--trials",
            "1",
            deps=dataclasses.replace(world.deps, run_trial=snapshot_then_run),
        )

        assert (
            "Estimate (rough; real cost may be higher)" in stderr_when_trials_start[0]
        )


class TestArtifactEstimate:
    def test_artifact_records_each_arms_estimated_cost(self, world):
        stub = _passing_stub(world)

        _cli(world, stub, "scout", "--model", "haiku", "--trials", str(SCOUT_TRIALS))

        written = _written(world)
        assert _arm_block(written, BASELINE_LABEL)[
            "estimated_cost_usd"
        ] == pytest.approx(BASELINE_TWO_ARM_ESTIMATE)
        assert _arm_block(written, CANDIDATE_LABEL)[
            "estimated_cost_usd"
        ] == pytest.approx(CANDIDATE_TWO_ARM_ESTIMATE)


class TestSpendRefusals:
    def test_unpriced_candidate_exits_2_naming_it_with_no_trial_and_no_placeholder(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--model", "opus")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "'opus' (candidate arm)" in stderr
        assert "sonnet" not in stderr
        assert_nothing_ran(stub, world)

    def test_estimate_above_max_cost_exits_2_naming_both_figures_with_no_trial_and_no_placeholder(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _run_over_max_cost(world, stub, yes=True)

        stderr = capsys.readouterr().err
        assert code == 2
        assert format_usd(TWO_ARM_ESTIMATE) in stderr
        assert format_usd(MAX_COST_BELOW_ESTIMATE) in stderr
        assert_nothing_ran(stub, world)

    def test_refused_run_still_printed_the_configuration_and_estimate(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        _run_over_max_cost(world, stub)

        lines = _stderr_lines(capsys)
        assert "Agent: scout" in lines
        assert any(line.startswith("Estimate (rough") for line in lines)

    def test_estimate_below_max_cost_runs(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--trials",
            str(SCOUT_TRIALS),
            "--max-cost",
            str(MAX_COST_ABOVE_FULL_RUN),
        )

        assert code == 0
        assert len(stub.calls) == FULL_RUN_CALLS

    @pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "cheap"])
    def test_max_cost_that_is_not_a_positive_number_is_a_usage_error(
        self, world, value
    ):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, "scout", "--max-cost", value)

        assert excinfo.value.code == 2
        assert_nothing_ran(stub, world)


class RaisingStdin:
    """A stdin whose read fails the way a terminal does on Ctrl-C."""

    def __init__(self, error: BaseException):
        self._error = error

    def readline(self) -> str:
        raise self._error


def _gated_deps(world: World, stdin, *, is_tty: bool = True) -> model_effort_ab.Deps:
    return dataclasses.replace(world.deps, stdin=stdin, stdin_is_tty=lambda: is_tty)


def _gated_cli(world: World, stub: StubClaude, stdin, *, is_tty: bool = True) -> int:
    return _cli(
        world,
        stub,
        "scout",
        "--model",
        "haiku",
        "--trials",
        "1",
        yes=False,
        deps=_gated_deps(world, stdin, is_tty=is_tty),
    )


DECLINED_MESSAGE = (
    "error: declined at the prompt, so no trial ran: rerun and answer y, or pass --yes"
)


class TestApprovalGate:
    def test_yes_flag_runs_trials_without_prompting_or_reading_stdin(
        self, world, capsys
    ):
        stub = _passing_stub(world)
        stdin = RaisingStdin(AssertionError("stdin must not be read"))

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--trials",
            "1",
            deps=_gated_deps(world, stdin),
        )

        assert code == 0
        assert len(stub.calls) == SINGLE_TRIAL_RUN_CALLS
        assert "Proceed?" not in capsys.readouterr().err

    def test_yes_flag_runs_trials_when_stdin_is_not_a_tty(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--trials",
            "1",
            deps=_gated_deps(world, io.StringIO(""), is_tty=False),
        )

        assert code == 0
        assert len(stub.calls) == SINGLE_TRIAL_RUN_CALLS

    @pytest.mark.parametrize("answer", ["y", "yes", " YES ", "Y", "Yes\t"])
    def test_affirmative_answer_prompts_on_stderr_then_runs_trials(
        self, world, capsys, answer
    ):
        stub = _passing_stub(world)

        code = _gated_cli(world, stub, io.StringIO(f"{answer}\n"))

        err = capsys.readouterr().err
        assert code == 0
        assert err.index("Estimate (rough") < err.index("Proceed? [y/N] ")
        assert err.index("Proceed? [y/N] ") < err.index("artifact written")
        assert len(stub.calls) == SINGLE_TRIAL_RUN_CALLS

    @pytest.mark.parametrize(
        "answer", ["n", "no", "", "  ", "ye", "yess", "yes please"]
    )
    def test_any_other_answer_exits_1_with_one_line_message_and_no_trial(
        self, world, capsys, answer
    ):
        stub = _passing_stub(world)

        code = _gated_cli(world, stub, io.StringIO(f"{answer}\n"))

        assert code == 1
        assert capsys.readouterr().err.endswith(DECLINED_MESSAGE + "\n")
        assert_nothing_ran(stub, world)

    def test_end_of_input_at_the_prompt_declines_on_its_own_line_with_no_trial(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        code = _gated_cli(world, stub, io.StringIO(""))

        assert code == 1
        assert capsys.readouterr().err.endswith("\n" + DECLINED_MESSAGE + "\n")
        assert_nothing_ran(stub, world)

    def test_ctrl_c_at_the_prompt_declines_with_no_trial_and_no_traceback(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        code = _gated_cli(world, stub, RaisingStdin(KeyboardInterrupt()))

        err = capsys.readouterr().err
        assert code == 1
        assert err.endswith("\n" + DECLINED_MESSAGE + "\n")
        assert "Traceback" not in err
        assert_nothing_ran(stub, world)

    def test_no_tty_without_yes_prints_the_estimate_then_exits_1_telling_how_to_proceed(
        self, world, capsys
    ):
        stub = _passing_stub(world)
        stdin = RaisingStdin(AssertionError("stdin must not be read"))

        code = _gated_cli(world, stub, stdin, is_tty=False)

        lines = capsys.readouterr().err.splitlines()
        assert code == 1
        assert any(line.startswith("Estimate (rough") for line in lines)
        assert lines[-1] == (
            "error: approval required and stdin is not a TTY: rerun with --yes"
        )
        assert_nothing_ran(stub, world)

    def test_estimate_above_max_cost_exits_2_before_prompting(self, world, capsys):
        stub = _passing_stub(world)
        stdin = RaisingStdin(AssertionError("stdin must not be read"))

        code = _run_over_max_cost(
            world, stub, yes=False, deps=_gated_deps(world, stdin)
        )

        assert code == 2
        assert "Proceed?" not in capsys.readouterr().err
        assert_nothing_ran(stub, world)


# --- Stop rules --------------------------------------------------------------

PASS, GRADED_FAIL = Outcome.PASS, Outcome.GRADED_FAIL
CLI_ERROR, TIMEOUT = Outcome.CLI_ERROR, Outcome.TIMEOUT
INFRA_FAILURE, MAX_COST = AbortReason.INFRA_FAILURE, AbortReason.MAX_COST


def _check(
    baseline=(), candidate=(), cost_usd=0.0, max_cost_usd=None, trials_remaining=1
):
    spend_limit = None if max_cost_usd is None else SpendLimit(max_cost_usd)
    return stop_rules.check_stop(
        {BASELINE_LABEL: list(baseline), CANDIDATE_LABEL: list(candidate)},
        cost_usd,
        spend_limit,
        trials_remaining=trials_remaining,
    )


class TestSpendLimit:
    def test_estimate_above_the_limit_is_refused_and_one_equal_to_it_is_not(self):
        limit = SpendLimit(0.5)

        assert limit.refuses(0.75) is True
        assert limit.refuses(0.5) is False

    def test_cost_above_the_limit_exceeds_it_and_one_equal_to_it_does_not(self):
        limit = SpendLimit(0.5)

        assert limit.exceeded_by(0.75) is True
        assert limit.exceeded_by(0.5) is False


class TestRunStatus:
    def test_a_run_is_complete_exactly_when_nothing_ended_it_early(self):
        assert RunStatus.of(None) is RunStatus.COMPLETE
        assert all(
            RunStatus.of(reason) is RunStatus.INCOMPLETE for reason in AbortReason
        )


class TestStopRules:
    def test_cost_strictly_above_max_cost_stops_for_max_cost(self):
        assert _check([PASS], [PASS], cost_usd=0.75, max_cost_usd=0.5) == MAX_COST

    def test_cost_equal_to_max_cost_does_not_stop(self):
        assert _check([PASS], [PASS], cost_usd=0.5, max_cost_usd=0.5) is None

    def test_any_cost_is_allowed_without_a_max_cost(self):
        assert _check([PASS], [PASS], cost_usd=1_000_000.0, max_cost_usd=None) is None

    def test_no_trials_yet_does_not_stop(self):
        assert _check() is None

    @pytest.mark.parametrize("outcome", [CLI_ERROR, TIMEOUT])
    def test_first_trial_of_the_baseline_arm_ending_in_an_infra_outcome_stops(
        self, outcome
    ):
        assert _check([outcome]) == INFRA_FAILURE

    @pytest.mark.parametrize("outcome", [CLI_ERROR, TIMEOUT])
    def test_first_trial_of_the_candidate_arm_ending_in_an_infra_outcome_stops(
        self, outcome
    ):
        assert _check([PASS], [outcome]) == INFRA_FAILURE

    def test_a_non_infra_failure_on_the_first_trial_does_not_stop(self):
        assert _check([GRADED_FAIL], [Outcome.TOOL_VIOLATION]) is None

    def test_single_later_cli_error_does_not_stop(self):
        assert _check([PASS, CLI_ERROR], [PASS, PASS]) is None

    def test_three_consecutive_infra_outcomes_in_one_arm_stop(self):
        assert _check([PASS, CLI_ERROR, TIMEOUT, CLI_ERROR]) == INFRA_FAILURE

    def test_two_consecutive_infra_outcomes_do_not_stop(self):
        assert _check([PASS, CLI_ERROR, TIMEOUT]) is None

    def test_a_pass_between_infra_outcomes_resets_the_count(self):
        history = [PASS, CLI_ERROR, CLI_ERROR, PASS, CLI_ERROR, CLI_ERROR]

        assert _check(history) is None

    def test_a_graded_failure_between_infra_outcomes_resets_the_count(self):
        history = [PASS, CLI_ERROR, CLI_ERROR, GRADED_FAIL, CLI_ERROR]

        assert _check(history) is None

    def test_infra_failures_alternating_across_arms_stop_only_when_one_arm_has_three(
        self,
    ):
        # Run order: B fail, C pass, B fail, C pass, B fail. B's own third fails.
        assert _check([PASS, CLI_ERROR], [PASS, PASS]) is None
        assert _check([PASS, CLI_ERROR, CLI_ERROR], [PASS, PASS]) is None
        assert (
            _check([PASS, CLI_ERROR, CLI_ERROR, CLI_ERROR], [PASS, PASS])
            == INFRA_FAILURE
        )

    def test_infra_failures_spread_over_two_arms_never_add_up(self):
        assert _check([PASS, CLI_ERROR, CLI_ERROR], [PASS, TIMEOUT, TIMEOUT]) is None

    def test_a_stop_condition_on_the_last_planned_trial_is_not_a_stop(self):
        assert (
            _check([CLI_ERROR], cost_usd=2.0, max_cost_usd=1.0, trials_remaining=0)
            is None
        )
        assert _check([CLI_ERROR], trials_remaining=0) is None

    def test_a_stop_condition_with_a_trial_still_to_run_stops(self):
        assert _check([CLI_ERROR], trials_remaining=1) == INFRA_FAILURE

    def test_max_cost_wins_when_the_infra_rule_also_applies(self):
        assert _check([CLI_ERROR], cost_usd=2.0, max_cost_usd=1.0) == MAX_COST


# --- Stopping early and keeping partial results ------------------------------

CLI_FAILURE = {"exit_code": 1, "stdout": "", "stderr": "boom: auth failed"}
TIMED_OUT_RECORD = process_record.TrialProcessRecord(
    exit_code=None, stdout="", stderr="", timed_out=True
)
CLEAN_FORM_ARGS = ("scout", "--model", "haiku", "--fixtures", "clean-form")


def _deps_acting_after(
    world: World, completed_trials: int, action: Callable[[], None]
) -> model_effort_ab.Deps:
    """Let the first `completed_trials` trials run for real, then run `action` in place of the next."""
    started = []

    def run_then_act(*args, **kwargs):
        if len(started) == completed_trials:
            action()
        started.append(args)
        return runner.run_trial(*args, **kwargs)

    return dataclasses.replace(world.deps, run_trial=run_then_act)


def _deps_raising_after(
    world: World, completed_trials: int, error: BaseException
) -> model_effort_ab.Deps:
    def raise_error() -> None:
        raise error

    return _deps_acting_after(world, completed_trials, raise_error)


def _deps_signalling_after(
    world: World, completed_trials: int, signum: int
) -> model_effort_ab.Deps:
    """Send `signum` to this process inside the trial after `completed_trials` real ones."""
    return _deps_acting_after(
        world, completed_trials, lambda: os.kill(os.getpid(), signum)
    )


def assert_cut_at_limit(text: str, prefix: str, filler: str) -> None:
    """Assert `text` shows `prefix` plus `filler` up to CAUSE_LIMIT characters, and no more."""
    __tracebackhide__ = True
    kept = filler * (CAUSE_LIMIT - len(prefix))
    assert prefix + kept in text, "the text was cut short of the limit"
    assert prefix + kept + filler not in text, "the text was kept beyond the limit"


def _deps_timing_out(
    world: World, timed_out_calls: Collection[int] | None = None
) -> model_effort_ab.Deps:
    """Make the trials at `timed_out_calls` (0-based; default all) end as timeouts.

    No process runs for those; the other trials run the stub. A real timeout is
    covered at the runner layer.
    """
    started = []

    def run_or_time_out(*args, **kwargs):
        call_number = len(started)
        started.append(args)
        if timed_out_calls is None or call_number in timed_out_calls:
            return TIMED_OUT_RECORD
        return runner.run_trial(*args, **kwargs)

    return dataclasses.replace(world.deps, run_trial=run_or_time_out)


def _always_failing(
    world: World, outcome_name: str
) -> tuple[StubClaude, model_effort_ab.Deps]:
    """A stub and deps under which every trial ends in `outcome_name` (cli_error or timeout)."""
    if outcome_name == "timeout":
        return StubClaude(world.stub_dir), _deps_timing_out(world)
    return StubClaude(world.stub_dir, **CLI_FAILURE), world.deps


def _interrupting_deps(world: World, completed_trials: int) -> model_effort_ab.Deps:
    """Press Ctrl-C inside the trial after `completed_trials` real ones."""
    return _deps_raising_after(world, completed_trials, KeyboardInterrupt())


def _outcomes(written: dict, label: str) -> list[str]:
    return [
        trial["outcome"]
        for fixture in _arm_block(written, label)["fixtures"]
        for trial in fixture["trials"]
    ]


def _progress_lines(capsys) -> list[str]:
    return [
        line
        for line in _stderr_lines(capsys)
        if line.startswith(("[baseline]", "[candidate]"))
    ]


class TestSpendLimitStop:
    def test_run_stops_after_the_trial_that_passes_max_cost_and_starts_no_more(
        self, world
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == TRIALS_BEFORE_STOP
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "max-cost",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]

    def test_incomplete_totals_count_only_the_completed_trials(self, world):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        written = _written(world)
        assert _arm_block(written, BASELINE_LABEL)["totals"]["pass"] == 2
        assert _arm_block(written, BASELINE_LABEL)["totals"][
            "actual_cost_usd"
        ] == pytest.approx(2 * TRIAL_COST)
        assert _arm_block(written, CANDIDATE_LABEL)["totals"]["pass"] == 1

    def test_stderr_names_the_abort_reason_and_the_artifact_path(self, world, capsys):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        err = capsys.readouterr().err
        assert "run stopped early (max-cost)" in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_actual_cost_equal_to_max_cost_lets_the_run_finish(self, world):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            "--max-cost",
            str(ARM_COUNT * TRIAL_COST),
        )

        assert code == 0
        assert len(stub.calls) == ARM_COUNT
        assert _written(world)["status"] == "complete"

    @staticmethod
    def _run_with_unreported_baseline_trials(world, kind):
        """Run to a limit the reported costs never pass, with the baseline's unreported trials charged."""
        limit = MAX_COST_ESTIMATE_FACTOR * TWO_ARM_ESTIMATE
        reported_cost = limit / (REPORTED_CALLS + SPARE_TRIAL_SHARE)
        stub = StubClaude(
            world.stub_dir,
            **_verdict_call(PASS_VERDICT, SONNET_MODEL_ID, cost=reported_cost),
        )
        if kind == "timeout":
            unreported_calls = range(2, FULL_RUN_CALLS, 4)
            deps = _deps_timing_out(world, set(unreported_calls))
        else:
            stub.queue(*[{}, {}, CLI_FAILURE, {}] * SCOUT_TRIALS)
            deps = world.deps
        code = _cli(
            world,
            stub,
            "scout",
            "--model",
            "haiku",
            "--trials",
            str(SCOUT_TRIALS),
            "--max-cost",
            str(limit),
            deps=deps,
        )
        return code, _written(world)

    @pytest.mark.parametrize("kind", ["cli_error", "timeout"])
    def test_trials_with_no_reported_cost_are_charged_the_arms_per_trial_estimate(
        self, world, kind
    ):
        _, written = self._run_with_unreported_baseline_trials(world, kind)

        baseline = _arm_block(written, BASELINE_LABEL)
        unreported_trials = [
            trial
            for fixture in baseline["fixtures"]
            for trial in fixture["trials"]
            if not trial["cost_reported"]
        ]
        per_trial_estimate = BASELINE_TWO_ARM_ESTIMATE / ARM_RUN_CALLS
        assert len(unreported_trials) >= 1
        assert baseline["totals"]["estimated_cost_charged_usd"] == pytest.approx(
            len(unreported_trials) * per_trial_estimate
        )

    @pytest.mark.parametrize("kind", ["cli_error", "timeout"])
    def test_charged_estimates_for_unreported_trials_stop_the_run_at_max_cost(
        self, world, kind
    ):
        code, written = self._run_with_unreported_baseline_trials(world, kind)

        completed = len(_outcomes(written, BASELINE_LABEL)) + len(
            _outcomes(written, CANDIDATE_LABEL)
        )
        assert code == 1
        assert written["abort_reason"] == "max-cost"
        assert completed < FULL_RUN_CALLS

    def test_cost_passing_max_cost_on_the_last_planned_trial_leaves_the_run_complete(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            "--max-cost",
            str(1.5 * TRIAL_COST),
        )

        written = _written(world)
        assert code == 0
        assert len(stub.calls) == 2
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert "run stopped early" not in capsys.readouterr().err


class TestSystemicFailureStop:
    @pytest.mark.parametrize("outcome", ["cli_error", "timeout"])
    def test_first_trial_ending_in_an_infra_outcome_stops_the_run_with_no_further_trial(
        self, world, outcome
    ):
        stub, deps = _always_failing(world, outcome)

        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5", deps=deps)

        written = _written(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "infra-failure",
        )
        assert _outcomes(written, BASELINE_LABEL) == [outcome]
        assert _outcomes(written, CANDIDATE_LABEL) == []

    def test_candidate_whose_first_trial_fails_stops_the_run_after_one_trial_each(
        self, world
    ):
        stub = _passing_stub(world)
        stub.queue({}, CLI_FAILURE)

        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == 2
        assert _outcomes(written, BASELINE_LABEL) == ["pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["cli_error"]

    @pytest.mark.parametrize(
        ("outcome", "cause"),
        [
            ("cli_error", "exit code 1: boom: auth failed"),
            ("timeout", "trial exceeded the time limit"),
        ],
    )
    def test_stderr_names_the_abort_reason_the_failing_trials_error_and_the_artifact(
        self, world, capsys, outcome, cause
    ):
        stub, deps = _always_failing(world, outcome)

        _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5", deps=deps)

        err = capsys.readouterr().err
        assert (
            f"error: run stopped early (infra-failure): the baseline arm ended in "
            f"{outcome}. Likely cause: {cause}. Fix that and rerun"
        ) in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_stderr_shows_the_cause_cut_at_the_cause_limit(self, world, capsys):
        long_stderr = "x" * (4 * CAUSE_LIMIT)
        stub = StubClaude(world.stub_dir, **{**CLI_FAILURE, "stderr": long_stderr})

        _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5")

        assert_cut_at_limit(capsys.readouterr().err, "exit code 1: ", "x")

    def test_terminal_control_sequences_in_the_cause_are_shown_escaped_not_executed(
        self, world, capsys
    ):
        hostile = "\x1b]0;pwned\x07\x1b[31mred\x1b[0m"
        stub = StubClaude(world.stub_dir, **{**CLI_FAILURE, "stderr": hostile})

        _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5")

        err = capsys.readouterr().err
        assert "\x1b" not in err and "\x07" not in err
        assert (
            "Likely cause: exit code 1: \\x1b]0;pwned\\x07\\x1b[31mred\\x1b[0m." in err
        )

    def test_three_consecutive_failures_in_the_baseline_arm_stop_the_run_on_the_third(
        self, world
    ):
        stub = _passing_stub(world)
        # Calls alternate baseline, candidate: the baseline fails on its trials 2, 3 and 4.
        stub.queue({}, {}, CLI_FAILURE, {}, CLI_FAILURE, {}, CLI_FAILURE)

        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == 7
        assert written["abort_reason"] == "infra-failure"
        assert _outcomes(written, BASELINE_LABEL) == [
            "pass",
            "cli_error",
            "cli_error",
            "cli_error",
        ]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass", "pass", "pass"]

    def test_single_later_cli_error_does_not_stop_the_run(self, world):
        stub = _passing_stub(world)
        stub.queue({}, {}, CLI_FAILURE)

        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "3")

        written = _written(world)
        assert code == 0
        assert len(stub.calls) == 6
        assert written["status"] == "complete"
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "cli_error", "pass"]


class TestInterrupt:
    def test_ctrl_c_after_three_trials_keeps_them_and_marks_the_artifact_interrupted(
        self, world
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 3),
        )

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == 3
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]

    def test_interrupt_prints_no_traceback_and_names_the_artifact_and_the_dropped_trial(
        self, world, capsys
    ):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 3),
        )

        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert (
            "error: run stopped early (interrupt): the trial in flight was dropped; "
            "3 completed trials were kept"
        ) in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_arm_with_no_completed_trial_lists_no_fixtures(self, world):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 1),
        )

        written = _written(world)
        assert _arm_block(written, CANDIDATE_LABEL)["fixtures"] == []
        assert _arm_block(written, CANDIDATE_LABEL)["totals"]["pass"] == 0
        assert _outcomes(written, BASELINE_LABEL) == ["pass"]

    def test_ctrl_c_inside_the_first_trial_writes_an_interrupted_artifact_with_no_results(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 0),
        )

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]
        assert "Traceback" not in err
        assert "0 completed trials were kept" in err
        assert f"artifact written: {world.artifact_path}" in err


def _note_signal(_signum, _frame) -> None:
    """A harmless handler: the signal is delivered and nothing else happens."""


@pytest.fixture
def harmless_termination_signals():
    """Swap in a no-op SIGTERM/SIGHUP handler so a signal a test sends cannot end pytest."""
    originals = {
        signum: signal.signal(signum, _note_signal) for signum in TERMINATION_SIGNALS
    }
    yield
    for signum, handler in originals.items():
        signal.signal(signum, handler)


class TestIgnoredTerminationSignals:
    def test_a_signal_that_was_ignored_stays_ignored_while_the_others_raise_interrupt(
        self,
    ):
        originals = {
            signum: signal.signal(signum, _note_signal)
            for signum in TERMINATION_SIGNALS
        }
        ignored, handled = TERMINATION_SIGNALS[0], TERMINATION_SIGNALS[1:]
        signal.signal(ignored, signal.SIG_IGN)
        try:
            with interrupts.termination_as_interrupt():
                assert signal.getsignal(ignored) is signal.SIG_IGN
                for signum in handled:
                    assert signal.getsignal(signum) is not _note_signal
            assert signal.getsignal(ignored) is signal.SIG_IGN
            for signum in handled:
                assert signal.getsignal(signum) is _note_signal
        finally:
            for signum, handler in originals.items():
                signal.signal(signum, handler)


@pytest.mark.usefixtures("harmless_termination_signals")
class TestTerminationSignals:
    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_termination_signal_ends_the_run_like_ctrl_c_and_keeps_the_completed_trials(
        self, world, capsys, signum
    ):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_signalling_after(world, 3, signum),
        )

        written = _written(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert "Traceback" not in capsys.readouterr().err

    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_a_termination_signal_raises_keyboard_interrupt_while_the_context_is_active(
        self, signum
    ):
        with interrupts.termination_as_interrupt(), pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signum)

    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_previous_handlers_are_back_in_place_after_the_run(self, world, signum):
        _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert signal.getsignal(signum) is _note_signal

    def test_previous_handlers_are_back_in_place_after_a_declined_run(self, world):
        _gated_cli(world, _passing_stub(world), io.StringIO("n\n"))

        assert all(
            signal.getsignal(signum) is _note_signal for signum in TERMINATION_SIGNALS
        )


ALL_INTERRUPT_SIGNALS = pytest.mark.parametrize(
    "signum", INTERRUPT_SIGNALS, ids=lambda n: n.name
)


def _deps_signalling_with_trial_run(
    world: World, completed_trials: int, signum: int
) -> model_effort_ab.Deps:
    """Send `signum` once the trial after `completed_trials` real ones has run.

    The process has exited by then, so the signal lands while its outcome is
    resolved and graded.
    """
    started = []

    def run_then_signal(*args, **kwargs):
        record = runner.run_trial(*args, **kwargs)
        if len(started) == completed_trials:
            os.kill(os.getpid(), signum)
        started.append(args)
        return record

    return dataclasses.replace(world.deps, run_trial=run_then_signal)


def _signal_during(monkeypatch, owner, step: str, signum: int) -> list[str]:
    """Send `signum` as `owner.step` starts; the returned list gets one entry per call.

    Call-through spy: the real step still runs. The public API cannot place a
    signal inside one step of the finish sequence, so the step is wrapped.
    """
    real_step = getattr(owner, step)
    calls = []

    def signal_then_run(*args, **kwargs):
        calls.append(step)
        os.kill(os.getpid(), signum)
        return real_step(*args, **kwargs)

    monkeypatch.setattr(owner, step, signal_then_run)
    return calls


def _spy_on_writes(monkeypatch) -> list[str]:
    """Record each artifact write and still perform it.

    Call-through spy: the public API shows only the final file, not how many
    writes produced it.
    """
    real_write = artifact_store.write_artifact
    writes = []

    def counting_write(path, text):
        writes.append(text)
        return real_write(path, text)

    monkeypatch.setattr(artifact_store, "write_artifact", counting_write)
    return writes


FINISH_STEPS = [
    pytest.param(artifact, "build_artifact", id="build"),
    pytest.param(artifact_store, "render_artifact", id="render"),
    pytest.param(artifact_store, "write_artifact", id="write"),
]


@pytest.mark.usefixtures("harmless_termination_signals")
class TestInterruptsAreHeldForTheRun:
    @ALL_INTERRUPT_SIGNALS
    def test_signal_after_the_process_exited_keeps_the_completed_trial(
        self, world, capsys, signum
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_signalling_with_trial_run(world, 3, signum),
        )

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == 4
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass", "pass"]
        assert (
            "run stopped early (interrupt): no trial was in flight; "
            "4 completed trials were kept"
        ) in capsys.readouterr().err

    @ALL_INTERRUPT_SIGNALS
    def test_signal_during_a_trial_kills_its_process_and_drops_only_that_trial(
        self, world, signum
    ):
        stub = _passing_stub(world)
        stub.queue({}, {}, {"sleep": 30})

        def signal_once_the_third_trial_runs() -> None:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if len(stub.calls) == 3:
                        break
                except ValueError:  # the stub was mid-write
                    pass
                time.sleep(0.02)
            signal.pthread_kill(threading.main_thread().ident, signum)

        threading.Thread(target=signal_once_the_third_trial_runs, daemon=True).start()
        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]
        with pytest.raises(ProcessLookupError):
            os.kill(stub.calls[2]["pid"], 0)

    def test_signal_while_the_timeout_is_handled_still_kills_the_group(
        self, stub_dir, fixture_root, monkeypatch
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        # Call-through spy on `_kill_process_group`: it sends a signal just before
        # the real kill. The public API cannot time a signal to that step of the
        # timeout handler.
        real_kill = runner._kill_process_group
        killed = []

        def signal_then_kill(process):
            os.kill(os.getpid(), signal.SIGTERM)
            killed.append(process.pid)
            real_kill(process)

        monkeypatch.setattr(runner, "_kill_process_group", signal_then_kill)
        held = interrupts.block()
        try:
            record = runner.run_trial(fixture, _config(stub), trial_timeout_seconds=1)
            still_pending = interrupts.take_pending()
        finally:
            interrupts.restore(held)

        assert record.timed_out is True
        assert still_pending, "the signal was dropped instead of left for the run"
        with pytest.raises(ProcessLookupError):
            os.kill(killed[0], 0)

    def test_interrupt_signals_are_blocked_from_the_first_trial_to_the_save_and_free_afterwards(
        self, world, monkeypatch
    ):
        blocked = {}
        real_trial, real_write = runner.run_trial, artifact_store.write_artifact

        def spy_trial(*args, **kwargs):
            blocked.setdefault("trial", _blocked_signals())
            return real_trial(*args, **kwargs)

        def spy_write(path, text):
            blocked["write"] = _blocked_signals()
            return real_write(path, text)

        monkeypatch.setattr(artifact_store, "write_artifact", spy_write)

        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=dataclasses.replace(world.deps, run_trial=spy_trial),
        )

        assert set(INTERRUPT_SIGNALS) <= blocked["trial"]
        assert set(INTERRUPT_SIGNALS) <= blocked["write"]
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_signal_pending_before_the_first_trial_starts_no_trial(self, world):
        scout_plan = _scout_plan(world)
        settings = run_types.TrialSettings(
            trials=run_types.TrialCount(1, "test"),
            trial_timeout_seconds=TIMEOUT_SECONDS,
            claude_bin="unused",
            expected_dir=world.expected_dir,
        )

        def must_not_run(*_args):
            raise AssertionError("a trial started")

        held = interrupts.block()
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            run = execution.run_trials(
                scout_plan, settings, _run_estimate(), run_trial=must_not_run
            )
        finally:
            interrupts.restore(held)

        assert (run.abort_reason, run.started_trials) == (AbortReason.INTERRUPT, 0)

    def test_a_pending_signal_is_consumed_so_it_is_not_delivered_later(self):
        held = interrupts.block()
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            first, second = interrupts.take_pending(), interrupts.take_pending()
        finally:
            interrupts.restore(held)

        assert (first, second) == (True, False)

    def test_a_signal_landing_just_before_the_restore_is_reported_not_raised(
        self, monkeypatch
    ):
        held = interrupts.block()

        def consume_then_receive_one_more() -> bool:
            os.kill(os.getpid(), signal.SIGTERM)
            return False

        # Fault injected: `take_pending` is replaced so a SIGTERM lands after the
        # consume and before the restore. That window is a few bytecodes wide; the
        # public API gives a test no way to send a signal into it.
        monkeypatch.setattr(interrupts, "take_pending", consume_then_receive_one_more)
        previous_handler = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        try:
            arrived = interrupts.restore_reporting(held)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

        assert arrived is True
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_a_sighup_the_process_ignores_does_not_stop_the_run(self, world):
        stub = _passing_stub(world)
        original = signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            code = _cli(
                world,
                stub,
                *CLEAN_FORM_ARGS,
                "--trials",
                "3",
                deps=_deps_signalling_after(world, 2, signal.SIGHUP),
            )
        finally:
            signal.signal(signal.SIGHUP, original)

        written = _written(world)
        assert code == 0
        assert len(stub.calls) == 6
        assert (written["status"], written["abort_reason"]) == ("complete", None)


@pytest.mark.usefixtures("harmless_termination_signals")
class TestSignalWhileFinishing:
    @pytest.mark.parametrize(("owner", "step"), FINISH_STEPS)
    def test_a_complete_run_stays_complete_is_saved_once_and_exits_1_truthfully(
        self, world, capsys, monkeypatch, owner, step
    ):
        calls = _signal_during(monkeypatch, owner, step, signal.SIGTERM)
        writes = _spy_on_writes(monkeypatch)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert calls == [step]
        assert len(writes) == 1
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert f"the artifact was written to {world.artifact_path}" in err
        assert "Traceback" not in err

    @pytest.mark.parametrize(("owner", "step"), FINISH_STEPS)
    def test_a_stopped_run_keeps_its_recorded_stop_reason(
        self, world, monkeypatch, owner, step
    ):
        _signal_during(monkeypatch, owner, step, signal.SIGINT)
        writes = _spy_on_writes(monkeypatch)

        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        written = _written(world)
        assert code == 1
        assert len(writes) == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "max-cost",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]

    @pytest.mark.parametrize(("owner", "step"), FINISH_STEPS)
    def test_a_second_signal_while_finishing_an_interrupted_run_loses_nothing(
        self, world, capsys, monkeypatch, owner, step
    ):
        _signal_during(monkeypatch, owner, step, signal.SIGHUP)
        writes = _spy_on_writes(monkeypatch)

        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_signalling_after(world, 3, signal.SIGTERM),
        )

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert len(writes) == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]
        assert f"artifact written: {world.artifact_path}" in err

    def test_a_signal_landing_as_the_signals_are_released_is_reported_as_finishing(
        self, world, capsys, monkeypatch
    ):
        # Fault injected: one more SIGTERM as `restore_reporting` hands the mask
        # back, still inside the session's guarded region. The public API cannot
        # reach that window: no step of the run runs there.
        real_restore = interrupts.restore_reporting

        def restore_then_receive_one_more(previous_mask):
            arrived = real_restore(previous_mask)
            os.kill(os.getpid(), signal.SIGTERM)
            return arrived

        monkeypatch.setattr(
            interrupts, "restore_reporting", restore_then_receive_one_more
        )

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert f"the artifact was written to {world.artifact_path}" in err
        assert "nothing was run or spent" not in err
        assert "Traceback" not in err

    def test_a_signal_landing_after_the_session_returns_is_not_reported_as_before_the_run(
        self, world, capsys, monkeypatch
    ):
        # Fault injected: a SIGTERM after `run_session` has returned, so it reaches
        # `main` with the signals free. The public API cannot reach that window:
        # the run is over and saved, and no step of it runs there.
        real_run_session = session.run_session

        def run_then_receive_one_more(*args, **kwargs):
            code = real_run_session(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return code

        monkeypatch.setattr(session, "run_session", run_then_receive_one_more)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert "nothing was run or spent" not in err
        assert model_effort_ab.INTERRUPTED_AFTER_RUN_MESSAGE in err
        assert "Traceback" not in err


class TestInterruptBeforeTheRun:
    def test_ctrl_c_before_the_first_trial_says_nothing_was_run_or_spent(
        self, world, capsys
    ):
        def interrupted_clock():
            raise KeyboardInterrupt

        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            deps=dataclasses.replace(world.deps, clock=interrupted_clock),
        )

        err = capsys.readouterr().err
        assert code == 1
        assert err.splitlines()[-1] == model_effort_ab.INTERRUPTED_BEFORE_RUN_MESSAGE
        assert "nothing was run or spent" in err
        assert "artifact" not in err
        assert_nothing_ran(stub, world)

    @pytest.mark.usefixtures("harmless_termination_signals")
    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_a_termination_signal_before_the_run_says_nothing_was_run_or_spent(
        self, world, capsys, signum
    ):
        def clock_that_receives_the_signal():
            os.kill(os.getpid(), signum)
            return NOW

        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            deps=dataclasses.replace(world.deps, clock=clock_that_receives_the_signal),
        )

        err = capsys.readouterr().err
        assert code == 1
        assert err.splitlines()[-1] == model_effort_ab.INTERRUPTED_BEFORE_RUN_MESSAGE
        assert_nothing_ran(stub, world)


class TestUnexpectedTrialError:
    def test_error_in_a_trial_keeps_the_completed_trials_and_marks_the_artifact_harness_error(
        self, world, capsys
    ):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 3, RuntimeError("staging exploded")),
        )

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "harness-error",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]
        assert "run stopped early (harness-error)" in err
        assert "RuntimeError: staging exploded" in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_error_text_in_the_stop_notice_is_cut_at_the_cause_limit(
        self, world, capsys
    ):
        long_message = "m" * (4 * CAUSE_LIMIT)
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 1, RuntimeError(long_message)),
        )

        assert_cut_at_limit(capsys.readouterr().err, "RuntimeError: ", "m")

    def test_terminal_control_sequences_in_the_error_are_shown_escaped(
        self, world, capsys
    ):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 1, RuntimeError("\x1b[2Jgone")),
        )

        err = capsys.readouterr().err
        assert "\x1b" not in err
        assert "RuntimeError: \\x1b[2Jgone" in err

    def test_staging_failure_while_grading_is_a_harness_error_not_a_graded_fail(
        self, world, capsys, monkeypatch
    ):
        def failing_copy(*_args, **_kwargs):
            raise OSError("no space left")

        monkeypatch.setattr(grading, "shutil", SimpleNamespace(copy2=failing_copy))

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "2")

        written = _written(world)
        assert code == 1
        assert written["abort_reason"] == "harness-error"
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]
        assert "OSError: no space left" in capsys.readouterr().err

    def test_error_in_the_first_trial_still_writes_an_artifact_with_no_results(
        self, world
    ):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_raising_after(world, 0, RuntimeError("no staging dir")),
        )

        written = _written(world)
        assert code == 1
        assert written["abort_reason"] == "harness-error"
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]


def _scout_plan(world: World) -> plan.RunPlan:
    return plan.plan_run(
        "scout",
        candidate_model="haiku",
        candidate_effort=None,
        fixture_stems=None,
        runs_dir=world.runs_dir,
        now=NOW,
        rng=FixedRng(),
        git_sha=None,
        agents_dir=world.deps.agents_dir,
        expected_dir=world.deps.expected_dir,
        fixtures_dir=world.deps.fixtures_dir,
    )


def _run_with_one_trial_each(abort_reason: AbortReason | None) -> run_types.RunResult:
    passed = [_trial_result(Outcome.PASS)]
    return run_types.RunResult(
        arm_runs=[_arm_run(BASELINE_LABEL, passed), _arm_run(CANDIDATE_LABEL, passed)],
        abort_reason=abort_reason,
        started_trials=ARM_COUNT,
        stopping_trial=None,
    )


class UnwritableStream:
    """A stderr whose reader has gone away."""

    def write(self, _text: str) -> int:
        raise BrokenPipeError("reader closed")

    def flush(self) -> None:
        pass


class TestFinishRun:
    def test_run_cut_short_before_any_trial_started_writes_no_artifact_and_says_so(
        self, world
    ):
        scout_plan = _scout_plan(world)
        stderr = io.StringIO()
        console = session.Console(io.StringIO(), lambda: False, io.StringIO(), stderr)
        run = run_types.RunResult(
            arm_runs=[],
            abort_reason=AbortReason.INTERRUPT,
            started_trials=0,
            stopping_trial=None,
        )

        code = session.finish_run(scout_plan, run, _run_estimate(), console)

        assert code == 1
        assert scout_plan.artifact_path.read_text(encoding="utf-8") == ""
        assert "interrupted before any trial started" in stderr.getvalue()

    def test_artifact_is_saved_before_the_stop_notice_is_printed(self, world):
        scout_plan = _scout_plan(world)
        console = session.Console(
            io.StringIO(), lambda: False, io.StringIO(), UnwritableStream()
        )
        run = _run_with_one_trial_each(AbortReason.MAX_COST)

        with pytest.raises(BrokenPipeError):
            session.finish_run(scout_plan, run, _run_estimate(), console)

        saved = json.loads(scout_plan.artifact_path.read_text(encoding="utf-8"))
        assert (saved["status"], saved["abort_reason"]) == ("incomplete", "max-cost")


class TestProgressAndSummary:
    def test_one_progress_line_per_completed_trial_in_run_order(self, world, capsys):
        _cli(world, _passing_stub(world), "scout", "--model", "haiku", "--trials", "2")

        cost = format_usd(TRIAL_COST)
        assert _progress_lines(capsys) == [
            f"[baseline] fixture 1/2 clean-form trial 1/2: pass {cost}",
            f"[candidate] fixture 1/2 clean-form trial 1/2: pass {cost}",
            f"[baseline] fixture 1/2 clean-form trial 2/2: pass {cost}",
            f"[candidate] fixture 1/2 clean-form trial 2/2: pass {cost}",
            f"[baseline] fixture 2/2 layered-svc trial 1/2: graded_fail {cost}",
            f"[candidate] fixture 2/2 layered-svc trial 1/2: graded_fail {cost}",
            f"[baseline] fixture 2/2 layered-svc trial 2/2: graded_fail {cost}",
            f"[candidate] fixture 2/2 layered-svc trial 2/2: graded_fail {cost}",
        ]

    def test_progress_lines_stop_with_the_run_and_match_the_trials_that_completed(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        assert len(_progress_lines(capsys)) == len(stub.calls) == TRIALS_BEFORE_STOP

    def test_progress_line_is_printed_before_the_next_trial_starts(self, world, capsys):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 1),
        )

        assert _progress_lines(capsys) == [
            f"[baseline] fixture 1/1 clean-form trial 1/5: pass {format_usd(TRIAL_COST)}"
        ]

    def test_summary_shows_per_arm_outcome_totals_and_actual_against_estimated_cost(
        self, world, capsys
    ):
        _cli(
            world,
            _passing_stub(world),
            "scout",
            "--model",
            "haiku",
            "--trials",
            str(SCOUT_TRIALS),
        )

        err = capsys.readouterr().err
        arm_cost = format_usd(ARM_RUN_CALLS * TRIAL_COST)
        assert (
            "Summary:\n"
            "  baseline: timeout 0, cli_error 0, tool_violation 0, parse_failure 0, "
            f"graded_fail {SCOUT_TRIALS}, pass {SCOUT_TRIALS}; cost {arm_cost}, "
            f"estimated {format_usd(BASELINE_TWO_ARM_ESTIMATE)}\n"
            "  candidate: timeout 0, cli_error 0, tool_violation 0, parse_failure 0, "
            f"graded_fail {SCOUT_TRIALS}, pass {SCOUT_TRIALS}; cost {arm_cost}, "
            f"estimated {format_usd(CANDIDATE_TWO_ARM_ESTIMATE)}\n"
            f"  total: cost {format_usd(FULL_RUN_COST)}, "
            f"estimated {format_usd(TWO_ARM_ESTIMATE)}\n"
            f"artifact written: {world.artifact_path}\n"
        ) in err

    def test_summary_marks_an_arms_cost_as_a_lower_bound_when_a_trial_reported_none(
        self, world, capsys
    ):
        stub = _passing_stub(world)
        stub.queue({}, {}, CLI_FAILURE)

        _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "3")

        lines = capsys.readouterr().err.splitlines()
        baseline = next(
            line for line in lines if line.startswith("  baseline: timeout")
        )
        candidate = next(
            line for line in lines if line.startswith("  candidate: timeout")
        )
        assert "(lower bound; $" in baseline
        assert "charged as estimate for trials with no reported cost)" in baseline
        assert "lower bound" not in candidate

    def test_incomplete_run_summary_counts_only_completed_trials(self, world, capsys):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        err = capsys.readouterr().err
        assert (
            f"  total: cost {format_usd(TRIALS_BEFORE_STOP * TRIAL_COST)}, estimated "
            in err
        )
