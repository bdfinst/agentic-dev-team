#!/usr/bin/env python3
"""Consolidate per-slice section artifacts into one deduplicated report.

Split into a **pure** ``consolidate(sections)`` (takes a list of section dicts,
returns the aggregated object) and a thin ``main()`` that reads
``.dev-team-reports/code-review/raw/section-*.json`` and calls it — the same
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

# Reach the sibling ledger.py regardless of cwd or sys.path mode (matches the
# house pattern in change_shape.py/codebase_recon.py for reaching a sibling
# module rather than relying on the implicit sys.path[0] a direct script
# invocation provides).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from ledger import raw_dir

# Single source of truth for the severity vocabulary (step 5c's ranking lived
# only in prose before): each severity's rank (for highest-wins merge and
# sorting) and its totals bucket key.
_SEVERITY = {
    "suggestion": (1, "suggestions"),
    "warning": (2, "warnings"),
    "error": (3, "errors"),
}
_DEFAULT_SEVERITY = "suggestion"

# A review dimension recurring across at least this many slices is a theme.
_THEME_MIN_SLICES = 2

# Real-world review-agent output drifts from the documented schema (#1261): some
# agents return their findings list under `issues` (the per-agent key in
# output-format.md) instead of `findings` (the section-artifact key). Accept
# either so a mis-keyed list is aggregated, never silently counted as zero. The
# canonical key is tried first; the alias is a fallback.
_FINDINGS_KEYS = ("findings", "issues")


def _rank(severity: str) -> int:
    return _SEVERITY.get(severity, (0, ""))[0]


def _bucket(severity: str) -> str:
    return _SEVERITY.get(severity, _SEVERITY[_DEFAULT_SEVERITY])[1]


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


def normalize_agent_result(raw: dict, agent_name: str | None = None) -> list:
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
    severity = finding.get("severity", _DEFAULT_SEVERITY)
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


def _tally_severity(totals: dict, severity: str) -> None:
    totals[_bucket(severity)] += 1


def _tally_theme(theme_slices: dict, theme_counts: dict, agent: str | None, slice_id) -> None:
    """Record one finding's contribution to the recurring-theme rollup for ``agent``."""
    if agent is None:
        return
    theme_slices.setdefault(agent, set()).add(slice_id)
    theme_counts[agent] = theme_counts.get(agent, 0) + 1


def consolidate(sections: list[dict]) -> dict:
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
    dispatch_failures: list = []
    totals = {"errors": 0, "warnings": 0, "suggestions": 0}

    for section in sections:
        slice_id = section.get("id")
        if section.get("is_declarative"):
            reduced_panel_slices.append(slice_id)
        section_dispatch_failures = section.get("dispatchFailures")
        if isinstance(section_dispatch_failures, list):
            dispatch_failures.extend(section_dispatch_failures)
        for finding in _findings_of(section):
            severity = finding.get("severity", _DEFAULT_SEVERITY)
            _tally_severity(totals, severity)
            _tally_theme(theme_slices, theme_counts, finding.get("agent"), slice_id)
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
    # A non-empty dispatchFailures forces overall: fail, unconditionally — applied
    # after the totals-based computation above so it always wins, mirroring the
    # legacy (non-sliced) path's own unconditional-override rule.
    if dispatch_failures:
        overall = "fail"

    return {
        "sliced": True,
        "sliceCount": len(sections),
        "overall": overall,
        "totals": totals,
        "topFindings": top_findings,
        "recurringThemes": recurring_themes,
        "reducedPanelSlices": _sorted_ids(reduced_panel_slices),
        "dispatchFailures": dispatch_failures,
        "summary": (
            f"{overall.upper()} across {len(sections)} slices — "
            f"{totals['errors']} errors, {totals['warnings']} warnings, "
            f"{totals['suggestions']} suggestions; "
            f"{len(recurring_themes)} recurring theme(s)."
        ),
    }


def _read_sections(root: str) -> tuple[list, list]:
    """Read every ``raw/section-*.json`` under ``root``.

    Returns ``(sections, malformed_paths)``. A malformed artifact is collected
    into ``malformed_paths`` (reported by the caller), never silently dropped.
    """
    sections, malformed = [], []
    for path in sorted(glob.glob(str(raw_dir(root) / "section-*.json"))):
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    sections, malformed = _read_sections(args.root)
    for path in malformed:
        print(f"WARNING: malformed section artifact skipped: {path}", file=sys.stderr)

    result = consolidate(sections)
    if malformed:
        result["malformedArtifacts"] = malformed
        # A malformed artifact means that slice's findings were never read —
        # the identical coverage gap `dispatchFailures` forces `overall`
        # to "fail" for a few lines up in consolidate(), and for the same
        # reason: an unexamined slice must never ride out as "pass" just
        # because the READABLE sections happened to look clean (#1763
        # security review — /pr --json checks only overall/status). The
        # `summary` string is rebuilt too (#1865) — it must not interpolate
        # the PRE-override `result['summary']` (built from `overall` INSIDE
        # consolidate(), before this override runs): doing so would print a
        # "FAIL ... ; WARN ..." self-contradicting summary. Rebuild it
        # entirely from the already-available totals/recurringThemes instead.
        result["overall"] = "fail"
        totals = result["totals"]
        result["summary"] = (
            f"FAIL across {len(sections)} slices — {len(malformed)} malformed "
            f"artifact(s) unreadable; {totals['errors']} errors, {totals['warnings']} warnings, "
            f"{totals['suggestions']} suggestions from readable slices; "
            f"{len(result['recurringThemes'])} recurring theme(s)."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    # Non-zero exit if any artifact was unreadable, so a caller notices.
    return 2 if malformed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
