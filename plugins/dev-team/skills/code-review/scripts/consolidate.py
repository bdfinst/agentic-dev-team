#!/usr/bin/env python3
"""Consolidate per-slice section artifacts into one deduplicated report.

Split into a **pure** ``consolidate(sections)`` (takes a list of section dicts,
returns the aggregated object) and a thin ``main()`` that reads
``DEV_TEAM_REPORTS/code-review/raw/section-*.json`` and calls it — the same
main-wraps-pure convention as ``check_version_drift.py``/``lesson_validate.py``,
so the aggregation logic is unit-tested with plain dicts and no filesystem.

Consolidation:
- Dedupe findings by ``file:line`` — one entry, reporting agents merged into an
  ``agents[]`` array, severity = the single highest enum (per SKILL.md step 5c).
- Recurring-theme rollup — a review dimension (agent) whose findings recur across
  two or more slices, so a systemic pattern surfaces above per-slice noise.
- Disclose which slices ran the reduced (declarative) panel.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import List, Optional

# Severity ranking (extracted — step 5c's ranking lived only in prose before).
_SEVERITY_RANK = {"suggestion": 1, "warning": 2, "error": 3}

# Maps a severity to its totals bucket, derived from the same vocabulary as
# _SEVERITY_RANK so the severity set has a single source of truth.
_SEVERITY_BUCKET = {"error": "errors", "warning": "warnings", "suggestion": "suggestions"}

# A review dimension recurring across at least this many slices is a theme.
_THEME_MIN_SLICES = 2

# Real-world review-agent output drifts from the documented schema (#1261): some
# agents return their findings list under `issues` (the per-agent key in
# output-format.md) instead of `findings` (the section-artifact key). Accept
# either so a mis-keyed list is aggregated, never silently counted as zero. The
# canonical key is tried first; the alias is a fallback.
_FINDINGS_KEYS = ("findings", "issues")


def _rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 0)


def _findings_of(container: dict) -> list:
    """Return the findings list from ``container`` tolerating key drift (#1261).

    Prefers ``findings`` (section-artifact key), falls back to ``issues``
    (per-agent key). A value that is present but not a list is treated as no
    findings rather than crashing the aggregation.
    """
    for key in _FINDINGS_KEYS:
        value = container.get(key)
        if isinstance(value, list):
            return value
    return []


def normalize_agent_result(raw: dict, agent_name: Optional[str] = None) -> list:
    """Coerce one review agent's result into a flat, ``agent``-tagged findings list.

    Absorbs the schema drift observed in real runs (#1261): the native per-agent
    ``{status, issues, summary}`` shape, findings keyed as ``issues`` **or**
    ``findings``, and any extra top-level keys (e.g. ``summary``) — all of which
    are ignored except the findings list. Each returned finding is tagged with
    its reporting ``agent`` (from ``raw["agentName"]``, else ``agent_name``) so
    ``consolidate()`` can merge reporters per ``file:line`` and roll up themes.

    Non-dict input, or a findings entry that is not a dict, yields an empty list
    / is skipped — this never raises, so a malformed agent result degrades to
    "reported nothing" rather than aborting the whole aggregation.
    """
    if not isinstance(raw, dict):
        return []
    agent = raw.get("agentName") or agent_name
    out = []
    for finding in _findings_of(raw):
        if not isinstance(finding, dict):
            continue
        tagged = dict(finding)
        tagged.setdefault("agent", agent)
        out.append(tagged)
    return out


def _dedupe_key(finding: dict):
    return (finding.get("file"), finding.get("line"))


def _sorted_ids(ids) -> list:
    """Return the non-None ids, sorted — the shared 'sorted, None-filtered' idiom."""
    return sorted(s for s in ids if s is not None)


def _merge_finding(merged: dict, order: list, finding: dict) -> None:
    """Insert ``finding`` into the ``file:line`` dedup map, or merge it into the
    existing entry: highest severity wins and keeps its message; reporting agents
    accumulate into ``agents[]`` without duplicates.
    """
    key = _dedupe_key(finding)
    agent = finding.get("agent")
    severity = finding.get("severity", "suggestion")
    entry = merged.get(key)
    if entry is None:
        order.append(key)
        merged[key] = {
            "severity": severity,
            "agents": [agent] if agent else [],
            "file": finding.get("file"),
            "line": finding.get("line"),
            "message": finding.get("message"),
        }
        return
    if _rank(severity) > _rank(entry["severity"]):
        entry["severity"] = severity
        entry["message"] = finding.get("message")
    if agent and agent not in entry["agents"]:
        entry["agents"].append(agent)


def consolidate(sections: List[dict]) -> dict:
    """Aggregate ``sections`` into the consolidated report object.

    ``sections`` is a list of per-slice artifacts (``id``/``files``/
    ``is_declarative``/``panel``/``findings``). Findings carry the usual
    ``severity``/``file``/``line``/``message`` and an optional ``agent`` naming
    the reporting review dimension. Returns the aggregated object; an empty input
    yields an empty (but well-formed) aggregate.
    """
    merged: dict = {}          # (file, line) -> consolidated finding
    order: list = []           # first-seen order of keys, for stable output
    theme_slices: dict = {}    # agent -> set of slice ids
    theme_counts: dict = {}    # agent -> total findings
    reduced_panel_slices: list = []
    totals = {"errors": 0, "warnings": 0, "suggestions": 0}

    for section in sections:
        slice_id = section.get("id")
        if section.get("is_declarative"):
            reduced_panel_slices.append(slice_id)
        for finding in _findings_of(section):
            severity = finding.get("severity", "suggestion")
            totals[_SEVERITY_BUCKET.get(severity, "suggestions")] += 1
            agent = finding.get("agent")
            if agent is not None:
                theme_slices.setdefault(agent, set()).add(slice_id)
                theme_counts[agent] = theme_counts.get(agent, 0) + 1
            _merge_finding(merged, order, finding)

    top_findings = [merged[k] for k in order]
    top_findings.sort(key=lambda f: (-_rank(f["severity"]), str(f["file"]), f["line"] or 0))

    recurring_themes = [
        {"agent": agent, "slices": _sorted_ids(slices), "occurrences": theme_counts[agent]}
        for agent, slices in theme_slices.items()
        if len(slices) >= _THEME_MIN_SLICES
    ]
    recurring_themes.sort(key=lambda t: (-t["occurrences"], t["agent"]))

    overall = "fail" if totals["errors"] else "warn" if totals["warnings"] else "pass"

    return {
        "sliced": True,
        "sliceCount": len(sections),
        "overall": overall,
        "totals": totals,
        "topFindings": top_findings,
        "recurringThemes": recurring_themes,
        "reducedPanelSlices": _sorted_ids(reduced_panel_slices),
        "summary": (
            f"{overall.upper()} across {len(sections)} slices — "
            f"{totals['errors']} errors, {totals['warnings']} warnings, "
            f"{totals['suggestions']} suggestions; "
            f"{len(recurring_themes)} recurring theme(s)."
        ),
    }


def _read_sections(root: str) -> "tuple[list, list]":
    """Read every ``raw/section-*.json`` under ``root``.

    Returns ``(sections, malformed_paths)``. A malformed artifact is collected
    into ``malformed_paths`` (reported by the caller), never silently dropped.
    """
    raw_dir = Path(root) / "DEV_TEAM_REPORTS" / "code-review" / "raw"
    sections, malformed = [], []
    for path in sorted(glob.glob(str(raw_dir / "section-*.json"))):
        try:
            obj = json.loads(Path(path).read_text())
        except (json.JSONDecodeError, OSError):
            malformed.append(path)
            continue
        # Valid JSON of the wrong shape (list, string, ...) is malformed too —
        # otherwise it would crash consolidate() at section.get(...).
        if not isinstance(obj, dict):
            malformed.append(path)
            continue
        sections.append(obj)
    return sections, malformed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    sections, malformed = _read_sections(args.root)
    for path in malformed:
        print(f"WARNING: malformed section artifact skipped: {path}", file=sys.stderr)

    result = consolidate(sections)
    if malformed:
        result["malformedArtifacts"] = malformed
    print(json.dumps(result, indent=2, sort_keys=True))
    # Non-zero exit if any artifact was unreadable, so a caller notices.
    return 2 if malformed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
