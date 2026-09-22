#!/usr/bin/env python3
"""Abort remaining checkpoint lens dispatch on a cheap-tier blocker (#2168).

``/build``'s inline review checkpoints dispatch review lenses cheap-first
(``select_lenses.py``'s ordering). When a cheap-tier lens already reports an
``error``-severity, ``high``-confidence finding, dispatching the remaining
(opus-tier) lenses for that round is very likely wasted spend — the fix loop
will re-dispatch everything anyway once the cheap-tier finding is addressed.
This module makes that abort decision, plus the small amount of pure
aggregation bookkeeping the checkpoint needs around it.

Three entry points:

1. ``decide_abort`` (and its CLI wrapper in ``main``) — the abort decision
   itself, given the cheap-tier lenses' finding JSON and the checkpoint's
   full ordered lens list.
2. ``compute_round_outcome`` — a pure function the checkpoint's
   outcome-reporting calls at the end of a round; it is the single place
   that guarantees an aborted round whose deferred lenses never re-dispatched
   cannot report a clean pass.
3. ``merge_findings`` — the one piece of production aggregation logic this
   script ships: dedup-and-append, used both by ``/build``'s SKILL.md prose
   (Step 1.2) when folding re-dispatched deferred-lens findings back into a
   round's finding set, and by this module's own fixture equivalence test,
   so that test exercises real shipped code rather than a test-local
   reimplementation of merging.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The bar this script's abort decision applies. Deliberately STRICTER than
# `skills/code-review/SKILL.md` step 6a's "Severity floor (rounds >= 2)" rule
# (`error`/`warning` findings at `high`/`medium` confidence continue that
# fix loop) — this script only fires on `error` severity AND `high`
# confidence, nothing looser. The two bars exist for different decisions:
# step 6a's floor decides whether an *already-dispatched* fix loop should
# keep iterating (continuing is cheap — the agents already ran), while this
# script decides whether to SKIP dispatching opus-tier lenses at all
# (skipping is only safe to do speculatively when the signal is as strong as
# it gets). They are intentionally different values for different purposes,
# not one constant with two names — do not extract a shared constant.
QUALIFYING_SEVERITY = "error"
QUALIFYING_CONFIDENCE = "high"


class CheckpointAbortError(ValueError):
    """Malformed cheap-tier finding input — never silently resolved into
    either an abort or a no-abort decision (see `decide_abort`)."""


def _validate_cheap_results(cheap_results) -> None:
    """Raise `CheckpointAbortError` on anything `decide_abort` cannot safely
    reason about: a non-list top level, a non-list `issues` field, or an
    issue missing `severity`/`confidence`. Fails loud, never loose."""
    if not isinstance(cheap_results, list):
        raise CheckpointAbortError(
            "cheap-tier results must be a JSON list of "
            f"{{agent, issues}} objects, got {type(cheap_results).__name__}"
        )
    for result in cheap_results:
        if not isinstance(result, dict):
            raise CheckpointAbortError(
                f"cheap-tier result entry must be an object, got "
                f"{type(result).__name__}: {result!r}"
            )
        agent = result.get("agent")
        issues = result.get("issues")
        if not isinstance(issues, list):
            raise CheckpointAbortError(
                f"cheap-tier result for agent {agent!r} has a non-list "
                f"'issues' field: {issues!r}"
            )
        for issue in issues:
            if not isinstance(issue, dict):
                raise CheckpointAbortError(
                    f"cheap-tier issue for agent {agent!r} must be an "
                    f"object, got {type(issue).__name__}: {issue!r}"
                )
            if "severity" not in issue or "confidence" not in issue:
                raise CheckpointAbortError(
                    f"cheap-tier issue for agent {agent!r} is missing a "
                    f"required 'severity' or 'confidence' field: {issue!r}"
                )


def decide_abort(cheap_results: list, ordered_lenses: list) -> dict:
    """Pure abort decision.

    ``cheap_results`` — the cheap-tier lenses' finding JSON, a list of
    ``{"agent": str, "issues": [{"severity": ..., "confidence": ...}, ...]}``
    in lens-dispatch order. ``ordered_lenses`` — the checkpoint's full
    ordered lens list (``select_lenses.py``'s cheap-first output).

    Returns ``{"abort": bool, "triggeringFinding": dict|None,
    "triggeringAgent": str|None, "deferredLenses": list[str]}``.

    Abort fires only on the first issue, in ``cheap_results`` order (each
    result's own ``issues`` list is also scanned in order), whose
    ``severity == "error"`` and ``confidence == "high"`` — the first
    qualifying finding wins when several qualify, never the last. An empty
    ``cheap_results`` never aborts (fail-open: nothing ran, nothing to gate
    on). ``deferredLenses`` is only ever non-empty when ``abort`` is true —
    it names every lens in ``ordered_lenses`` that had not already reported
    into ``cheap_results`` (order preserved).

    Raises `CheckpointAbortError` on malformed input — never silently
    resolves to either decision.
    """
    _validate_cheap_results(cheap_results)

    triggering_finding = None
    triggering_agent = None
    for result in cheap_results:
        for issue in result["issues"]:
            if (
                issue.get("severity") == QUALIFYING_SEVERITY
                and issue.get("confidence") == QUALIFYING_CONFIDENCE
            ):
                triggering_finding = issue
                triggering_agent = result.get("agent")
                break
        if triggering_finding is not None:
            break

    if triggering_finding is None:
        return {
            "abort": False,
            "triggeringFinding": None,
            "triggeringAgent": None,
            "deferredLenses": [],
        }

    already_ran = {result.get("agent") for result in cheap_results}
    deferred_lenses = [lens for lens in ordered_lenses if lens not in already_ran]
    return {
        "abort": True,
        "triggeringFinding": triggering_finding,
        "triggeringAgent": triggering_agent,
        "deferredLenses": deferred_lenses,
    }


def compute_round_outcome(aborted: bool, redispatched: bool, findings: list) -> dict:
    """Pure function the checkpoint's outcome-reporting calls at round end.

    Returns ``{"outcome": "pass"|"blocked", "reason": str|None}``.

    When ``aborted`` is true and ``redispatched`` is false, always returns
    ``"blocked"`` regardless of ``findings`` (including an empty list) — the
    round cannot report a clean pass while the lenses it deferred at abort
    time never actually ran. Otherwise, ``outcome`` is computed from
    ``findings`` alone: any findings present -> ``"blocked"``; none ->
    ``"pass"``.
    """
    if aborted and not redispatched:
        return {
            "outcome": "blocked",
            "reason": (
                "round aborted on a cheap-tier blocker and its deferred "
                "lenses were never re-dispatched"
            ),
        }
    if findings:
        return {"outcome": "blocked", "reason": f"{len(findings)} finding(s) remain"}
    return {"outcome": "pass", "reason": None}


def _finding_key(finding: dict) -> tuple:
    """The dedup key `merge_findings` groups on: `(agent, file, line,
    severity, message)`."""
    return (
        finding.get("agent"),
        finding.get("file"),
        finding.get("line"),
        finding.get("severity"),
        finding.get("message"),
    )


def merge_findings(existing: list, new: list) -> list:
    """Dedupe `new` against `existing` by `(agent, file, line, severity,
    message)` and append the remainder in `new`'s original order.

    Pure, no I/O — returns a new list; never mutates either argument.
    """
    seen = {_finding_key(finding) for finding in existing}
    merged = list(existing)
    for finding in new:
        key = _finding_key(finding)
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)
    return merged


def _read_cheap_results(path_or_dash: str) -> str:
    if path_or_dash == "-":
        return sys.stdin.read()
    return Path(path_or_dash).read_text(encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Decide whether to abort remaining opus-tier lens dispatch for "
            "a /build checkpoint round, given the cheap-tier lenses' "
            "results."
        )
    )
    parser.add_argument(
        "--cheap-results-from",
        default="-",
        help=(
            "Path to a JSON file holding the cheap-tier lens results (a "
            "list of {agent, issues: [{severity, confidence}, ...]} "
            "objects) in lens-dispatch order, or '-' for stdin (default)."
        ),
    )
    parser.add_argument(
        "--lenses",
        nargs="*",
        default=[],
        help=(
            "The checkpoint's full ordered lens list (select_lenses.py's "
            "cheap-first output)."
        ),
    )
    args = parser.parse_args(argv)

    try:
        raw = _read_cheap_results(args.cheap_results_from)
    except OSError as exc:
        print(
            f"checkpoint_abort.py: cannot read {args.cheap_results_from}: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        cheap_results = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"checkpoint_abort.py: cheap-tier results are not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        result = decide_abort(cheap_results, args.lenses)
    except CheckpointAbortError as exc:
        print(
            f"checkpoint_abort.py: malformed cheap-tier finding data: {exc}",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
