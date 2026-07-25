#!/usr/bin/env python3
"""build_slice_scope.py — freeze-scope wiring for `/build` (issue #865).

Auto-freeze is OPT-IN VIA PLAN METADATA: a top-level `**Scope enforcement:**
freeze` line in the plan enables it. Declared per-slice `**Files:**` alone
only feeds `plan_waves.py`'s scope-mismatch warnings (see `plan_waves.py`) —
it never freezes anything by itself.

When engaged, `/build` calls this script at slice dispatch to write
`hooks/freeze-state.json` (the same contract `/freeze` writes and
`hooks/pre_tool_guard.py` already enforces) with `allowed_patterns` equal to
the slice's declared paths **plus a fixed bookkeeping allowlist** (the plan
file itself, `.claude/memory/**`, `.claude/metrics/**`, and the AC3-exempt
`metrics/verify-log.jsonl`) — without which `/build` could not update its
own Build Progress checkboxes, `.claude/memory/build-phase.json`, or its
own exempt verify-log entry. At slice completion, `/build` calls this
script again to clear the state.

Stdlib-only. Python 3.8+ (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import plan_parse

_SCOPE_ENFORCEMENT_RE = re.compile(
    r"^\*\*Scope enforcement:?\*\*\s*:?\s*(.+)$", re.IGNORECASE | re.MULTILINE
)
_TOKEN_SPLIT_RE = re.compile(r"[,\s]+")

FREEZE_STATE_FILENAME = "freeze-state.json"


def scope_enforcement_enabled(plan_text: str) -> bool:
    """True when the plan's top-level `**Scope enforcement:** freeze` line
    is present (case-insensitive). Any other value (or its absence) means
    declared Files feeds mismatch warnings only — no auto-freeze."""
    match = _SCOPE_ENFORCEMENT_RE.search(plan_text)
    if not match:
        return False
    return match.group(1).strip().lower().startswith("freeze")


def declared_files_for_slice(plan_text: str, slice_id: str) -> list[str]:
    """Return the tokenized slice-level `**Files:**` declaration for
    `slice_id`, or `[]` when the slice declares none."""
    rows = plan_parse.parse_slices(plan_text.splitlines())
    for sid, _deps, files_raw in rows:
        if sid == slice_id:
            return [f for f in _TOKEN_SPLIT_RE.split(files_raw) if f]
    return []


def bookkeeping_allowlist(plan_path: Path) -> list[str]:
    """The fixed allowlist every freeze must include so `/build` never
    self-blocks its own progress writes: the plan file itself, plus
    `.claude/memory/**`, `.claude/metrics/**`, and the AC3-exempt
    `metrics/verify-log.jsonl` (deliberately not relocated under `.claude/`
    — see docs/artifact-migration.md)."""
    return [
        plan_path.name,
        ".claude/memory/**",
        ".claude/metrics/**",
        "metrics/verify-log.jsonl",
    ]


def build_allowed_patterns(plan_path: Path, plan_text: str, slice_id: str) -> list[str]:
    declared = declared_files_for_slice(plan_text, slice_id)
    return declared + bookkeeping_allowlist(plan_path)


def write_freeze_state(hooks_dir: Path, allowed_patterns: list[str]) -> Path:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    state_path = hooks_dir / FREEZE_STATE_FILENAME
    payload = {
        "active": True,
        "allowed_patterns": allowed_patterns,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.write_text(json.dumps(payload, indent=2) + "\n")
    return state_path


def clear_freeze_state(hooks_dir: Path) -> Path:
    """Remove the freeze-state file — mirrors `/unfreeze`'s `rm -f`."""
    state_path = hooks_dir / FREEZE_STATE_FILENAME
    if state_path.exists():
        state_path.unlink()
    return state_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_slice_scope.py",
        description="Engage/clear /build's per-slice freeze scope lock (issue #865).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enabled_p = sub.add_parser(
        "enabled", help="Exit 0 if the plan opts into freeze scope enforcement."
    )
    enabled_p.add_argument("plan", type=Path)

    engage_p = sub.add_parser(
        "engage", help="Write freeze-state.json scoped to a slice's declared Files."
    )
    engage_p.add_argument("plan", type=Path)
    engage_p.add_argument("--slice", required=True)
    engage_p.add_argument("--hooks-dir", type=Path, default=Path("hooks"))

    clear_p = sub.add_parser("clear", help="Clear freeze-state.json.")
    clear_p.add_argument("--hooks-dir", type=Path, default=Path("hooks"))

    args = parser.parse_args(argv)

    if args.command == "enabled":
        plan_text = args.plan.read_text(encoding="utf-8")
        if scope_enforcement_enabled(plan_text):
            print("enabled")
            return 0
        print("disabled")
        return 1

    if args.command == "engage":
        plan_text = args.plan.read_text(encoding="utf-8")
        allowed = build_allowed_patterns(args.plan, plan_text, args.slice)
        state_path = write_freeze_state(args.hooks_dir, allowed)
        print(f"Freeze engaged for slice {args.slice}: {state_path}")
        print(f"Allowed patterns: {', '.join(allowed)}")
        return 0

    if args.command == "clear":
        state_path = clear_freeze_state(args.hooks_dir)
        print(f"Freeze cleared: {state_path}")
        return 0

    return 2  # pragma: no cover — argparse enforces a valid subcommand


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
