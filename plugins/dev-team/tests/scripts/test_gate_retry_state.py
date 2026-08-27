"""Unit tests for skills/pr/scripts/gate_retry_state.py (#2087).

The headline acceptance criterion: a second `/pr` invocation on the same
branch, after a human fixes findings from the first invocation's
`/code-review --since <merge-base>` call, scopes its next check to just the
fix delta (`last_reviewed_sha`) instead of re-scanning the whole branch —
with exactly one mandatory full-branch confirmation pass before the gate can
close.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "skills" / "pr" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import gate_retry_state as grs

_CODE_REVIEW_SCRIPTS_DIR = _PLUGIN_ROOT / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_CODE_REVIEW_SCRIPTS_DIR))

import finding_signature

BASE = "base0000"
HEAD1 = "head1111"
HEAD2 = "head2222"
HEAD3 = "head3333"
HEAD4 = "head4444"
BRANCH = "feature/2087"


def _run(state_path, branch=BRANCH, base_sha=BASE, head_sha=HEAD1, last_outcome=None, reset=False):
    cmd = [
        sys.executable,
        str(_SCRIPTS_DIR / "gate_retry_state.py"),
        "--state",
        str(state_path),
        "--branch",
        branch,
        "--base-sha",
        base_sha,
        "--head-sha",
        head_sha,
    ]
    if last_outcome:
        cmd += ["--last-outcome", last_outcome]
    if reset:
        cmd += ["--reset"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


class TestDriftGuards:
    def test_max_rounds_matches_finding_signature(self):
        assert grs.PR_GATE_MAX_ROUNDS == finding_signature.MAX_ROUNDS

    def test_state_ttl_matches_finding_signature(self):
        assert grs.PR_GATE_STATE_TTL_SECONDS == finding_signature.STATE_TTL_SECONDS


class TestFreshStart:
    def test_no_state_file_starts_full_branch_round_one(self, tmp_path):
        state = tmp_path / "s.json"
        payload = _run(state)
        assert payload == {
            "since_ref": BASE,
            "phase": "initial",
            "round": 1,
            "reset_reason": None,
            "escalate": False,
        }

    def test_fresh_start_persists_a_crash_recovery_placeholder(self, tmp_path):
        state = tmp_path / "s.json"
        _run(state)
        assert state.is_file()
        stored = json.loads(state.read_text(encoding="utf-8"))
        assert stored["phase"] == "initial"
        assert stored["round"] == 1
        assert stored["branch"] == BRANCH
        assert stored["base_sha"] == BASE


class TestResetTriggers:
    def _seed_fix_diff_state(self, tmp_path, state):
        _run(state, head_sha=HEAD1)
        _run(state, head_sha=HEAD1, last_outcome="fail")

    def test_explicit_reset_starts_fresh(self, tmp_path):
        state = tmp_path / "s.json"
        self._seed_fix_diff_state(tmp_path, state)
        payload = _run(state, reset=True)
        assert payload["reset_reason"] == "explicit-reset"
        assert payload["phase"] == "initial"
        assert payload["since_ref"] == BASE

    def test_branch_mismatch_starts_fresh(self, tmp_path):
        state = tmp_path / "s.json"
        self._seed_fix_diff_state(tmp_path, state)
        payload = _run(state, branch="feature/other")
        assert payload["reset_reason"] == "branch-mismatch"
        assert payload["phase"] == "initial"
        assert payload["since_ref"] == BASE

    def test_base_sha_mismatch_starts_fresh(self, tmp_path):
        state = tmp_path / "s.json"
        self._seed_fix_diff_state(tmp_path, state)
        payload = _run(state, base_sha="newbase0")
        assert payload["reset_reason"] == "base-sha-mismatch"
        assert payload["phase"] == "initial"
        assert payload["since_ref"] == "newbase0"

    def test_stale_state_starts_fresh(self, tmp_path):
        state = tmp_path / "s.json"
        self._seed_fix_diff_state(tmp_path, state)
        stored = json.loads(state.read_text(encoding="utf-8"))
        stored["started_at"] = "2020-01-01T00:00:00Z"
        state.write_text(json.dumps(stored), encoding="utf-8")

        payload = _run(state)
        assert payload["reset_reason"] == "stale-state"
        assert payload["phase"] == "initial"
        assert payload["since_ref"] == BASE

    def test_corrupt_state_file_fails_toward_a_reset(self, tmp_path):
        state = tmp_path / "s.json"
        state.write_text("{not json", encoding="utf-8")
        payload = _run(state)
        assert payload["reset_reason"] == "unreadable-state"
        assert payload["phase"] == "initial"
        assert payload["since_ref"] == BASE


class TestHappyPathSequence:
    """The full initial -> fail -> fix-diff -> pass -> confirm -> pass ->
    done trace, asserting since_ref at each step: base_sha, then
    last_reviewed_sha, then base_sha again, then null."""

    def test_full_sequence(self, tmp_path):
        state = tmp_path / "s.json"

        # Call A: first call of the /pr invocation, nothing on disk yet.
        a = _run(state, head_sha=HEAD1)
        assert a["since_ref"] == BASE
        assert a["phase"] == "initial"
        assert a["round"] == 1
        # /code-review --since BASE --json -> overall: fail

        # Call B: record the fail.
        b = _run(state, head_sha=HEAD1, last_outcome="fail")
        assert b["since_ref"] == HEAD1
        assert b["phase"] == "fix-diff"
        assert b["round"] == 2
        assert b["escalate"] is False

        # A human fixes the findings; the branch advances to HEAD2.
        # Next /pr invocation, first call: resumes at fix-diff scope.
        c = _run(state, head_sha=HEAD2)
        assert c["since_ref"] == HEAD1
        assert c["phase"] == "fix-diff"
        assert c["round"] == 2
        # /code-review --since HEAD1 --json -> overall: pass

        # Call D: record the pass -> fix-diff converged -> confirm phase,
        # same /pr invocation, no human round-trip.
        d = _run(state, head_sha=HEAD2, last_outcome="pass")
        assert d["since_ref"] == BASE
        assert d["phase"] == "confirm"
        assert d["round"] == 3
        assert d["escalate"] is False
        # /code-review --since BASE --json (this same invocation) -> pass

        # Call E: record the confirm pass -> fully done.
        e = _run(state, head_sha=HEAD2, last_outcome="pass")
        assert e["since_ref"] is None
        assert e["phase"] == "done"
        assert not state.is_file(), "the done transition deletes the state file"


class TestInitialPassInOneShot:
    def test_full_branch_pass_on_the_first_round_skips_confirm(self, tmp_path):
        state = tmp_path / "s.json"
        first = _run(state, head_sha=HEAD1)
        assert first["phase"] == "initial"
        assert first["since_ref"] == BASE

        second = _run(state, head_sha=HEAD1, last_outcome="pass")
        assert second["since_ref"] is None
        assert second["phase"] == "done"
        assert not state.is_file()


class TestRoundCapEscalation:
    def test_enough_consecutive_fails_escalate_and_stop_advancing(self, tmp_path):
        state = tmp_path / "s.json"

        # Round 1 (initial) fails -> round becomes 2 (fix-diff).
        _run(state, head_sha=HEAD1)
        r2 = _run(state, head_sha=HEAD1, last_outcome="fail")
        assert r2["round"] == 2
        assert r2["escalate"] is False

        # Round 2 (fix-diff) fails -> round becomes 3.
        _run(state, head_sha=HEAD2)
        r3 = _run(state, head_sha=HEAD2, last_outcome="fail")
        assert r3["round"] == 3
        assert r3["escalate"] is False

        # Round 3 (fix-diff) fails -> round becomes 4, at the cap.
        _run(state, head_sha=HEAD3)
        r4 = _run(state, head_sha=HEAD3, last_outcome="fail")
        assert r4["round"] == grs.PR_GATE_MAX_ROUNDS
        assert r4["escalate"] is True
        assert r4["since_ref"] is None

        # A further no-outcome call refuses to advance: escalate again,
        # without ever calling /code-review.
        again = _run(state, head_sha=HEAD4)
        assert again["escalate"] is True
        assert again["since_ref"] is None
        assert again["round"] == grs.PR_GATE_MAX_ROUNDS

        # A further --last-outcome call (misuse) also refuses to advance
        # the round past the cap.
        misuse = _run(state, head_sha=HEAD4, last_outcome="fail")
        assert misuse["escalate"] is True
        assert misuse["round"] == grs.PR_GATE_MAX_ROUNDS


class TestConfirmFailBehavesLikeAnyOtherFail:
    def test_confirm_phase_failing_returns_to_fix_diff_not_stuck_forever(self, tmp_path):
        # Reaching "confirm" always costs exactly 2 prior rounds (initial
        # fail -> round 2, fix-diff pass -> round 3), so a confirm-phase
        # fail here lands on round 4 -- PR_GATE_MAX_ROUNDS itself. That is a
        # real, expected interaction with the round cap (asserted below),
        # not a reason the phase transition should behave differently: the
        # phase still becomes "fix-diff", never stays "confirm".
        state = tmp_path / "s.json"
        _run(state, head_sha=HEAD1)
        _run(state, head_sha=HEAD1, last_outcome="fail")
        _run(state, head_sha=HEAD2)
        confirm_transition = _run(state, head_sha=HEAD2, last_outcome="pass")
        assert confirm_transition["phase"] == "confirm"

        # The mandatory confirm pass fails.
        result = _run(state, head_sha=HEAD2, last_outcome="fail")
        assert result["phase"] == "fix-diff", "never stuck reporting confirm after a fail"
        assert result["round"] == grs.PR_GATE_MAX_ROUNDS
        assert result["escalate"] is True

        # Next invocation: the round cap (not "confirm") is what stops
        # automatic retries -- the stored phase is still fix-diff, never
        # reverted back to or stuck at confirm.
        resumed = _run(state, head_sha=HEAD3)
        assert resumed["phase"] == "fix-diff"
        assert resumed["escalate"] is True

    def test_confirm_fail_transition_in_isolation_from_the_round_cap(self):
        # Same phase transition as above, exercised directly through
        # decide() with a synthetic low round number, so the assertion is
        # decoupled from the round-cap interaction the subprocess-driven
        # test above documents.
        stored = {
            "branch": BRANCH,
            "base_sha": BASE,
            "last_reviewed_sha": HEAD2,
            "round": 1,
            "phase": "confirm",
            "started_at": grs._now_iso(),
            "updated_at": grs._now_iso(),
        }
        result, new_state, delete = grs.decide(
            stored, None, BRANCH, BASE, HEAD3, last_outcome="fail"
        )
        assert result["phase"] == "fix-diff"
        assert result["since_ref"] == HEAD3
        assert result["escalate"] is False
        assert delete is False
        assert new_state["phase"] == "fix-diff"
        assert new_state["last_reviewed_sha"] == HEAD3


class TestCrashRecoveryResume:
    def test_a_never_recorded_initial_call_resumes_full_branch_at_the_same_round(self, tmp_path):
        state = tmp_path / "s.json"
        # First call decides a full-branch check but the process "crashes"
        # before --last-outcome is ever recorded.
        first = _run(state, head_sha=HEAD1)
        assert first["phase"] == "initial"

        # A fresh /pr invocation resumes — still full-branch, same round —
        # rather than jumping to a narrower scope that never actually ran.
        second = _run(state, head_sha=HEAD1)
        assert second["phase"] == "initial"
        assert second["round"] == 1
        assert second["since_ref"] == BASE
        assert second["reset_reason"] is None
