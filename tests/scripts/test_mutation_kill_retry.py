"""Pytest tests for mutation_kill_retry.py — the retry-then-downgrade policy
on repeated headless-generation failures (#1908), split out of
test_mutation_kill_shared.py (#1925) alongside the module extraction it
mirrors: mutation_kill_retry.py itself was carved out of mutation_kill_shared.py
once that module grew into a five-concern grab-bag.

Every scenario here still monkeypatches ``mutation_kill_shared.run_claude_headless``
(via ``sequenced_run_claude_headless(monkeypatch, shared, ...)``), never a
re-exported copy — ``mutation_kill_retry`` calls
``mutation_kill_shared.run_claude_headless``/``resolve_fallback_model`` through
the module object rather than a bound import, so a patch on
``mutation_kill_shared`` itself is what the retry closure actually observes at
call time (mirrors the identical contract ``mutation_kill_loop_python.py`` and
``mutation_kill_headless.py`` already rely on for their own re-exported names).
"""

from __future__ import annotations

import sys

import pytest
from _mutation_test_helpers import (
    SCRIPTS_DIR,
    gateway_error,
    sequenced_run_claude_headless,
)

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_retry as retry
import mutation_kill_shared as shared


# =============================================================================
# is_gateway_class_error — the exact 502/gateway-class error definition
# (#1908, Slice 3 Step 3.2).
# =============================================================================
def _exit_error(stderr: str) -> shared.HeadlessCallFailed:
    return gateway_error(stderr)


def _timeout_error() -> RuntimeError:
    return RuntimeError(
        "claude --print generation timed out after 300s (set "
        "DEV_TEAM_MUTATION_GENERATION_TIMEOUT_S to raise it)"
    )


@pytest.mark.parametrize(
    "marker",
    [
        "HTTP 502",
        "status: 503",
        "error code 504",
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
    assert retry.is_gateway_class_error(_exit_error(f"boom: {marker} boom")) is True


def test_is_gateway_class_error_is_false_for_the_timeout_shape():
    """The TimeoutExpired-derived shape is a local generation timeout, never
    an upstream provider signal — never gateway-class."""
    assert retry.is_gateway_class_error(_timeout_error()) is False


def test_is_gateway_class_error_is_false_for_an_unmatched_nonzero_exit():
    assert retry.is_gateway_class_error(_exit_error("permission denied")) is False


def test_is_gateway_class_error_is_false_for_a_bare_numeral_with_no_status_context():
    """A bare digit run with no status-context word (status/http/code) does
    not anchor — "request id 502391" must not false-positive on the "502"
    substring it happens to contain (#1938)."""
    assert retry.is_gateway_class_error(_exit_error("request id 502391 failed")) is False


def test_is_gateway_class_error_detects_a_marker_past_byte_500_of_stderr():
    """A gateway marker past byte 500 of stderr is no longer invisible: the
    classifier reads the full, untruncated HeadlessCallFailed.stderr, not
    __str__'s 500-byte-truncated message (#1938)."""
    padding = "x" * 550
    stderr = f"{padding} HTTP 502 {'y' * 50}"
    assert len(stderr) > 600
    assert retry.is_gateway_class_error(_exit_error(stderr)) is True


def test_is_gateway_class_error_returns_false_for_a_plain_runtime_error_with_marker_text():
    """The type gate — not just content — excludes a plain RuntimeError, even
    when its message contains a marker string verbatim (#1938)."""
    assert retry.is_gateway_class_error(RuntimeError("HTTP 502 Bad Gateway")) is False


def test_is_gateway_class_error_matches_a_lowercase_anchored_numeral_marker():
    assert retry.is_gateway_class_error(_exit_error("boom: http 502 boom")) is True


def test_is_gateway_class_error_status_gap_boundary_matches_at_exactly_12_chars():
    """Exactly 12 non-digit characters between the status word and the digits
    still matches the `[^0-9]{0,12}` gap bound (#1938)."""
    stderr = "status" + ("x" * 12) + "502"
    assert retry.is_gateway_class_error(_exit_error(stderr)) is True


def test_is_gateway_class_error_status_gap_boundary_does_not_match_at_13_chars():
    """One more non-digit character than the `[^0-9]{0,12}` gap bound no
    longer matches (#1938)."""
    stderr = "status" + ("x" * 13) + "502"
    assert retry.is_gateway_class_error(_exit_error(stderr)) is False


def test_generation_exhausted_is_a_runtime_error():
    """So the existing `except RuntimeError` handling in both --headless
    CLIs' main() (and any --all driver relying on the same taxonomy) catches
    it exactly like today's failed-revert/failed-commit RuntimeErrors — this
    file's exhaustion is reported and the process exits non-zero; it never
    surfaces as an uncaught traceback that would abort an outer --all run
    differently from any other per-file failure."""
    assert issubclass(retry.GenerationExhausted, RuntimeError)


# =============================================================================
# _RetryState — named, guarded transition methods (#1918, Slice 2 Step 2.1).
# =============================================================================
def test_spend_downgrade_sets_model_and_downgraded_on_a_fresh_state():
    state = retry._RetryState(model="opus")

    state.spend_downgrade("haiku")

    assert state.model == "haiku"
    assert state.downgraded is True


def test_spend_downgrade_raises_when_already_spent():
    state = retry._RetryState(model="sonnet", downgraded=True)

    with pytest.raises(RuntimeError):
        state.spend_downgrade("haiku")

    assert state.model == "sonnet"  # unchanged by the rejected call


def test_record_gateway_failure_returns_the_new_streak_count():
    state = retry._RetryState(model="opus")

    assert state.record_gateway_failure() == 1
    assert state.record_gateway_failure() == 2


def test_reset_streak_zeroes_the_counter_regardless_of_its_prior_value():
    state = retry._RetryState(model="opus", streak=2)

    state.reset_streak()

    assert state.streak == 0


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
    call = retry.make_retrying_headless_call(initial_model="opus", sleep=sleeps.append)

    result = call("prompt", "foo.py", 1)

    assert result == "generated-test"
    assert sleeps == [1, 2]


def test_backoff_default_sleep_parameter_is_the_real_time_sleep():
    """The public contract's default ``sleep`` is the real ``time.sleep`` —
    verified by introspection so this test never actually sleeps. A
    zero-failure call (any success path) never invokes ``sleep`` at all,
    which is exactly why the default is safe to leave unexercised here."""
    import inspect

    sig = inspect.signature(retry.make_retrying_headless_call)
    assert sig.parameters["sleep"].default is retry.time.sleep


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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(
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
    call = retry.make_retrying_headless_call(
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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call_a = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")
    call_a("prompt", "file-a.py", 1)  # file A downgrades to sonnet

    calls_b = sequenced_run_claude_headless(monkeypatch, shared, "ok-on-opus")
    call_b = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")
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

    call_a = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")
    call_b = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="haiku", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=downgrades.append)

    with pytest.raises(retry.GenerationExhausted) as exc_info:
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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="haiku", on_downgrade=downgrades.append)

    with pytest.raises(retry.GenerationExhausted):
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
    call = retry.make_retrying_headless_call(
        sleep=lambda _s: None, initial_model=None, on_downgrade=downgrades.append
    )

    with pytest.raises(retry.GenerationExhausted) as exc_info:
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
    call = retry.make_retrying_headless_call(
        sleep=lambda _s: None,
        initial_model="claude-sonnet-4-5",
        on_downgrade=downgrades.append,
    )

    with pytest.raises(retry.GenerationExhausted) as exc_info:
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
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus")

    outer_loop_continued = False
    try:
        call("prompt", "foo.py", 1)
    except RuntimeError:
        outer_loop_continued = True  # the --all driver moves on to the next file

    assert outer_loop_continued is True


# =============================================================================
# DowngradeEvent.exhausted — derived from to_model, not stored (#1918 Step
# 2.3). Proven by construction, not convention: the removed field must raise
# TypeError if passed explicitly, the same standard #1937's
# inspect.signature() tests applied.
# =============================================================================
def test_downgrade_event_exhausted_is_true_when_to_model_is_none():
    event = retry.DowngradeEvent(
        source_file="foo.py",
        round_num=5,
        from_model="haiku",
        to_model=None,
        error_class="gateway-class",
    )

    assert event.exhausted is True


def test_downgrade_event_exhausted_is_false_when_to_model_names_a_fallback():
    event = retry.DowngradeEvent(
        source_file="foo.py",
        round_num=3,
        from_model="opus",
        to_model="haiku",
        error_class="gateway-class",
    )

    assert event.exhausted is False


def test_downgrade_event_no_longer_accepts_an_explicit_exhausted_keyword():
    with pytest.raises(TypeError):
        retry.DowngradeEvent(
            source_file="foo.py",
            round_num=5,
            from_model="haiku",
            to_model=None,
            error_class="gateway-class",
            exhausted=True,
        )


# =============================================================================
# make_downgrade_audit_hook — the on_downgrade/get_label_override pair that
# carries a downgrade event into the commit-message audit trail (#1908 Step
# 3.2b). The live-output print (log()) already happens unconditionally
# inside make_retrying_headless_call above; this is the OTHER half —
# whether the printed event also reaches get_label_override() so a caller's
# RunContext.label_override_provider can thread it into a commit trailer.
# =============================================================================
def test_get_label_override_is_none_before_any_downgrade():
    _on_downgrade, get_label_override = retry.make_downgrade_audit_hook()
    assert get_label_override() is None


def test_on_downgrade_sets_a_label_naming_file_round_models_and_error_class():
    on_downgrade, get_label_override = retry.make_downgrade_audit_hook()
    event = retry.DowngradeEvent(
        source_file="foo.py",
        round_num=3,
        from_model="opus",
        to_model="sonnet",
        error_class="gateway-class",
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
    on_downgrade, get_label_override = retry.make_downgrade_audit_hook()
    event = retry.DowngradeEvent(
        source_file="foo.py",
        round_num=5,
        from_model="haiku",
        to_model=None,
        error_class="gateway-class",
    )

    on_downgrade(event)

    assert get_label_override() is None


def test_make_retrying_headless_call_uses_the_injected_call_headless_transport(
    monkeypatch: pytest.MonkeyPatch,
):
    """#1918 Step 2.2: when constructed with ``call_headless=<a fake>``, every
    generation attempt — the initial attempt AND the 3rd-failure retry
    attempt — goes through the fake, never
    ``mutation_kill_shared.run_claude_headless``. The full retry-then-downgrade
    policy (3-failure threshold, one retry, one downgrade) behaves
    identically to the default-transport case in
    ``test_failed_retry_downgrades_one_step_down_the_ladder`` above, driven
    through the injection point instead of monkeypatching the shared module."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)

    def poison(*args, **kwargs):
        raise AssertionError(
            "mutation_kill_shared.run_claude_headless must not be called "
            "when call_headless is injected"
        )

    monkeypatch.setattr(shared, "run_claude_headless", poison)

    logged: list[str] = []
    downgrades: list = []
    outcomes = [
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),
        _exit_error("502 Bad Gateway"),  # the retry — also fails -> downgrade
        "ok-on-sonnet",
    ]
    fake_calls: list[tuple[str, str | None]] = []

    def fake_call_headless(prompt, *, model=None, cwd=None):
        fake_calls.append((prompt, model))
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    call = retry.make_retrying_headless_call(
        sleep=lambda _s: None,
        initial_model="opus",
        log=logged.append,
        on_downgrade=downgrades.append,
        call_headless=fake_call_headless,
    )

    result = call("prompt", "foo.py", 3)

    assert result == "ok-on-sonnet"
    assert len(fake_calls) == 5
    assert fake_calls[-1][1] == "sonnet"
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


def test_make_downgrade_audit_hook_wired_end_to_end_with_make_retrying_headless_call(
    monkeypatch: pytest.MonkeyPatch,
):
    """on_downgrade, passed straight through as make_retrying_headless_call's
    on_downgrade kwarg, drives get_label_override — the exact wiring each
    loop's make_headless_generator performs."""
    monkeypatch.delenv("DEV_TEAM_MUTATION_FALLBACK_MODEL", raising=False)
    on_downgrade, get_label_override = retry.make_downgrade_audit_hook()
    sequenced_run_claude_headless(
        monkeypatch, shared,
        *([_exit_error("502 Bad Gateway")] * 4),  # 3 fail + failed retry -> downgrade
        "ok-on-sonnet",
    )
    call = retry.make_retrying_headless_call(sleep=lambda _s: None, initial_model="opus", on_downgrade=on_downgrade)

    assert get_label_override() is None  # nothing before the call

    result = call("prompt", "foo.py", 3)

    assert result == "ok-on-sonnet"
    label = get_label_override()
    assert label is not None
    assert "opus" in label and "sonnet" in label and "foo.py" in label

