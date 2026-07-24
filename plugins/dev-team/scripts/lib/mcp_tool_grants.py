#!/usr/bin/env python3
"""Shared plumbing for the code-intelligence MCP tool-grant checks.

Three sibling check scripts consume this module as peers — none is any other's
library:

- ``check_review_agent_mcp_tools.py`` — the 24 read-only ``*-review`` agents, all
  granted the same ``BASE_MCP_TOOLS`` set (#1102).
- ``check_agent_tool_mapping.py`` — the non-review team agents, granted per-tier
  sets built from ``BASE_MCP_TOOLS`` (± ``GET_WHY``) (#1108).
- ``check_security_assessment_mcp_tools.py`` — the security-assessment plugin's
  code-reading agents, granted the same ``BASE_MCP_TOOLS`` set as the review-agent
  check above, but discovered via a named roster rather than a filename glob
  (#1388).

This module owns the canonical tool-name constants and the frontmatter
``tools:``-line parse/fix plumbing all three checks need. The fix helpers take a
caller-supplied ``required`` list so each check can request its own set (the
5-name review/narrow set, or the 6-name rationale set) without duplicating the
merge logic.
"""

import re

# CodeGraph + the four Repowise tools granted to every read-only review agent,
# and the shared base of the non-review tiers (#1102's canonical set). A granted
# tool whose MCP server is absent is simply unavailable at runtime (no error);
# agents fall back to Read/Grep/Glob.
BASE_MCP_TOOLS = [
    "mcp__codegraph__codegraph_explore",
    "mcp__plugin_repowise_repowise__get_context",
    "mcp__plugin_repowise_repowise__get_symbol",
    "mcp__plugin_repowise_repowise__search_codebase",
    "mcp__plugin_repowise_repowise__get_risk",
]

# The rationale/decision tier additionally grants get_why (code-existence
# rationale) — see check_agent_tool_mapping.py.
GET_WHY = "mcp__plugin_repowise_repowise__get_why"

# Match the inline `tools:` line only. Group 1 (`tools:` + horizontal space) and
# group 3 (trailing horizontal space) use `[ \t]` — NOT `\s` — so the match can
# never cross a newline into a YAML block-scalar/sequence form
# (`tools:\n  - Read`). Group 2 is the inline value (no newline).
_TOOLS_RE = re.compile(r"^(tools:[ \t]*)([^\n]*?)([ \t]*)$", re.MULTILINE)


def parse_tools(text):
    """Return the comma-separated tokens on the inline ``tools:`` line, or None.

    Returns None when there is no ``tools:`` line, or when it has no inline value
    (an empty line, or a YAML block form with the list on following lines) — such
    a line is not safely appendable, so callers treat None as *unfixable* rather
    than mangling it.
    """
    m = _TOOLS_RE.search(text)
    if not m:
        return None
    value = m.group(2).strip()
    if not value:
        return None
    return [tok.strip() for tok in value.split(",") if tok.strip()]


def _server_wildcard_forms(name):
    """Return the ``mcp__<server>__*`` and bare ``mcp__<server>`` forms that
    satisfy a specific ``mcp__<server>__<tool>`` grant requirement, per
    agent-contract.json's tools: value_format ("mcp__<server> or
    mcp__<server>__*" grants every tool from that server).
    """
    parts = name.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return ()
    server = "__".join(parts[:2])
    return (f"{server}__*", server)


def _is_satisfied(name, present):
    """True if ``name`` is granted exactly, or via a server-wide wildcard grant."""
    if name in present:
        return True
    return any(form in present for form in _server_wildcard_forms(name))


def _compute_missing(present, required):
    """Return the ``required`` names not satisfied by the ``present`` grant set."""
    return [name for name in required if not _is_satisfied(name, present)]


def missing_tools(text, required):
    """Return the ``required`` tool names absent from the agent's ``tools:`` line.

    A required ``mcp__<server>__<tool>`` name is considered present when the
    agent instead grants ``mcp__<server>__*`` or bare ``mcp__<server>`` —
    both equivalent, broader grants per the official contract.

    Returns the full ``required`` list when the agent has no parseable ``tools:``
    line at all.
    """
    tokens = parse_tools(text)
    if tokens is None:
        return list(required)
    return _compute_missing(set(tokens), required)


def fix_tools_line(text, required):
    """Append any missing ``required`` names to the ``tools:`` line. Idempotent.

    Returns ``(new_text, added_names)``. Order-preserving: existing tokens keep
    their order; missing names are appended in ``required`` order. A line already
    containing every required name is returned unchanged (``added == []``). A file
    with no parseable ``tools:`` line is returned unchanged (``added == []``).
    """
    m = _TOOLS_RE.search(text)
    if not m:
        return text, []
    tokens = parse_tools(text)
    if tokens is None:
        # No inline value (block form or empty) — unfixable, never mangle it.
        return text, []
    added = _compute_missing(set(tokens), required)
    if not added:
        return text, []
    new_tokens = tokens + added
    new_line = m.group(1) + ", ".join(new_tokens)
    new_text = text[: m.start()] + new_line + text[m.end() - len(m.group(3)) :]
    return new_text, added


def run_grants_check(targets, apply_fix=False):
    """Single read+parse pass per target, shared by all three grant-check scripts.

    ``targets`` is ``{name: (path, required)}``. Each target's file is read from
    disk **at most once** regardless of ``apply_fix`` — the offender computation
    below reuses the (possibly just-fixed) in-memory text rather than re-reading,
    which is what let ``--fix`` runs silently do a second full read+parse pass
    per file in the three callers before this helper existed (#1392).

    Returns ``(offenders, fixed, unfixable)``:
      - ``offenders``: ``{name: [missing tool names]}``, reflecting the
        post-fix state when ``apply_fix`` is true.
      - ``fixed``: ``{name: [tool names added]}`` — populated only when
        ``apply_fix`` is true.
      - ``unfixable``: ``[name, ...]`` — targets whose file exists but has no
        appendable inline ``tools:`` line — populated only when ``apply_fix``
        is true (mirrors each caller's prior ``apply_fixes()`` semantics).
    """
    offenders = {}
    fixed = {}
    unfixable = []
    for name, (path, required) in targets.items():
        if not path.is_file():
            offenders[name] = list(required)
            continue
        text = path.read_text(encoding="utf-8")
        if apply_fix:
            if parse_tools(text) is None:
                unfixable.append(name)
            else:
                new_text, added = fix_tools_line(text, required)
                if added:
                    path.write_text(new_text, encoding="utf-8")
                    fixed[name] = added
                    text = new_text
        missing = missing_tools(text, required)
        if missing:
            offenders[name] = missing
    return offenders, fixed, unfixable


def build_json_report(check, evaluated, offenders, ok, fixed=None, unfixable=None, unclassified=None, notes=None):
    """Build the common ``--json`` envelope shared by all three grant-check scripts (#1393).

    Each script's ``--json`` output previously diverged in shape (``reviewed`` vs
    ``covered``, an ``unclassified`` key present on two scripts but absent on the
    third, ``fixed``/``unfixable`` only appearing conditionally on ``--fix``) — a
    caller wanting to aggregate "which grant checks are failing" across scripts had
    no uniform surface to read. This helper gives every script the same top-level
    keys, always present, so a future aggregator never needs a per-script branch:

    - ``check``: a stable slug identifying which script produced the report.
    - ``evaluated``: every target name the check looked at.
    - ``offenders``: ``{name: [missing tool names]}`` (post-fix state if fixed).
    - ``unclassified``: names present but classified into neither a required nor
      an excluded bucket — ``[]`` when the check has no such concept.
    - ``fixed`` / ``unfixable``: from ``run_grants_check`` — empty when detection
      only (no ``--fix``).
    - ``ok``: the caller's own exit-code decision, passed through rather than
      re-derived here — some checks (e.g. the review-agent script's skill-prose
      check) fail for reasons ``offenders``/``unclassified`` alone don't capture,
      so this helper must not guess at "ok" from the other fields.
    - ``notes``: a namespaced bag for the one or two fields that are genuinely
      script-specific (e.g. ``skill_missing_phrases``, ``swept``) rather than
      forcing every script into an identical key set that doesn't fit.
    """
    return {
        "check": check,
        "evaluated": list(evaluated),
        "offenders": offenders,
        "unclassified": list(unclassified or []),
        "fixed": fixed or {},
        "unfixable": list(unfixable or []),
        "ok": ok,
        "notes": notes or {},
    }
