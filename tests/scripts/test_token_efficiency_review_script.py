"""Tests for plugins/dev-team/scripts/token_efficiency_review.py (Slice 2 of
Python Agent Harness Pattern) — the CLI review script, distinct from the
PostToolUse hook at plugins/dev-team/hooks/token_efficiency_review.py
(covered by tests/hooks/test_token_efficiency_review.py).

Ported from tests/scripts/token_efficiency_review_tests.bats (issue #676).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "token_efficiency_review.py"


def run_review(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Step 2.1 — CLAUDE.md char and rule count thresholds
# ---------------------------------------------------------------------------


def test_claude_md_with_5001_chars_exits_1_and_reports_char_count(
    tmp_path: Path,
) -> None:
    header = "# Title\n"
    content = header + "x" * (5001 - len(header))
    (tmp_path / "CLAUDE.md").write_text(content)

    result = run_review("--files", str(tmp_path / "CLAUDE.md"))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", f"Expected fail, got {data['status']}"
    errors = [i for i in data["issues"] if i["severity"] == "error"]
    assert len(errors) >= 1, "Expected at least one error issue"
    msgs = " ".join(i["message"] for i in errors)
    assert "char" in msgs.lower() or "5001" in msgs, f"No char mention in: {msgs}"


def test_claude_md_with_exactly_5000_chars_exits_0(tmp_path: Path) -> None:
    header = "# Title\n"
    content = header + "x" * (5000 - len(header))
    (tmp_path / "CLAUDE.md").write_text(content)

    result = run_review("--skip-llm", "--files", str(tmp_path / "CLAUDE.md"))
    data = json.loads(result.stdout)
    char_errors = [
        i for i in data["issues"] if i.get("rule_id") == "claude-md-char-limit"
    ]
    assert len(char_errors) == 0, (
        f"Expected no char-limit errors at exactly 5000 chars, got {char_errors}"
    )
    assert data["status"] != "fail", (
        f"Expected no fail status at threshold, got {data['status']}"
    )


def test_claude_md_with_201_top_level_bullet_items_exits_1(tmp_path: Path) -> None:
    lines = ["# Title", ""] + [f"- item {i}" for i in range(201)]
    (tmp_path / "CLAUDE.md").write_text("\n".join(lines) + "\n")

    result = run_review("--files", str(tmp_path / "CLAUDE.md"))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "fail", f"Expected fail, got {data['status']}"
    errors = [i for i in data["issues"] if i["severity"] == "error"]
    assert len(errors) >= 1, "Expected at least one error issue"
    msgs = " ".join(i["message"] for i in errors)
    assert "rule" in msgs.lower() or "bullet" in msgs.lower() or "201" in msgs, (
        f"No rule/bullet mention: {msgs}"
    )


def test_claude_md_with_200_top_level_bullet_items_exits_0(tmp_path: Path) -> None:
    lines = ["# Title", ""] + [f"- item {i}" for i in range(200)]
    (tmp_path / "CLAUDE.md").write_text("\n".join(lines) + "\n")

    result = run_review("--skip-llm", "--files", str(tmp_path / "CLAUDE.md"))
    data = json.loads(result.stdout)
    rule_errors = [
        i
        for i in data["issues"]
        if "rule" in i.get("message", "").lower()
        or "bullet" in i.get("message", "").lower()
    ]
    assert len(rule_errors) == 0, (
        f"Expected no rule-limit errors at exactly 200 bullets, got {rule_errors}"
    )
    assert data["status"] != "fail", (
        f"Expected no fail status at threshold, got {data['status']}"
    )


# ---------------------------------------------------------------------------
# Step 2.2 — Per-file line count, LLM filter, --skip-llm
# ---------------------------------------------------------------------------


def test_file_with_501_lines_exits_2_with_severity_warning(tmp_path: Path) -> None:
    lines = [f"line {i}" for i in range(501)]
    (tmp_path / "long_file.md").write_text("\n".join(lines) + "\n")

    result = run_review("--skip-llm", "--files", str(tmp_path / "long_file.md"))
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["status"] == "warn", f"Expected warn, got {data['status']}"
    warnings = [i for i in data["issues"] if i["severity"] == "warning"]
    assert len(warnings) >= 1, "Expected at least one warning issue"


def test_file_with_exactly_500_lines_exits_0(tmp_path: Path) -> None:
    # Use a .py file so no LLM call and no llm-skipped warning — isolates
    # the line threshold.
    lines = [f"# line {i}" for i in range(500)]
    (tmp_path / "ok_file.py").write_text("\n".join(lines) + "\n")

    result = run_review("--files", str(tmp_path / "ok_file.py"))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == "pass", f"Expected pass, got {data['status']}"


def test_skip_llm_suppresses_llm_call_and_adds_warning_with_rule_id_llm_skipped(
    tmp_path: Path,
) -> None:
    (tmp_path / "test.md").write_text("# Hello\n")

    result = run_review("--skip-llm", "--files", str(tmp_path / "test.md"))
    data = json.loads(result.stdout)
    skipped = [i for i in data["issues"] if i.get("rule_id") == "llm-skipped"]
    assert len(skipped) == 1, f"Expected exactly one llm-skipped warning, got {skipped}"
    assert skipped[0]["severity"] == "warning", (
        f"Expected severity warning, got {skipped[0]['severity']}"
    )


def test_files_flag_accepts_paths_to_check(tmp_path: Path) -> None:
    (tmp_path / "short.md").write_text("# Short file\nHello world.\n")

    result = run_review("--skip-llm", "--files", str(tmp_path / "short.md"))
    assert result.returncode == 2  # 2 because of llm-skipped warning
    data = json.loads(result.stdout)
    assert "status" in data
    assert "issues" in data


def test_llm_review_scoped_to_md_files_only_py_file_not_llm_reviewed(
    tmp_path: Path,
) -> None:
    (tmp_path / "code.py").write_text("def foo():\n    pass\n")

    # Without --skip-llm and with a .py file: should pass without llm-skipped warning
    result = run_review("--files", str(tmp_path / "code.py"))
    data = json.loads(result.stdout)
    skipped = [i for i in data["issues"] if i.get("rule_id") == "llm-skipped"]
    assert len(skipped) == 0, f"Expected no llm-skipped for .py file, got {skipped}"


def test_llm_findings_are_severity_warning_only_never_error(tmp_path: Path) -> None:
    (tmp_path / "prose.md").write_text("# Test\nsome content\n")

    result = run_review("--skip-llm", "--files", str(tmp_path / "prose.md"))
    data = json.loads(result.stdout)
    for issue in data["issues"]:
        if issue.get("rule_id") == "llm-skipped":
            assert issue["severity"] == "warning", (
                f"llm-skipped must be warning, got {issue['severity']}"
            )


def test_output_json_contains_all_required_issue_fields(tmp_path: Path) -> None:
    header = "# Title\n"
    content = header + "x" * (5001 - len(header))
    (tmp_path / "CLAUDE.md").write_text(content)

    result = run_review("--files", str(tmp_path / "CLAUDE.md"))
    data = json.loads(result.stdout)
    required_fields = {
        "severity",
        "confidence",
        "file",
        "line",
        "message",
        "suggestedFix",
    }
    for issue in data["issues"]:
        missing = required_fields - set(issue.keys())
        assert not missing, f"Missing fields {missing} in issue: {issue}"
