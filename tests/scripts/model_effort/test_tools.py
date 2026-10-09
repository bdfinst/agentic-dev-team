"""Tool resolution: an agent's `tools:` frontmatter line is split into the read-only built-ins the harness enables,
the entries it withholds, and the write-capable entries that make it refuse the agent.
"""

from __future__ import annotations

import pytest
from _model_effort_support import SCOUT_TOOLS
from model_effort import agent_file, tools


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
