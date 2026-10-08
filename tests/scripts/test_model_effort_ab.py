"""Tests for the model/effort A/B harness (scripts/lib/model_effort/).

Tool resolution: an agent's `tools:` frontmatter line is split into the
read-only built-ins the harness enables, the entries it withholds, and the
write-capable entries that make it refuse the agent.

Trial runner: a fixture is staged into a fresh temp dir per trial and the CLI
is invoked with an exact, isolating argv. A stub executable stands in for
`claude` and records its argv, cwd and the files it saw.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

for _path in (
    REPO_ROOT / "scripts",
    REPO_ROOT / "scripts" / "lib",
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from model_effort import runner, tools


def _write_agent(agents_dir: Path, name: str, tools_line: str | None) -> None:
    lines = ["---", f"name: {name}"]
    if tools_line is not None:
        lines.append(f"tools: {tools_line}")
    lines += ["---", "", "Body."]
    (agents_dir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "agents"
    directory.mkdir()
    return directory


class TestClassifyTools:
    def test_read_grep_enabled_mcp_and_scoped_bash_withheld(self):
        profile = tools.classify_tools(
            "Read, Grep, mcp__codegraph__*, Bash(graphify *)"
        )

        assert profile.enabled == ("Read", "Grep")
        assert profile.withheld == ("mcp__codegraph__*", "Bash(graphify *)")
        assert profile.refused == ()

    def test_unlisted_builtin_is_withheld_not_enabled(self):
        profile = tools.classify_tools("Read, WebFetch")

        assert profile.enabled == ("Read",)
        assert profile.withheld == ("WebFetch",)

    def test_skill_and_agent_are_withheld(self):
        profile = tools.classify_tools("Read, Skill, Agent")

        assert profile.enabled == ("Read",)
        assert profile.withheld == ("Skill", "Agent")

    def test_glob_is_enabled(self):
        assert tools.classify_tools("Glob").enabled == ("Glob",)

    @pytest.mark.parametrize(
        "write_tool", ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"]
    )
    def test_write_capable_tool_is_refused(self, write_tool):
        profile = tools.classify_tools(f"Read, {write_tool}")

        assert profile.refused == (write_tool,)
        assert write_tool not in profile.enabled
        assert write_tool not in profile.withheld

    def test_scoped_bash_is_withheld_not_refused(self):
        profile = tools.classify_tools("Bash(git log *)")

        assert profile.refused == ()
        assert profile.withheld == ("Bash(git log *)",)

    def test_no_tools_line_yields_empty_profile(self):
        profile = tools.classify_tools(None)

        assert (profile.enabled, profile.withheld, profile.refused) == ((), (), ())

    def test_blank_tools_line_yields_empty_profile(self):
        profile = tools.classify_tools("")

        assert (profile.enabled, profile.withheld, profile.refused) == ((), (), ())

    def test_whitespace_and_empty_entries_are_dropped(self):
        profile = tools.classify_tools("  Read ,, Grep  ,")

        assert profile.enabled == ("Read", "Grep")

    def test_tool_names_are_matched_case_sensitively(self):
        profile = tools.classify_tools("read, bash")

        assert profile.enabled == ()
        assert profile.refused == ()
        assert profile.withheld == ("read", "bash")

    def test_agent_with_only_withheld_tools_has_no_enabled_tools(self):
        profile = tools.classify_tools("mcp__codegraph__*, WebFetch")

        assert profile.enabled == ()
        assert profile.has_enabled_tools is False


class TestLoadToolProfile:
    def test_reads_tools_from_agent_frontmatter(self, agents_dir):
        _write_agent(agents_dir, "scout", "Read, Grep, mcp__x__y, Bash(graphify *)")

        profile = tools.load_tool_profile("scout", agents_dir)

        assert profile.enabled == ("Read", "Grep")
        assert profile.withheld == ("mcp__x__y", "Bash(graphify *)")

    def test_agent_without_tools_line_has_no_tools(self, agents_dir):
        _write_agent(agents_dir, "bare", None)

        profile = tools.load_tool_profile("bare", agents_dir)

        assert profile.enabled == ()
        assert profile.has_enabled_tools is False

    def test_write_capable_agent_raises_naming_agent_and_tools(self, agents_dir):
        _write_agent(agents_dir, "editor", "Read, Edit, Write")

        with pytest.raises(tools.WriteCapableAgentError) as excinfo:
            tools.load_tool_profile("editor", agents_dir)

        message = str(excinfo.value)
        assert "editor" in message
        assert "Edit" in message and "Write" in message
        assert "write-capable agents are not supported yet" in message

    def test_unknown_agent_raises_listing_valid_names(self, agents_dir):
        _write_agent(agents_dir, "alpha", "Read")
        _write_agent(agents_dir, "beta", "Read")

        with pytest.raises(tools.UnknownAgentError) as excinfo:
            tools.load_tool_profile("gamma", agents_dir)

        message = str(excinfo.value)
        assert "gamma" in message
        assert "alpha" in message and "beta" in message

    def test_agent_name_with_path_separator_is_unknown(self, agents_dir):
        _write_agent(agents_dir, "alpha", "Read")
        (agents_dir.parent / "outside.md").write_text(
            "---\ntools: Read\n---\n", encoding="utf-8"
        )

        with pytest.raises(tools.UnknownAgentError):
            tools.load_tool_profile("../outside", agents_dir)

    def test_agent_file_without_frontmatter_raises_clear_error(self, agents_dir):
        (agents_dir / "broken.md").write_text("no frontmatter here", encoding="utf-8")

        with pytest.raises(tools.AgentFrontmatterError) as excinfo:
            tools.load_tool_profile("broken", agents_dir)

        assert "broken" in str(excinfo.value)

    def test_tools_given_as_a_yaml_list_raises_clear_error(self, agents_dir):
        _write_agent(agents_dir, "listy", "[Read, Grep]")

        with pytest.raises(tools.AgentFrontmatterError) as excinfo:
            tools.load_tool_profile("listy", agents_dir)

        assert "listy" in str(excinfo.value)
        assert "comma-separated" in str(excinfo.value)


class TestShippedAgents:
    def test_data_flow_tracer_enables_read_tools_and_withholds_mcp_and_scoped_bash(
        self,
    ):
        profile = tools.load_tool_profile("data-flow-tracer")

        assert profile.enabled == ("Read", "Grep", "Glob")
        assert "Bash(graphify *)" in profile.withheld
        assert any(entry.startswith("mcp__") for entry in profile.withheld)

    def test_architect_is_refused_for_unscoped_bash(self):
        with pytest.raises(tools.WriteCapableAgentError) as excinfo:
            tools.load_tool_profile("architect")

        assert "architect" in str(excinfo.value)
        assert "Bash" in str(excinfo.value)


STUB_TEMPLATE = """#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

RECORD = Path(__RECORD__)
BEHAVIOR = json.loads(__BEHAVIOR__)
cwd = Path(os.getcwd())
files_before = {
    str(p.relative_to(cwd)): p.read_text()
    for p in sorted(cwd.rglob("*"))
    if p.is_file()
}
calls = json.loads(RECORD.read_text()) if RECORD.exists() else []
calls.append({"argv": sys.argv[1:], "cwd": str(cwd), "files_before": files_before})
RECORD.write_text(json.dumps(calls))
if BEHAVIOR.get("tamper"):
    for p in cwd.rglob("*"):
        if p.is_file():
            p.write_text(p.read_text() + "TAMPERED")
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
        self.path.write_text(
            STUB_TEMPLATE.replace("__RECORD__", repr(str(self._record))).replace(
                "__BEHAVIOR__", repr(json.dumps(behavior))
            ),
            encoding="utf-8",
        )
        self.path.chmod(0o755)

    @property
    def calls(self) -> list[dict]:
        return json.loads(self._record.read_text(encoding="utf-8"))


def _config(stub: StubClaude, **overrides) -> runner.TrialConfig:
    fields = {
        "model": "haiku",
        "effort": "low",
        "system_prompt": "You are a reviewer.",
        "enabled_tools": ("Read", "Grep"),
        "claude_bin": str(stub.path),
    }
    return runner.TrialConfig(**{**fields, **overrides})


def _flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


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


class TestStagingFixtures:
    def test_file_fixture_is_staged_under_its_own_name(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = fixture_root / "form.html"
        fixture.write_text("<form></form>", encoding="utf-8")

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

    @pytest.mark.parametrize("kind", ["file", "directory"])
    def test_two_trials_each_see_a_pristine_copy_and_source_is_unchanged(
        self, kind, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, tamper=True)
        if kind == "file":
            fixture = fixture_root / "form.html"
            fixture.write_text("<form></form>", encoding="utf-8")
        else:
            fixture = _make_directory_fixture(fixture_root)
        source_before = _snapshot(fixture)

        runner.run_trial(fixture, _config(stub))
        runner.run_trial(fixture, _config(stub))

        first, second = stub.calls
        assert first["files_before"] == second["files_before"]
        assert not any("TAMPERED" in text for text in second["files_before"].values())
        assert _snapshot(fixture) == source_before

    def test_trials_run_in_distinct_temp_dirs(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")

        runner.run_trial(fixture, _config(stub))
        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["cwd"] != stub.calls[1]["cwd"]

    def test_temp_dir_is_removed_after_the_trial(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")

        runner.run_trial(fixture, _config(stub))

        assert not Path(stub.calls[0]["cwd"]).exists()

    def test_temp_dir_is_removed_after_a_timeout(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")

        runner.run_trial(fixture, _config(stub), trial_timeout=1)

        assert not Path(stub.calls[0]["cwd"]).exists()


class TestTrialArgv:
    def _run(self, stub_dir, fixture_root, **config_overrides) -> dict:
        stub = StubClaude(stub_dir)
        fixture = fixture_root / "form.html"
        fixture.write_text("<form></form>", encoding="utf-8")
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

    def test_add_dir_is_only_the_knowledge_dir_and_not_under_evals(
        self, stub_dir, fixture_root
    ):
        call = self._run(stub_dir, fixture_root)

        add_dirs = [
            call["argv"][i + 1]
            for i, arg in enumerate(call["argv"])
            if arg == "--add-dir"
        ]
        assert add_dirs == [str(runner.KNOWLEDGE_DIR)]
        assert runner.KNOWLEDGE_DIR.is_dir()
        assert (REPO_ROOT / "evals") not in Path(add_dirs[0]).parents

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


class TestBuildArgv:
    def test_argv_starts_with_the_injected_binary(self):
        config = runner.TrialConfig(
            model="haiku",
            effort="low",
            system_prompt="s",
            enabled_tools=("Read",),
            claude_bin="/opt/bin/claude-x",
        )

        argv = runner.build_argv(config, "go")

        assert argv[:3] == ["/opt/bin/claude-x", "-p", "go"]


class TestExecution:
    def test_exit_code_stdout_and_stderr_are_captured_for_a_failing_run(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(
            stub_dir, exit_code=3, stdout="out-line", stderr="boom: bad model"
        )
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")

        record = runner.run_trial(fixture, _config(stub))

        assert record == runner.RunRecord(
            exit_code=3, stdout="out-line", stderr="boom: bad model", timed_out=False
        )

    def test_successful_run_reports_zero_exit_and_not_timed_out(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, stdout="ok")
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout, record.timed_out) == (0, "ok", False)

    def test_run_exceeding_the_time_limit_is_marked_timed_out_and_killed(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")

        started = time.monotonic()
        record = runner.run_trial(fixture, _config(stub), trial_timeout=1)

        assert record.timed_out is True
        assert record.exit_code is None
        assert time.monotonic() - started < 15
