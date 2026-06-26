"""review_result — shared output contract for all Python review scripts.

Provides build_result() and main_exit() so every script emits identical
JSON and consistent exit codes:
  0 = pass (no findings)
  1 = fail (hard errors)
  2 = warn (warnings only or LLM check skipped)
"""

from __future__ import annotations

import json
import sys
from typing import Optional


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
