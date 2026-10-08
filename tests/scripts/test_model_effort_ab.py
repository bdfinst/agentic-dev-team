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

from model_effort import grading, outcome, runner, tools, transcript


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

    def test_missing_claude_binary_yields_exit_127_with_the_os_error_as_stderr(
        self, tmp_path, fixture_root
    ):
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")
        missing = tmp_path / "no-such-claude"

        record = runner.run_trial(
            fixture,
            runner.TrialConfig(
                model="haiku",
                effort="low",
                system_prompt="x",
                enabled_tools=("Read",),
                claude_bin=str(missing),
            ),
        )

        assert (record.exit_code, record.timed_out) == (127, False)
        assert "no-such-claude" in record.stderr

    def test_non_executable_claude_binary_yields_exit_127(self, tmp_path, fixture_root):
        fixture = fixture_root / "a.txt"
        fixture.write_text("a", encoding="utf-8")
        not_executable = tmp_path / "claude-plain-file"
        not_executable.write_text("not a program", encoding="utf-8")
        not_executable.chmod(0o644)

        record = runner.run_trial(
            fixture,
            runner.TrialConfig(
                model="haiku",
                effort="low",
                system_prompt="x",
                enabled_tools=("Read",),
                claude_bin=str(not_executable),
            ),
        )

        assert record.exit_code == 127
        assert record.stderr != ""


TRANSCRIPT_FIXTURES = Path(__file__).parent / "fixtures" / "model_effort_ab"
HAIKU_MODEL_ID = "claude-haiku-5-5"


def _read_transcript(name: str) -> transcript.ParsedTranscript:
    text = (TRANSCRIPT_FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8")
    return transcript.parse_stream(text)


def _stream(*events: dict | str) -> str:
    return "\n".join(e if isinstance(e, str) else json.dumps(e) for e in events)


def _result_event(text="ok", model_usage=None, **fields) -> dict:
    usage = {HAIKU_MODEL_ID: {}} if model_usage is None else model_usage
    return {
        "type": "result",
        "result": text,
        "is_error": False,
        "total_cost_usd": 0.01,
        "modelUsage": usage,
        **fields,
    }


def _tool_use_event(*names: str) -> dict:
    blocks = [{"type": "tool_use", "name": n, "input": {}} for n in names]
    return {"type": "assistant", "message": {"content": blocks}}


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


CLEAN_STEM = "a11y-clean-form"
CLEAN_AGENT = "a11y-review"
PASSING_VERDICT = {"status": "pass", "issues": [], "summary": "No problems."}


class TestGradeTrial:
    def test_verdict_matching_the_real_expected_entry_passes(self):
        passed, messages = grading.grade_trial(CLEAN_AGENT, CLEAN_STEM, PASSING_VERDICT)

        assert (passed, messages) == (True, [])

    def test_verdict_with_the_wrong_status_fails_with_a_status_message(self):
        wrong = {"status": "fail", "issues": [], "summary": ""}

        passed, messages = grading.grade_trial(CLEAN_AGENT, CLEAN_STEM, wrong)

        assert passed is False
        assert any("status" in message for message in messages)

    def test_only_the_named_expected_file_reaches_the_grader(self, tmp_path):
        expected_dir = tmp_path / "expected"
        expected_dir.mkdir()
        (expected_dir / "one.json").write_text(
            json.dumps({"agents": {"x-review": {"expectedStatus": "pass"}}}),
            encoding="utf-8",
        )
        # A malformed sibling would crash the grader if it were copied too.
        (expected_dir / "two.json").write_text("{not json", encoding="utf-8")

        passed, _ = grading.grade_trial(
            "x-review", "one", {"status": "pass"}, expected_dir=expected_dir
        )

        assert passed is True

    def test_agent_absent_from_the_expected_entry_fails_with_a_message(self):
        passed, messages = grading.grade_trial("no-such-agent", CLEAN_STEM, {})

        assert passed is False
        assert messages

    def test_grading_leaves_no_temp_dir_behind(self, tmp_path, monkeypatch):
        monkeypatch.setattr(grading.tempfile, "tempdir", str(tmp_path))

        grading.grade_trial(CLEAN_AGENT, CLEAN_STEM, PASSING_VERDICT)

        assert list(tmp_path.iterdir()) == []


class TestIsExpectedClean:
    def test_expected_status_pass_is_clean(self):
        entry = {"agents": {"a": {"expectedStatus": "pass"}}}

        assert grading.is_expected_clean(entry, "a") is True

    def test_expected_status_fail_is_not_clean(self):
        entry = {"agents": {"a": {"expectedStatus": "fail"}}}

        assert grading.is_expected_clean(entry, "a") is False

    def test_agent_missing_from_entry_is_not_clean(self):
        assert grading.is_expected_clean({"agents": {}}, "a") is False

    def test_real_clean_fixture_entry_is_clean(self):
        entry = json.loads(
            (grading.EXPECTED_DIR / f"{CLEAN_STEM}.json").read_text(encoding="utf-8")
        )

        assert grading.is_expected_clean(entry, CLEAN_AGENT) is True


ENABLED = ("Read", "Grep")


def _record(exit_code=0, stdout="", stderr="", timed_out=False) -> runner.RunRecord:
    return runner.RunRecord(
        exit_code=exit_code, stdout=stdout, stderr=stderr, timed_out=timed_out
    )


def _resolve(stdout: str, grader=None, **record_fields) -> outcome.TrialResult:
    record = _record(stdout=stdout, **record_fields)
    parsed = transcript.parse_stream(stdout)
    grader = grader or (lambda agent_json: (True, []))
    return outcome.resolve_outcome(record, parsed, ENABLED, grader)


def _real_grader(agent_json: dict) -> tuple[bool, list[str]]:
    return grading.grade_trial(CLEAN_AGENT, CLEAN_STEM, agent_json)


def _verdict_stream(verdict: dict, *tool_names: str) -> str:
    events = [_tool_use_event(*tool_names)] if tool_names else []
    return _stream(*events, _result_event(json.dumps(verdict)))


class TestTrialOutcomes:
    def test_json_satisfying_the_expected_entry_is_pass(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT), _real_grader)

        assert result.outcome == outcome.OUTCOME_PASS
        assert result.error is None
        assert result.grader_messages == ()

    def test_json_with_the_wrong_status_is_graded_fail_with_grader_messages(self):
        wrong = {"status": "fail", "issues": [], "summary": ""}

        result = _resolve(_verdict_stream(wrong), _real_grader)

        assert result.outcome == outcome.OUTCOME_GRADED_FAIL
        assert any("status" in m for m in result.grader_messages)

    def test_text_with_no_json_object_is_parse_failure(self):
        result = _resolve(_stream(_result_event("I found nothing to report.")))

        assert result.outcome == outcome.OUTCOME_PARSE_FAILURE
        assert result.error

    def test_call_to_a_tool_outside_the_enabled_set_is_tool_violation_naming_it(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT, "Read", "Bash"))

        assert result.outcome == outcome.OUTCOME_TOOL_VIOLATION
        assert "Bash" in result.error
        assert "Read" not in result.error

    def test_webfetch_call_with_passing_json_is_tool_violation(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT, "WebFetch"), _real_grader)

        assert result.outcome == outcome.OUTCOME_TOOL_VIOLATION
        assert "WebFetch" in result.error

    def test_non_zero_exit_is_cli_error_carrying_stderr(self):
        result = _resolve(
            _verdict_stream(PASSING_VERDICT), exit_code=1, stderr="model not found"
        )

        assert result.outcome == outcome.OUTCOME_CLI_ERROR
        assert "model not found" in result.error

    def test_webfetch_call_with_non_zero_exit_is_cli_error(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT, "WebFetch"), exit_code=1)

        assert result.outcome == outcome.OUTCOME_CLI_ERROR

    def test_exit_zero_with_no_result_event_is_cli_error(self):
        result = _resolve(_stream(_tool_use_event("Read")))

        assert result.outcome == outcome.OUTCOME_CLI_ERROR
        assert "result" in result.error

    def test_result_event_flagged_is_error_is_cli_error_even_with_exit_zero(self):
        stdout = _stream(_result_event("model gone", is_error=True))

        result = _resolve(stdout)

        assert result.outcome == outcome.OUTCOME_CLI_ERROR
        assert "model gone" in result.error

    def test_timed_out_run_is_timeout_even_with_other_failures(self):
        result = _resolve(
            _stream(_tool_use_event("WebFetch")),
            exit_code=None,
            timed_out=True,
        )

        assert result.outcome == outcome.OUTCOME_TIMEOUT

    def test_grader_is_not_called_unless_every_earlier_check_passed(self):
        calls = []

        def spy(agent_json):
            calls.append(agent_json)
            return True, []

        _resolve(_verdict_stream(PASSING_VERDICT, "WebFetch"), spy)
        _resolve(_stream(_result_event("no json")), spy)
        _resolve(_verdict_stream(PASSING_VERDICT), spy, exit_code=1)
        _resolve(_verdict_stream(PASSING_VERDICT), spy, exit_code=None, timed_out=True)

        assert calls == []

    def test_cost_and_model_id_come_from_the_transcript(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT))

        assert result.cost_usd == pytest.approx(0.01)
        assert result.model_id == HAIKU_MODEL_ID
        assert result.model_id_note is None

    def test_cost_is_kept_for_a_failed_trial(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT, "WebFetch"))

        assert result.cost_usd == pytest.approx(0.01)

    def test_grader_messages_and_error_are_capped_at_500_characters(self):
        long_message = "m" * 900

        graded = _resolve(
            _verdict_stream(PASSING_VERDICT), lambda j: (False, [long_message])
        )
        errored = _resolve(
            _verdict_stream(PASSING_VERDICT), exit_code=1, stderr="e" * 900
        )

        assert [len(m) for m in graded.grader_messages] == [500]
        assert len(errored.error) == 500

    def test_trial_result_is_immutable(self):
        result = _resolve(_verdict_stream(PASSING_VERDICT))

        with pytest.raises(AttributeError):
            result.outcome = "pass"
