"""Tests for the agent-readiness scanner MVP (issue #117).

File-presence/heuristic scoring of a single local repo against the
Agent-Readiness Scorecard, with weights/thresholds externalized to YAML.

Ported from tests/repo/agent_readiness_tests.bats (#673).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = (
    REPO_ROOT / "plugins" / "dev-team" / "skills" / "agent-readiness" / "scanner.py"
)
FIX = REPO_ROOT / "tests" / "fixtures" / "agent-readiness"


def _run_scanner(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCANNER), *args],
        capture_output=True,
        text=True,
    )


def test_scanner_minimal_repo_scores_agent_hostile(tmp_path: Path) -> None:
    out = tmp_path / "min.json"
    result = _run_scanner(str(FIX / "repo_minimal"), "--json", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(out.read_text())
    assert data["tier"] == "Agent-Hostile"


def test_scanner_well_configured_repo_scores_agent_ready_all_criteria_2(
    tmp_path: Path,
) -> None:
    out = tmp_path / "wc.json"
    result = _run_scanner(str(FIX / "repo_well_configured"), "--json", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(out.read_text())
    assert data["tier"] == "Agent-Ready"
    scores = sorted(
        {
            crit["score"]
            for cat in data["categories"].values()
            for crit in (cat.get("criteria") or {}).values()
            if "score" in crit
        }
    )
    assert scores == [2]


def test_scanner_per_criterion_evidence_strings_are_present(tmp_path: Path) -> None:
    out = tmp_path / "wc.json"
    _run_scanner(str(FIX / "repo_well_configured"), "--json", str(out))
    data = json.loads(out.read_text())
    evidence = data["categories"]["documentation"]["criteria"]["D1_readme"]["evidence"]
    assert "README" in evidence


def test_scanner_deferred_categories_are_reported_not_scored(tmp_path: Path) -> None:
    out = tmp_path / "min.json"
    _run_scanner(str(FIX / "repo_minimal"), "--json", str(out))
    data = json.loads(out.read_text())
    assert data["categories"]["test_infrastructure"]["scored"] is False
    assert data["categories"]["type_safety"]["scored"] is False


def test_scanner_b3_detects_committed_vs_gitignored_lock_file(tmp_path: Path) -> None:
    d = tmp_path / "gi"
    d.mkdir()
    (d / "package-lock.json").write_text("{}\n")
    (d / ".gitignore").write_text("package-lock.json\n")
    out = d / "r.json"
    _run_scanner(str(d), "--json", str(out))
    data = json.loads(out.read_text())
    assert (
        data["categories"]["build_env"]["criteria"]["B3_dependency_management"]["score"]
        == 1
    )


def test_scanner_acceptance_scoring_this_repo_yields_full_report(
    tmp_path: Path,
) -> None:
    json_out = tmp_path / "self.json"
    md_out = tmp_path / "self.md"
    result = _run_scanner(
        str(REPO_ROOT), "--json", str(json_out), "--markdown", str(md_out)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(json_out.read_text())
    assert isinstance(data["overall_score"], (int, float))
    assert isinstance(data["manual_review_flags"], list)
    assert "Agent-Readiness Report" in md_out.read_text()


def test_scanner_thresholds_are_externalized(tmp_path: Path) -> None:
    # A custom config that makes every tier threshold 0 forces Agent-Ready.
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        """version: "test"
weights: { documentation: 1.0 }
tiers: { agent_ready: 0, agent_assisted: 0, agent_limited: 0 }
criteria:
  documentation:
    D1_readme: { mvp: true }
thresholds: { readme_min_words: 200, ai_instructions_min_words: 100,
              file_size_p90_small: 300, file_size_p90_large: 500 }
source_extensions: [".py"]
exclude_dirs: [".git"]
"""
    )
    out = tmp_path / "r.json"
    _run_scanner(str(FIX / "repo_minimal"), "--config", str(cfg), "--json", str(out))
    data = json.loads(out.read_text())
    assert data["tier"] == "Agent-Ready"
