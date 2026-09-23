"""Unit tests for scripts/checkpoint_abort.py (#2168).

Covers the abort decision (error/high only, first-qualifying-finding-wins,
fail-open on empty input, loud failure on malformed input),
`compute_round_outcome`'s hard "never pass on an unre-dispatched abort" rule
and its severity-floor finding filter, `merge_findings`'s dedup-and-append
contract, the fixture equivalence test proving `merge_findings` is
order-independent under a cheap/deferred split (Step 1.1's central
safety-property test), and the CLI's three `--mode` entry points.
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
            "aborted": False,
            "triggeringFinding": None,
            "triggeringAgent": None,
            "deferredLenses": [],
        }

    def test_empty_cheap_results_never_aborts(self):
        out = checkpoint_abort.decide_abort([], ["arch-review", "security-review"])
        assert out["aborted"] is False
        assert out["deferredLenses"] == []

    def test_error_severity_without_high_confidence_never_aborts(self):
        results = [_result("naming-review", _issue("error", "medium"))]
        out = checkpoint_abort.decide_abort(results, ["naming-review", "arch-review"])
        assert out["aborted"] is False

    def test_high_confidence_without_error_severity_never_aborts(self):
        results = [_result("naming-review", _issue("warning", "high"))]
        out = checkpoint_abort.decide_abort(results, ["naming-review", "arch-review"])
        assert out["aborted"] is False


class TestDecideAbortAborts:
    def test_error_high_finding_aborts_with_deferred_lenses(self):
        results = [_result("naming-review", _issue("error", "high"))]
        ordered = ["naming-review", "arch-review", "security-review"]
        out = checkpoint_abort.decide_abort(results, ordered)
        assert out["aborted"] is True
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
        assert out["aborted"] is True
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
        assert out["aborted"] is True
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

    def test_missing_agent_raises(self):
        results = [{"issues": [_issue("error", "high")]}]
        with pytest.raises(checkpoint_abort.CheckpointAbortError):
            checkpoint_abort.decide_abort(results, ["naming-review"])

    def test_empty_agent_raises(self):
        results = [{"agent": "", "issues": [_issue("error", "high")]}]
        with pytest.raises(checkpoint_abort.CheckpointAbortError):
            checkpoint_abort.decide_abort(results, ["naming-review"])


class TestComputeRoundOutcome:
    def test_aborted_and_not_redispatched_never_passes_with_no_findings(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True, redispatched=False, findings=[]
        )
        assert out["outcome"] == "blocked"
        assert out["reason"] == (
            "round aborted on a cheap-tier blocker and its deferred "
            "lenses were never re-dispatched"
        )

    def test_aborted_and_not_redispatched_never_passes_with_findings(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True,
            redispatched=False,
            findings=[_issue("error", "high")],
        )
        assert out["outcome"] == "blocked"
        assert out["reason"] == (
            "round aborted on a cheap-tier blocker and its deferred "
            "lenses were never re-dispatched"
        )

    def test_aborted_and_redispatched_computes_from_findings_empty(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True, redispatched=True, findings=[]
        )
        assert out["outcome"] == "pass"
        assert out["reason"] is None

    def test_aborted_and_redispatched_computes_from_findings_nonempty(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=True,
            redispatched=True,
            findings=[_issue("error", "high")],
        )
        assert out["outcome"] == "blocked"
        assert out["reason"] == "1 finding(s) remain"

    def test_never_aborted_computes_from_findings(self):
        out = checkpoint_abort.compute_round_outcome(
            aborted=False, redispatched=False, findings=[]
        )
        assert out["outcome"] == "pass"
        assert out["reason"] is None

    def test_only_suggestion_or_low_confidence_findings_pass(self):
        findings = [
            _issue("suggestion", "high"),
            _issue("error", "low"),
            _issue("warning", "none"),
        ]
        out = checkpoint_abort.compute_round_outcome(
            aborted=False, redispatched=False, findings=findings
        )
        assert out["outcome"] == "pass"
        assert out["reason"] is None

    def test_one_blocking_finding_among_suggestion_tier_blocks(self):
        findings = [
            _issue("suggestion", "high"),
            _issue("warning", "medium"),
        ]
        out = checkpoint_abort.compute_round_outcome(
            aborted=False, redispatched=False, findings=findings
        )
        assert out["outcome"] == "blocked"
        assert out["reason"] == "1 finding(s) remain"

    def test_differently_cased_severity_and_confidence_still_block(self):
        """Regression (backstop review, #2168): the severity floor is now
        imported from `finding_signature.is_actionable`, which lowercases
        `severity`/`confidence` before comparing — a prior local copy here
        compared case-sensitively, so a finding tagged `"Error"`/`"High"`
        (a differently-cased but semantically identical value) silently
        never blocked while `finding_signature`'s own fix loop treated it
        as fully actionable. Both modules must now agree on any casing."""
        out = checkpoint_abort.compute_round_outcome(
            aborted=False, redispatched=False, findings=[_issue("Error", "High")]
        )
        assert out["outcome"] == "blocked"
        assert out["reason"] == "1 finding(s) remain"


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


class TestMergeDedupIdentityDivergence:
    """Documents that `_finding_key`'s dedup identity is deliberately
    stricter than, and independent of, `finding_signature.py`'s round-ledger
    identity relation — mirrors `gate_retry_state.py`'s
    `test_max_rounds_matches_finding_signature`-style drift-awareness test,
    applied to a deliberately-divergent (not deliberately-matching) pair of
    constants. See the "Merge-dedup identity intentionally diverges from
    finding_signature.py" comment above `_finding_key` in checkpoint_abort.py.
    """

    def test_finding_key_uses_exact_line_and_raw_message(self):
        # finding_signature.py tolerates a +/-3 line shift and normalizes
        # the message; _finding_key does neither — two findings that would
        # be the SAME finding under finding_signature's relation must be
        # DISTINCT here, because merge_findings folds together two tiers
        # dispatched against the same unmoved diff, where an exact
        # positional key is what avoids over-merging.
        a = {
            "agent": "naming-review",
            "file": "a.py",
            "line": 10,
            "severity": "warning",
            "message": "ambiguous name 'x'",
        }
        b = dict(a, line=12, message="ambiguous name 'x' (renamed)")
        assert checkpoint_abort._finding_key(a) != checkpoint_abort._finding_key(b)


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
        assert payload["aborted"] is False

    def test_abort_prints_deferred_lenses_and_exits_zero(self):
        results = [_result("naming-review", _issue("error", "high"))]
        result = self._run(results, ["naming-review", "arch-review"], check=True)
        payload = json.loads(result.stdout)
        assert payload["aborted"] is True
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

    def test_cheap_results_from_file_happy_path(self, tmp_path):
        results = [_result("naming-review", _issue("error", "high"))]
        results_file = tmp_path / "cheap-results.json"
        results_file.write_text(json.dumps(results), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "checkpoint_abort.py"),
                "--cheap-results-from",
                str(results_file),
                "--lenses",
                "naming-review",
                "arch-review",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["aborted"] is True
        assert payload["deferredLenses"] == ["arch-review"]

    def test_cheap_results_from_nonexistent_file_exits_nonzero(self, tmp_path):
        missing = tmp_path / "does-not-exist.json"
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "checkpoint_abort.py"),
                "--cheap-results-from",
                str(missing),
                "--lenses",
                "naming-review",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "cannot read" in result.stderr.lower()


class TestCliModeOutcome:
    def _run(self, payload, check=False):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "checkpoint_abort.py"), "--mode", "outcome"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=check,
        )

    def test_happy_path_prints_outcome_json(self):
        result = self._run(
            {"aborted": False, "redispatched": False, "findings": []}, check=True
        )
        payload = json.loads(result.stdout)
        assert payload == {"outcome": "pass", "reason": None}

    def test_malformed_input_exits_nonzero_with_clear_error(self):
        result = self._run({"aborted": True, "findings": []}, check=False)
        assert result.returncode != 0
        assert "malformed" in result.stderr.lower()

    def test_from_file_happy_path(self, tmp_path):
        payload_file = tmp_path / "outcome-input.json"
        payload_file.write_text(
            json.dumps({"aborted": True, "redispatched": False, "findings": []}),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "checkpoint_abort.py"),
                "--mode",
                "outcome",
                "--from",
                str(payload_file),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["outcome"] == "blocked"

    def test_from_nonexistent_file_exits_nonzero(self, tmp_path):
        """Regression (backstop review, #2168): `--mode outcome`'s
        `--from`-file read shares `_run_abort_mode`'s exact error-handling
        shape but had no test of its own for this branch."""
        missing = tmp_path / "does-not-exist.json"
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "checkpoint_abort.py"),
                "--mode",
                "outcome",
                "--from",
                str(missing),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "cannot read" in result.stderr.lower()

    def test_invalid_json_exits_nonzero_with_clear_error(self):
        """Regression (backstop review, #2168) — same rationale as
        `test_from_nonexistent_file_exits_nonzero` above."""
        result = self._run_raw("not json")
        assert result.returncode != 0
        assert "json" in result.stderr.lower()

    def _run_raw(self, raw_input, check=False):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "checkpoint_abort.py"), "--mode", "outcome"],
            input=raw_input,
            capture_output=True,
            text=True,
            check=check,
        )


class TestCliModeMerge:
    def _run(self, payload, check=False):
        return subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "checkpoint_abort.py"), "--mode", "merge"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=check,
        )

    def test_happy_path_prints_merged_json_array(self):
        existing = [
            {
                "agent": "naming-review",
                "file": "a.py",
                "line": 1,
                "severity": "warning",
                "message": "m1",
            }
        ]
        new = [
            {
                "agent": "arch-review",
                "file": "b.py",
                "line": 2,
                "severity": "error",
                "message": "m2",
            }
        ]
        result = self._run({"existing": existing, "new": new}, check=True)
        merged = json.loads(result.stdout)
        assert merged == existing + new

    def test_malformed_input_exits_nonzero_with_clear_error(self):
        result = self._run({"existing": "not-a-list", "new": []}, check=False)
        assert result.returncode != 0
        assert "malformed" in result.stderr.lower()

    def test_from_file_happy_path(self, tmp_path):
        payload_file = tmp_path / "merge-input.json"
        payload_file.write_text(json.dumps({"existing": [], "new": []}), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "checkpoint_abort.py"),
                "--mode",
                "merge",
                "--from",
                str(payload_file),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        merged = json.loads(result.stdout)
        assert merged == []

    def test_from_nonexistent_file_exits_nonzero(self, tmp_path):
        """Regression (backstop review, #2168) — mirrors
        `TestCliModeOutcome`'s equivalent test; `--mode merge`'s `--from`
        read shares the same error-handling shape and had no test of its
        own for this branch."""
        missing = tmp_path / "does-not-exist.json"
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "checkpoint_abort.py"),
                "--mode",
                "merge",
                "--from",
                str(missing),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "cannot read" in result.stderr.lower()

    def test_invalid_json_exits_nonzero_with_clear_error(self):
        """Regression (backstop review, #2168) — same rationale as
        `test_from_nonexistent_file_exits_nonzero` above."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "checkpoint_abort.py"), "--mode", "merge"],
            input="not json",
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "json" in result.stderr.lower()
