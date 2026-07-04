"""Tests for scripts/lib/review_result.py — shared review output helper.

Ported from tests/scripts/review_result_tests.bats (issue #676).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

ERR = [
    {
        "severity": "error",
        "confidence": "high",
        "file": "a.md",
        "line": 1,
        "message": "bad",
        "suggestedFix": "",
    }
]
WARN = [
    {
        "severity": "warning",
        "confidence": "medium",
        "file": "b.md",
        "line": 2,
        "message": "meh",
        "suggestedFix": "",
    }
]
NONE: list = []


def _call_make_issue(**kwargs) -> subprocess.CompletedProcess:
    code = f"""
import sys, json
sys.path.insert(0, {str(SCRIPTS_DIR)!r})
from lib.review_result import make_issue

kwargs = json.loads(sys.argv[1])
print(json.dumps(make_issue(**kwargs)))
"""
    return subprocess.run(
        [sys.executable, "-c", code, json.dumps(kwargs)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_make_issue_returns_canonical_shape_with_default_confidence() -> None:
    result = _call_make_issue(
        severity="error", file="a.py", line=3, message="bad thing"
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data == {
        "severity": "error",
        "confidence": "high",
        "file": "a.py",
        "line": 3,
        "message": "bad thing",
        "suggestedFix": "",
    }


def test_make_issue_accepts_suggested_fix_and_confidence_override() -> None:
    result = _call_make_issue(
        severity="warning",
        confidence="medium",
        file="b.py",
        line=0,
        message="meh",
        suggested_fix="do the thing",
    )
    data = json.loads(result.stdout)
    assert data == {
        "severity": "warning",
        "confidence": "medium",
        "file": "b.py",
        "line": 0,
        "message": "meh",
        "suggestedFix": "do the thing",
    }


def test_make_issue_only_includes_rule_id_when_provided() -> None:
    without = json.loads(_call_make_issue(severity="error", message="x").stdout)
    assert "rule_id" not in without

    with_rule = json.loads(
        _call_make_issue(severity="error", message="x", rule_id="my-rule").stdout
    )
    assert with_rule["rule_id"] == "my-rule"


def test_make_issue_defaults_file_and_line_when_omitted() -> None:
    data = json.loads(_call_make_issue(severity="error", message="x").stdout)
    assert data["file"] == ""
    assert data["line"] == 0


def _call_helper(errors: list, warnings: list) -> subprocess.CompletedProcess:
    code = f"""
import sys, json
sys.path.insert(0, {str(SCRIPTS_DIR)!r})
from lib.review_result import build_result, main_exit

errors   = json.loads(sys.argv[1])
warnings = json.loads(sys.argv[2])
result   = build_result(errors, warnings)
sys.exit(main_exit(result))
"""
    return subprocess.run(
        [sys.executable, "-c", code, json.dumps(errors), json.dumps(warnings)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_result_with_errors_exit_1_and_status_fail() -> None:
    result = _call_helper(ERR, NONE)
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data


def test_build_result_with_warnings_only_exit_2_and_status_warn() -> None:
    result = _call_helper(NONE, WARN)
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "warn", data


def test_build_result_with_no_issues_exit_0_and_status_pass() -> None:
    result = _call_helper(NONE, NONE)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "pass", data


def test_stdout_is_valid_json_containing_issues_array_and_summary_field() -> None:
    result = _call_helper(ERR, NONE)
    data = json.loads(result.stdout)
    assert "status" in data
    assert "issues" in data
    assert isinstance(data["issues"], list)
    assert "summary" in data


def test_errors_take_precedence_over_warnings_exit_1_when_both_present() -> None:
    result = _call_helper(ERR, WARN)
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", data


def test_issues_list_contains_both_errors_and_warnings() -> None:
    result = _call_helper(ERR, WARN)
    data = json.loads(result.stdout)
    assert len(data["issues"]) == 2, data["issues"]
    severities = {i["severity"] for i in data["issues"]}
    assert "error" in severities
    assert "warning" in severities
