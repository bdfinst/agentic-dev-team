"""The exact argv the trial runner builds for the CLI."""

from __future__ import annotations

from pathlib import Path

from _model_effort_support import (
    StubClaude,
    _config,
    _eval_paths,
    _flag_value,
    _make_file_fixture,
)
from model_effort import invocation, paths, runner

from _repo_root import REPO_ROOT


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

    def test_add_dir_follows_a_redirected_knowledge_dir(
        self, stub_dir, fixture_root, tmp_path
    ):
        knowledge = tmp_path / "other-knowledge"
        knowledge.mkdir()

        call = self._run(
            stub_dir, fixture_root, eval_paths=_eval_paths(knowledge_dir=knowledge)
        )

        assert _flag_value(call["argv"], "--add-dir") == str(knowledge)

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
            eval_paths=_eval_paths(plugin_root=plugin_root),
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
