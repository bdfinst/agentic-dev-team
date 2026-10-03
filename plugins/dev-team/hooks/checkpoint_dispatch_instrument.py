#!/usr/bin/env python3
"""checkpoint_dispatch_instrument.py — PreToolUse dispatch-time ledger probe.

Registered on the `"Agent|Task"` PreToolUse matcher. For every dispatch of a
registered review lens whose prompt carries the scope marker, it resolves the
dispatch's files against the verdict ledger in-process (the same pipeline
`scripts/verdict_scope.py` runs) and appends one `ledger-skips.jsonl` row
tagged `source: "dispatch-hook"`. The stream is therefore written whether or
not the model ran the consult by hand; the model's own consult still narrows
dispatches, this hook only guarantees the measurement.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin (Agent/Task matcher)
    Output: always exit 0 — fail-open, never blocks or alters a dispatch.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
_SCRIPTS_DIR = _HOOK_DIR.parent / "scripts"
for _dir in (_LIB_DIR, _SCRIPTS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

from instrument_log import append_row  # type: ignore[import-not-found]
from review_agent_registry import (  # type: ignore[import-not-found]
    is_registered_review_lens,
    strip_plugin_prefix,
)
from review_verdicts import parse_scope_marker  # type: ignore[import-not-found]
from stdin_json import read_stdin_json  # type: ignore[import-not-found]
from verdict_scope import resolve_for_root  # type: ignore[import-not-found]


def main() -> int:
    payload = read_stdin_json()
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    subagent_type = tool_input.get("subagent_type")
    prompt = tool_input.get("prompt")
    if not isinstance(subagent_type, str) or not isinstance(prompt, str):
        return 0
    if not is_registered_review_lens(subagent_type):
        return 0
    files = parse_scope_marker(prompt)
    if not files:
        return 0

    cwd = Path(payload.get("cwd") or ".")
    lens = strip_plugin_prefix(subagent_type)
    result = resolve_for_root({lens: files}, cwd)
    append_row(
        "ledger-skips",
        {
            "source": "dispatch-hook",
            "candidate_pairs": len(files),
            "skipped_pairs": sum(len(v) for v in result["skipped"].values()),
            "fully_skipped_lenses": result["fullySkippedLenses"],
        },
        cwd=cwd,
        session_id=payload.get("session_id"),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a dispatch
        sys.exit(0)
