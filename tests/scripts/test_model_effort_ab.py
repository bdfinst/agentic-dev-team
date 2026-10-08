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

import json
import os
import shutil
import signal
import sys
import threading
import time
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
from model_effort import (
    agent_file,
    agent_spec,
    artifact,
    artifact_store,
    grading,
    outcome,
    paths,
    plan,
    runner,
    tools,
    transcript,
)
from model_effort import fixtures as fixture_resolution
from model_effort.arm import (
    BASELINE_LABEL,
    CANDIDATE_LABEL,
    Arm,
    arm_by_label,
)
from model_effort.errors import UsageError
from model_effort.outcome import Outcome

TRANSCRIPT_FIXTURES = Path(__file__).parent / "fixtures" / "model_effort_ab"
HAIKU_MODEL_ID = "claude-haiku-5-5"
SONNET_MODEL_ID = "claude-sonnet-5-5"
NOW = datetime(2026, 10, 8, 12, 30, 45, tzinfo=timezone.utc)
RUN_ID = "20261008T123045Z-scout-haiku-high-0ab3"
SCOUT_TOOLS = "Read, Grep, mcp__x__y, Bash(graphify *)"
PASS_VERDICT = {"status": "pass", "issues": [], "summary": "Nothing to report."}
FAIL_VERDICT = {"status": "fail", "issues": [], "summary": "Layer violation."}
TRIAL_COST = 0.01
ENABLED = ("Read", "Grep")
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


# --- Trial runner ------------------------------------------------------------

STUB_TEMPLATE = """#!/usr/bin/env python3
import json, os, subprocess, sys, time
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
    "argv": sys.argv[1:],
    "cwd": str(cwd),
    "files_before": files_before,
    "symlinks": symlinks,
    "env_names": sorted(os.environ),
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
) -> runner.TrialConfig:
    profile = tools.ToolProfile(
        enabled_tools=tuple(enabled_tools), withheld_tools=(), refused_tools=()
    )
    return runner.TrialConfig(
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

        runner.run_trial(fixture, _config(stub), trial_timeout=TIMEOUT_SECONDS)

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

        argv = runner.build_argv(config, "go")

        assert argv[:3] == ["/opt/bin/claude-x", "-p", "go"]


class TestTrialEnvironment:
    def test_parent_session_identity_variables_are_removed_and_the_rest_kept(self):
        parent = {
            "CLAUDE_CODE_SESSION_ID": "parent-session",
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            "HOME": "/home/me",
            "ANTHROPIC_API_KEY": "key",
        }

        env = runner.build_trial_env(parent)

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

        assert record == runner.RunRecord(
            exit_code=3, stdout="out-line", stderr="boom: bad model", timed_out=False
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

        record = runner.run_trial(fixture, _config(stub), trial_timeout=TIMEOUT_SECONDS)

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
            trial_timeout=TIMEOUT_SECONDS,
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

        def interrupt_once_spawned() -> None:
            deadline = time.monotonic() + 10
            while not spawned.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)

        threading.Thread(target=interrupt_once_spawned, daemon=True).start()
        with pytest.raises(KeyboardInterrupt):
            runner.run_trial(
                _make_file_fixture(fixture_root, "a.txt", "a"),
                _config(stub),
                trial_timeout=60,
            )
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
        assert parsed.tool_names == ("Read", "Read")

    def test_real_run_with_a_denied_read_shows_the_attempt_and_the_denial(self):
        parsed = _read_transcript("read-outside-denied")

        assert parsed.has_result is True
        assert parsed.tool_names == ("Read",)
        assert parsed.permission_denials == 1

    def test_real_run_with_allowed_reads_has_no_permission_denials(self):
        assert _read_transcript("pass-readonly").permission_denials == 0

    def test_real_bad_model_run_is_an_error_with_no_model_id_and_a_note(self):
        parsed = _read_transcript("bad-model")

        assert parsed.has_result is True
        assert parsed.is_error is True
        assert parsed.cost_usd == 0
        assert parsed.model_id is None
        assert parsed.model_id_note

    def test_real_run_where_the_model_declines_bash_has_no_tool_use(self):
        parsed = _read_transcript("tool-denied-bash")

        assert parsed.tool_names == ()
        assert parsed.model_id == HAIKU_MODEL_ID

    def test_real_run_with_no_tools_has_no_tool_use(self):
        parsed = _read_transcript("no-tools")

        assert parsed.tool_names == ()
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

        assert parsed.tool_names == ("Read",)
        assert parsed.result_text == "done"

    def test_missing_result_event_reports_has_result_false(self):
        parsed = transcript.parse_stream(_stream(_tool_use_event("Grep")))

        assert parsed.has_result is False
        assert parsed.result_text is None
        assert parsed.tool_names == ("Grep",)
        assert parsed.cost_usd == 0

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

        assert parsed.tool_names == ("Read", "Grep", "WebFetch")


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


def _record(exit_code=0, stdout="", stderr="", timed_out=False) -> runner.RunRecord:
    return runner.RunRecord(
        exit_code=exit_code, stdout=stdout, stderr=stderr, timed_out=timed_out
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

    def test_session_config_comes_from_the_transcript_init_event(self):
        stdout = _stream(_init_event(), _result_event(json.dumps(PASS_VERDICT)))

        result = _resolve(stdout)

        assert result.session_config == _expected_session_config(HAIKU_MODEL_ID)


class TestMessageCaps:
    def test_error_is_capped_at_500_characters(self):
        errored = _resolve(_verdict_stream(PASS_VERDICT), exit_code=1, stderr="e" * 900)

        assert len(errored.error) == 500

    def test_a_single_long_grader_message_is_capped_at_500_characters(self):
        graded = _resolve(_verdict_stream(PASS_VERDICT), lambda j: (False, ["m" * 900]))

        assert [len(m) for m in graded.grader_messages] == [500]

    def test_combined_grader_messages_are_capped_at_500_characters(self):
        messages = ["a" * 300, "b" * 300, "c" * 300]

        graded = _resolve(_verdict_stream(PASS_VERDICT), lambda j: (False, messages))

        assert graded.grader_messages == ("a" * 300, "b" * 200)

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
) -> outcome.TrialResult:
    return outcome.TrialResult(
        outcome=outcome_value,
        cost_usd=cost,
        model_id=model_id,
        model_id_note=note,
        grader_messages=(),
        error=None,
        session_config=session_config,
    )


def _arm(label: str = CANDIDATE_LABEL) -> Arm:
    profile = tools.ToolProfile(
        enabled_tools=("Read",), withheld_tools=(), refused_tools=()
    )
    return Arm(label=label, model="haiku", effort="high", profile=profile)


def _arm_run(
    label: str, results: list[outcome.TrialResult], expected_clean: bool = False
) -> artifact.ArmRun:
    fixture = artifact.FixtureTrials(
        stem="f",
        kind=fixture_resolution.FixtureKind.FILE,
        expected_clean=expected_clean,
        results=results,
    )
    return artifact.ArmRun(arm=_arm(label), trials_per_fixture=1, fixtures=[fixture])


def _metadata(
    abort_reason: artifact.AbortReason | None = None,
) -> artifact.RunMetadata:
    return artifact.RunMetadata(
        run_id=RUN_ID,
        created=NOW,
        git_sha=None,
        agent="scout",
        knowledge_dir="knowledge",
        abort_reason=abort_reason,
    )


def _built_arm(
    results: list[outcome.TrialResult], expected_clean: bool = False
) -> dict:
    run = _arm_run(CANDIDATE_LABEL, results, expected_clean)
    return artifact.build_artifact(_metadata(), [run])["arms"][0]


class TestRunId:
    def test_run_id_joins_utc_time_agent_candidate_model_effort_and_four_hex(self):
        run_id = artifact.make_run_id(NOW, "scout", "haiku", "high", FixedRng())

        assert run_id == RUN_ID


class TestArmLookup:
    def test_arm_is_found_by_label_regardless_of_position(self):
        arms = [_arm(CANDIDATE_LABEL), _arm(BASELINE_LABEL)]

        assert arm_by_label(arms, BASELINE_LABEL) is arms[1]

    def test_unknown_label_raises(self):
        with pytest.raises(LookupError):
            arm_by_label([_arm(CANDIDATE_LABEL)], BASELINE_LABEL)


class TestArtifactStatus:
    def test_run_without_an_abort_reason_is_complete(self):
        built = artifact.build_artifact(_metadata(), [])

        assert (built["status"], built["abort_reason"]) == ("complete", None)

    @pytest.mark.parametrize(
        "reason", list(artifact.AbortReason), ids=lambda reason: reason.value
    )
    def test_run_with_an_abort_reason_is_incomplete_and_names_it(self, reason):
        built = artifact.build_artifact(_metadata(reason), [])

        assert (built["status"], built["abort_reason"]) == ("incomplete", reason.value)

    def test_abort_reasons_use_the_contract_strings(self):
        assert [reason.value for reason in artifact.AbortReason] == [
            "max-cost",
            "infra-failure",
            "interrupt",
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
        }

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

        built = artifact.build_artifact(_metadata(), [candidate, baseline])

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
    monkeypatch.setattr(
        artifact_store,
        "os",
        SimpleNamespace(replace=_failing_replace, fsync=os.fsync),
    )


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


def _verdict_call(verdict: dict, model_id: str, *tool_names: str) -> dict:
    events = [_tool_use_event(*tool_names)] if tool_names else []
    result = _result_event(json.dumps(verdict), model_usage={model_id: {}})
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
def world(tmp_path: Path) -> World:
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
    )
    return World(tmp_path, deps)


def _cli(world: World, stub: StubClaude, *args: str) -> int:
    argv = [
        *args,
        "--claude-bin",
        str(stub.path),
        "--runs-dir",
        str(world.runs_dir),
    ]
    return model_effort_ab.main(argv, deps=world.deps)


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
    code = _cli(world, stub, "scout", "--model", "haiku", "--trials", "3")
    return code, _written(world), stub


def _trial(outcome_name: str, error: str | None = None) -> dict:
    return {
        "outcome": outcome_name,
        "cost_usd": TRIAL_COST,
        "grader_messages": [],
        "error": error,
    }


def _fixture_block(stem: str, kind: str, clean: bool, trials: list[dict]) -> dict:
    return {"stem": stem, "kind": kind, "expected_clean": clean, "trials": trials}


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
            "trials": 3,
            "estimated_cost_usd": None,
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
            "trials": 3,
            "estimated_cost_usd": None,
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

        code = _cli(world, stub, "scout", "--fixtures", "layered-svc", "--trials", "1")

        assert code == 0
        assert len(stub.calls) == 2
        assert all("layered-svc/src/app.py" in c["files_before"] for c in stub.calls)

    def test_enabled_tools_reach_the_cli_and_withheld_tools_only_the_artifact(
        self, world
    ):
        stub = _passing_stub(world)

        _cli(world, stub, "scout", "--fixtures", "clean-form", "--trials", "1")

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
        stub = StubClaude(world.stub_dir, sleep=30)

        code = _cli(
            world,
            stub,
            "scout",
            "--fixtures",
            "clean-form",
            "--trials",
            "1",
            "--trial-timeout",
            "1",
        )

        assert code == 0
        for arm in _written(world)["arms"]:
            assert arm["totals"]["timeout"] == 1
            assert arm["fixtures"][0]["trials"][0]["outcome"] == "timeout"


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
        assert stub.calls == [] and world.artifacts == []

    def test_unknown_fixture_exits_2_naming_it_and_listing_valid_stems(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", "clean-form,nope")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "nope" in stderr
        assert "clean-form" in stderr and "layered-svc" in stderr
        assert stub.calls == [] and world.artifacts == []

    def test_fixture_whose_expected_entry_names_another_agent_exits_2(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--fixtures", "other-only")

        assert code == 2
        assert "other-only" in capsys.readouterr().err
        assert stub.calls == []

    def test_agent_with_no_expected_entries_exits_2_stating_no_fixtures_found(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "lonely")

        assert code == 2
        assert "no fixtures were found" in capsys.readouterr().err
        assert stub.calls == [] and world.artifacts == []

    def test_write_capable_agent_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "write-capable")

        assert code == 2
        assert "write-capable agents are not supported yet" in capsys.readouterr().err
        assert stub.calls == [] and world.artifacts == []

    def test_missing_runs_directory_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        world.runs_dir.rmdir()

        code = _cli(world, stub, "scout")

        assert code == 2
        assert "runs directory" in capsys.readouterr().err
        assert stub.calls == []

    def test_zero_trials_is_a_usage_error_and_runs_nothing(self, world):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            _cli(world, stub, "scout", "--trials", "0")

        assert excinfo.value.code == 2
        assert stub.calls == [] and world.artifacts == []

    def test_malformed_expected_json_exits_2_naming_the_file(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        broken = world.expected_dir / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        code = _cli(world, stub, "scout")

        assert code == 2
        assert str(broken) in capsys.readouterr().err
        assert stub.calls == [] and world.artifacts == []

    def test_misspelled_candidate_effort_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--effort", "hgih")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "hgih" in stderr and "high" in stderr
        assert stub.calls == [] and world.artifacts == []

    def test_candidate_model_with_path_characters_exits_2_before_any_trial(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = _cli(world, stub, "scout", "--model", "../../etc")

        assert code == 2
        assert "--model" in capsys.readouterr().err
        assert stub.calls == [] and world.artifacts == []


class TestArtifactReservationAndWrite:
    def test_run_that_ends_before_any_trial_completes_leaves_no_placeholder(
        self, world, monkeypatch
    ):
        def interrupted(*_args, **_kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(model_effort_ab, "run_trials", interrupted)

        with pytest.raises(KeyboardInterrupt):
            _cli(world, StubClaude(world.stub_dir), "scout")

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
