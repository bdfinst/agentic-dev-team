"""#1108 — /project-init Step 4c offers the three code-lookup tools as one
all-or-none group and installs Repowise (keyless, gitignored, MCP-registered).

#1134 — accepting the group installs *and builds* the keyless CodeGraph and
Repowise indexes in the same run (CodeGraph via `npm install -g
@colbymchenry/codegraph` + non-interactive `codegraph init .`).

#1135 — the group stays all-or-none, but the prompt must disclose that Graphify
(unlike the keyless indexes) requires a model/API key, and Graphify's graph
build is idempotent (`graphify update .` when a graph exists) and non-fatal.

Content-guard sensor over the shipped project-init SKILL.md prose — a pure text
grep, no state-mutating operations.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "project-init" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


# --- All-or-none group -------------------------------------------------------


def test_step_4c_is_all_or_none_group():
    text = _text()
    assert "all-or-none" in text
    assert "CodeGraph" in text and "Repowise" in text and "Graphify" in text


def test_group_recommends_yes_when_missing():
    # The prompt's recommended default is yes ([Y/n]) when anything is missing.
    assert "[Y/n]" in _text()


def test_group_scopes_to_missing_set_idempotently():
    text = _text()
    assert "missing" in text
    assert "already present" in text  # idempotent: skip when all present


def test_group_respects_prior_explicit_decline():
    text = _text()
    assert "install_declined" in text
    assert "excluded from the" in text or "excluded from" in text


def test_group_discloses_graphify_repo_footprint():
    text = _text()
    # The prompt copy must name Graphify's CLAUDE.md write + git hooks.
    assert "CLAUDE.md" in text and "git hooks" in text


def test_group_prints_terminal_visible_decline_message():
    text = _text()
    assert "fall back to Read/Grep/Glob" in text
    assert "re-run /project-init" in text


def test_group_surfaces_partial_install_failure():
    text = _text()
    assert "Partial failure" in text or "partially installed" in text


# --- Repowise sub-section ----------------------------------------------------


def test_repowise_subsection_present():
    assert "#### Repowise" in _text()


def test_repowise_install_is_keyless_and_gitignored():
    text = _text()
    assert "--index-only" in text  # keyless index
    assert ".repowise/" in text  # gitignored index location


def test_repowise_registers_mcp_and_flags_server_name_coupling():
    text = _text()
    assert "mcp add" in text
    assert "plugin_repowise_repowise" in text  # server-name caveat


def test_repowise_has_detection_probe():
    text = _text()
    assert "command -v repowise" in text


# --- #1134: CodeGraph + Repowise install AND build keyless indexes -----------


def test_codegraph_installs_keyless_package():
    # Accepting the group installs the CLI, not just prints instructions.
    assert "npm install -g @colbymchenry/codegraph" in _text()


def test_codegraph_builds_index_non_interactively():
    text = _text()
    assert "codegraph init ." in text
    assert "codegraph init -i" not in text  # no interactive flag (#1134)


def test_group_states_codegraph_repowise_are_keyless():
    text = _text()
    # Both keyless tools must be labeled as needing no API key.
    assert "keyless" in text.lower()


# --- #1135: Graphify's model/API-key requirement is disclosed ----------------


def test_group_prompt_discloses_graphify_key_requirement():
    text = _text()
    # The all-or-none prompt must warn that Graphify needs a model/API key.
    assert "REQUIRES a model/API key" in text


def test_graphify_build_is_idempotent_with_update_fallback():
    text = _text()
    assert "graphify extract ." in text  # fresh build
    assert "graphify update ." in text  # incremental refresh when graph exists
    assert "graphify-out/graph.json" in text  # idempotency probe


def test_graphify_build_is_non_fatal():
    text = _text()
    # Extraction failure (e.g. no key) is reported, not aborting setup.
    assert "build_failed" in text
