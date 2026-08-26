"""Pytest tests for mutation_kill_shared.py — cross-language loop mechanics
shared between mutation_kill_loop.py (C#) and mutation_kill_loop_python.py
(Python/mutmut) (#1583).

The full git_revert/git_reset_and_revert/git_commit behavioral suite
(timeout handling, argv shape, add/commit/reset branch coverage) lives here
as the single source of truth (#1603). It was previously triplicated
near-verbatim across test_mutation_kill_loop_verify.py (C#) and
test_mutation_kill_loop_python.py (Python) despite both loops sharing this
exact implementation since #1583 — a behavior change to any of these three
functions required updating assertions in up to three files to stay in sync.
Both loop test files now carry only an identity check (``assert loop.git_revert
is mutation_kill_shared.git_revert``, etc.) plus whatever integration coverage
is genuinely loop-specific (e.g. the Python loop's real-git hermetic
regression tests, which exercise these same functions against a real repo
rather than a mocked ``subprocess.run``).

The ``claude --print`` headless-generation glue (``resolve_model``,
``strip_code_fences``, ``claude_cli_available``, ``run_claude_headless``) and
the ``InsertOutcome``/``InsertionRefused`` result shape also live here now
(moved from ``mutation_kill_headless.py`` and ``mutation_safety_gate.py``
respectively, #1601/#1602) — both loops import them from this module rather
than from each other or from a module scoped to a different concept.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_shared as shared


# =============================================================================
# stop_reason — the "no improvement across rounds" stop predicate
# =============================================================================
def test_stop_reason_is_none_when_survivors_remain_and_no_prior_round():
    assert shared.stop_reason(3, None) is None


def test_stop_reason_is_none_when_survivor_count_improved():
    assert shared.stop_reason(2, 5) is None


def test_stop_reason_flags_zero_survivors_as_done():
    assert str(shared.stop_reason(0, None)) == "no survivors — done"


def test_stop_reason_flags_zero_survivors_as_done_even_with_a_prior_round():
    assert str(shared.stop_reason(0, 4)) == "no survivors — done"


def test_stop_reason_flags_no_improvement_when_count_is_unchanged():
    assert str(shared.stop_reason(3, 3)) == "no improvement this round — stopping"


def test_stop_reason_flags_no_improvement_when_count_got_worse():
    assert str(shared.stop_reason(4, 3)) == "no improvement this round — stopping"


# --- #2030: the four stop paths, and default-off equivalence ----------------


def test_all_pre_2030_stop_paths_are_terminal():
    """The three original stops are the loop's own call — no operator needed."""
    assert shared.stop_reason(0, None).terminal is True
    assert shared.stop_reason(0, 4).terminal is True
    assert shared.stop_reason(3, 3).terminal is True


def test_omitting_both_2030_flags_reproduces_pre_2030_verdicts_exactly():
    """#2030 AC: unflagged behavior is byte-identical to today's.

    Swept over the full (survivor, prev) grid the old two-clause predicate
    could see, compared against a local re-implementation of it, so this
    cannot pass by agreeing with the new code's own bugs.
    """

    def pre_2030(survivor_count, prev_survivor_count):
        if survivor_count == 0:
            return "no survivors — done"
        if prev_survivor_count is not None and survivor_count >= prev_survivor_count:
            return "no improvement this round — stopping"
        return None

    for survivors in range(12):
        for prev in [None, *range(12)]:
            expected = pre_2030(survivors, prev)
            actual = shared.stop_reason(survivors, prev)
            assert (actual is None) == (expected is None), (survivors, prev)
            if expected is not None:
                assert str(actual) == expected, (survivors, prev)


def test_target_met_stops_the_file_and_is_terminal():
    decision = shared.stop_reason(5, 20, honest_score=82.0, target_honest_score=80.0)
    assert decision is not None and decision.terminal is True
    assert "82.0%" in str(decision) and "80.0%" in str(decision)


def test_target_met_exactly_at_the_threshold_stops():
    """Phase 8 gates on >= target, so the loop must stop AT it, not past it."""
    assert (
        shared.stop_reason(5, 20, honest_score=80.0, target_honest_score=80.0)
        is not None
    )


def test_below_target_does_not_stop_on_the_target_clause():
    assert shared.stop_reason(5, 20, honest_score=79.9, target_honest_score=80.0) is None


def test_target_clause_inert_when_score_is_unavailable():
    """A missing score must not read as 'target met' — that would stop a file
    the gate has not cleared."""
    assert shared.stop_reason(5, 20, honest_score=None, target_honest_score=80.0) is None


def test_yield_floor_stop_is_advisory_not_terminal():
    """#2030 AC: a below-floor round reaches the operator, never a silent stop."""
    decision = shared.stop_reason(19, 20, min_kills_per_round=3)
    assert decision is not None
    assert decision.terminal is False
    assert "[c]ontinue" in str(decision) and "[q]uit" in str(decision)


def test_yield_floor_does_not_fire_when_the_round_met_the_floor():
    assert shared.stop_reason(17, 20, min_kills_per_round=3) is None


def test_yield_floor_is_skipped_once_the_target_is_met():
    """Target-met is the better reason and is terminal; the floor must not
    downgrade it to an advisory stop."""
    decision = shared.stop_reason(
        19, 20, honest_score=90.0, target_honest_score=80.0, min_kills_per_round=3
    )
    assert decision is not None and decision.terminal is True
    assert "mutation target" in str(decision)


def test_no_improvement_outranks_the_yield_floor():
    """A round that killed nothing is a real convergence stop, not an operator
    judgement call."""
    decision = shared.stop_reason(20, 20, min_kills_per_round=3)
    assert decision is not None and decision.terminal is True


def test_yield_floor_inert_on_the_first_round():
    """No previous count means no yield to compare against."""
    assert shared.stop_reason(20, None, min_kills_per_round=3) is None


# --- #2030: resolve_kill_floor ----------------------------------------------


def test_kill_floor_absolute_values_are_used_verbatim():
    assert shared.resolve_kill_floor(3, 40) == 3
    assert shared.resolve_kill_floor(1, 40) == 1


def test_kill_floor_fraction_is_a_share_of_starting_survivors():
    assert shared.resolve_kill_floor(0.25, 40) == 10


def test_kill_floor_fraction_rounds_up_so_it_never_silently_disables():
    """0.1 * 5 == 0.5; truncating would yield a floor of 0, which reads as
    configured but checks nothing."""
    assert shared.resolve_kill_floor(0.1, 5) == 1


def test_kill_floor_disabled_for_none_zero_and_negative():
    assert shared.resolve_kill_floor(None, 40) is None
    assert shared.resolve_kill_floor(0, 40) is None
    assert shared.resolve_kill_floor(-1, 40) is None


def test_kill_floor_fraction_with_no_starting_survivors_is_disabled():
    assert shared.resolve_kill_floor(0.25, 0) is None


# =============================================================================
# _timeout_from_env — parser both loops (and mutation_kill_headless.py's
# generation timeout) rely on.
# =============================================================================
def test_timeout_from_env_returns_the_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SOME_SHARED_TIMEOUT_VAR", raising=False)
    assert shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42) == 42


def test_timeout_from_env_parses_an_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_SHARED_TIMEOUT_VAR", "99")
    assert shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42) == 99


def test_timeout_from_env_rejects_a_non_numeric_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_SHARED_TIMEOUT_VAR", "not-a-number")
    with pytest.raises(ValueError, match="SOME_SHARED_TIMEOUT_VAR"):
        shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42)


def test_timeout_from_env_rejects_a_non_positive_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOME_SHARED_TIMEOUT_VAR", "0")
    with pytest.raises(ValueError, match="positive"):
        shared._timeout_from_env("SOME_SHARED_TIMEOUT_VAR", 42)


# =============================================================================
# git_revert / git_reset_and_revert / git_commit — argv shape.
# =============================================================================
def test_git_revert_checks_out_only_the_given_file(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    seen: list = []

    def fake_run(argv, **k):
        seen.append(argv)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    shared.git_revert(tmp_path / "Foo.txt")

    assert seen[0] == ["git", "--literal-pathspecs", "checkout", "--", str(tmp_path / "Foo.txt")]


def test_git_reset_and_revert_resets_then_checks_out(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is True
    assert [c[2] for c in calls] == ["reset", "checkout"]


def test_git_commit_stages_then_commits_only_the_given_file(tmp_path: Path, monkeypatch):
    class _R:
        returncode = 0

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is True
    assert calls[0] == ["git", "--literal-pathspecs", "add", "--", str(tmp_path / "Foo.txt")]
    assert calls[1] == [
        "git",
        "--literal-pathspecs",
        "commit",
        "-m",
        "msg",
        "--",
        str(tmp_path / "Foo.txt"),
    ]


def test_git_commit_returns_false_on_a_non_timeout_commit_failure(
    tmp_path: Path, monkeypatch
):
    """git_commit's own commit-leg failure branch (a non-zero returncode with
    no timeout involved — e.g. "nothing to commit") — direct coverage, not
    just the timeout variant already covered elsewhere (#1563 gap 2)."""

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R(0) if len(calls) == 1 else _R(1)

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is False
    assert [c[2] for c in calls] == ["add", "commit"]


# =============================================================================
# git_revert / git_commit / git_reset_and_revert — timeout handling and
# branch coverage. Consolidated from both loops' test suites (#1603).
# =============================================================================
def test_git_revert_returns_true_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class _R:
        returncode = 0

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **k: _R())

    assert shared.git_revert(tmp_path / "Foo.txt") is True


def test_git_revert_returns_false_on_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class _R:
        returncode = 1

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **k: _R())

    assert shared.git_revert(tmp_path / "Foo.txt") is False


def test_git_revert_passes_a_timeout_to_subprocess_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    captured: dict = {}

    class _R:
        returncode = 0

    def fake_run(argv, **k):
        captured.update(k)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    shared.git_revert(tmp_path / "Foo.txt")

    assert captured["timeout"] == shared.GIT_TIMEOUT_S


def test_git_revert_returns_false_and_logs_not_raises_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_revert(tmp_path / "Foo.txt") is False  # must not raise

    err = capsys.readouterr().err
    assert str(shared.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git checkout" in err


def test_git_commit_passes_a_timeout_to_add_and_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    result = shared.git_commit("msg", tmp_path / "Foo.txt")

    assert result is True
    assert calls[0][1]["timeout"] == shared.GIT_TIMEOUT_S
    assert calls[1][1]["timeout"] == shared.GIT_TIMEOUT_S


def test_git_commit_add_leg_timeout_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is False
    err = capsys.readouterr().err
    assert str(shared.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git add" in err


def test_git_commit_commit_leg_timeout_returns_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """The `git add` leg succeeds; only the `git commit` leg's own
    subprocess.run call times out — a distinct branch from the add-leg
    timeout above, since git_commit short-circuits on add before ever
    reaching commit."""

    calls: list = []

    class _R:
        returncode = 0

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            return _R()
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_commit("msg", tmp_path / "Foo.txt") is False
    assert calls[0][:3] == ["git", "--literal-pathspecs", "add"]
    err = capsys.readouterr().err
    assert str(shared.GIT_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_GIT_TIMEOUT_S" in err
    assert "git commit" in err


def test_git_commit_proceeds_to_commit_after_a_non_timeout_add_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Pins the documented behavior: git_commit only inspects git add's
    timeout, not its returncode, so a non-timeout git add failure (e.g. bad
    pathspec) still falls through to attempting the commit."""

    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(returncode=1) if len(calls) == 1 else _R(returncode=0)

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    result = shared.git_commit("msg", tmp_path / "Foo.txt")

    assert result is True
    assert len(calls) == 2
    assert calls[1][:3] == ["git", "--literal-pathspecs", "commit"]


def test_git_reset_and_revert_returns_false_when_reset_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _R(1)  # reset fails

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is False
    # Only the reset call happens — checkout (git_revert) is never reached.
    assert len(calls) == 1
    assert calls[0][:3] == ["git", "--literal-pathspecs", "reset"]


def test_git_reset_and_revert_returns_false_when_reset_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is False


def test_git_reset_and_revert_returns_false_when_checkout_fails_after_reset_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[2] == "reset":
            return _R(0)  # reset succeeds
        return _R(1)  # checkout (git_revert) fails

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    assert shared.git_reset_and_revert(tmp_path / "Foo.txt") is False
    assert [c[2] for c in calls] == ["reset", "checkout"]


# =============================================================================
# resolve_model / strip_code_fences / claude_cli_available / run_claude_headless
# — the claude --print invocation glue, moved here from
# mutation_kill_headless.py (#1601). mutation_kill_headless.py (C#) and
# mutation_kill_loop_python.py both import these directly from this module.
# =============================================================================
def test_resolve_model_prefers_explicit_over_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_TEAM_MUTATION_MODEL", "env-model")
    assert shared.resolve_model("flag-model") == "flag-model"


def test_resolve_model_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_TEAM_MUTATION_MODEL", "env-model")
    assert shared.resolve_model() == "env-model"


def test_resolve_model_is_none_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEV_TEAM_MUTATION_MODEL", raising=False)
    assert shared.resolve_model() is None


# =============================================================================
# resolve_fallback_model — one-step model-downgrade ladder + the
# DEV_TEAM_MUTATION_FALLBACK_MODEL override (#1908, Slice 3 Step 3.1).
# =============================================================================
def test_resolve_fallback_model_steps_down_from_opus(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    assert shared.resolve_fallback_model("opus") == "sonnet"


def test_resolve_fallback_model_steps_down_from_sonnet(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    assert shared.resolve_fallback_model("sonnet") == "haiku"


def test_resolve_fallback_model_returns_none_for_an_unresolved_model(
    monkeypatch: pytest.MonkeyPatch,
):
    """``resolve_model()`` returns ``None`` for "unspecified, CLI default".
    There is no way to observe the CLI's own actual default from this
    codebase, so treating ``None`` as if it were "opus" would be an
    unverified assumption (#1908 review) — it returns ``None`` uniformly
    with the floor and an unrecognized model instead: "no known ladder
    position to step down to"."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    assert shared.resolve_fallback_model(None) is None


def test_resolve_fallback_model_returns_none_at_the_floor(
    monkeypatch: pytest.MonkeyPatch,
):
    """haiku is the ladder floor — no further downgrade is possible."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    assert shared.resolve_fallback_model("haiku") is None


def test_resolve_fallback_model_returns_none_for_an_unrecognized_model(
    monkeypatch: pytest.MonkeyPatch,
):
    """A model string outside {opus, sonnet, haiku} (e.g. an operator-supplied
    ``--model claude-sonnet-4-5``) has no ladder position defined for it
    either — same "no known position" outcome as the floor or an unresolved
    model, not a fall-through to a misleading default (#1908 review)."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    assert shared.resolve_fallback_model("claude-sonnet-4-5") is None


def test_resolve_fallback_model_env_override_wins_over_the_ladder_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "haiku")
    assert shared.resolve_fallback_model("opus") == "haiku"


def test_resolve_fallback_model_env_override_accepts_a_same_or_higher_tier(
    monkeypatch: pytest.MonkeyPatch,
):
    """No ordering is enforced on an explicit operator override — it's
    authoritative even when it names a tier at or above the current one."""
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "opus")
    assert shared.resolve_fallback_model("haiku") == "opus"


def test_resolve_fallback_model_env_override_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "HAIKU")
    assert shared.resolve_fallback_model("opus") == "haiku"


def test_resolve_fallback_model_env_override_accepts_fable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """``fable`` is a display-latency variant, not a capability tier — it
    has no entry in the opus->sonnet->haiku ladder — but it is one of
    ``agent-contract.json``'s valid ``--model`` values, so an explicit
    override naming it must be accepted outright, not rejected as invalid
    (#1908 review, FIX 8)."""
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "fable")
    assert shared.resolve_fallback_model("opus") == "fable"
    assert capsys.readouterr().err == ""


def test_resolve_fallback_model_invalid_env_override_falls_back_to_the_ladder_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "gpt-4")
    assert shared.resolve_fallback_model("opus") == "sonnet"


def test_resolve_fallback_model_invalid_env_override_is_reported_not_silently_accepted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "not-a-model")
    shared.resolve_fallback_model("sonnet")
    err = capsys.readouterr().err
    assert "not-a-model" in err
    assert "DEV_TEAM_MUTATION_FALLBACK_MODEL" in err


def test_strip_code_fences_removes_leading_and_trailing_fence():
    text = "```python\ndef test_new():\n    assert True\n```"
    assert shared.strip_code_fences(text) == "def test_new():\n    assert True"


def test_strip_code_fences_is_a_noop_without_fences():
    assert shared.strip_code_fences("def test_new():\n    assert True") == (
        "def test_new():\n    assert True"
    )


def test_claude_cli_available_is_true_when_the_cli_responds(
    monkeypatch: pytest.MonkeyPatch,
):
    class _OK:
        returncode = 0

    monkeypatch.setattr(shared.subprocess, "run", lambda *a, **k: _OK())
    assert shared.claude_cli_available() is True


def test_claude_cli_available_is_false_when_the_binary_is_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    def _missing(*a, **k):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(shared.subprocess, "run", _missing)
    assert shared.claude_cli_available() is False


def test_claude_cli_available_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    class _OK:
        returncode = 0

    def fake_run(*a, **k):
        captured.update(k)
        return _OK()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    shared.claude_cli_available()
    assert captured["timeout"] == shared.CLAUDE_VERSION_TIMEOUT_S


def test_claude_cli_available_treats_a_timeout_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(*a, **k):
        raise shared.subprocess.TimeoutExpired(a[0] if a else [], k.get("timeout"))

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    assert shared.claude_cli_available() is False


def test_run_claude_headless_sends_the_prompt_over_stdin_not_argv(
    monkeypatch: pytest.MonkeyPatch,
):
    """The prompt must not appear as a trailing argv element (#1607) — an
    argv-passed prompt is parsed for dash-prefixed option injection by the
    CLI's own arg parser, and is visible to any other process on the host via
    ps/procfs for the subprocess's lifetime. Routed over stdin instead."""
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "def test_new(): pass"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    out = shared.run_claude_headless("a prompt with -- dashes and -flags", model=None)

    assert "a prompt with -- dashes and -flags" not in captured["argv"]
    assert captured["kwargs"]["input"] == "a prompt with -- dashes and -flags"
    assert out == "def test_new(): pass"


def test_run_claude_headless_passes_the_model_flag_when_set(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    shared.run_claude_headless("prompt", model="some-model")

    argv = captured["argv"]
    assert argv[0] == shared.CLAUDE_CLI
    assert "--print" in argv
    assert argv[argv.index("--model") + 1] == "some-model"


def test_run_claude_headless_omits_model_flag_when_unset(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    shared.run_claude_headless("prompt", model=None)

    assert "--model" not in captured["argv"]


def test_run_claude_headless_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    shared.run_claude_headless("prompt", model=None)

    assert captured["timeout"] == shared.CLAUDE_GENERATION_TIMEOUT_S


def test_run_claude_headless_timeout_raises_a_named_error(
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        shared.run_claude_headless("prompt", model=None)

    assert str(shared.CLAUDE_GENERATION_TIMEOUT_S) in str(exc_info.value)
    assert "DEV_TEAM_MUTATION_GENERATION_TIMEOUT_S" in str(exc_info.value)


def test_run_claude_headless_raises_on_a_nonzero_claude_exit(
    monkeypatch: pytest.MonkeyPatch,
):
    class _R:
        returncode = 1
        stdout = ""
        stderr = "authentication required\n"

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **kwargs: _R())

    with pytest.raises(RuntimeError, match="authentication required"):
        shared.run_claude_headless("prompt", model=None)


# =============================================================================
# RevertFailed — typed revert-failure error, marking a possibly-mutated
# working tree (#1939 Slice 1 Step 1.1).
# =============================================================================
def test_revert_failed_is_a_runtime_error():
    assert isinstance(shared.RevertFailed("x"), RuntimeError)
    assert issubclass(shared.RevertFailed, RuntimeError)


def test_revert_failed_str_is_a_plain_passthrough_of_the_message():
    """Unlike HeadlessCallFailed (which reformats its constructor args
    through a custom __str__), RevertFailed takes no custom __init__/__str__
    — the call site already builds a complete message string, so str(exc)
    must equal that message unchanged."""
    assert str(shared.RevertFailed("some message")) == "some message"


# =============================================================================
# HeadlessCallFailed — typed gateway-class error, replacing the plain
# RuntimeError raised on a non-zero claude CLI exit (#1938 Slice 1 Step 1.1).
# =============================================================================
def test_headless_call_failed_is_a_runtime_error():
    assert issubclass(shared.HeadlessCallFailed, RuntimeError)


def test_headless_call_failed_str_matches_todays_exact_message():
    exc = shared.HeadlessCallFailed(1, "some error text")
    assert str(exc) == "claude CLI failed (exit 1): some error text"


def test_run_claude_headless_raises_headless_call_failed_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
):
    class _R:
        returncode = 1
        stdout = ""
        stderr = "some error text"

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **kwargs: _R())

    with pytest.raises(shared.HeadlessCallFailed) as exc_info:
        shared.run_claude_headless("prompt", model=None)

    assert exc_info.value.returncode == 1
    assert exc_info.value.stderr == "some error text"


def test_run_claude_headless_headless_call_failed_stderr_is_not_truncated(
    monkeypatch: pytest.MonkeyPatch,
):
    long_stderr = "x" * 600

    class _R:
        returncode = 1
        stdout = ""
        stderr = long_stderr

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **kwargs: _R())

    with pytest.raises(shared.HeadlessCallFailed) as exc_info:
        shared.run_claude_headless("prompt", model=None)

    assert exc_info.value.stderr == long_stderr
    assert len(exc_info.value.stderr) == 600
    # __str__ still truncates to 500 bytes — only the constructor arg/attr
    # carries the full, untruncated stderr.
    assert len(str(exc_info.value)) < 600


def test_run_claude_headless_timeout_path_still_raises_plain_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """The TimeoutExpired branch is untouched — it must never raise
    HeadlessCallFailed, only a plain RuntimeError."""

    def fake_run(argv, **kwargs):
        raise shared.subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(shared.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        shared.run_claude_headless("prompt", model=None)

    assert type(exc_info.value) is RuntimeError


def test_run_claude_headless_strips_fences_from_the_result(
    monkeypatch: pytest.MonkeyPatch,
):
    class _R:
        returncode = 0
        stdout = "```python\ndef test_new():\n    assert True\n```"
        stderr = ""

    monkeypatch.setattr(shared.subprocess, "run", lambda argv, **kwargs: _R())

    out = shared.run_claude_headless("prompt", model=None)

    assert "```" not in out
    assert "test_new" in out


# =============================================================================
# InsertOutcome / InsertionRefused — moved here from mutation_safety_gate.py
# (#1602): neither is a safety concept, they're the plain result/exception
# shape both loops' insertion mechanics (mutation_kill_insert.py,
# mutation_kill_insert_python.py) share verbatim (#1583).
# =============================================================================
def test_insert_outcome_carries_inserted_and_reason():
    outcome = shared.InsertOutcome(True, "inserted")
    assert outcome.inserted is True
    assert outcome.reason == "inserted"


def test_insert_outcome_is_frozen():
    outcome = shared.InsertOutcome(False, "no tests generated")
    with pytest.raises(AttributeError):
        outcome.inserted = True


def test_insertion_refused_is_an_exception():
    assert issubclass(shared.InsertionRefused, Exception)
    with pytest.raises(shared.InsertionRefused, match="nope"):
        raise shared.InsertionRefused("nope")
