"""Gate for the Model column of plugins/dev-team/docs/agent_info.md.

Agent frontmatter is authoritative; every row under a table header that has
Agent and Model columns must name the model its agent file declares.
"""

from __future__ import annotations

import pytest
from _plugin_dirs import frontmatter_block, frontmatter_field

from _repo_root import REPO_ROOT

AGENT_INFO_PATH = REPO_ROOT / "plugins" / "dev-team" / "docs" / "agent_info.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
AGENT_INFO_AGENT_COLUMN = "Agent"
AGENT_INFO_MODEL_COLUMN = "Model"
ERROR_EXCERPT_WIDTH = 60


class AgentInfoRowError(ValueError):
    """A row of the agent_info.md model table has fewer cells than its header."""


def agent_info_model_pairs(text: str) -> list[tuple[str, str]]:
    """(agent, model) per row of the table whose header has Agent and Model columns.

    Raises:
        AgentInfoRowError: a row has too few cells to reach the Agent or Model column.
    """
    pairs, columns = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            columns = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if columns is None:
            if AGENT_INFO_AGENT_COLUMN in cells and AGENT_INFO_MODEL_COLUMN in cells:
                columns = (
                    cells.index(AGENT_INFO_AGENT_COLUMN),
                    cells.index(AGENT_INFO_MODEL_COLUMN),
                )
            continue
        if set("".join(cells)) <= {"-", ":", " "}:
            continue
        agent_index, model_index = columns
        if len(cells) <= max(agent_index, model_index):
            raise AgentInfoRowError(
                f"row has {len(cells)} cells, needs {max(agent_index, model_index) + 1}: "
                f"{line[:ERROR_EXCERPT_WIDTH]}"
            )
        pairs.append((cells[agent_index].strip("`"), cells[model_index]))
    return pairs


def agent_info_mismatches(pairs, declared_model_for) -> list[str]:
    """One error per pair whose table model differs from the declared one."""
    errors = []
    for agent, table_model in pairs:
        declared = declared_model_for(agent)
        if declared is None:
            errors.append(f"{agent}: no agent file")
        elif declared != table_model:
            errors.append(
                f"{agent}: table says {table_model}, frontmatter says {declared}"
            )
    return errors


def repo_declared_model(agent: str):
    source = AGENTS_DIR / f"{agent}.md"
    return (
        frontmatter_field(frontmatter_block(source), "model")
        if source.is_file()
        else None
    )


# --- real repository ---------------------------------------------------------


def test_agent_info_model_column_matches_frontmatter():
    pairs = agent_info_model_pairs(AGENT_INFO_PATH.read_text(encoding="utf-8"))
    assert pairs, "no agent rows found under a Model column"
    assert agent_info_mismatches(pairs, repo_declared_model) == []


# --- synthetic fixtures ------------------------------------------------------

AGENT_INFO_TABLE = """\
| Agent | File | Purpose |
| --- | --- | --- |
| `team` | t.md | not a model table |

| Agent | File | Model | What It Checks |
| --- | --- | --- | --- |
| `a` | a.md | sonnet | x |
| `b` | b.md | haiku | y |
"""


def test_agent_info_pairs_come_from_the_model_column_only():
    assert agent_info_model_pairs(AGENT_INFO_TABLE) == [("a", "sonnet"), ("b", "haiku")]


def test_agent_info_row_shorter_than_the_header_is_a_named_error():
    text = AGENT_INFO_TABLE + "| `c` | c.md |\n"
    with pytest.raises(AgentInfoRowError, match="row has 2 cells, needs 3"):
        agent_info_model_pairs(text)


def test_agent_info_table_without_a_model_column_yields_no_pairs():
    assert (
        agent_info_model_pairs("| Agent | File |\n| --- | --- |\n| `a` | a.md |\n")
        == []
    )


def test_agent_info_model_mismatch_is_reported():
    declared = {"a": "sonnet", "b": "sonnet"}.get
    assert agent_info_mismatches(
        agent_info_model_pairs(AGENT_INFO_TABLE), declared
    ) == ["b: table says haiku, frontmatter says sonnet"]


def test_agent_info_row_without_an_agent_file_is_reported():
    assert agent_info_mismatches([("ghost", "haiku")], {}.get) == [
        "ghost: no agent file"
    ]
