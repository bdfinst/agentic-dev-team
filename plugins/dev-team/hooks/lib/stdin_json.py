"""stdin_json — single source of truth for the stdin-JSON-read helper.

Every Claude Code hook receives its payload as JSON on stdin. Seven hooks
(pre_commit_review.py, pre_commit_knowledge_index.py, knowledge_index.py,
mutation_testing_smoke_gate.py, code_intelligence_nudge.py, codegraph_bootstrap.py,
bash_retry_guard.py) each carried an identical copy of this read/parse/
validate step (#732). This module is the shared extraction. Also adopted by
context_ceiling_guard.py (#779), replacing its own local copy of the same
read/parse/validate step.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import sys


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
