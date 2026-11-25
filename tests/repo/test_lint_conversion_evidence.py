"""Recorded evidence the lint-conversion batch promises.

Each test names a fact a reader would otherwise check by opening a file: the
Node gate is advisory, the measurements file records token counts and lint
times, and `/upgrade` drives the scaffold script's `--check` and `--refresh`.
"""

from __future__ import annotations

import json
import re

from _repo_root import REPO_ROOT

STATUS_CHECKS = REPO_ROOT / ".github" / "required-status-checks.json"
MEASUREMENTS = REPO_ROOT / "plugins/dev-team/templates/eslint/dev/MEASUREMENTS.md"
UPGRADE_SKILL = REPO_ROOT / "plugins/dev-team/skills/upgrade/SKILL.md"
NODE_GATE = "ESLint templates (Node)"
TABLE_ROW = re.compile(r"^\|.*\d.*\|$", re.MULTILINE)


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match, f"MEASUREMENTS.md has no '## {heading}' section"
    return match.group(0)


def test_node_gate_is_exempt_not_required():
    manifest = json.loads(STATUS_CHECKS.read_text(encoding="utf-8"))
    assert NODE_GATE in manifest["exempt"]
    assert NODE_GATE not in manifest["required"]


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _row(section: str, label: str) -> list[str]:
    """The cells of the table row whose first cell holds `label`."""
    rows = [_cells(r) for r in TABLE_ROW.findall(section)]
    matching = [cells for cells in rows if label in cells[0]]
    assert matching, f"no table row names {label!r}"
    return matching[0]


def test_measurements_record_token_counts_before_and_after_for_both_agents():
    section = _section(MEASUREMENTS.read_text(encoding="utf-8"), "Tokens")
    for agent in ("esm-enforcer", "js-fp-review"):
        _, before, after = _row(section, agent)
        assert before.isdigit() and after.isdigit(), (agent, before, after)


def test_measurements_record_typed_and_untyped_lint_times():
    section = _section(MEASUREMENTS.read_text(encoding="utf-8"), "Lint latency")
    for mode in ("typed", "untyped"):
        p50, p95 = _row(section, mode)[-2:]
        assert float(p50) > 0 and float(p95) > 0, (mode, p50, p95)


def test_upgrade_skill_drives_scaffold_check_and_refresh():
    skill = UPGRADE_SKILL.read_text(encoding="utf-8")
    assert re.search(r"scaffold_lint_config\.py\"? .*--check", skill)
    assert re.search(r"scaffold_lint_config\.py\"? .*--refresh", skill)
