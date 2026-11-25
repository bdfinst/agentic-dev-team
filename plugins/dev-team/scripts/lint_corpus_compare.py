#!/usr/bin/env python3
"""Compare what a review agent found with what a lint rule found, per rule.

Both inputs are JSON: a list of findings, or an object with a ``findings``
list. A finding has ``file`` (string) and ``line`` (integer). Agent findings
carry ``rule``: the lint rule id that would decide the case, or ``null`` when
no rule does. Rule findings carry ``rule``: the rule id ESLint reported.

For each rule the report gives:

- ``agent_found``: agent cases mapped to the rule.
- ``rule_found``: findings the rule reported.
- ``false_positives``: rule findings on a line where the agent reported
  nothing (under any rule, or under ``null``).
- ``residual``: ``file:line`` of agent cases the rule missed.
- ``convertible``: the rule covers every agent case, reports no false
  positive, and has at least one agent case as evidence.

Usage:
    python3 lint_corpus_compare.py --agent-found FILE --rule-found FILE
                                   [--rules FILE] [--format json|text]

``--rules`` is a JSON list of rule ids to report even when neither side found
anything. Exit 0 when at least one rule is convertible, 3 when none is (a
stop report is printed to stderr), 2 on unreadable or malformed input.

Stdlib only. Own loader: shares no code with the other lint scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXIT_NONE_CONVERTIBLE = 3
EXIT_BAD_INPUT = 2

STOP_REPORT = (
    "gate: none convertible. No rule covers all agent cases with zero false "
    "positives, so no Detect bullet should become a lint-rule pointer."
)

Finding = dict[str, Any]
Location = tuple[str, int]


class InputError(ValueError):
    """An input file is unreadable or not shaped like a findings list."""


def _validate(items: Any, label: str, *, rule_required: bool) -> list[Finding]:
    if isinstance(items, dict) and isinstance(items.get("findings"), list):
        items = items["findings"]
    if not isinstance(items, list):
        raise InputError(f"{label}: expected a list or an object with 'findings'")
    for index, item in enumerate(items):
        problem = _finding_problem(item, rule_required)
        if problem:
            raise InputError(f"{label}[{index}]: {problem}")
    return items


def _finding_problem(item: Any, rule_required: bool) -> str | None:
    if not isinstance(item, dict):
        return "not an object"
    if not isinstance(item.get("file"), str):
        return "'file' must be a string"
    line = item.get("line")
    if not isinstance(line, int) or isinstance(line, bool):
        return "'line' must be an integer"
    rule = item.get("rule")
    if rule is not None and not isinstance(rule, str):
        return "'rule' must be a string or null"
    if rule_required and rule is None:
        return "'rule' is required"
    return None


def load_findings(path: str, *, rule_required: bool) -> list[Finding]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{path}: {error}") from error
    return _validate(raw, path, rule_required=rule_required)


def load_rules(path: str) -> list[str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputError(f"{path}: {error}") from error
    if not isinstance(raw, list) or not all(isinstance(rule, str) for rule in raw):
        raise InputError(f"{path}: expected a list of rule id strings")
    return raw


def _by_rule(items: list[Finding]) -> dict[str, dict[Location, Finding]]:
    grouped: dict[str, dict[Location, Finding]] = {}
    for item in items:
        if item["rule"] is not None:
            grouped.setdefault(item["rule"], {})[(item["file"], item["line"])] = item
    return grouped


def compare(
    agent_found: list[Finding],
    rule_found: list[Finding],
    rules: list[str] | None = None,
) -> dict[str, Any]:
    """Return the per-rule comparison and the sorted list of convertible rules."""
    agent_by_rule = _by_rule(agent_found)
    rule_by_rule = _by_rule(rule_found)
    agent_lines = {(item["file"], item["line"]) for item in agent_found}
    rule_ids = sorted({*agent_by_rule, *rule_by_rule, *(rules or [])})

    entries: dict[str, dict[str, Any]] = {}
    for rule in rule_ids:
        agent_at = agent_by_rule.get(rule, {})
        rule_at = rule_by_rule.get(rule, {})
        residual = sorted(loc for loc in agent_at if loc not in rule_at)
        false_positives = sorted(loc for loc in rule_at if loc not in agent_lines)
        entries[rule] = {
            "agent_found": len(agent_at),
            "rule_found": len(rule_at),
            "false_positives": len(false_positives),
            "false_positive_at": [f"{file}:{line}" for file, line in false_positives],
            "residual": [f"{file}:{line}" for file, line in residual],
            "convertible": bool(agent_at) and not residual and not false_positives,
        }
    return {
        "rules": entries,
        "convertible": [rule for rule, entry in entries.items() if entry["convertible"]],
    }


def render_text(report: dict[str, Any]) -> str:
    lines = ["rule | agent_found | rule_found | false_positives | residual | verdict"]
    for rule, entry in report["rules"].items():
        verdict = "convertible" if entry["convertible"] else "NOT convertible"
        lines.append(
            f"{rule} | {entry['agent_found']} | {entry['rule_found']} | "
            f"{entry['false_positives']} | {len(entry['residual'])} | {verdict}"
        )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--agent-found", required=True)
    parser.add_argument("--rule-found", required=True)
    parser.add_argument("--rules")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        agent_found = load_findings(args.agent_found, rule_required=False)
        rule_found = load_findings(args.rule_found, rule_required=True)
        rules = load_rules(args.rules) if args.rules else None
    except InputError as error:
        print(f"lint_corpus_compare: {error}", file=sys.stderr)
        return EXIT_BAD_INPUT

    report = compare(agent_found, rule_found, rules)
    if args.format == "text":
        print(render_text(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    if not report["convertible"]:
        print(STOP_REPORT, file=sys.stderr)
        return EXIT_NONE_CONVERTIBLE
    return 0


if __name__ == "__main__":
    sys.exit(main())
