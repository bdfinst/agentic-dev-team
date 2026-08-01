"""Unit tests for skills/code-review/scripts/finding_signature.py (#1625).

The three acceptance criteria from the issue, directly:
  - same finding re-reported after an unrelated fix -> same signature
  - a genuinely new finding in the fix's blast radius -> new signature
  - a message differing only in line number/identifier -> same signature

plus the three termination rules (severity floor, loop-until-dry, round cap).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import finding_signature as fs


def _f(**kw):
    base = {
        "agent": "correctness-review",
        "file": "src/cache.js",
        "line": 42,
        "rule": "missing-guard",
        "severity": "error",
        "confidence": "high",
        "message": "Cache.get returns undefined when the key is absent",
    }
    base.update(kw)
    return base


class TestSignatureStability:
    def test_same_finding_after_an_unrelated_fix_keeps_its_signature(self):
        # An unrelated fix elsewhere in the file shifts this finding by 2
        # lines and nothing else changes.
        before = fs.finding_key(_f(line=42))
        after = fs.finding_key(_f(line=44))
        assert before.signature == after.signature
        assert fs.same_finding(before, after)

    def test_message_differing_only_in_line_number_is_the_same_finding(self):
        a = _f(message="Unhandled branch at src/cache.js:42:7")
        b = _f(message="Unhandled branch at src/cache.js:118:3")
        assert fs.signature(a) == fs.signature(b)

    def test_message_differing_only_in_a_renamed_identifier_is_the_same_finding(self):
        a = _f(message="`getEntry` mutates its parameter")
        b = _f(message="`readEntry` mutates its parameter")
        assert fs.signature(a) == fs.signature(b)

    def test_message_differing_only_in_a_timestamp_or_sha_is_the_same_finding(self):
        a = _f(message="Introduced in 1a2b3c4d5e at 2026-07-31T12:06:43Z")
        b = _f(message="Introduced in 9f8e7d6c5b at 2026-07-30T22:31:53Z")
        assert fs.signature(a) == fs.signature(b)

    def test_genuinely_new_finding_in_the_fix_blast_radius_gets_a_new_signature(self):
        original = fs.finding_key(_f(line=42))
        # Same file, same agent, adjacent line — but a different defect.
        introduced = fs.finding_key(
            _f(line=43, rule="unused-binding", message="`store` is assigned but never read")
        )
        assert original.signature != introduced.signature
        assert not fs.same_finding(original, introduced)

    def test_different_agents_reporting_the_same_text_are_distinct_findings(self):
        assert fs.signature(_f(agent="structure-review")) != fs.signature(
            _f(agent="correctness-review")
        )

    def test_different_files_are_distinct_findings(self):
        assert fs.signature(_f(file="src/a.js")) != fs.signature(_f(file="src/b.js"))

    def test_category_alone_is_read_the_same_way_rule_is(self):
        # `category` is the canonical taxonomy field (#1639); a finding that
        # only sets `category` (no `rule` at all) must hash identically to
        # the equivalent `rule=`-only finding — the two are the same field
        # under different names, not two independent pieces of identity.
        del_rule = _f()
        del del_rule["rule"]
        with_category = {**del_rule, "category": "missing-guard"}
        assert fs.signature(with_category) == fs.signature(_f(rule="missing-guard"))

    def test_category_takes_priority_over_rule_when_both_are_present(self):
        # #1639 settled `category` as canonical; `rule`/`ruleId` are legacy
        # fallbacks only. When a finding somehow carries both (a producer
        # migrating, or an external tool), `category` must win — pinning the
        # fallback order `signature()` actually implements, not just the
        # order that happens to produce the same result when only one field
        # is set (the common case every other test in this class exercises).
        a = _f(category="unmet-criterion", rule="missing-guard")
        b = _f(category="unmet-criterion", rule="something-else-entirely")
        assert fs.signature(a) == fs.signature(b)

        different_category = _f(category="different-category", rule="missing-guard")
        assert fs.signature(a) != fs.signature(different_category)

    def test_rule_id_is_used_only_when_category_and_rule_are_both_absent(self):
        # Unlike test_category_takes_priority_over_rule_when_both_are_present
        # above, this does NOT exercise the category-vs-rule ordering —
        # both are absent here, so it only pins ruleId's own terminal-
        # fallback role (true before and after #1639's reorder).
        del_rule = _f()
        del del_rule["rule"]
        rule_id_only = {**del_rule, "ruleId": "missing-guard"}
        assert fs.signature(rule_id_only) == fs.signature(_f(rule="missing-guard"))

    def test_leading_dot_slash_does_not_change_the_signature(self):
        assert fs.signature(_f(file="./src/cache.js")) == fs.signature(_f(file="src/cache.js"))

    def test_agent_name_key_alias_is_accepted(self):
        del_agent = _f()
        del del_agent["agent"]
        del_agent["agentName"] = "correctness-review"
        assert fs.signature(del_agent) == fs.signature(_f())


class TestLineTolerance:
    @pytest.mark.parametrize("delta", [0, 1, 3, -3])
    def test_within_tolerance_is_the_same_finding(self, delta):
        assert fs.same_finding(fs.finding_key(_f(line=42)), fs.finding_key(_f(line=42 + delta)))

    @pytest.mark.parametrize("delta", [4, -4, 40])
    def test_beyond_tolerance_is_treated_as_new(self, delta):
        assert not fs.same_finding(fs.finding_key(_f(line=42)), fs.finding_key(_f(line=42 + delta)))

    def test_a_pair_straddling_a_bucket_boundary_still_matches(self):
        # The reason the line is not hashed into a bucket: lines 6 and 7 are
        # 1 apart and must never read as two distinct findings.
        assert fs.same_finding(fs.finding_key(_f(line=6)), fs.finding_key(_f(line=7)))

    @pytest.mark.parametrize("line", [None, "42", -1, True])
    def test_unusable_lines_normalize_to_zero_and_still_compare(self, line):
        key = fs.finding_key(_f(line=line))
        assert key.line == 0
        assert fs.same_finding(key, fs.finding_key(_f(line=line)))


class TestSeverityFloor:
    @pytest.mark.parametrize(
        ("severity", "confidence", "expected"),
        [
            ("error", "high", True),
            ("error", "medium", True),
            ("warning", "high", True),
            ("warning", "medium", True),
            ("suggestion", "high", False),
            ("error", "none", False),
            ("warning", "low", False),
            ("suggestion", "none", False),
        ],
    )
    def test_only_error_warning_at_high_medium_confidence_justifies_a_round(
        self, severity, confidence, expected
    ):
        assert fs.is_actionable(_f(severity=severity, confidence=confidence)) is expected


class TestClassifyRound:
    def test_first_round_findings_are_all_new(self):
        result = fs.classify_round([_f()], [], round_number=1)
        assert len(result["new"]) == 1
        assert result["carried"] == []
        assert result["terminate"] is False

    def test_repeat_of_a_prior_finding_is_carried_not_new(self):
        first = fs.classify_round([_f()], [], round_number=1)
        second = fs.classify_round([_f(line=44)], first["all_keys"], round_number=2)
        assert second["new"] == []
        assert len(second["carried"]) == 1

    def test_loop_until_dry_terminates_when_no_new_actionable_findings(self):
        first = fs.classify_round([_f()], [], round_number=1)
        second = fs.classify_round([], first["all_keys"], round_number=2)
        assert second["terminate"] is True
        assert second["reason"] == "converged"

    def test_a_wording_nit_only_round_does_not_trigger_another_round(self):
        """#1619's round 5 existed to chase a wording nit. Under the severity
        floor that round converges instead of re-dispatching."""
        first = fs.classify_round([_f()], [], round_number=1)
        nit = _f(
            line=200,
            rule="wording",
            severity="suggestion",
            confidence="high",
            message="attributes a V8-specific error message to the spec",
        )
        second = fs.classify_round([nit], first["all_keys"], round_number=2)
        assert len(second["new"]) == 1, "the nit is still recorded"
        assert second["actionable_new"] == [], "but it does not clear the severity floor"
        assert second["terminate"] is True
        assert second["reason"] == "converged"

    def test_a_new_error_finding_does_trigger_another_round(self):
        first = fs.classify_round([_f()], [], round_number=1)
        introduced = _f(line=90, rule="unused-binding", message="`store` assigned but never read")
        second = fs.classify_round([introduced], first["all_keys"], round_number=2)
        assert len(second["actionable_new"]) == 1
        assert second["terminate"] is False
        assert second["reason"] is None

    def test_hard_round_cap_escalates_regardless_of_findings(self):
        result = fs.classify_round([_f(line=500, rule="other")], [], round_number=fs.MAX_ROUNDS)
        assert result["terminate"] is True
        assert result["reason"] == "round-cap"

    def test_round_cap_would_have_surfaced_1619_churn_at_round_four(self):
        # #1619 ran 9 rounds. With the cap, a human sees the ledger at 4.
        keys = []
        rounds = []
        for n in range(1, 10):
            result = fs.classify_round(
                [_f(line=n * 50, rule=f"rule-{n}")], keys, round_number=n
            )
            keys = result["all_keys"]
            rounds.append(result)
            if result["terminate"]:
                break
        assert len(rounds) == fs.MAX_ROUNDS
        assert rounds[-1]["reason"] == "round-cap"

    def test_all_keys_accumulates_without_duplicating_carried_findings(self):
        first = fs.classify_round([_f()], [], round_number=1)
        second = fs.classify_round([_f(line=43)], first["all_keys"], round_number=2)
        assert len(second["all_keys"]) == 1

    def test_non_dict_entries_are_ignored(self):
        result = fs.classify_round(["oops", None, _f()], [], round_number=1)
        assert len(result["new"]) == 1


class TestCli:
    def test_cli_writes_and_reuses_durable_round_state(self, tmp_path):
        state = tmp_path / "review-round-state.json"
        findings = tmp_path / "r1.json"
        findings.write_text(json.dumps([_f()]), encoding="utf-8")

        first = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "finding_signature.py"),
                "--round",
                "1",
                "--findings",
                str(findings),
                "--state",
                str(state),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(first.stdout)["new"] == 1
        assert state.is_file()

        # Round 2 re-reports the same finding, shifted by 2 lines.
        findings2 = tmp_path / "r2.json"
        findings2.write_text(json.dumps([_f(line=44)]), encoding="utf-8")
        second = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "finding_signature.py"),
                "--round",
                "2",
                "--findings",
                str(findings2),
                "--state",
                str(state),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(second.stdout)
        assert payload["new"] == 0
        assert payload["carried"] == 1
        assert payload["terminate"] is True
        assert payload["reason"] == "converged"

        ledger = json.loads(state.read_text(encoding="utf-8"))
        assert [r["round"] for r in ledger["rounds"]] == [1, 2]

    def test_cli_accepts_findings_on_stdin(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "finding_signature.py"), "--round", "1"],
            input=json.dumps({"findings": [_f()]}),
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["new"] == 1

    def test_corrupt_state_file_does_not_crash_the_run(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{not json", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "finding_signature.py"),
                "--round",
                "1",
                "--state",
                str(state),
            ],
            input=json.dumps([_f()]),
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["new"] == 1


class TestRoundStateLifecycle:
    """The durable ledger must never leak across runs. Reusing a ledger from
    an unrelated changeset would misclassify a genuinely-new finding as
    'carried' (suppressing a round that should have run) and inflate the
    round counter toward the cap on unrelated history."""

    def _run(self, tmp_path, state, round_number, findings, run_id=None, reset=False):
        cmd = [
            sys.executable,
            str(_SCRIPTS_DIR / "finding_signature.py"),
            "--round",
            str(round_number),
            "--state",
            str(state),
        ]
        if run_id:
            cmd += ["--run-id", run_id]
        if reset:
            cmd += ["--reset"]
        result = subprocess.run(
            cmd, input=json.dumps(findings), capture_output=True, text=True, check=True
        )
        return json.loads(result.stdout)

    def test_round_one_always_starts_a_fresh_ledger(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()])
        # A brand-new review of a different changeset, starting at round 1.
        payload = self._run(tmp_path, state, 1, [_f()])
        assert payload["new"] == 1, "round 1 must not treat the prior run's finding as carried"
        assert payload["carried"] == 0
        assert payload["ledger_reset"] == "new-run-round-1"

    def test_round_two_resumes_the_same_run(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="abc")
        payload = self._run(tmp_path, state, 2, [_f(line=44)], run_id="abc")
        assert payload["carried"] == 1
        assert payload["ledger_reset"] is None

    def test_a_different_run_id_discards_the_stored_ledger(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="changeset-A")
        payload = self._run(tmp_path, state, 2, [_f(line=44)], run_id="changeset-B")
        assert payload["new"] == 1, "a different changeset must not inherit signatures"
        assert payload["ledger_reset"] == "run-id-mismatch"

    def test_an_explicit_reset_discards_the_stored_ledger(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="abc")
        payload = self._run(tmp_path, state, 2, [_f(line=44)], run_id="abc", reset=True)
        assert payload["new"] == 1
        assert payload["ledger_reset"] == "explicit-reset"

    def test_a_stale_ledger_is_discarded(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="abc")
        stored = json.loads(state.read_text(encoding="utf-8"))
        stored["started_at"] = "2020-01-01T00:00:00Z"
        state.write_text(json.dumps(stored), encoding="utf-8")

        payload = self._run(tmp_path, state, 2, [_f(line=44)], run_id="abc")
        assert payload["new"] == 1
        assert payload["ledger_reset"] == "stale-state"

    def test_a_corrupt_ledger_starts_fresh_rather_than_half_parsed(self, tmp_path):
        state = tmp_path / "s.json"
        state.write_text("{not json", encoding="utf-8")
        payload = self._run(tmp_path, state, 3, [_f()], run_id="abc")
        assert payload["new"] == 1
        assert payload["ledger_reset"] == "unreadable-state"

    def test_reset_precedence_explicit_beats_round_number(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="abc")
        payload = self._run(tmp_path, state, 5, [_f()], run_id="abc", reset=True)
        assert payload["ledger_reset"] == "explicit-reset"

    def test_the_state_file_records_run_identity_and_timestamps(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="abc")
        stored = json.loads(state.read_text(encoding="utf-8"))
        assert stored["run_id"] == "abc"
        assert stored["started_at"]
        assert stored["updated_at"]

    def test_started_at_is_preserved_across_rounds_of_one_run(self, tmp_path):
        state = tmp_path / "s.json"
        self._run(tmp_path, state, 1, [_f()], run_id="abc")
        first = json.loads(state.read_text(encoding="utf-8"))["started_at"]
        self._run(tmp_path, state, 2, [_f(line=90, rule="other")], run_id="abc")
        assert json.loads(state.read_text(encoding="utf-8"))["started_at"] == first

    def test_no_state_path_still_works(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "finding_signature.py"), "--round", "1"],
            input=json.dumps([_f()]),
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["new"] == 1
