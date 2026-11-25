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


def test_measurements_record_token_counts_before_and_after_for_both_agents():
    section = _section(MEASUREMENTS.read_text(encoding="utf-8"), "Tokens")
    rows = [row for row in TABLE_ROW.findall(section)]
    assert any("esm-enforcer" in row for row in rows)
    assert any("js-fp-review" in row for row in rows)


def test_measurements_record_typed_and_untyped_lint_times():
    section = _section(MEASUREMENTS.read_text(encoding="utf-8"), "Lint latency")
    rows = TABLE_ROW.findall(section)
    assert any(row.lstrip("| ").startswith("typed") for row in rows)
    assert any(row.lstrip("| ").startswith("untyped") for row in rows)


def test_upgrade_skill_drives_scaffold_check_and_refresh():
    skill = UPGRADE_SKILL.read_text(encoding="utf-8")
    assert re.search(r"scaffold_lint_config\.py\"? .*--check", skill)
    assert re.search(r"scaffold_lint_config\.py\"? .*--refresh", skill)
