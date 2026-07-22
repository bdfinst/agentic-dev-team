"""Tests for scripts/validate_agent_contract.py — the official Claude Code
sub-agent frontmatter contract validator (agent-contract.json), issue #1285.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validate_agent_contract.py"


def run_validator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LANG": "C.UTF-8"},
    )


def write_agent(path: Path, frontmatter: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\nBody.\n")
    return path


def test_valid_agent_passes_clean(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\ntools: Read, Grep\neffort: high",
    )
    result = run_validator(str(agent))
    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["status"] == "pass", data


def test_missing_name_is_error(tmp_path: Path) -> None:
    agent = write_agent(tmp_path / "my-agent.md", "description: does stuff")
    result = run_validator(str(agent))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("name" in m for m in msgs), msgs


def test_missing_description_is_error(tmp_path: Path) -> None:
    agent = write_agent(tmp_path / "my-agent.md", "name: my-agent")
    result = run_validator(str(agent))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("description" in m for m in msgs), msgs


def test_bad_name_pattern_is_error(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: My_Agent\ndescription: does stuff",
    )
    result = run_validator(str(agent))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("pattern" in m for m in msgs), msgs


def test_unknown_frontmatter_key_is_warning(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\neffrot: high",
    )
    result = run_validator(str(agent))
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "warn", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("effrot" in m for m in msgs), msgs


def test_invalid_effort_value_is_error(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\neffort: ultra",
    )
    result = run_validator(str(agent))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("effort" in m for m in msgs), msgs


def test_model_alias_is_valid(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\nmodel: opus",
    )
    result = run_validator(str(agent))
    assert result.returncode == 0, result.stdout


def test_model_full_id_is_valid(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\nmodel: claude-opus-4-8",
    )
    result = run_validator(str(agent))
    assert result.returncode == 0, result.stdout


def test_model_unrecognized_value_is_error(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\nmodel: gpt-4",
    )
    result = run_validator(str(agent))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("model" in m for m in msgs), msgs


def test_hooks_on_plugin_agent_is_warning(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "plugins" / "test-plugin" / "agents" / "my-agent.md",
        "name: my-agent\ndescription: does stuff\nhooks: {}",
    )
    result = run_validator(str(agent))
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "warn", data
    msgs = [i["message"] for i in data["issues"]]
    assert any("hooks" in m and "ignored" in m for m in msgs), msgs


def test_hooks_outside_plugin_agents_path_is_not_flagged(tmp_path: Path) -> None:
    agent = write_agent(
        tmp_path / "my-agent.md",
        "name: my-agent\ndescription: does stuff\nhooks: {}",
    )
    result = run_validator(str(agent))
    assert result.returncode == 0, result.stdout


def test_no_findings_against_a_real_shipped_agent() -> None:
    """A real agent already in the repo should not raise a false positive —
    guards against the validator drifting out of sync with actual usage."""
    agent = REPO_ROOT / "plugins" / "dev-team" / "agents" / "architect.md"
    assert agent.exists()
    result = run_validator(str(agent))
    data = json.loads(result.stdout)
    assert result.returncode == 0, data
    assert data["status"] == "pass", data
