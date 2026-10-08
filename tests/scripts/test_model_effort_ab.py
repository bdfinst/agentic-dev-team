"""Tests for the model/effort A/B harness (scripts/lib/model_effort/).

Tool resolution: an agent's `tools:` frontmatter line is split into the
read-only built-ins the harness enables, the entries it withholds, and the
write-capable entries that make it refuse the agent.
"""

from __future__ import annotations

import sys
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

from model_effort import tools


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
