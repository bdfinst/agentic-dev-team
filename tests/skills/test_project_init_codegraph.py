"""Doc-inspection tests for the state-aware CodeGraph step (Step 4c) in
/project-init. The command is an LLM-interpreted markdown spec; the only
stable test surface is the literal strings the spec must contain. Each test
pins one specific string the implementer must preserve.

CodeGraph's install/init state machine originally lived in
/init-dev-team's Step 2.5 and was migrated to /project-init's Step 4c
(issue #846), replacing the old "commit .mcp.json to share with the team"
behavior with a personal/user-scope MCP registration instead. This file was
ported and retargeted from
tests/commands/test_init_dev_team_codegraph.py accordingly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CMD = REPO_ROOT / "plugins" / "dev-team" / "skills" / "project-init" / "SKILL.md"


@pytest.fixture(scope="module")
def text() -> str:
    return CMD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# State classifier (entry to the CodeGraph step)
# ---------------------------------------------------------------------------


def test_state_classifier_installed_detection_documented(text: str) -> None:
    assert "command -v codegraph" in text


def test_state_classifier_initialized_detection_documented(text: str) -> None:
    assert '[ -d "${PWD}/.codegraph" ]' in text


# ---------------------------------------------------------------------------
# Install prompt branch (installed=false, initialized=false)
# ---------------------------------------------------------------------------


def test_install_prompt_text_present(text: str) -> None:
    assert "Install CodeGraph for code intelligence? (y/N)" in text


def test_install_accept_url_present(text: str) -> None:
    # Kept as the non-fatal manual-install hint when npm install fails.
    assert "https://github.com/colbymchenry/codegraph#installation" in text


def test_install_runs_npm_package(text: str) -> None:
    # #1134: accepting installs the CLI keylessly rather than only printing a URL.
    assert "npm install -g @colbymchenry/codegraph" in text


# ---------------------------------------------------------------------------
# Init prompt branch (installed=true, initialized=false)
# ---------------------------------------------------------------------------


def test_init_prompt_text_present(text: str) -> None:
    assert (
        "CodeGraph is installed but not initialized in this project. "
        "Initialize now? (y/N)" in text
    )


def test_init_run_command_documented(text: str) -> None:
    # #1134: non-interactive init targeting the repo dir (no -i flag).
    assert "codegraph init ." in text


def test_init_run_command_is_non_interactive(text: str) -> None:
    # The interactive `-i` form must not reappear anywhere in the spec.
    assert "codegraph init -i" not in text


def test_init_run_announcement_present(text: str) -> None:
    assert "Running 'codegraph init .' in this project..." in text


def test_init_success_message_present(text: str) -> None:
    assert "CodeGraph: initialized ✓" in text


def test_init_failure_message_present(text: str) -> None:
    assert "CodeGraph init failed (exit code" in text


# ---------------------------------------------------------------------------
# MCP registration (personal, user-scope — replaces the old "share with the
# team" committed .mcp.json behavior). See ADR 0012 and the #846 migration.
# ---------------------------------------------------------------------------


def test_mcp_registration_heading_present(text: str) -> None:
    assert (
        "Register the MCP server at user scope (never a repo file)" in text
    )


def test_mcp_registration_command_documented(text: str) -> None:
    assert "claude mcp add codegraph -- codegraph serve --mcp" in text


def test_mcp_registration_is_not_committed(text: str) -> None:
    assert (
        "Do not attempt to write `.mcp.json` in the project root, and do\n"
        "not run `git add`/`git commit` for anything under `.codegraph/`."
        in text
    )


def test_no_committed_mcp_json_write(text: str) -> None:
    # The old shared-.mcp.json write must not reappear.
    assert '"command":"codegraph","args":["serve","--mcp"]' not in text


def test_no_share_with_team_heading(text: str) -> None:
    # The old "Share CodeGraph with the team" step is intentionally gone.
    assert "Share CodeGraph with the team" not in text


# ---------------------------------------------------------------------------
# Skip-note texts (state-aware re-runs)
# ---------------------------------------------------------------------------


def test_decline_install_skip_note_text(text: str) -> None:
    assert (
        "CodeGraph: previously declined install (remove the codegraph key "
        "from .claude/init-state.json to re-prompt)" in text
    )


def test_decline_init_skip_note_text(text: str) -> None:
    assert (
        "CodeGraph: previously declined init (remove the codegraph key "
        "from .claude/init-state.json to re-prompt)" in text
    )


# ---------------------------------------------------------------------------
# State keys + stale-state override
# ---------------------------------------------------------------------------


def test_state_keys_install_accepted_documented(text: str) -> None:
    assert "install_accepted" in text


def test_state_keys_install_declined_documented(text: str) -> None:
    assert "install_declined" in text


def test_state_keys_init_accepted_documented(text: str) -> None:
    assert "init_accepted" in text


def test_state_keys_init_declined_documented(text: str) -> None:
    assert "init_declined" in text


def test_stale_state_override_documented(text: str) -> None:
    # The doc must explain that install_declined is ignored when
    # installed=true AND init_declined is ignored when initialized=true. We
    # check for a single heading that introduces this rule.
    assert "Stale-state override" in text
