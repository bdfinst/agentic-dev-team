"""Structural tests for the per-rule semgrep fixtures (#124).

Deterministic and semgrep-free (the semgrep-executing measurement runs as
its own CI job): every custom rule must have a positive + negative fixture,
and the known-broken list must reference only real rule ids.

Ported from tests/repo/semgrep_fixtures_tests.bats (#673).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = (
    REPO_ROOT / "plugins" / "security-assessment" / "knowledge" / "semgrep-rules"
)
FIX_DIR = REPO_ROOT / "plugins" / "security-assessment" / "knowledge" / "rule-fixtures"
KNOWN_BROKEN = FIX_DIR / "known-broken-rules.txt"

_ID_RE = re.compile(r"^\s*- id:\s*(\S+)")
_FP_RATE_RE = re.compile(r"fp_rate:")
_STATUS_RE = re.compile(r"semgrep_status:")


def _rule_ids() -> List[str]:
    ids = []
    for yaml_file in sorted(RULES_DIR.glob("*.yaml")):
        for line in yaml_file.read_text().splitlines():
            match = _ID_RE.match(line)
            if match:
                ids.append(match.group(1))
    return ids


def test_all_36_custom_rules_are_present() -> None:
    assert len(_rule_ids()) == 36


def test_every_rule_has_at_least_one_positive_and_negative_fixture() -> None:
    missing = []
    for rule_id in _rule_ids():
        d = FIX_DIR / rule_id
        has_positive = d.is_dir() and any(d.glob("positive.*"))
        has_negative = d.is_dir() and any(d.glob("negative.*"))
        if not (has_positive and has_negative):
            missing.append(rule_id)
    assert not missing, f"missing fixtures for: {' '.join(missing)}"


def test_every_rule_records_fp_rate_or_semgrep_status_in_metadata() -> None:
    # The measurement stamps fp_rate (working rules) or semgrep_status
    # (broken).
    n_fp = 0
    n_status = 0
    for yaml_file in RULES_DIR.glob("*.yaml"):
        text = yaml_file.read_text()
        n_fp += len(_FP_RATE_RE.findall(text))
        n_status += len(_STATUS_RE.findall(text))
    assert n_fp + n_status == 36


def test_known_broken_every_listed_id_is_a_real_rule_id() -> None:
    ids = set(_rule_ids())
    bad = []
    for raw_line in KNOWN_BROKEN.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line not in ids:
            bad.append(line)
    assert not bad, f"unknown rule ids in known-broken-rules.txt: {' '.join(bad)}"


def test_audit_the_semgrep_fixtures_audit_script_exists_and_parses() -> None:
    script = REPO_ROOT / "scripts" / "audit-semgrep-fixtures.py"
    assert script.is_file()
    ast.parse(script.read_text())
