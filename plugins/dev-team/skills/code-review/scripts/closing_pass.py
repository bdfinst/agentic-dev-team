#!/usr/bin/env python3
"""Closing-pass composition for `/code-review`'s fix loop (#1626).

`/code-review` step 6a used to mandate: after ANY fix-loop iteration ran,
re-dispatch the **full** original agent panel once more against the final
staged content. The reason was structural, not editorial — the pre-commit
gate (#1461) needs `>= 2` distinct dispatches whose `subject_hash` equals the
FINAL staged hash, and the loop's targeted re-dispatches only cover the
agents that happened to have findings. So a one-line fix re-triggered an
18-agent panel. That is the single biggest cost multiplier in the loop, and
#1619 paid it repeatedly.

This module computes the **closing pass** instead: the minimal dispatch set
that preserves both properties the full re-panel was defending.

## The two properties, and how each is preserved

1. **The gate's corroboration floor, satisfied by construction.**
   `pre_commit_review.py`'s `_MIN_DISTINCT_DISPATCHES` is 2. The composition
   rule below tops up from the resolver's eligible roster until at least 2
   distinct registered agents dispatch at the final hash. No hook change, no
   exemption event, no ledger change — the floor is met the same way it is
   met today, just with 2-3 dispatches instead of 18.

2. **Not a rubber stamp.** Closing-pass agents keep full review authority:
   any actionable finding re-enters the fix loop exactly as before (subject
   to #1625's round cap). What changes is *how many* agents re-read *how
   much* content — never whether their findings count. A pass whose findings
   carried no consequence would be exactly the "dispatch trivial calls purely
   to clear the gate" abuse `pre_commit_review.py`'s own docstring names.

## Scope: the fix delta, not the whole changeset

The round-1 panel already reviewed the full changeset. Only the *fix delta*
— what changed between what the panel reviewed and the final staged content
— is unreviewed. The closing pass reviews that delta.

**Escape hatch.** If the fix delta touches files the original panel never
targeted, scope grew mid-loop and the delta-only argument no longer holds:
fall back to the full re-dispatch over the whole changeset. That condition is
a deterministic set-comparison of two file lists, checked here rather than
judged in prose.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: Mirrors `hooks/pre_commit_review.py`'s `_MIN_DISTINCT_DISPATCHES`. Kept as
#: a named constant here (rather than imported) because this script must not
#: depend on the hook package to compute a dispatch plan; the drift test in
#: `plugins/dev-team/tests/scripts/test_closing_pass.py` asserts the two stay
#: equal, so a future change to the gate's floor fails a test rather than
#: silently under-composing the closing pass.
MIN_DISTINCT_DISPATCHES = 2


def _normalize(path) -> str:
    text = str(path or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def scope_grew(panel_files, fix_delta_files) -> bool:
    """True when the fix delta touches a file the original panel never
    targeted — the escape-hatch condition. A pure set comparison."""
    panel = {_normalize(p) for p in panel_files if str(p or "").strip()}
    delta = {_normalize(p) for p in fix_delta_files if str(p or "").strip()}
    return not delta.issubset(panel)


def compose(
    fixed_by_agents,
    eligible_roster,
    panel_agents,
    panel_files=(),
    fix_delta_files=(),
    minimum: int = MIN_DISTINCT_DISPATCHES,
) -> dict:
    """Compute the closing-pass dispatch plan.

    Args:
        fixed_by_agents: agents whose findings were fixed during the loop.
            Each verifies its own fixes at the final hash.
        eligible_roster: the resolver's eligible lenses in `select_lenses.py`
            order — cheap-first (non-opus before opus). Top-ups are taken
            from the front, so a top-up never reaches for an opus lens while
            a cheaper eligible one is available.
        panel_agents: the full round-1 panel, used only by the escape hatch.
        panel_files / fix_delta_files: drive `scope_grew`.
        minimum: the gate's distinct-dispatch floor.

    Returns `{"agents", "scope", "escape_hatch", "reason", "topped_up"}`.
    `scope` is `fix-delta` normally, `full-changeset` under the escape hatch.
    """
    fixed = _dedupe(fixed_by_agents)
    roster = _dedupe(eligible_roster)
    panel = _dedupe(panel_agents)

    if scope_grew(panel_files, fix_delta_files):
        return {
            "agents": panel or roster,
            "scope": "full-changeset",
            "escape_hatch": True,
            "reason": "fix-delta-touched-files-outside-the-panel-target-set",
            "topped_up": [],
        }

    agents = list(fixed)
    topped_up = []
    for candidate in roster:
        if len(agents) >= minimum:
            break
        if candidate not in agents:
            agents.append(candidate)
            topped_up.append(candidate)

    reason = None
    if len(agents) < minimum:
        # The eligible roster itself cannot supply the floor (a tiny or
        # heavily-filtered roster). Say so explicitly rather than emitting a
        # plan that will fail the gate for reasons the operator can't see.
        reason = "eligible-roster-smaller-than-gate-floor"

    return {
        "agents": agents,
        "scope": "fix-delta",
        "escape_hatch": False,
        "reason": reason,
        "topped_up": topped_up,
    }


def _dedupe(values) -> list:
    seen, out = set(), []
    for value in values or ():
        name = str(value or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _load_list(value: str | None) -> list:
    """Accept either a comma-separated inline list or `@path` to a JSON file
    holding a list (or `{"lenses": [...]}`, matching `select_lenses.py`)."""
    if not value:
        return []
    if value.startswith("@"):
        data = json.loads(Path(value[1:]).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("lenses", data.get("agents", []))
        return list(data) if isinstance(data, list) else []
    return [v.strip() for v in value.split(",") if v.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compose the /code-review closing pass.")
    parser.add_argument("--fixed-by", default="", help="Agents whose findings were fixed")
    parser.add_argument("--roster", default="", help="Eligible roster, cheap-first (or @file.json)")
    parser.add_argument("--panel", default="", help="The full round-1 panel (or @file.json)")
    parser.add_argument("--panel-files", default="", help="Files the round-1 panel targeted")
    parser.add_argument("--fix-delta-files", default="", help="Files the cumulative fix touched")
    args = parser.parse_args(argv)

    plan = compose(
        _load_list(args.fixed_by),
        _load_list(args.roster),
        _load_list(args.panel),
        _load_list(args.panel_files),
        _load_list(args.fix_delta_files),
    )
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
