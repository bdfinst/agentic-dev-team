"""CI freshness gate. docs/skills.md is generated from each skills/<name>/SKILL.md
frontmatter (name + description). It must match what a fresh build produces, so
a skill added/removed/renamed — or a description edited — can never leave the
catalog stale (the drift that left 14 skills uncatalogued before this gate).

Ported from tests/repo/skills_index_current.bats (issue #671).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "build_skills_index.py"


def _run_builder(
    args: list[str], env: dict | None = None
) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        env=full_env,
        capture_output=True,
        text=True,
    )


def test_skills_md_is_current_with_the_skills_on_disk() -> None:
    res = _run_builder(["--check"])
    assert res.returncode == 0, res.stdout + res.stderr


def test_every_skill_on_disk_appears_in_the_generated_catalog() -> None:
    skills_dir = REPO_ROOT / "plugins" / "dev-team" / "skills"
    disk = sorted(p.name for p in skills_dir.iterdir() if p.is_dir())
    catalog = (REPO_ROOT / "plugins" / "dev-team" / "docs" / "skills.md").read_text()
    indexed = sorted(
        set(
            m.group(1)
            for m in re.finditer(r"skills/([A-Za-z0-9._-]+)/SKILL\.md", catalog)
        )
    )
    assert disk == indexed


def test_a_new_skill_makes_check_fail_until_the_catalog_is_rebuilt(
    tmp_path: Path,
) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "one" / "SKILL.md").write_text(
        "---\nname: one\ndescription: First.\nuser-invocable: true\n---\n"
    )
    (tmp_path / "two").mkdir()
    (tmp_path / "two" / "SKILL.md").write_text(
        "---\nname: two\ndescription: Second.\n---\n"
    )
    out = tmp_path / "skills.md"

    env = {"SKILLS_INDEX_SKILLS_DIR": str(tmp_path), "SKILLS_INDEX_OUTPUT": str(out)}
    _run_builder([], env=env)
    res = _run_builder(["--check"], env=env)
    assert res.returncode == 0, res.stdout + res.stderr

    # Add a skill without rebuilding -> the gate fails.
    (tmp_path / "three").mkdir()
    (tmp_path / "three" / "SKILL.md").write_text(
        "---\nname: three\ndescription: Third.\nuser-invocable: true\n---\n"
    )
    res = _run_builder(["--check"], env=env)
    assert res.returncode == 1
    assert "three" in (res.stdout + res.stderr)


def test_user_invocable_skills_render_as_slash_commands_agent_loaded_do_not(
    tmp_path: Path,
) -> None:
    (tmp_path / "cmd").mkdir()
    (tmp_path / "cmd" / "SKILL.md").write_text(
        "---\nname: cmd\ndescription: A command.\nuser-invocable: true\n---\n"
    )
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "SKILL.md").write_text(
        "---\nname: lib\ndescription: A module.\n---\n"
    )
    out = tmp_path / "skills.md"
    env = {"SKILLS_INDEX_SKILLS_DIR": str(tmp_path), "SKILLS_INDEX_OUTPUT": str(out)}
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "`/cmd`" in rendered
    assert "| lib |" in rendered
    assert "`/lib`" not in rendered


def test_unparseable_frontmatter_fails_the_build_loudly(tmp_path: Path) -> None:
    # An unquoted description with a bare ': ' is invalid YAML — the builder must
    # error naming the file, not emit an empty/miscategorized row.
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "SKILL.md").write_text(
        "---\nname: bad\ndescription: refers to foo: bar inline\nuser-invocable: true\n---\n"
    )
    env = {
        "SKILLS_INDEX_SKILLS_DIR": str(tmp_path),
        "SKILLS_INDEX_OUTPUT": str(tmp_path / "o.md"),
    }
    res = _run_builder([], env=env)
    assert res.returncode == 1
    assert "bad/SKILL.md" in (res.stdout + res.stderr)


def test_a_description_with_a_pipe_is_escaped_for_the_table(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "SKILL.md").write_text(
        "---\nname: p\ndescription: alpha | beta\nuser-invocable: true\n---\n"
    )
    out = tmp_path / "skills.md"
    env = {"SKILLS_INDEX_SKILLS_DIR": str(tmp_path), "SKILLS_INDEX_OUTPUT": str(out)}
    _run_builder([], env=env)
    assert "alpha \\| beta" in out.read_text()


def test_catalog_is_grouped_by_capability_not_by_invocation_type() -> None:
    md = (REPO_ROOT / "plugins" / "dev-team" / "docs" / "skills.md").read_text()
    assert re.search(r"^## Specs & Planning", md, re.MULTILINE)
    assert re.search(r"^## Testing & Coverage", md, re.MULTILINE)
    assert re.search(r"^## Harness Governance & Tuning", md, re.MULTILINE)
    # the old invocation-type sections are gone
    assert not re.search(r"^## User-invocable skills", md, re.MULTILINE)
    assert not re.search(r"^## Agent-loaded skills", md, re.MULTILINE)


def test_options_column_argument_hint_used_verbatim(tmp_path: Path) -> None:
    (tmp_path / "cmd").mkdir()
    (tmp_path / "cmd" / "SKILL.md").write_text(
        "---\nname: cmd\ndescription: A command.\nuser-invocable: true\n"
        "argument-hint: \"<path> [--dry-run]\"\n---\n"
    )
    out = tmp_path / "skills.md"
    env = {"SKILLS_INDEX_SKILLS_DIR": str(tmp_path), "SKILLS_INDEX_OUTPUT": str(out)}
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "<path> [--dry-run]" in rendered


def test_options_column_no_flags_fallback_for_user_invocable_without_hint(
    tmp_path: Path,
) -> None:
    (tmp_path / "cmd").mkdir()
    (tmp_path / "cmd" / "SKILL.md").write_text(
        "---\nname: cmd\ndescription: A command.\nuser-invocable: true\n---\n"
    )
    out = tmp_path / "skills.md"
    env = {"SKILLS_INDEX_SKILLS_DIR": str(tmp_path), "SKILLS_INDEX_OUTPUT": str(out)}
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "no flags — run directly" in rendered
    # The table row for this skill should not say "agent-loaded"
    for line in rendered.splitlines():
        if "`/cmd`" in line:
            assert "agent-loaded" not in line, f"Unexpected agent-loaded in row: {line}"


def test_options_column_agent_loaded_fallback(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "SKILL.md").write_text(
        "---\nname: lib\ndescription: A module.\n---\n"
    )
    out = tmp_path / "skills.md"
    env = {"SKILLS_INDEX_SKILLS_DIR": str(tmp_path), "SKILLS_INDEX_OUTPUT": str(out)}
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "agent-loaded — not directly invocable" in rendered
    assert "no flags" not in rendered


def test_commands_dir_entries_are_included(tmp_path: Path) -> None:
    """commands/*.md are unioned with skills/*/SKILL.md in the catalog."""
    plugin_dir = tmp_path / "plugin"
    skills_dir = plugin_dir / "skills"
    commands_dir = plugin_dir / "commands"
    docs_dir = plugin_dir / "docs"
    skills_dir.mkdir(parents=True)
    commands_dir.mkdir()
    docs_dir.mkdir()

    (skills_dir / "myskill").mkdir()
    (skills_dir / "myskill" / "SKILL.md").write_text(
        "---\nname: myskill\ndescription: A skill.\nuser-invocable: false\n---\n"
    )
    (commands_dir / "mycmd.md").write_text(
        "---\nname: mycmd\ndescription: A command.\nuser-invocable: true\n"
        "argument-hint: \"<target>\"\n---\n"
    )
    out = docs_dir / "skills.md"
    env = {
        "SKILLS_INDEX_SKILLS_DIR": str(skills_dir),
        "SKILLS_INDEX_OUTPUT": str(out),
    }
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "myskill" in rendered
    assert "`/mycmd`" in rendered
    assert "<target>" in rendered


def test_missing_categories_file_produces_ungrouped_section(
    tmp_path: Path,
) -> None:
    """When no skill_categories.yaml exists the catalog renders one 'Ungrouped' section."""
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: Alpha.\nuser-invocable: true\n---\n"
    )
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "SKILL.md").write_text(
        "---\nname: beta\ndescription: Beta.\n---\n"
    )
    out = tmp_path / "skills.md"
    # Point categories at a non-existent file
    env = {
        "SKILLS_INDEX_SKILLS_DIR": str(tmp_path),
        "SKILLS_INDEX_OUTPUT": str(out),
        "SKILLS_INDEX_CATEGORIES": str(tmp_path / "nonexistent_cats.yaml"),
    }
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "## Ungrouped" in rendered
    assert "## Other" not in rendered


def test_plugin_dir_flag_points_to_security_assessment(tmp_path: Path) -> None:
    """--plugin-dir with security-assessment unions skills/ (3) and commands/ (5) = 8 entries."""
    sa_dir = REPO_ROOT / "plugins" / "security-assessment"
    if not sa_dir.is_dir():
        return  # plugin not present in this checkout
    out = tmp_path / "sa-skills.md"
    env = {"SKILLS_INDEX_OUTPUT": str(out)}
    res = _run_builder(["--plugin-dir", str(sa_dir)], env=env)
    assert res.returncode == 0, res.stderr
    rendered = out.read_text()
    # 3 skills + 5 commands = 8 entries; count SKILL.md and .md links
    skill_links = re.findall(r"\[`[^`]+`\]\(\.\./(?:skills|commands)/", rendered)
    assert len(skill_links) == 8, f"Expected 8 entries, got {len(skill_links)}: {skill_links}"


def test_a_skill_outside_the_taxonomy_lands_in_a_trailing_other_section(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / "skills"
    (skills_dir / "known").mkdir(parents=True)
    (skills_dir / "known" / "SKILL.md").write_text(
        "---\nname: known\ndescription: Known.\nuser-invocable: true\n---\n"
    )
    (skills_dir / "stray").mkdir()
    (skills_dir / "stray" / "SKILL.md").write_text(
        "---\nname: stray\ndescription: Stray.\nuser-invocable: true\n---\n"
    )
    cats = tmp_path / "cats.yaml"
    cats.write_text("categories:\n  - name: Demo\n    skills: [known]\n")
    out = tmp_path / "skills.md"
    env = {
        "SKILLS_INDEX_SKILLS_DIR": str(skills_dir),
        "SKILLS_INDEX_OUTPUT": str(out),
        "SKILLS_INDEX_CATEGORIES": str(cats),
    }
    _run_builder([], env=env)
    rendered = out.read_text()
    assert "\n## Demo" in rendered or rendered.startswith("## Demo")
    assert "## Other" in rendered
    assert "`/known`" in rendered
    assert "`/stray`" in rendered
