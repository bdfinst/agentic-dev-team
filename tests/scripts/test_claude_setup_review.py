"""Tests for scripts/claude_setup_review.py — claude setup review validator.

Ported from tests/scripts/claude_setup_review_tests.bats (issue #676).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

# Ships with the plugin: the `claude-setup-review` agent and the `/agent-audit`
# skill both name it via `${CLAUDE_PLUGIN_ROOT}/scripts/`, so it has to be
# inside the plugin for a user's install to resolve it at all.
SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "claude_setup_review.py"


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    (tmp_path / "agents").mkdir()
    return tmp_path


def run_review(plugin_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--plugin-root", str(plugin_root), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LANG": "C.UTF-8"},
    )


def make_valid_claude_md(plugin_root: Path) -> None:
    (plugin_root / "CLAUDE.md").write_text(
        "# Test Plugin\n\n## Overview\nA test plugin.\n"
    )


def make_valid_agent(
    plugin_root: Path, name: str = "my-agent", file: str | None = None
) -> None:
    filename = file or f"{name}.md"
    (plugin_root / "agents" / filename).write_text(
        f"---\nname: {name}\ndescription: does stuff\neffort: low\n---\n\n# {name}\n\nBody here.\n"
    )


# ---------------------------------------------------------------------------
# Step 1.1: Frontmatter field presence and effort validation
# ---------------------------------------------------------------------------


def test_1_1_missing_description_field_is_exit_1(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\nname: my-agent\neffort: low\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("description" in m for m in msgs), msgs
    assert any("my-agent.md" in i.get("file", "") for i in data["issues"]), data[
        "issues"
    ]


def test_1_1_missing_name_field_is_exit_1(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\ndescription: does stuff\neffort: low\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("name" in m for m in msgs), msgs


def test_1_1_missing_effort_field_is_exit_1(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\nname: my-agent\ndescription: does stuff\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("effort" in m for m in msgs), msgs


def test_1_1_invalid_effort_value_ultra_is_exit_1(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\nname: my-agent\ndescription: does stuff\neffort: ultra\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("ultra" in m or "effort" in m for m in msgs), msgs


def test_1_1_top_level_model_field_is_accepted_no_warning(
    plugin_root: Path,
) -> None:
    """A plugin agent's `model:` is honored per the verified contract
    (agent-contract.json) — only hooks/mcpServers/permissionMode are ignored
    for plugin-supplied agents, so `model:` alone must not warn."""
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\nname: my-agent\ndescription: does stuff\neffort: low\n"
        "model: claude-opus-4-5\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    data = json.loads(result.stdout)
    non_llm_issues = [
        i for i in data["issues"] if "llm-skipped" not in i.get("rule_id", "")
    ]
    assert non_llm_issues == [], non_llm_issues


def test_1_1_top_level_permission_mode_field_is_exit_2_with_warning_severity(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\nname: my-agent\ndescription: does stuff\neffort: low\n"
        "permissionMode: acceptEdits\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "warn", data
    severities = [
        i["severity"]
        for i in data["issues"]
        if "llm-skipped" not in i.get("rule_id", "")
    ]
    assert any(s == "warning" for s in severities), data["issues"]


def test_1_1_valid_agent_with_all_required_fields_is_exit_0_with_skip_llm(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    make_valid_agent(plugin_root, "my-agent")
    result = run_review(plugin_root, "--skip-llm")
    # exit 2 because --skip-llm adds a warning, but no errors
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] != "fail", data
    errs = [i for i in data["issues"] if i["severity"] == "error"]
    assert len(errs) == 0, errs


# ---------------------------------------------------------------------------
# Step 1.2: Path resolution, naming convention, and root discovery
# ---------------------------------------------------------------------------


def test_1_2_claude_md_reference_to_nonexistent_skill_path_is_exit_1_with_file_and_line(
    plugin_root: Path,
) -> None:
    (plugin_root / "CLAUDE.md").write_text(
        "# Test Plugin\n\nSee skills/nonexistent/SKILL.md for details.\n"
    )
    make_valid_agent(plugin_root, "my-agent")
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    line_issues = [i for i in data["issues"] if i.get("line", 0) > 0]
    assert len(line_issues) > 0, data["issues"]


def test_1_2_non_kebab_case_filename_myagent_md_is_exit_1(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "MyAgent.md").write_text(
        "---\nname: my-agent\ndescription: does stuff\neffort: low\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data


def test_1_2_filename_stem_and_name_field_mismatch_is_exit_1(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "my-agent.md").write_text(
        "---\nname: other-agent\ndescription: does stuff\neffort: low\n---\n\nBody.\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any(
        "mismatch" in m or "other-agent" in m or "my-agent" in m for m in msgs
    ), msgs


def test_1_2_no_claude_md_in_target_path_is_exit_1_with_descriptive_message(
    plugin_root: Path,
) -> None:
    make_valid_agent(plugin_root, "my-agent")
    # No CLAUDE.md created
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("CLAUDE.md" in m for m in msgs), msgs


def test_1_2_plugin_root_flag_sets_root_and_resolved_root_does_not_cause_failure(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    make_valid_agent(plugin_root, "my-agent")
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode != 1, result.stdout


def test_1_2_plugin_root_stderr_prints_resolved_root_path(plugin_root: Path) -> None:
    make_valid_claude_md(plugin_root)
    make_valid_agent(plugin_root, "my-agent")
    result = run_review(plugin_root, "--skip-llm")
    assert str(plugin_root) in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# Step 1.3: Duplicate name detection, JSON output, and LLM integration
# ---------------------------------------------------------------------------


def test_1_3_two_agents_with_same_name_is_exit_1_listing_both_paths(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    (plugin_root / "agents" / "agent-one.md").write_text(
        "---\nname: my-agent\ndescription: first agent\neffort: low\n---\n"
    )
    (plugin_root / "agents" / "agent-two.md").write_text(
        "---\nname: my-agent\ndescription: second agent\neffort: low\n---\n"
    )
    result = run_review(plugin_root, "--skip-llm")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = (
        " ".join(i["message"] for i in data["issues"])
        + " "
        + " ".join(i.get("file", "") for i in data["issues"])
    )
    assert "agent-one.md" in msgs or "agent-two.md" in msgs, data["issues"]


def test_1_3_clean_plugin_config_is_exit_2_when_no_llm_no_agents_dir(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    # No agents — no structural errors; LLM skipped
    result = run_review(plugin_root, "--skip-llm")
    # With --skip-llm and no errors: exit 2 (warn from llm-skipped)
    assert result.returncode == 2
    data = json.loads(result.stdout)
    errs = [i for i in data["issues"] if i["severity"] == "error"]
    assert len(errs) == 0, errs


def test_1_3_skip_llm_flag_adds_warning_finding_with_rule_id_llm_skipped(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    make_valid_agent(plugin_root, "my-agent")
    result = run_review(plugin_root, "--skip-llm")
    data = json.loads(result.stdout)
    llm_skip = [i for i in data["issues"] if i.get("rule_id") == "llm-skipped"]
    assert len(llm_skip) == 1, data["issues"]
    assert llm_skip[0]["severity"] == "warning", llm_skip[0]


def test_1_3_structurally_valid_output_is_valid_json_with_required_fields(
    plugin_root: Path,
) -> None:
    make_valid_claude_md(plugin_root)
    make_valid_agent(plugin_root, "my-agent")
    result = run_review(plugin_root, "--skip-llm")
    data = json.loads(result.stdout)
    assert "status" in data
    assert "issues" in data
    assert "summary" in data
    assert isinstance(data["issues"], list)
    for issue in data["issues"]:
        for field in (
            "severity",
            "confidence",
            "file",
            "line",
            "message",
            "suggestedFix",
        ):
            assert field in issue, issue


def test_1_3_llm_unavailable_causes_exit_2_not_exit_1(
    plugin_root: Path, tmp_path: Path
) -> None:
    make_valid_claude_md(plugin_root)
    make_valid_agent(plugin_root, "my-agent")
    # Create a fake claude that always exits non-zero to simulate unavailability
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_claude = fake_bin / "claude"
    fake_claude.write_text("#!/bin/sh\nexit 127\n")
    fake_claude.chmod(0o755)

    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--plugin-root", str(plugin_root)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    # Must NOT be exit 1 (that would mean structural errors caused by LLM
    # failure). Should be exit 2 (LLM unavailable = warning, not error).
    assert result.returncode == 2
