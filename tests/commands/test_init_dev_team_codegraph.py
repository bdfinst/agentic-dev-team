"""Doc-inspection tests for the state-aware CodeGraph step in
/init-dev-team. The command is an LLM-interpreted markdown spec; the only
stable test surface is the literal strings the spec must contain. Each test
pins one specific string the implementer must preserve.

Ported from tests/commands/init_dev_team_codegraph_test.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CMD = REPO_ROOT / "plugins" / "dev-team" / "skills" / "init-dev-team" / "SKILL.md"


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
    assert "https://github.com/colbymchenry/codegraph#installation" in text


# ---------------------------------------------------------------------------
# Init prompt branch (installed=true, initialized=false)
# ---------------------------------------------------------------------------


def test_init_prompt_text_present(text: str) -> None:
    assert (
        "CodeGraph is installed but not initialized in this project. "
        "Initialize now? (y/N)" in text
    )


def test_init_run_command_documented(text: str) -> None:
    assert "codegraph init -i" in text


def test_init_run_announcement_present(text: str) -> None:
    assert "Running 'codegraph init -i' in this project..." in text


def test_init_success_message_present(text: str) -> None:
    assert "CodeGraph: initialized ✓" in text


def test_init_failure_message_present(text: str) -> None:
    assert "CodeGraph init failed (exit code" in text


# ---------------------------------------------------------------------------
# Share-with-the-team step (after a successful init): commit .mcp.json so
# clones auto-bootstrap. See ADR 0012.
# ---------------------------------------------------------------------------


def test_share_step_heading_present(text: str) -> None:
    assert "Share CodeGraph with the team" in text


def test_share_step_writes_mcp_json(text: str) -> None:
    assert '"command":"codegraph","args":["serve","--mcp"]' in text


def test_share_step_merge_preserves_existing_servers(text: str) -> None:
    # Deep-merge so an existing mcpServers entry is not clobbered.
    assert ". * $add" in text


def test_share_step_commit_guidance_present(text: str) -> None:
    assert (
        "commit it with .codegraph/.gitignore so teammates auto-bootstrap "
        "CodeGraph on clone" in text
    )


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


# ---------------------------------------------------------------------------
# Step 9 — JS bootstrap via js-project-init when no package.json
# ---------------------------------------------------------------------------


def test_js_bootstrap_check_present(text: str) -> None:
    assert "test -f package.json" in text


def test_js_bootstrap_announcement_present(text: str) -> None:
    assert (
        "No package.json found. Running /dev-team:js-project-init first to "
        "scaffold the project." in text
    )


def test_js_bootstrap_invokes_skill(text: str) -> None:
    assert "/dev-team:js-project-init" in text


def test_js_abort_message_present(text: str) -> None:
    assert (
        "Stryker skipped — no package.json. Re-run /init-dev-team after "
        "scaffolding your JS project." in text
    )


def test_js_failure_message_present(text: str) -> None:
    assert (
        "Stryker skipped — js-project-init failed. See errors above and "
        "re-run /init-dev-team after resolving them." in text
    )


def test_js_package_present_path_unchanged(text: str) -> None:
    # The pre-existing 'Check if already installed (project-local)' section
    # must still be present and follow the new bootstrap block.
    assert "Check if already installed (project-local)" in text
