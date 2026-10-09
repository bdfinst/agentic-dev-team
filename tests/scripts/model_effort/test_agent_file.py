"""Agent file loading (model_effort.agent_file)."""

from __future__ import annotations

import pytest
from _model_effort_support import _write_agent
from model_effort import agent_file


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
