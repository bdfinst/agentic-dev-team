"""Structural invariants for the security-assessment plugin's /upgrade
command. The plugin ships its own /upgrade (parallel to dev-team's) so
users with only the security plugin installed have an in-session update
path.

Ported from tests/commands/security_upgrade_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

UPGRADE = REPO_ROOT / "plugins" / "security-assessment" / "commands" / "upgrade.md"


@pytest.fixture(scope="module")
def text() -> str:
    return UPGRADE.read_text(encoding="utf-8")


def test_ships_upgrade_md_command() -> None:
    assert UPGRADE.is_file()


def test_upgrade_frontmatter_declares_name_and_user_invocable(text: str) -> None:
    # YAML frontmatter is between the first two '---' lines.
    lines = text.splitlines()
    fence_indices = [i for i, line in enumerate(lines) if line == "---"]
    assert len(fence_indices) >= 2
    frontmatter = "\n".join(lines[fence_indices[0] + 1 : fence_indices[1]])
    assert re.search(r"^name:\s*upgrade$", frontmatter, re.MULTILINE)
    assert re.search(r"^user-invocable:\s*true$", frontmatter, re.MULTILINE)


def test_upgrade_targets_correct_plugin_id(text: str) -> None:
    # The Python detection block must pin PLUGIN to security-assessment.
    assert re.search(r'PLUGIN\s*=\s*"security-assessment"', text)
    # And the install/update commands must reference security-assessment,
    # not dev-team.
    assert "security-assessment@{marketplace}" in text


def test_upgrade_uses_scope_on_plugin_update(text: str) -> None:
    # Same scope-detection contract as dev-team's /upgrade — must not let
    # the CLI default to user-scope against a project-scope install.
    assert re.search(
        r"claude plugin update --scope \{scope\} security-assessment@\{marketplace\}",
        text,
    )


def test_upgrade_asks_before_enabling_auto_update(text: str) -> None:
    # No silent enablement: the consent prompt + yes-branch wording must be
    # present.
    assert re.search(r"Would you like to enable auto-update", text)
    assert re.search(
        r"enable block.*run only if the user consents", text, re.IGNORECASE
    )


def test_upgrade_warns_about_marketplace_scope_of_auto_update_flag(
    text: str,
) -> None:
    # Auto-update is per-marketplace, not per-plugin — users must
    # understand consenting here also affects dev-team.
    assert re.search(r"marketplace-level", text, re.IGNORECASE)
    assert "dev-team" in text


def test_upgrade_surfaces_companion_dependency_check(text: str) -> None:
    # If dev-team isn't installed, the user should be told.
    assert re.search(
        r"(dev-team@.* is not installed|"
        r"claude plugin install --scope \{scope\} dev-team@\{marketplace\})",
        text,
    )


def test_upgrade_prompts_a_restart(text: str) -> None:
    assert re.search(r"Restart Claude Code", text)


def test_upgrade_registered_in_claude_md_dispatch_table() -> None:
    claude_md = REPO_ROOT / "plugins" / "security-assessment" / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    # Must appear in the dispatch registry table.
    assert re.search(r"\| `/upgrade` \|", text)
    # And in the Commands list (count bumped from 4 to 5).
    assert re.search(r"\*\*Commands\*\* \(5\)", text)


def test_upgrade_documented_in_readme() -> None:
    readme = REPO_ROOT / "plugins" / "security-assessment" / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert re.search(r"^## Update", text, re.MULTILINE)
    assert re.search(r"\| `/upgrade` \|", text)
