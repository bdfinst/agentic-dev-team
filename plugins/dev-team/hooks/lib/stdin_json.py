"""stdin_json — single source of truth for the stdin-JSON-read helper.

Every Claude Code hook receives its payload as JSON on stdin. Seven hooks
(pre_commit_review.py, pre_commit_knowledge_index.py, knowledge_index.py,
mutation_testing_smoke_gate.py, code_intelligence_nudge.py, codegraph_bootstrap.py,
bash_retry_guard.py) each carried an identical copy of this read/parse/
validate step (#732). This module is the shared extraction. Also adopted by
context_ceiling_guard.py (#779), replacing its own local copy of the same
read/parse/validate step, and by several more hooks (code_intelligence_turn_mark.py,
contract_version_guard.py, cost_meter.py, destructive_guard.py,
eval_compliance_check.py, js_fp_review.py, task_completion_metrics.py) whose
own copies had drifted back in independently of the #732 migration.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def read_stdin_json() -> dict | None:
    """Read stdin, parse as JSON, return the dict on success.

    Returns None on:
      - an OSError while reading stdin
      - empty/whitespace-only input
      - malformed JSON
      - valid JSON that is not a dict (e.g. a list or scalar)
    """
    try:
        raw = sys.stdin.read()
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def resolve_cwd(payload: dict) -> str:
    """Return the hook payload's ``cwd`` if it names a real directory, else
    the process's own working directory.

    Previously copy-pasted verbatim in mcp_json_repowise_nudge.py,
    repo_review_nudge.py, and pending_review_notify.py, alongside their own
    (also copy-pasted) stdin-read preamble — now just `read_stdin_json()`.
    """
    cwd = payload.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_dir():
        return os.getcwd()
    return cwd
