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
from _mutation_test_helpers import SCRIPTS_DIR, sequenced_run_claude_headless

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
    assert shared.stop_reason(0, None) == "no survivors — done"


def test_stop_reason_flags_zero_survivors_as_done_even_with_a_prior_round():
    assert shared.stop_reason(0, 4) == "no survivors — done"


def test_stop_reason_flags_no_improvement_when_count_is_unchanged():
    assert shared.stop_reason(3, 3) == "no improvement this round — stopping"


def test_stop_reason_flags_no_improvement_when_count_got_worse():
    assert shared.stop_reason(4, 3) == "no improvement this round — stopping"


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
# is_gateway_class_error — the exact 502/gateway-class error definition
# (#1908, Slice 3 Step 3.2).
# =============================================================================
def _exit_error(stderr: str) -> RuntimeError:
    return RuntimeError(f"claude CLI failed (exit 1): {stderr}")


def _timeout_error() -> RuntimeError:
    return RuntimeError(
        "claude --print generation timed out after 300s (set "
        "DEV_TEAM_MUTATION_GENERATION_TIMEOUT_S to raise it)"
    )


@pytest.mark.parametrize(
    "marker",
    [
        "502",
        "503",
        "504",
        "Bad Gateway",
        "SERVICE UNAVAILABLE",
        "Gateway Timeout",
        "overloaded_error",
        "Upstream Connect Error",
        "Connection Reset",
    ],
)
def test_is_gateway_class_error_matches_every_documented_marker_case_insensitively(
    marker: str,
):
    assert shared.is_gateway_class_error(_exit_error(f"boom: {marker} boom")) is True


def test_is_gateway_class_error_is_false_for_the_timeout_shape():
    """The TimeoutExpired-derived shape is a local generation timeout, never
    an upstream provider signal — never gateway-class."""
    assert shared.is_gateway_class_error(_timeout_error()) is False


def test_is_gateway_class_error_is_false_for_an_unmatched_nonzero_exit():
    assert shared.is_gateway_class_error(_exit_error("permission denied")) is False


def test_generation_exhausted_is_a_runtime_error():
    """So the existing `except RuntimeError` handling in both --headless
    CLIs' main() (and any --all driver relying on the same taxonomy) catches
    it exactly like today's failed-revert/failed-commit RuntimeErrors — this
    file's exhaustion is reported and the process exits non-zero; it never
    surfaces as an uncaught traceback that would abort an outer --all run
    differently from any other per-file failure."""
    assert issubclass(shared.GenerationExhausted, RuntimeError)


# =============================================================================
# make_retrying_headless_call — the 3-consecutive-gateway-class-failures ->
# 1-same-model-retry -> at-most-once-per-file-downgrade mechanism (#1908,
# Slice 3 Step 3.2). Every scenario in the plan's Slice 3 Behavior block is
# covered here; mutation_kill_headless.py / mutation_kill_loop_python.py's
# own test files only prove the make_headless_generator wiring around this.
# =============================================================================
def test_backoff_sleeps_with_increasing_duration_between_pre_threshold_retries(
    monkeypatch: pytest.MonkeyPatch,
):
    """3 consecutive gateway-class failures: an injected ``sleep`` is called
    before the 2nd and 3rd attempts (once the streak reaches 1 and 2), with
    increasing, capped durations — ``min(2 ** (streak - 1), 10)`` — so a
    single ``call()`` invocation's up-to-4 same-model attempts don't hammer
    an already-overloaded upstream with zero delay (#1908 review). Not
    called before the 1st attempt, and not called again for the 3rd-failure
    same-model retry itself — that attempt already earned its slot via the
    threshold."""
    sleeps: list[float] = []
    sequenced_run_claude_headless(
        monkeypatch,
        shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "generated-test",
    )
    call = shared.make_retrying_headless_call(initial_model="opus", sleep=sleeps.append)

    result = call("prompt", "foo.py", 1)

    assert result == "generated-test"
    assert sleeps == [1, 2]


def test_backoff_default_sleep_parameter_is_the_real_time_sleep():
    """The public contract's default ``sleep`` is the real ``time.sleep`` —
    verified by introspection so this test never actually sleeps. A
    zero-failure call (any success path) never invokes ``sleep`` at all,
    which is exactly why the default is safe to leave unexercised here."""
    import inspect

    sig = inspect.signature(shared.make_retrying_headless_call)
    assert sig.parameters["sleep"].default is shared.time.sleep


def test_third_consecutive_gateway_failure_triggers_exactly_one_same_model_retry(
    monkeypatch: pytest.MonkeyPatch,
):
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("503 Service Unavailable"),
        _exit_error("504 Gateway Timeout"),
        "generated-test",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    result = call("prompt", "foo.py", 1)

    assert result == "generated-test"
    assert len(calls) == 4
    assert {model for _, model in calls} == {"opus"}
    assert downgrades == []


def test_successful_retry_avoids_downgrade_entirely(monkeypatch: pytest.MonkeyPatch):
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "ok",  # the 3rd-failure retry succeeds
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    assert call("prompt", "foo.py", 1) == "ok"
    assert len(calls) == 4
    assert downgrades == []


def test_gateway_failure_after_a_success_counts_as_the_first_not_the_third(
    monkeypatch: pytest.MonkeyPatch,
):
    """A success between failures resets the consecutive-failure count: 2
    gateway failures, a success, then exactly 3 MORE (not fewer) fresh
    gateway failures are needed before the retry fires again."""
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "ok-1",  # success resets the streak to 0
        _exit_error("502 Bad Gateway"),  # 1st post-reset failure
        _exit_error("502 Bad Gateway"),  # 2nd
        _exit_error("502 Bad Gateway"),  # 3rd — now the retry fires
        "ok-after-retry",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    assert call("prompt", "foo.py", 1) == "ok-1"
    assert call("prompt", "foo.py", 2) == "ok-after-retry"
    assert len(calls) == 7
    assert downgrades == []  # the post-reset retry succeeded — no downgrade needed


def test_non_gateway_failures_never_count_toward_the_threshold(
    monkeypatch: pytest.MonkeyPatch,
):
    """3 consecutive non-gateway-class failures — call() must propagate
    each one immediately (unchanged, pre-existing behavior); no retry or
    downgrade mechanism ever fires for them."""
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("validation error"),
        _exit_error("validation error"),
        _exit_error("validation error"),
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    for _ in range(3):
        with pytest.raises(RuntimeError, match="validation error"):
            call("prompt", "foo.py", 1)

    assert len(calls) == 3
    assert downgrades == []


def test_non_gateway_failure_resets_an_in_progress_gateway_streak(
    monkeypatch: pytest.MonkeyPatch,
):
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("503 Service Unavailable"),
        _exit_error("validation error"),  # non-gateway — resets the streak, raises
        _exit_error("502 Bad Gateway"),  # 1st post-reset gateway failure
        _exit_error("502 Bad Gateway"),  # 2nd
        _exit_error("502 Bad Gateway"),  # 3rd — now the retry fires
        "ok-after-retry",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    with pytest.raises(RuntimeError, match="validation error"):
        call("prompt", "foo.py", 1)

    assert call("prompt", "foo.py", 2) == "ok-after-retry"
    assert len(calls) == 7
    assert downgrades == []


def test_failed_retry_downgrades_one_step_down_the_ladder(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    logged: list[str] = []
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),  # the retry — also fails -> downgrade
        "ok-on-sonnet",
    )
    call = shared.make_retrying_headless_call(
        sleep=lambda _s: None,
        initial_model="opus",
        log=logged.append,
        on_downgrade=downgrades.append,
    )

    result = call("prompt", "foo.py", 3)

    assert result == "ok-on-sonnet"
    assert len(calls) == 5
    assert calls[-1][1] == "sonnet"
    assert len(downgrades) == 1
    event = downgrades[0]
    assert event.source_file == "foo.py"
    assert event.round_num == 3
    assert event.from_model == "opus"
    assert event.to_model == "sonnet"
    assert event.error_class == "gateway-class"
    assert event.exhausted is False
    assert len(logged) == 1
    assert "foo.py" in logged[0]
    assert "opus" in logged[0] and "sonnet" in logged[0]


def test_downgrade_is_printed_before_the_next_generation_attempt(
    monkeypatch: pytest.MonkeyPatch,
):
    """Order between the print and the audit-trail write is not itself
    tested (that's Step 3.2b's own seam) — only that the print happens
    before the fallback model's first generation attempt for that round."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    events: list[str] = []
    outcomes = [
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "ok-on-sonnet",
    ]

    def fake(prompt, *, model=None, cwd=None):
        events.append(f"call:{model}")
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(shared, "run_claude_headless", fake)
    call = shared.make_retrying_headless_call(
        sleep=lambda _s: None,
        initial_model="opus",
        log=lambda msg: events.append(f"log:{msg}"),
    )

    call("prompt", "foo.py", 3)

    assert events[:4] == ["call:opus"] * 4
    assert events[4].startswith("log:")
    assert events[5] == "call:sonnet"


def test_retry_failure_triggers_downgrade_even_when_non_gateway_class(
    monkeypatch: pytest.MonkeyPatch,
):
    """The retry's own outcome is a plain pass/fail — the error-class filter
    only gates entry into the 3-failure count, never re-filters the retry's
    own result. A non-gateway-class retry failure still downgrades."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    downgrades: list = []
    sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("validation error"),  # the retry — non-gateway-class failure
        "ok-on-sonnet",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    result = call("prompt", "foo.py", 2)

    assert result == "ok-on-sonnet"
    assert len(downgrades) == 1
    assert downgrades[0].error_class == "non-gateway-class"
    assert downgrades[0].to_model == "sonnet"


def test_downgrade_does_not_persist_to_the_next_file(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "ok-on-sonnet",
    )
    call_a = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")
    call_a("prompt", "file-a.py", 1)  # file A downgrades to sonnet

    calls_b = sequenced_run_claude_headless(monkeypatch, shared, "ok-on-opus")
    call_b = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")
    call_b("prompt", "file-b.py", 1)

    assert calls_b == [("prompt", "opus")]  # file B starts fresh, not on sonnet


def test_concurrent_closures_for_different_files_do_not_leak_downgrade_state(
    monkeypatch: pytest.MonkeyPatch,
):
    """Two closures constructed for two different files BEFORE either is
    called — downgrading one must never affect the other's model."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    responses = {
        "file-a.py": [
            _exit_error("502 Bad Gateway"),
            _exit_error("502 Bad Gateway"),
            _exit_error("502 Bad Gateway"),
            _exit_error("502 Bad Gateway"),
            "ok-a-on-sonnet",
        ],
        "file-b.py": ["ok-b-on-opus"],
    }
    seen_models: dict[str, list[str | None]] = {"file-a.py": [], "file-b.py": []}

    def make_fake(name):
        def fake(prompt, *, model=None, cwd=None):
            seen_models[name].append(model)
            outcome = responses[name].pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        return fake

    call_a = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")
    call_b = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")

    monkeypatch.setattr(shared, "run_claude_headless", make_fake("file-a.py"))
    call_a("prompt-a", "file-a.py", 1)  # downgrades A to sonnet

    monkeypatch.setattr(shared, "run_claude_headless", make_fake("file-b.py"))
    result_b = call_b("prompt-b", "file-b.py", 1)

    assert result_b == "ok-b-on-opus"
    assert seen_models["file-b.py"] == ["opus"]  # unaffected by A's downgrade


def test_downgrade_uses_the_fallback_model_env_override_unordered(
    monkeypatch: pytest.MonkeyPatch,
):
    """No ordering is enforced on an explicit operator override — accepted
    even when it names a tier at or above the one currently in use."""
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "opus")
    downgrades: list = []
    sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "ok",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="haiku", on_downgrade=downgrades.append)

    call("prompt", "foo.py", 1)

    assert downgrades[0].to_model == "opus"


def test_invalid_fallback_override_falls_back_to_the_ladder_default_and_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", "not-a-model")
    downgrades: list = []
    sequenced_run_claude_headless(
        monkeypatch, shared,
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        "ok",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    call("prompt", "foo.py", 1)

    assert downgrades[0].to_model == "sonnet"  # ladder default, override rejected
    err = capsys.readouterr().err
    assert "not-a-model" in err
    assert "DEV_TEAM_MUTATION_FALLBACK_MODEL" in err


def test_fallback_tier_exhaustion_surfaces_no_second_downgrade_mid_ladder(
    monkeypatch: pytest.MonkeyPatch,
):
    """Mid-ladder tier (sonnet, reached from opus) — not only the true floor
    (haiku) — since a prior review round found that exact ambiguity."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    downgrades: list = []
    calls = sequenced_run_claude_headless(
        monkeypatch, shared,
        *([_exit_error("502 Bad Gateway")] * 4),  # opus: 3 fail + failed retry -> downgrade
        *([_exit_error("502 Bad Gateway")] * 4),  # sonnet: 3 fail + failed retry -> exhaustion
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    with pytest.raises(shared.GenerationExhausted) as exc_info:
        call("prompt", "foo.py", 5)

    assert len(calls) == 8
    assert [model for _, model in calls[:4]] == ["opus"] * 4
    assert [model for _, model in calls[4:]] == ["sonnet"] * 4
    assert len(downgrades) == 2
    assert downgrades[0].to_model == "sonnet"
    assert downgrades[0].exhausted is False
    assert downgrades[1].from_model == "sonnet"
    assert downgrades[1].to_model is None
    assert downgrades[1].exhausted is True
    message = str(exc_info.value)
    assert "foo.py" in message
    assert "sonnet" in message
    assert "no further downgrade" in message


def test_exhaustion_when_already_at_the_floor_with_no_fallback_tier(
    monkeypatch: pytest.MonkeyPatch,
):
    """Starting already at haiku (the floor) — the first downgrade attempt
    has no lower tier to move to, so it exhausts immediately, never
    attempting a "downgrade" to nowhere."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    downgrades: list = []
    sequenced_run_claude_headless(monkeypatch, shared, *([_exit_error("502 Bad Gateway")] * 4))
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="haiku", on_downgrade=downgrades.append)

    with pytest.raises(shared.GenerationExhausted):
        call("prompt", "foo.py", 1)

    assert len(downgrades) == 1
    assert downgrades[0].exhausted is True
    assert downgrades[0].to_model is None


def test_exhaustion_when_initial_model_is_unresolved_none(
    monkeypatch: pytest.MonkeyPatch,
):
    """``initial_model=None`` (resolve_model()'s "unspecified, let the CLI
    pick its own default" result) has no observable ladder position — it is
    NOT treated as equivalent to "opus" (#1908 review: that was an
    unverified assumption). The first downgrade attempt from ``None``
    exhausts immediately, with an accurate message naming the model as
    unspecified rather than a misleading "no further downgrade" framing
    (no downgrade was ever attempted in the first place)."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    downgrades: list = []
    sequenced_run_claude_headless(monkeypatch, shared, *([_exit_error("502 Bad Gateway")] * 4))
    call = shared.make_retrying_headless_call(
        sleep=lambda _s: None, initial_model=None, on_downgrade=downgrades.append
    )

    with pytest.raises(shared.GenerationExhausted) as exc_info:
        call("prompt", "foo.py", 1)

    assert len(downgrades) == 1
    assert downgrades[0].exhausted is True
    assert downgrades[0].to_model is None
    assert downgrades[0].from_model is None
    message = str(exc_info.value)
    assert "foo.py" in message
    assert "no downgrade ladder position" in message


def test_exhaustion_when_initial_model_is_unrecognized(
    monkeypatch: pytest.MonkeyPatch,
):
    """An operator-supplied model string outside {opus, sonnet, haiku} (e.g.
    ``--model claude-sonnet-4-5``) has no ladder position either — same
    "no known position" outcome and message shape as the unresolved-model
    case above, not the floor-specific wording (#1908 review)."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    downgrades: list = []
    sequenced_run_claude_headless(monkeypatch, shared, *([_exit_error("502 Bad Gateway")] * 4))
    call = shared.make_retrying_headless_call(
        sleep=lambda _s: None,
        initial_model="claude-sonnet-4-5",
        on_downgrade=downgrades.append,
    )

    with pytest.raises(shared.GenerationExhausted) as exc_info:
        call("prompt", "foo.py", 1)

    assert len(downgrades) == 1
    assert downgrades[0].exhausted is True
    assert downgrades[0].to_model is None
    assert downgrades[0].from_model == "claude-sonnet-4-5"
    message = str(exc_info.value)
    assert "claude-sonnet-4-5" in message
    assert "no downgrade ladder position" in message


def test_generation_exhausted_never_aborts_the_whole_process_uncaught(
    monkeypatch: pytest.MonkeyPatch,
):
    """The whole failure/surface path never aborts --all: a caller wrapping
    this in a per-file try/except (mirroring each --headless CLI's own
    main()) sees a normal, catchable RuntimeError — never an uncaught
    traceback — and can continue on to the next file."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    sequenced_run_claude_headless(monkeypatch, shared, *([_exit_error("502 Bad Gateway")] * 8))
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")

    outer_loop_continued = False
    try:
        call("prompt", "foo.py", 1)
    except RuntimeError:
        outer_loop_continued = True  # the --all driver moves on to the next file

    assert outer_loop_continued is True


# =============================================================================
# make_downgrade_audit_hook — the on_downgrade/get_label_override pair that
# carries a downgrade event into the commit-message audit trail (#1908 Step
# 3.2b). The live-output print (log()) already happens unconditionally
# inside make_retrying_headless_call above; this is the OTHER half —
# whether the printed event also reaches get_label_override() so a caller's
# RunContext.label_override_provider can thread it into a commit trailer.
# =============================================================================
def test_get_label_override_is_none_before_any_downgrade():
    _on_downgrade, get_label_override = shared.make_downgrade_audit_hook()
    assert get_label_override() is None


def test_on_downgrade_sets_a_label_naming_file_round_models_and_error_class():
    on_downgrade, get_label_override = shared.make_downgrade_audit_hook()
    event = shared.DowngradeEvent(
        source_file="foo.py",
        round_num=3,
        from_model="opus",
        to_model="sonnet",
        error_class="gateway-class",
        exhausted=False,
    )

    on_downgrade(event)

    label = get_label_override()
    assert label is not None
    assert "foo.py" in label
    assert "3" in label
    assert "opus" in label
    assert "sonnet" in label
    assert "gateway-class" in label


def test_on_downgrade_leaves_get_label_override_none_for_an_exhausted_event():
    """The exhausted ("no further downgrade") event never reaches a commit —
    GenerationExhausted is raised before generation returns — so it must not
    be recorded as a label override either."""
    on_downgrade, get_label_override = shared.make_downgrade_audit_hook()
    event = shared.DowngradeEvent(
        source_file="foo.py",
        round_num=5,
        from_model="haiku",
        to_model=None,
        error_class="gateway-class",
        exhausted=True,
    )

    on_downgrade(event)

    assert get_label_override() is None


def test_make_downgrade_audit_hook_wired_end_to_end_with_make_retrying_headless_call(
    monkeypatch: pytest.MonkeyPatch,
):
    """on_downgrade, passed straight through as make_retrying_headless_call's
    on_downgrade kwarg, drives get_label_override — the exact wiring each
    loop's make_headless_generator performs."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    on_downgrade, get_label_override = shared.make_downgrade_audit_hook()
    sequenced_run_claude_headless(
        monkeypatch, shared,
        *([_exit_error("502 Bad Gateway")] * 4),  # 3 fail + failed retry -> downgrade
        "ok-on-sonnet",
    )
    call = shared.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=on_downgrade)

    assert get_label_override() is None  # nothing before the call

    result = call("prompt", "foo.py", 3)

    assert result == "ok-on-sonnet"
    label = get_label_override()
    assert label is not None
    assert "opus" in label and "sonnet" in label and "foo.py" in label


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
