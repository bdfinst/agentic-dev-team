"""Tests for scripts/audit-rules-vs-prompts.sh - the rules-vs-prompts
enforcement sensor (issue #118). Exercises the pass case on the real tree
and each failure mode via synthetic manifests injected through the env
seams (RULE_MAP, OWASP_DOC, PLUGIN_ROOT).

Ported from tests/repo/audit_rules_vs_prompts_tests.bats (#673).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = REPO_ROOT / "scripts" / "audit-rules-vs-prompts.sh"


def _run(env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(AUDIT)],
        cwd=str(REPO_ROOT),
        env=full_env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def synthetic_plugin(tmp_path: Path) -> Dict[str, str]:
    plugin = tmp_path / "plugin"
    (plugin / "knowledge" / "rule-fixtures" / "A03.sql-injection").mkdir(parents=True)
    (
        plugin / "knowledge" / "rule-fixtures" / "A03.sql-injection" / "positive.js"
    ).write_text("q(`${x}`)\n")
    (
        plugin / "knowledge" / "rule-fixtures" / "A03.sql-injection" / "negative.js"
    ).write_text('q("?", [x])\n')
    (plugin / "knowledge" / "owasp-detection.md").write_text("# OWASP\n")
    return {
        "PLUGIN_ROOT": str(plugin),
        "RULE_MAP": str(plugin / "knowledge" / "security-review-rule-map.yaml"),
        "OWASP_DOC": str(plugin / "knowledge" / "owasp-detection.md"),
    }


def test_audit_passes_on_the_real_repository_tree() -> None:
    result = _run()
    assert result.returncode == 0
    assert "audit OK" in result.stdout + result.stderr


def test_audit_a_correct_synthetic_manifest_passes(
    synthetic_plugin: Dict[str, str],
) -> None:
    Path(synthetic_plugin["RULE_MAP"]).write_text(
        """version: 1.1.0
mappings:
  A03.sql-injection: semgrep.generic.sql-injection
  A01.idor: security-review.a01.idor
classes:
  A03.sql-injection:
    surface: rule
    fp_rate: 0.05
    fixtures: knowledge/rule-fixtures/A03.sql-injection
  A01.idor: { surface: prompt }
"""
    )
    result = _run(synthetic_plugin)
    assert result.returncode == 0, result.stdout + result.stderr


def test_audit_fails_when_fp_rate_exceeds_10_percent(
    synthetic_plugin: Dict[str, str],
) -> None:
    Path(synthetic_plugin["RULE_MAP"]).write_text(
        """version: 1.1.0
mappings: { A03.sql-injection: semgrep.generic.sql-injection }
classes:
  A03.sql-injection:
    surface: rule
    fp_rate: 0.25
    fixtures: knowledge/rule-fixtures/A03.sql-injection
"""
    )
    result = _run(synthetic_plugin)
    assert result.returncode == 1
    assert "DEMOTION CANDIDATE" in result.stdout + result.stderr


def test_audit_fails_on_cross_surface_duplication(
    synthetic_plugin: Dict[str, str],
) -> None:
    Path(synthetic_plugin["RULE_MAP"]).write_text(
        """version: 1.1.0
mappings: { A01.idor: semgrep.generic.idor }
classes:
  A01.idor: { surface: prompt }
"""
    )
    result = _run(synthetic_plugin)
    assert result.returncode == 1
    assert "two surfaces" in result.stdout + result.stderr


def test_audit_fails_when_rule_surface_class_lacks_fixtures(
    synthetic_plugin: Dict[str, str],
) -> None:
    Path(synthetic_plugin["RULE_MAP"]).write_text(
        """version: 1.1.0
mappings: { A05.cors-wildcard: semgrep.generic.cors-wildcard }
classes:
  A05.cors-wildcard:
    surface: rule
    fp_rate: 0.0
    fixtures: knowledge/rule-fixtures/does-not-exist
"""
    )
    result = _run(synthetic_plugin)
    assert result.returncode == 1
    assert "positive.*" in result.stdout + result.stderr


def test_audit_fails_when_rule_surface_class_is_agent_detection_row(
    synthetic_plugin: Dict[str, str],
) -> None:
    Path(synthetic_plugin["RULE_MAP"]).write_text(
        """version: 1.1.0
mappings: { A03.sql-injection: semgrep.generic.sql-injection }
classes:
  A03.sql-injection:
    surface: rule
    fp_rate: 0.0
    fixtures: knowledge/rule-fixtures/A03.sql-injection
"""
    )
    Path(synthetic_plugin["OWASP_DOC"]).write_text(
        "# OWASP\n"
        "| Pattern | Language | Grep Signal | Category |\n"
        "| SQL concat | All | string concat in query | `A03.sql-injection` |\n"
    )
    result = _run(synthetic_plugin)
    assert result.returncode == 1
    assert "detection row" in result.stdout + result.stderr


def test_audit_fails_on_invalid_surface_value(synthetic_plugin: Dict[str, str]) -> None:
    Path(synthetic_plugin["RULE_MAP"]).write_text(
        """version: 1.1.0
mappings: { A01.idor: security-review.a01.idor }
classes:
  A01.idor: { surface: maybe }
"""
    )
    result = _run(synthetic_plugin)
    assert result.returncode == 1
    assert "invalid surface" in result.stdout + result.stderr
