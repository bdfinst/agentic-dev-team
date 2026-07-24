"""Unit tests for the #821 benchmark harness's hit/miss/noise scorer."""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

import scorer

_HUNK = {"file": "src/a.js", "start_line": 10, "end_line": 12}


def test_hit_exact_line() -> None:
    result = scorer.score([_HUNK], [{"file": "src/a.js", "line": 11}])
    assert result["hit"] is True
    assert len(result["matched"]) == 1
    assert result["unmatched"] == []


def test_hit_within_default_tolerance() -> None:
    # tolerance=3, hunk is 10-12, so line 15 (12+3) is within range, 16 is not.
    assert scorer.score([_HUNK], [{"file": "src/a.js", "line": 15}])["hit"] is True
    assert scorer.score([_HUNK], [{"file": "src/a.js", "line": 16}])["hit"] is False


def test_miss_wrong_file() -> None:
    result = scorer.score([_HUNK], [{"file": "src/other.js", "line": 11}])
    assert result["hit"] is False
    assert len(result["unmatched"]) == 1


def test_miss_no_findings() -> None:
    result = scorer.score([_HUNK], [])
    assert result["hit"] is False
    assert result["matched"] == []
    assert result["unmatched"] == []


def test_unmatched_findings_are_noise_not_false_positives() -> None:
    findings = [
        {"file": "src/a.js", "line": 11},  # matches
        {"file": "src/b.js", "line": 3},  # unrelated real finding
        {"file": "src/c.js", "line": 99},  # unrelated real finding
    ]
    result = scorer.score([_HUNK], findings)
    assert result["hit"] is True
    assert len(result["matched"]) == 1
    assert len(result["unmatched"]) == 2


def test_tolerance_is_configurable() -> None:
    findings = [{"file": "src/a.js", "line": 20}]
    assert scorer.score([_HUNK], findings, tolerance=0)["hit"] is False
    assert scorer.score([_HUNK], findings, tolerance=8)["hit"] is True


def test_finding_missing_line_never_matches() -> None:
    result = scorer.score([_HUNK], [{"file": "src/a.js", "line": None}])
    assert result["hit"] is False


def test_path_normalization_ignores_leading_dot_slash() -> None:
    result = scorer.score([_HUNK], [{"file": "./src/a.js", "line": 11}])
    assert result["hit"] is True
