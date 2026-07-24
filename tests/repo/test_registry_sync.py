"""Registry-completeness sensor. knowledge/agent-registry.md (agents + agent-loaded
skills) and the plugin CLAUDE.md slash-command table (user-invocable skills)
must stay in sync with the agents/ and skills/ on disk. This is the drift class
that silently desynced the routing tables (unregistered agents/skills, orphaned
rows). The check fails loudly so /agent-create, /agent-remove, or a hand-edit
cannot leave the catalog stale.

Ported from tests/repo/registry_sync_tests.bats (issue #671).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

CHECK = REPO_ROOT / "scripts" / "check_registry_sync.py"

_AGENT_REGISTRY = """## Review Agents

| Agent | File | What It Checks |
|-------|------|----------------|
| foo | `agents/foo.md` | something |

## Skills Registry

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Bar | `skills/bar/SKILL.md` | 100 | Orchestrator |
"""

_AGENT_REGISTRY_WITH_ORPHAN = """## Review Agents

| Agent | File | What It Checks |
|-------|------|----------------|
| foo | `agents/foo.md` | something |
| gone | `agents/gone.md` | orphan row, no file on disk |

## Skills Registry

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Bar | `skills/bar/SKILL.md` | 100 | Orchestrator |
"""

_AGENT_REGISTRY_NO_BAR_SKILL = """## Review Agents

| Agent | File | What It Checks |
|-------|------|----------------|
| foo | `agents/foo.md` | something |

## Skills Registry

| Skill | File | ~Tokens | Used By |
|-------|------|---------|---------|
| Baz | `skills/baz/SKILL.md` | 100 | Orchestrator |
"""


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    """A minimal synthetic plugin tree the script can scan in isolation."""
    (tmp_path / "plugins" / "dev-team" / "agents").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "skills" / "bar").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "knowledge").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "agents" / "foo.md").write_text(
        "---\nname: foo\n---\n"
    )
    (tmp_path / "plugins" / "dev-team" / "skills" / "bar" / "SKILL.md").write_text(
        "---\nname: bar\n---\n"
    )
    (tmp_path / "plugins" / "dev-team" / "knowledge" / "agent-registry.md").write_text(
        _AGENT_REGISTRY
    )
    (tmp_path / "plugins" / "dev-team" / "CLAUDE.md").write_text("# Plugin CLAUDE.md\n")
    return tmp_path


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_passes_on_the_real_repository_tree() -> None:
    res = _run(REPO_ROOT)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_fully_registered_fixture_is_in_sync(fixture_root: Path) -> None:
    res = _run(fixture_root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_an_agent_file_with_no_registry_row_fails_missing(fixture_root: Path) -> None:
    (fixture_root / "plugins" / "dev-team" / "agents" / "extra.md").write_text(
        "---\nname: extra\n---\n"
    )
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "MISSING" in out
    assert "agents/extra.md" in out


def test_a_registry_row_pointing_at_a_missing_file_fails_orphan(
    fixture_root: Path,
) -> None:
    # The orphan row must live inside the Review Agents section — agent extraction
    # is scoped there so prose mentions elsewhere are not mistaken for rows.
    (
        fixture_root / "plugins" / "dev-team" / "knowledge" / "agent-registry.md"
    ).write_text(_AGENT_REGISTRY_WITH_ORPHAN)
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "ORPHAN" in out
    assert "agents/gone.md" in out


def test_a_skill_with_no_catalog_row_fails_missing(fixture_root: Path) -> None:
    (fixture_root / "plugins" / "dev-team" / "skills" / "baz").mkdir()
    (fixture_root / "plugins" / "dev-team" / "skills" / "baz" / "SKILL.md").write_text(
        "---\nname: baz\n---\n"
    )
    res = _run(fixture_root)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "MISSING" in out
    assert "skills/baz/SKILL.md" in out


def test_a_slash_command_skill_catalogued_only_in_claude_md_is_in_sync(
    fixture_root: Path,
) -> None:
    (fixture_root / "plugins" / "dev-team" / "skills" / "cmd").mkdir()
    (fixture_root / "plugins" / "dev-team" / "skills" / "cmd" / "SKILL.md").write_text(
        "---\nname: cmd\n---\n"
    )
    claude_md = fixture_root / "plugins" / "dev-team" / "CLAUDE.md"
    with claude_md.open("a") as f:
        f.write("| `/cmd` | `skills/cmd/SKILL.md` | worker | does a thing |\n")
    res = _run(fixture_root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_slash_command_skill_catalogued_only_in_skills_registry_md_is_in_sync(
    fixture_root: Path,
) -> None:
    # After the CLAUDE.md size reduction, user-invocable skill paths move from the
    # CLAUDE.md table to knowledge/skills-registry.md. The script must scan that
    # file as a third source so no skills are reported MISSING.
    # Fixture: agent-registry.md has NO skill paths, CLAUDE.md has no skill paths;
    # skills-registry.md has bar/SKILL.md. The script should exit 0 (bar is found
    # via the knowledge file).
    (fixture_root / "plugins" / "dev-team" / "skills" / "baz").mkdir()
    (fixture_root / "plugins" / "dev-team" / "skills" / "baz" / "SKILL.md").write_text(
        "---\nname: baz\n---\n"
    )
    # Overwrite agent-registry to remove bar from Skills Registry
    (
        fixture_root / "plugins" / "dev-team" / "knowledge" / "agent-registry.md"
    ).write_text(_AGENT_REGISTRY_NO_BAR_SKILL)
    # bar is registered only via knowledge/skills-registry.md, not CLAUDE.md or
    # agent-registry.md
    (
        fixture_root / "plugins" / "dev-team" / "knowledge" / "skills-registry.md"
    ).write_text("| `/bar` | `skills/bar/SKILL.md` | worker | does a thing |\n")
    res = _run(fixture_root)
    assert res.returncode == 0, res.stdout + res.stderr
