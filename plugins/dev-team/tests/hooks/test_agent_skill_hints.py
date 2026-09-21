"""Unit tests for hooks/lib/agent_skill_hints.py (#2187, Slice 1 Step 1.1).

Uses a fixture agent `.md` file written to a temp `agents_dir` per test,
rather than a real production agent file, so these tests don't couple to
production frontmatter that can drift (per the plan's Step 1.1 TEST note).
"""

from __future__ import annotations

import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

from agent_skill_hints import skills_for_agent_type


def _write_agent(agents_dir: Path, name: str, body: str) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(body, encoding="utf-8")


def test_known_agent_type_with_skills_returns_the_list(tmp_path: Path) -> None:
    _write_agent(
        tmp_path,
        "fixture-agent",
        "---\n"
        "name: fixture-agent\n"
        "description: test fixture\n"
        "skills:\n"
        "  - test-driven-development\n"
        "  - systematic-debugging\n"
        "---\n\n# Fixture Agent\n",
    )

    assert skills_for_agent_type("fixture-agent", tmp_path) == [
        "test-driven-development",
        "systematic-debugging",
    ]


def test_unrecognized_agent_type_returns_empty_list(tmp_path: Path) -> None:
    assert skills_for_agent_type("not-a-real-agent", tmp_path) == []


def test_agent_file_with_no_skills_key_returns_empty_list(tmp_path: Path) -> None:
    _write_agent(
        tmp_path,
        "no-skills-agent",
        "---\nname: no-skills-agent\ndescription: no skills field\n---\n\n# Body\n",
    )

    assert skills_for_agent_type("no-skills-agent", tmp_path) == []


def test_malformed_frontmatter_returns_empty_list_without_raising(
    tmp_path: Path,
) -> None:
    # Missing the closing `---` marker — FrontmatterError from
    # extract_frontmatter_block.
    _write_agent(
        tmp_path,
        "malformed-unterminated",
        "---\nname: malformed-unterminated\nskills:\n  - foo\n\n# Body\n",
    )
    assert skills_for_agent_type("malformed-unterminated", tmp_path) == []

    # Well-terminated frontmatter but invalid YAML shape — YamlError from
    # parse_yaml (unquoted scalar containing ": ").
    _write_agent(
        tmp_path,
        "malformed-bad-yaml",
        "---\nname: malformed-bad-yaml\nskills: not: a: list\n---\n\n# Body\n",
    )
    assert skills_for_agent_type("malformed-bad-yaml", tmp_path) == []
