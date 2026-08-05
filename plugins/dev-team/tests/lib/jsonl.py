"""Shared JSONL-reading helper for plugins/dev-team/tests/ (#1889).

`read_jsonl` was duplicated verbatim across test_boundary_events.py,
test_workflow_state.py, test_iteration_journal_gate.py, and
test_autoship_log.py — each parsing a metrics stream's lines into dicts the
same way. Extracted here so a future change to that shape (e.g. tolerating
blank lines differently) lands once.
"""

from __future__ import annotations

import json
from pathlib import Path


def read_jsonl(path: Path) -> list:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]
