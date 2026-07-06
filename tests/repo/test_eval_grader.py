"""Tests for scripts/eval_grade.py — the deterministic eval grader that backs
the CI agent-eval gate (issue #99). The grader is model-free: it grades
recorded agent/skill outputs ("actuals") against evals/expected/*.json
exactly. These tests pin that grading + regression-vs-baseline behavior on
a tiny self-contained corpus.

Ported from tests/repo/eval_grader_tests.bats (issue #572: bash -> Python).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADER = REPO_ROOT / "scripts" / "eval_grade.py"

EXPECTED_AR_DEMO = """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": {
    "arch-review": {
      "expectedStatus": "fail",
      "issueCount": { "min": 1, "max": 3 },
      "severities": { "error": { "min": 1, "max": 2 } },
      "mustMention": ["layer"],
      "mustNotMention": ["clean"]
    }
  }
}
"""


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "expected" / "ar-demo.json").write_text(EXPECTED_AR_DEMO)
    (tmp_path / "fixtures" / "ar-demo.ts").write_text("")
    return tmp_path


def _grade(case: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GRADER), *args],
        capture_output=True,
        text=True,
        cwd=str(case),
    )


def _write(case: Path, name: str, content: str) -> Path:
    p = case / name
    p.write_text(content)
    return p


def test_correct_actual_output_grades_pass(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{
  "ar-demo": {
    "agents": {
      "arch-review": {
        "status": "fail",
        "issues": [{ "severity": "error", "message": "domain imports infra layer" }],
        "summary": "layer violation"
      }
    }
  }
}
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_wrong_status_grades_fail_with_readable_diff(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "looks clean" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "ar-demo::arch-review" in out
    assert "status: expected 'fail', got 'pass'" in out


def test_missing_mustmention_keyword_fails(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "bad import" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "mustMention: missing 'layer'" in out


def test_mustnotmention_violation_fails(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer is clean actually" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "mustNotMention: found forbidden 'clean'" in out


def test_severity_count_out_of_range_fails(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [
    { "severity": "error", "message": "layer a" },
    { "severity": "error", "message": "layer b" },
    { "severity": "error", "message": "layer c" }
  ],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "severities.error" in out


def test_min_confidence_any_of_passes_when_one_issue_matches(case: Path) -> None:
    # issue #885: correctness-review fixtures assert at least one issue at
    # high-or-medium confidence, without pinning an exact per-confidence count.
    _write(
        case,
        "expected/ar-demo.json",
        """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": {
    "arch-review": {
      "expectedStatus": "fail",
      "minConfidenceAnyOf": ["high", "medium"]
    }
  }
}
""",
    )
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "confidence": "high", "message": "layer violation" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_min_confidence_any_of_fails_when_no_issue_matches(case: Path) -> None:
    _write(
        case,
        "expected/ar-demo.json",
        """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": {
    "arch-review": {
      "expectedStatus": "fail",
      "minConfidenceAnyOf": ["high", "medium"]
    }
  }
}
""",
    )
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "confidence": "none", "message": "layer violation" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "minConfidenceAnyOf" in out


def test_baseline_isolates_regressions(case: Path) -> None:
    """Baseline says arch-review WAS passing; a new failure is a [REGRESSION]."""
    (case / "baseline.json").write_text('{ "passing": ["ar-demo::arch-review"] }')
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--baseline",
        str(case / "baseline.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "[REGRESSION]" in out


def test_failure_not_in_baseline_does_not_block(case: Path) -> None:
    (case / "baseline.json").write_text('{ "passing": [] }')
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--baseline",
        str(case / "baseline.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "No regressions against baseline." in out


def test_only_scopes_grading_to_named_agent(case: Path) -> None:
    (case / "expected" / "nm-demo.json").write_text(
        """{ "fixture": "nm-demo.ts", "applicableAgents": ["naming-review"],
  "agents": { "naming-review": { "expectedStatus": "fail" } } }
"""
    )
    (case / "fixtures" / "nm-demo.ts").write_text("")
    _write(
        case,
        "actuals.json",
        """{
  "ar-demo": { "agents": { "arch-review": {
    "status": "fail",
    "issues": [{ "severity": "error", "message": "layer violation" }],
    "summary": "" } } },
  "nm-demo": { "agents": { "naming-review": { "status": "pass", "issues": [], "summary": "" } } }
}
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--only",
        "arch-review",
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "diff-scoped to: arch-review" in out
    assert "nm-demo::naming-review" not in out


def test_empty_only_grades_everything(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer violation" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--only",
        "",
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_write_baseline_records_passing_pairs(case: Path) -> None:
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer violation" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--write-baseline",
        str(case / "baseline.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert (case / "baseline.json").is_file()
    data = json.loads((case / "baseline.json").read_text())
    assert data["passing"][0] == "ar-demo::arch-review"
    # a measured run stamps provenance=measured (#133)
    assert data["provenance"] == "measured"


def test_shipped_baseline_declares_provenance() -> None:
    """Provenance must be honestly DECLARED — 'hand-authored' or 'measured' (#133)."""
    baseline = json.loads((REPO_ROOT / "evals" / "baseline.json").read_text())
    assert baseline["provenance"] in ("hand-authored", "measured"), (
        f"unexpected provenance: {baseline.get('provenance')}"
    )


def test_write_baseline_merges_untested_pairs(case: Path) -> None:
    """Pre-existing baseline has a pair this run never touches; it must survive."""
    (case / "baseline.json").write_text('{ "passing": ["other-demo::naming-review"] }')
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "layer violation" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--only",
        "arch-review",
        "--write-baseline",
        str(case / "baseline.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "baseline.json").read_text())
    assert data["passing"] == ["ar-demo::arch-review", "other-demo::naming-review"]


def test_write_baseline_drops_now_failing_pair(case: Path) -> None:
    (case / "baseline.json").write_text(
        '{ "passing": ["ar-demo::arch-review","keep::naming-review"] }'
    )
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "pass", "issues": [], "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
        "--only",
        "arch-review",
        "--write-baseline",
        str(case / "baseline.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "baseline.json").read_text())
    # arch-review failed this run -> removed; keep::naming-review untouched.
    assert data["passing"] == ["keep::naming-review"]


def test_check_corpus_passes_on_wellformed(case: Path) -> None:
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Eval corpus OK" in out


def test_check_corpus_fails_on_invalid_json(case: Path) -> None:
    (case / "expected" / "broken.json").write_text("{ not json\n")
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, out
    assert "invalid JSON" in out


def test_check_corpus_flags_applicableagents_drift(case: Path) -> None:
    (case / "expected" / "drift.json").write_text(
        """{
  "fixture": "drift.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "naming-review": { "expectedStatus": "pass" } }
}
"""
    )
    (case / "fixtures" / "drift.ts").write_text("")
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, out
    assert "not in applicableAgents" in out


# --- Pluggable grader registry (#309) ---------------------------------------


def test_registry_explicit_verdict_grader(case: Path) -> None:
    (case / "expected" / "ar-demo.json").write_text(
        """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": {
    "arch-review": {
      "grader": "verdict",
      "expectedStatus": "fail",
      "mustMention": ["layer"]
    }
  }
}
"""
    )
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "domain imports infra layer" }],
  "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_registry_unknown_grader_fails_grading(case: Path) -> None:
    (case / "expected" / "ar-demo.json").write_text(
        """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "arch-review": { "grader": "made-up", "expectedStatus": "fail" } }
}
"""
    )
    _write(
        case,
        "actuals.json",
        """{ "ar-demo": { "agents": { "arch-review": {
  "status": "fail", "issues": [], "summary": "" } } } }
""",
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "unknown grader 'made-up'" in out


def test_registry_check_corpus_rejects_unknown_grader(case: Path) -> None:
    (case / "expected" / "ar-demo.json").write_text(
        """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "arch-review": { "grader": "nope", "expectedStatus": "fail" } }
}
"""
    )
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, out
    assert "unknown grader 'nope'" in out


def test_registry_check_corpus_accepts_registered_grader(case: Path) -> None:
    (case / "expected" / "ar-demo.json").write_text(
        """{
  "fixture": "ar-demo.ts",
  "applicableAgents": ["arch-review"],
  "agents": { "arch-review": { "grader": "verdict", "expectedStatus": "fail" } }
}
"""
    )
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Eval corpus OK" in out
