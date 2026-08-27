"""Unit tests for skills/harness-audit/scripts/redundancy_criterion.py (#1983 Part 2).

Proves the subset-redundancy criterion — "this lens's applied findings are a
subset of what an integrated deterministic tool reported for the same
rounds" — is a real, computable comparison, using synthetic fixture data:

  - a redundant lens: every finding it ever applies is one a pre-pass tool
    (lizard/jscpd-shaped envelope) already reported for that round.
  - a non-redundant lens: at least one round it finds something the
    pre-pass tool did not.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0, str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "harness-audit" / "scripts")
)

import redundancy_criterion as rc

# ---------------------------------------------------------------------------
# is_round_redundant — single-round unit coverage
# ---------------------------------------------------------------------------


def test_round_with_no_applied_findings_is_undefined_not_redundant() -> None:
    """A quiet round proves nothing about redundancy either way."""
    assert rc.is_round_redundant([], [{"file": "a.py", "line": 10}]) is None


def test_round_fully_covered_by_pretool_is_redundant() -> None:
    applied = [{"file": "a.py", "line": 10}, {"file": "a.py", "line": 42}]
    pretool = [
        {"file": "a.py", "line": 11, "rule_id": "lizard.complexity.cyclomatic"},
        {"file": "a.py", "line": 40, "rule_id": "jscpd.duplication.clone"},
    ]
    assert rc.is_round_redundant(applied, pretool, tolerance=3) is True


def test_round_with_uncovered_finding_is_not_redundant() -> None:
    applied = [{"file": "a.py", "line": 10}, {"file": "b.py", "line": 99}]
    pretool = [{"file": "a.py", "line": 11, "rule_id": "lizard.complexity.cyclomatic"}]
    # b.py:99 has no matching pretool finding at all.
    assert rc.is_round_redundant(applied, pretool, tolerance=3) is False


def test_round_finding_outside_tolerance_is_not_covered() -> None:
    applied = [{"file": "a.py", "line": 10}]
    pretool = [{"file": "a.py", "line": 20}]  # 10 lines away, tolerance=3
    assert rc.is_round_redundant(applied, pretool, tolerance=3) is False


def test_round_finding_missing_line_is_never_covered() -> None:
    applied = [{"file": "a.py", "line": None}]
    pretool = [{"file": "a.py", "line": 10}]
    assert rc.is_round_redundant(applied, pretool) is False


# ---------------------------------------------------------------------------
# classify_lens_redundancy — aggregate verdicts, the acceptance-criterion proof
# ---------------------------------------------------------------------------


def _redundant_round(n: int) -> dict:
    """A round where the lens found exactly what the pre-pass tool already
    flagged (same file, line within tolerance)."""
    return {
        "applied_findings": [{"file": f"mod_{n}.py", "line": 10}],
        "pretool_findings": [
            {
                "file": f"mod_{n}.py",
                "line": 11,
                "rule_id": "lizard.complexity.cyclomatic",
                "metadata": {"source": "lizard"},
            }
        ],
    }


def test_classify_redundant_lens_all_findings_subsumed() -> None:
    """The redundant-lens proof: `complexity-review`-shaped rounds where
    every applied finding matches a lizard pre-pass finding."""
    rounds = [_redundant_round(i) for i in range(6)]  # >= DEFAULT_MIN_ROUNDS
    result = rc.classify_lens_redundancy(rounds)
    assert result["verdict"] == "redundant-candidate"
    assert result["rounds_with_findings"] == 6
    assert result["rounds_fully_subsumed"] == 6
    assert result["rounds_no_op"] == 0


def test_classify_non_redundant_lens_found_something_the_tool_missed() -> None:
    """The non-redundant-lens proof: mostly-subsumed rounds, but one round
    the lens caught a real issue (a semantic bug, say) with no pre-pass
    counterpart at all."""
    rounds = [_redundant_round(i) for i in range(5)]
    rounds.append(
        {
            "applied_findings": [{"file": "auth.py", "line": 88}],
            "pretool_findings": [],  # nothing from the deterministic pre-pass
        }
    )
    result = rc.classify_lens_redundancy(rounds)
    assert result["verdict"] == "not-redundant"
    assert result["rounds_with_findings"] == 6
    assert result["rounds_fully_subsumed"] == 5


def test_classify_below_min_rounds_is_insufficient_data() -> None:
    """Small-N honesty: fewer than `min_rounds` judged rounds never yields a
    redundancy verdict either way — mirrors Step 4's own N>=5 floor."""
    rounds = [_redundant_round(i) for i in range(3)]
    result = rc.classify_lens_redundancy(rounds, min_rounds=5)
    assert result["verdict"] == "insufficient-data"
    assert result["rounds_with_findings"] == 3


def test_classify_no_op_rounds_are_excluded_from_the_judged_count() -> None:
    """A lens that mostly no-ops, but is redundant on every round it DID
    find something, still reaches a verdict — no-op rounds don't count
    against or for it, they're simply excluded."""
    rounds = [_redundant_round(i) for i in range(5)]
    rounds.extend(
        {"applied_findings": [], "pretool_findings": [{"file": "x.py", "line": 1}]}
        for _ in range(10)
    )
    result = rc.classify_lens_redundancy(rounds)
    assert result["rounds_total"] == 15
    assert result["rounds_with_findings"] == 5
    assert result["rounds_no_op"] == 10
    assert result["verdict"] == "redundant-candidate"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_reads_rounds_file_and_prints_json(tmp_path, capsys) -> None:
    import json as json_module

    rounds_path = tmp_path / "rounds.json"
    rounds_path.write_text(
        json_module.dumps([_redundant_round(i) for i in range(6)]), encoding="utf-8"
    )
    exit_code = rc.main(["--rounds", str(rounds_path)])
    assert exit_code == 0
    out = json_module.loads(capsys.readouterr().out)
    assert out["verdict"] == "redundant-candidate"


def test_cli_missing_file_fails_loudly(tmp_path, capsys) -> None:
    exit_code = rc.main(["--rounds", str(tmp_path / "does-not-exist.json")])
    assert exit_code == 1
    assert "cannot read" in capsys.readouterr().err
