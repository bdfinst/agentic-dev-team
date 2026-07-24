"""Integration validation: all 7 agent-audit items fixed after wave 1 merges.

Ported from tests/agents/agent_audit_integration_validation_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import re
import subprocess
import sys

from _repo_root import REPO_ROOT

AGENTS = REPO_ROOT / "plugins" / "dev-team" / "agents"
HOOKS = REPO_ROOT / "plugins" / "dev-team" / "hooks"


def test_session_analysis_has_output_json_header() -> None:
    text = (AGENTS / "session-analysis.md").read_text(encoding="utf-8")
    assert "Output JSON:" in text


def test_session_analysis_json_block_contains_status_field() -> None:
    text = (AGENTS / "session-analysis.md").read_text(encoding="utf-8")
    assert '"status": "pass|warn|fail|skip"' in text


def test_session_analysis_has_severity_definitions() -> None:
    text = (AGENTS / "session-analysis.md").read_text(encoding="utf-8")
    assert "Severity:" in text


def test_session_analysis_has_skip_section() -> None:
    text = (AGENTS / "session-analysis.md").read_text(encoding="utf-8")
    assert "## Skip" in text


def test_session_analysis_has_context_needs_full_file() -> None:
    text = (AGENTS / "session-analysis.md").read_text(encoding="utf-8")
    assert "Context needs: full-file" in text


def test_claude_setup_review_has_context_needs_project_structure() -> None:
    text = (AGENTS / "claude-setup-review.md").read_text(encoding="utf-8")
    assert "Context needs: project-structure" in text


def test_orchestrator_declares_enforcement_script_and_implemented_by() -> None:
    # `Enforcement: script` is a body-level declaration, not frontmatter
    # (issue #1333).
    text = (AGENTS / "orchestrator.md").read_text(encoding="utf-8")
    assert re.search(r"^Enforcement:\s*script", text, re.MULTILINE)
    assert re.search(r"^> \*\*Implemented by:\*\*", text, re.MULTILINE)


def test_mutation_gate_hook_import_clean() -> None:
    hook = HOOKS / "mutation_gate.py"
    code = (
        "import importlib.util, pathlib; "
        f"p = pathlib.Path({str(hook)!r}); "
        "s = importlib.util.spec_from_file_location('mutation_gate', p); "
        "m = importlib.util.module_from_spec(s); "
        "s.loader.exec_module(m); print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout


def test_eval_compliance_check_hook_import_clean() -> None:
    hook = HOOKS / "eval_compliance_check.py"
    code = (
        "import importlib.util, pathlib; "
        f"p = pathlib.Path({str(hook)!r}); "
        "s = importlib.util.spec_from_file_location('eval_compliance_check', p); "
        "m = importlib.util.module_from_spec(s); "
        "s.loader.exec_module(m); print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout


def test_both_hooks_parse_cleanly_under_py_compile() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(HOOKS / "mutation_gate.py"),
            str(HOOKS / "eval_compliance_check.py"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
