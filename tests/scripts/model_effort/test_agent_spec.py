"""Agent spec (model_effort.agent_spec), plus the smoke test over the shipped agent file."""

from __future__ import annotations

from pathlib import Path

import pytest
from _model_effort_support import _write_agent
from model_effort import agent_file, agent_spec, external, paths, tools


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


MISSING = object()


def _agent_file(**frontmatter) -> agent_file.AgentFile:
    return agent_file.AgentFile(
        path=Path("scout.md"), frontmatter=frontmatter, body="Body.\n"
    )


VALID_FRONTMATTER = {"model": "sonnet", "effort": "high"}
UNUSABLE_VALUES = (
    pytest.param(MISSING, id="missing"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="blank"),
    pytest.param(None, id="null"),
    pytest.param(3, id="number"),
    pytest.param(["sonnet"], id="list"),
    pytest.param(True, id="boolean"),
)


class TestRequiredText:
    @pytest.mark.parametrize("key", ["model", "effort"])
    @pytest.mark.parametrize("value", UNUSABLE_VALUES)
    def test_a_missing_or_non_text_value_raises_naming_the_key(self, key, value):
        frontmatter = {**VALID_FRONTMATTER}
        if value is MISSING:
            del frontmatter[key]
        else:
            frontmatter[key] = value

        with pytest.raises(agent_file.AgentFrontmatterError, match=f"`{key}:`"):
            agent_spec.build_agent_spec("scout", _agent_file(**frontmatter))

    @pytest.mark.parametrize("key", ["model", "effort"])
    def test_a_padded_value_is_stripped(self, key):
        built = agent_spec.build_agent_spec(
            "scout", _agent_file(**{**VALID_FRONTMATTER, key: "  padded \t"})
        )

        assert getattr(built, key) == "padded"


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

        rate = external.pricing().rate(
            external.pricing().load_pricing(paths.PRICING_PATH), model
        )

        assert rate is not None
        assert rate["input"] > 0 and rate["output"] > 0
