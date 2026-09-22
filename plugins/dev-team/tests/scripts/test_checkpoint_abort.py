"""Unit tests for scripts/checkpoint_abort.py (#2168).

Covers the abort decision (error/high only, first-qualifying-finding-wins,
fail-open on empty input, loud failure on malformed input),
`compute_round_outcome`'s hard "never pass on an unre-dispatched abort" rule,
`merge_findings`'s dedup-and-append contract, and the fixture equivalence
test proving `merge_findings` is order-independent under a cheap/deferred
split (Step 1.1's central safety-property test).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import checkpoint_abort


def _issue(severity="error", confidence="high", **extra):
    return {"severity": severity, "confidence": confidence, **extra}


def _result(agent, *issues):
    return {"agent": agent, "issues": list(issues)}


class TestDecideAbortNoAbort:
    def test_clean_results_do_not_abort(self):
        results = [_result("naming-review", _issue("warning", "medium"))]
        out = checkpoint_abort.decide_abort(results, ["naming-review", "arch-review"])
        assert out == {
            "abort": False,
            "triggeringFinding": None,
            "triggeringAgent": None,
            "deferredLenses": [],
        }

    def test_empty_cheap_results_never_aborts(self):
        out = checkpoint_abort.decide_abort([], ["arch-review", "security-review"])
        assert out["abort"] is False
        assert out["deferredLenses"] == []

    def test_error_severity_without_high_confidence_never_aborts(self):
        results = [_result("naming-review", _issue("error", "medium"))]
        out = checkpoint_abort.decide_abort(results, ["naming-review", "arch-review"])
        assert out["abort"] is False

    def test_high_confidence_without_error_severity_never_aborts(self):
        results = [_result("naming-review", _issue("warning", "high"))]
        out = checkpoint_abort.decide_abort(results, ["naming-review", "arch-review"])
        assert out["abort"] is False


class TestDecideAbortAborts:
    def test_error_high_finding_aborts_with_deferred_lenses(self):
        results = [_result("naming-review", _issue("error", "high"))]
        ordered = ["naming-review", "arch-review", "security-review"]
        out = checkpoint_abort.decide_abort(results, ordered)
        assert out["abort"] is True
        assert out["triggeringFinding"] == _issue("error", "high")
        assert out["triggeringAgent"] == "naming-review"
        assert out["deferredLenses"] == ["arch-review", "security-review"]

    def test_first_qualifying_finding_in_lens_dispatch_order_wins(self):
        results = [
            _result("naming-review", _issue("error", "high", message="first")),
            _result("doc-review", _issue("error", "high", message="second")),
        ]
        ordered = ["naming-review", "doc-review", "arch-review"]
        out = checkpoint_abort.decide_abort(results, ordered)
        assert out["abort"] is True
        assert out["triggeringAgent"] == "naming-review"
        assert out["triggeringFinding"]["message"] == "first"
        # Both cheap-tier agents already ran; only the un-run lens defers.
        assert out["deferredLenses"] == ["arch-review"]

    def test_second_issue_in_a_lens_own_issue_list_can_trigger(self):
        results = [
            _result(
                "naming-review",
                _issue("warning", "high"),
                _issue("error", "high", message="second issue"),
            ),
        ]
        out = checkpoint_abort.decide_abort(results, ["naming-review", "arch-review"])
        assert out["abort"] is True
        assert out["triggeringFinding"]["message"] == "second issue"


class TestDecideAbortMalformedInput:
    def test_missing_severity_raises(self):
        results = [_result("naming-review", {"confidence": "high"})]
        with pytest.raises(checkpoint_abort.CheckpointAbortError):
            checkpoint_abort.decide_abort(results, ["naming-review"])

    def test_missing_confidence_raises(self):
        results = [_result("naming-review", {"severity": "error"})]
        with pytest.raises(checkpoint_abort.CheckpointAbortError):
            checkpoint_abort.decide_abort(results, ["naming-review"])

    def test_non_list_issues_raises(self):
        results = [{"agent": "naming-review", "issues": "not-a-list"}]
        with pytest.raises(checkpoint_abort.CheckpointAbortError):
            checkpoint_abort.decide_abort(results, ["naming-review"])

    def test_non_list_top_level_raises(self):
        with pytest.raises(checkpoint_abort.CheckpointAbortError):
            checkpoint_abort.decide_abort({"not": "a list"}, ["naming-review"])


class TestComputeRoundOutcome:
    def test_aborted_and_not_redispatched_never_passes_with_no_findings(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True, redispatched=False, findings=[]
        )
        assert out["outcome"] == "blocked"

    def test_aborted_and_not_redispatched_never_passes_with_findings(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True, redispatched=False, findings=[{"severity": "error"}]
        )
        assert out["outcome"] == "blocked"

    def test_aborted_and_redispatched_computes_from_findings_empty(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True, redispatched=True, findings=[]
        )
        assert out["outcome"] == "pass"

    def test_aborted_and_redispatched_computes_from_findings_nonempty(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True, redispatched=True, findings=[{"severity": "error"}]
        )
        assert out["outcome"] == "blocked"

    def test_never_aborted_computes_from_findings(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=False, redispatched=False, findings=[]
        )
        assert out["outcome"] == "pass"


class TestMergeFindings:
    def _finding(self, **kw):
        base = {
            "agent": "naming-review",
            "file": "a.py",
            "line": 1,
            "severity": "warning",
            "message": "m",
        }
        base.update(kw)
        return base

    def test_disjoint_lists_concatenate_in_order(self):
        existing = [self._finding(line=1), self._finding(line=2)]
        new = [self._finding(line=3), self._finding(line=4)]
        merged = checkpoint_abort.merge_findings(existing, new)
        assert merged == existing + new

    def test_overlapping_lists_dedupe(self):
        dup = self._finding(line=1)
        existing = [dup]
        new = [dup, self._finding(line=2)]
        merged = checkpoint_abort.merge_findings(existing, new)
        assert merged == [dup, self._finding(line=2)]

    def test_empty_existing_returns_new_unchanged(self):
        new = [self._finding(line=1), self._finding(line=2)]
        merged = checkpoint_abort.merge_findings([], new)
        assert merged == new

    def test_does_not_mutate_arguments(self):
        existing = [self._finding(line=1)]
        new = [self._finding(line=2)]
        existing_copy, new_copy = list(existing), list(new)
        checkpoint_abort.merge_findings(existing, new)
        assert existing == existing_copy
        assert new == new_copy


class TestFixtureEquivalence:
    """Proves `merge_findings` is order-independent under a cheap/deferred
    split — checkpoint_abort.py's only production aggregation logic. Whether
    /build's live runtime actually invokes merge_findings correctly is
    verified separately by Step 1.2's content-guard test, not here."""

    @staticmethod
    def _as_set(findings):
        return {json.dumps(f, sort_keys=True) for f in findings}

    def test_cheap_then_deferred_merge_is_set_equal_to_one_shot_merge(self):
        cheap_findings = [
            {
                "agent": "naming-review",
                "file": "src/a.py",
                "line": 10,
                "severity": "warning",
                "message": "ambiguous name",
            },
            {
                "agent": "naming-review",
                "file": "src/b.py",
                "line": 3,
                "severity": "error",
                "message": "shadowed import",
            },
        ]
        deferred_findings = [
            {
                "agent": "arch-review",
                "file": "src/c.py",
                "line": 42,
                "severity": "warning",
                "message": "layering violation",
            },
            # Same key as a cheap-tier finding — proves dedup behaves
            # identically whether it happens in one call or split in two.
            {
                "agent": "naming-review",
                "file": "src/a.py",
                "line": 10,
                "severity": "warning",
                "message": "ambiguous name",
            },
        ]

        # Path A: one call, simulating a single non-aborted dispatch.
        path_a = checkpoint_abort.merge_findings(
            [], cheap_findings + deferred_findings
        )
        # Path B: two calls, simulating cheap-tier-then-deferred-tier.
        path_b = checkpoint_abort.merge_findings(
            checkpoint_abort.merge_findings([], cheap_findings), deferred_findings
        )

        assert self._as_set(path_a) == self._as_set(path_b)
        # Both paths should have deduped the shared-key finding to one copy.
        assert len(path_a) == 3
        assert len(path_b) == 3


class TestCli:
    def _run(self, cheap_results, lenses, check=False):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "checkpoint_abort.py"), "--lenses", *lenses],
            input=json.dumps(cheap_results),
            capture_output=True,
            text=True,
            check=check,
        )

    def test_no_abort_prints_json_and_exits_zero(self):
        result = self._run([], ["naming-review"], check=True)
        payload = json.loads(result.stdout)
        assert payload["abort"] is False

    def test_abort_prints_deferred_lenses_and_exits_zero(self):
        results = [_result("naming-review", _issue("error", "high"))]
        result = self._run(results, ["naming-review", "arch-review"], check=True)
        payload = json.loads(result.stdout)
        assert payload["abort"] is True
        assert payload["deferredLenses"] == ["arch-review"]

    def test_malformed_input_exits_nonzero_with_clear_error(self):
        results = [_result("naming-review", {"severity": "error"})]
        result = self._run(results, ["naming-review"], check=False)
        assert result.returncode != 0
        assert "malformed" in result.stderr.lower()

    def test_invalid_json_exits_nonzero_with_clear_error(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "checkpoint_abort.py"), "--lenses", "x"],
            input="not json",
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "json" in result.stderr.lower()
