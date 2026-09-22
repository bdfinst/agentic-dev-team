#!/usr/bin/env python3
"""Tier-1/Tier-2 rendering for `/code-review` step 7's prose report (#2170).

Step 7's prose-mode path lists every remaining finding in full — severity,
confidence, file, line, message, and suggested fix all inline — which makes a
report with a dozen findings a wall of text even when most of them are
routine. This module renders a compact Tier-1 line per finding by default,
and defers the full message/suggestedFix narrative (Tier-2) to an explicit
`--expand <finding-id>|all`, using the SAME in-memory finding list already
aggregated for the report — no re-dispatch, no I/O beyond the finding JSON
already on hand.

This script is prose-path only. `--json` (step 7's other branch) and
`./corrections/*.json` (step 8) read/write the full finding objects
independently and never call into this module — see Step 3.2, which wires
that non-interference into `/code-review` itself. Nothing here needs to
special-case `--json`.

## Finding-id scheme

`agent:file:line:severity`, plus `:category` appended when the finding
carries a truthy taxonomy tag. Two or more findings in the same run that
still land on an identical base id after that get a `#0`, `#1`, ... ordinal
suffix in list order — deterministic and collision-free within a single run
because the caller's list order is already fixed for that run (the `#`
separator, rather than `:`, is used for the ordinal so it can never collide
with a base-id segment, which is `:`-delimited). IDs are not meant to be
stable *across* runs (a re-dispatched round may reorder or drop findings).

`agent` is read as `finding.get("agent")` first (the aggregated/flattened
finding shape `consolidate.py` produces, `agent`-tagged per finding) falling
back to `finding.get("agentName")` (the raw per-agent-result field name) —
the same two-field fallback `finding_signature.py`'s `signature()` already
uses for the identical purpose, so this module reads either the pre- or
post-flattening shape without extra glue.

The taxonomy tag itself mirrors `finding_signature.py`'s `signature()`
fallback chain exactly: `category` → `smell` → `rule` → `ruleId`, first
truthy wins. `smell` is `test-smell-review`'s taxonomy field per
`knowledge/review-agent-output-contract.md`'s "Documented per-agent
extensions" section — without this fallback a `test-smell-review` finding's
id loses its taxonomy segment and falls back to a bare ordinal suffix.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

#: Rendered instead of any per-finding line when a round has zero findings —
#: there is nothing to list and nothing to expand.
CLEAN_PASS_SUMMARY = "Clean pass: 0 findings this round — nothing to expand."

#: Rendered once, after the Tier-1 lines, when the round has at least one
#: finding. Omitted entirely on a zero-finding round (see CLEAN_PASS_SUMMARY)
#: because there is nothing an --expand call could act on.
EXPAND_HINT = "Expand a finding with --expand <finding-id>, or --expand all for every finding."

#: First-sentence split: a `.`/`!`/`?` followed by whitespace or end-of-string.
#: Deliberately simple (no abbreviation handling) — finding messages in this
#: codebase's contract are short, single-clause statements
#: ("God object: AuthController handles login, registration, and password
#: reset"), not prose with embedded abbreviations; a message with no
#: terminator at all renders in full.
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")


def first_sentence(message) -> str:
    """The first sentence of `message`, or the whole (stripped) string when
    no sentence terminator is found. Always a single line: internal
    whitespace runs (including embedded newlines) are collapsed to a single
    space, so a Tier-1 entry built from this is always exactly one line."""
    text = str(message or "").strip()
    if not text:
        return ""
    match = _SENTENCE_END_RE.search(text)
    result = text if match is None else text[: match.start() + 1]
    return " ".join(result.split())


def _finding_agent(finding: dict) -> str:
    return str(finding.get("agent") or finding.get("agentName") or "")


def _finding_line(finding: dict) -> str:
    line = finding.get("line")
    return "" if line is None else str(line)


def _finding_category(finding: dict) -> str:
    """The taxonomy tag for this finding, mirroring `finding_signature.py`'s
    `signature()` fallback chain exactly: `category` -> `smell` -> `rule` ->
    `ruleId`, first truthy wins."""
    return str(
        finding.get("category")
        or finding.get("smell")
        or finding.get("rule")
        or finding.get("ruleId")
        or ""
    )


def base_id(finding: dict) -> str:
    """The finding-id before ordinal-suffix collision resolution:
    `agent:file:line:severity`, plus `:category` when the taxonomy tag
    (see `_finding_category`) is truthy on this finding."""
    parts = [
        _finding_agent(finding),
        str(finding.get("file") or ""),
        _finding_line(finding),
        str(finding.get("severity") or ""),
    ]
    category = _finding_category(finding)
    if category:
        parts.append(category)
    return ":".join(parts)


def compute_ids(findings: list[dict]) -> list[str]:
    """Finding-id for each entry in `findings`, in list order.

    A base id unique in this round is used as-is. A base id shared by two or
    more findings gets a `#0`, `#1`, ... ordinal suffix, assigned in list
    order — deterministic because the input order is already fixed for a
    given run. `#` (rather than `:`, which the base id itself uses as its
    segment separator) guarantees the suffix can never collide with a
    base-id segment.
    """
    bases = [base_id(f) for f in findings]
    counts = Counter(bases)
    next_ordinal: dict[str, int] = {}
    ids = []
    for base in bases:
        if counts[base] > 1:
            ordinal = next_ordinal.get(base, 0)
            next_ordinal[base] = ordinal + 1
            ids.append(f"{base}#{ordinal}")
        else:
            ids.append(base)
    return ids


def render_tier1_line(finding: dict, finding_id: str) -> str:
    """One Tier-1 line: `file:line [agent] severity/confidence —
    <first sentence of message> (<finding-id>)`."""
    file_ = str(finding.get("file") or "")
    line = _finding_line(finding)
    agent = _finding_agent(finding)
    severity = str(finding.get("severity") or "")
    confidence = str(finding.get("confidence") or "")
    sentence = first_sentence(finding.get("message", ""))
    return f"{file_}:{line} [{agent}] {severity}/{confidence} — {sentence} ({finding_id})"


def render_tier1_report(findings: list[dict], ids: list[str]) -> str:
    """The full Tier-1 report: one line per finding plus the expansion hint,
    or `CLEAN_PASS_SUMMARY` alone when there are no findings."""
    if not findings:
        return CLEAN_PASS_SUMMARY
    lines = [render_tier1_line(f, i) for f, i in zip(findings, ids)]
    lines.append(EXPAND_HINT)
    return "\n".join(lines)


def render_tier2_block(finding: dict, finding_id: str) -> str:
    """The full Tier-2 block for one finding: id header, full message, and
    the suggested fix (when the finding carries one)."""
    lines = [f"=== {finding_id} ===", str(finding.get("message") or "")]
    fix = finding.get("suggestedFix")
    if fix:
        lines.append(f"Suggested fix: {fix}")
    return "\n".join(lines)


def render_tier2_report(findings: list[dict], ids: list[str]) -> str:
    """Every finding's Tier-2 block, in list order, separated by a blank
    line. `CLEAN_PASS_SUMMARY` alone when there are no findings."""
    if not findings:
        return CLEAN_PASS_SUMMARY
    return "\n\n".join(render_tier2_block(f, i) for f, i in zip(findings, ids))


def render_expand_one(findings: list[dict], ids: list[str], finding_id: str) -> str | None:
    """The single Tier-2 block for `finding_id`, or `None` when no finding
    in this round has that id (the caller turns that into a non-zero exit)."""
    try:
        index = ids.index(finding_id)
    except ValueError:
        return None
    return render_tier2_block(findings[index], ids[index])


def _load_findings(path: str) -> list[dict]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(raw) if raw.strip() else []
    if isinstance(data, dict):
        data = data.get("findings", [])
    if not isinstance(data, list):
        return []
    return [f for f in data if isinstance(f, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--findings",
        default="-",
        help="Path to this round's finding-list JSON ('-' for stdin, the default).",
    )
    parser.add_argument(
        "--expand",
        default=None,
        help="A finding-id to render Tier-2 for, or 'all' to render every finding's Tier-2 block.",
    )
    args = parser.parse_args(argv)

    findings = _load_findings(args.findings)
    ids = compute_ids(findings)

    tier1 = render_tier1_report(findings, ids)

    if args.expand is None:
        print(tier1)
        return 0

    if args.expand == "all":
        print(tier1)
        print()
        print(render_tier2_report(findings, ids))
        return 0

    block = render_expand_one(findings, ids, args.expand)
    if block is None:
        sys.stderr.write(
            f"render_tiered_findings: finding-id not found in this round's findings: {args.expand!r}\n"
        )
        return 1
    print(tier1)
    print()
    print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
