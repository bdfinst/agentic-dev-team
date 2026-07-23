"""review_result — shared output contract for all Python review scripts.

Provides build_result() and main_exit() so every script emits identical
JSON and consistent exit codes:
  0 = pass (no findings)
  1 = fail (hard errors)
  2 = warn (warnings only or LLM check skipped)
"""

from __future__ import annotations

import json


def build_result(
    errors: list,
    warnings: list,
    summary: str = "",
) -> dict:
    """Return canonical review output dict."""
    if errors:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"
    return {
        "status": status,
        "issues": errors + warnings,
        "summary": summary,
    }


def main_exit(result: dict) -> int:
    """Serialize result to stdout and return the appropriate exit code."""
    print(json.dumps(result))
    status = result.get("status", "pass")
    if status == "fail":
        return 1
    if status == "warn":
        return 2
    return 0


def make_issue(
    severity: str,
    confidence: str = "high",
    file: str = "",
    line: int = 0,
    message: str = "",
    suggested_fix: str = "",
    rule_id: str = "",
) -> dict:
    """Return a canonical issue dict — the shared shape every review script
    (progress_guardian, claude_setup_review, test_modernization_review,
    token_efficiency_review) independently duplicated before #732.

    `rule_id` is included only when truthy, matching the pre-dedup
    token_efficiency_review._issue behavior.
    """
    issue: dict = {
        "severity": severity,
        "confidence": confidence,
        "file": file,
        "line": line,
        "message": message,
        "suggestedFix": suggested_fix,
    }
    if rule_id:
        issue["rule_id"] = rule_id
    return issue


def skipped_llm_warning(message: str = "LLM check skipped (--skip-llm)") -> dict:
    """Return a single warning finding for use when --skip-llm suppresses the LLM call."""
    return {
        "severity": "warning",
        "confidence": "high",
        "file": "",
        "line": 0,
        "message": message,
        "suggestedFix": "",
        "rule_id": "llm-skipped",
    }
