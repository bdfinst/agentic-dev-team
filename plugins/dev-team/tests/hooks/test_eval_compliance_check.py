"""Unit tests for hooks/eval_compliance_check.py EVAL REQUIRED advisory (#860).

Verifies the eval-gate escalation described in
plugins/dev-team/skills/feedback-learning/SKILL.md § Evaluate: editing a
review agent listed in any evals/expected/*.json `applicableAgents` emits an
`EVAL REQUIRED` advisory naming `/agent-eval --agent <name>`; editing an
unfixtured agent, or running where evals/expected/ does not exist (the
cache-only plugin-install case), emits no such line. The hook always stays
advisory and exits 0 (docs/python-hook-contract.md).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "eval_compliance_check.py"

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks"))
import eval_compliance_check as ecc  # noqa: E402

_AGENT_BODY = """---
name: security-review
role: worker
model tier: mid
context needs: diff-only
---

# Security Review

## Detect
Checks for XSS.

## Skip
Skip generated files.

Output JSON with status/issues/summary.
Severity: error, warning, suggestion.
"""


def _run(payload: dict, env_extra: dict) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(env_extra)
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    agents_dir = tmp_path / "plugins" / "dev-team" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "security-review.md").write_text(_AGENT_BODY, encoding="utf-8")
    (agents_dir / "naming-review.md").write_text(_AGENT_BODY, encoding="utf-8")
    return tmp_path


def _fixture_evals(project_root: Path) -> None:
    expected_dir = project_root / "evals" / "expected"
    expected_dir.mkdir(parents=True)
    (expected_dir / "sec-xss.json").write_text(
        json.dumps({"applicableAgents": ["security-review"]}), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _fixtured_agents
# ---------------------------------------------------------------------------


def test_fixtured_agents_empty_when_no_evals_dir(tmp_path: Path):
    assert ecc._fixtured_agents(tmp_path) == set()


def test_fixtured_agents_collects_applicable_agents(tmp_path: Path):
    _fixture_evals(tmp_path)
    assert ecc._fixtured_agents(tmp_path) == {"security-review"}


def test_fixtured_agents_skips_malformed_json(tmp_path: Path):
    expected_dir = tmp_path / "evals" / "expected"
    expected_dir.mkdir(parents=True)
    (expected_dir / "broken.json").write_text("not json", encoding="utf-8")
    assert ecc._fixtured_agents(tmp_path) == set()


# ---------------------------------------------------------------------------
# main() end-to-end via subprocess
# ---------------------------------------------------------------------------


def test_eval_required_fires_for_fixtured_agent(project: Path):
    _fixture_evals(project)
    file_path = str(project / "plugins" / "dev-team" / "agents" / "security-review.md")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path},
        "cwd": str(project),
    }
    result = _run(payload, {"CLAUDE_PROJECT_DIR": str(project)})
    assert result.returncode == 0
    assert "EVAL REQUIRED" in result.stdout
    assert "/agent-eval --agent security-review" in result.stdout


def test_eval_required_absent_for_unfixtured_agent(project: Path):
    _fixture_evals(project)
    file_path = str(project / "plugins" / "dev-team" / "agents" / "naming-review.md")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path},
        "cwd": str(project),
    }
    result = _run(payload, {"CLAUDE_PROJECT_DIR": str(project)})
    assert result.returncode == 0
    assert "EVAL REQUIRED" not in result.stdout


def test_eval_required_absent_when_evals_dir_missing(project: Path):
    # No evals/expected/ at all — the cache-only plugin-install case.
    file_path = str(project / "plugins" / "dev-team" / "agents" / "security-review.md")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path},
        "cwd": str(project),
    }
    result = _run(payload, {"CLAUDE_PROJECT_DIR": str(project)})
    assert result.returncode == 0
    assert "EVAL REQUIRED" not in result.stdout


def test_hook_exits_zero_even_with_eval_required(project: Path):
    _fixture_evals(project)
    file_path = str(project / "plugins" / "dev-team" / "agents" / "security-review.md")
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path},
        "cwd": str(project),
    }
    result = _run(payload, {"CLAUDE_PROJECT_DIR": str(project)})
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# _agent_checks — Context needs: artifact-stream (issue #1038)
# ---------------------------------------------------------------------------

_AGENT_TEMPLATE = """\
---
name: test-agent
role: worker
model tier: mid
context needs: {ctx}
---

# Test Agent

## Detect
Checks something.

## Skip
Skip generated files.

Output JSON with status/issues/summary.
Severity: error, warning, suggestion.
"""


def _ctx_warnings(ctx_value: str) -> str:
    """Return the _agent_checks output for an agent with the given context needs value."""
    content = _AGENT_TEMPLATE.format(ctx=ctx_value)
    return ecc._agent_checks(content, "test-agent", "agents/test-agent.md")


def test_context_needs_artifact_stream_alone_passes():
    out = _ctx_warnings("artifact-stream")
    assert "Context needs" not in out or "invalid" not in out


def test_context_needs_combined_artifact_stream_full_file_passes():
    out = _ctx_warnings("artifact-stream, full-file")
    assert "Context needs" not in out or "invalid" not in out


def test_context_needs_unknown_token_warns():
    out = _ctx_warnings("unknown-value")
    assert "Context needs" in out
    assert "invalid" in out
    assert "unknown-value" in out


def test_context_needs_combined_with_invalid_token_warns_on_bad_token():
    out = _ctx_warnings("artifact-stream, bogus-value")
    assert "bogus-value" in out


def test_context_needs_existing_values_still_pass():
    for value in ("diff-only", "full-file", "project-structure"):
        out = _ctx_warnings(value)
        assert "Context needs" not in out or "invalid" not in out, (
            f"Value {value!r} should pass but got: {out}"
        )
