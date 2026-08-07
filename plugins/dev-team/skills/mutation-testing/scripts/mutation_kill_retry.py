#!/usr/bin/env python3
"""mutation_kill_retry.py — retry-then-downgrade on repeated headless-generation
failures (#1908), extracted out of ``mutation_kill_shared.py`` (#1925).

``mutation_kill_shared.py`` had grown into a grab-bag of five separate
concerns (git revert/commit mechanics, the stop-round predicate, headless-CLI
invocation glue, this retry/downgrade policy, and the cross-language
``InsertOutcome``/``InsertionRefused`` shapes). A fix to git-revert semantics
and a fix to the downgrade ladder shared the same file and the same review
blast radius, with neither small enough to read in one pass and confirm it
doesn't touch the other's state. This module owns exactly the retry/downgrade
concern; ``mutation_kill_shared.py`` keeps git mechanics, ``_timeout_from_env``,
``stop_reason``, ``resolve_model``/``resolve_fallback_model`` and the headless
``claude --print`` invocation glue, and the ``InsertOutcome``/``InsertionRefused``
shapes.

The type precondition for the 502/gateway-class error definition is EXACT: a
:class:`mutation_kill_shared.HeadlessCallFailed` raised by
``run_claude_headless``'s non-zero-exit shape (never its
``TimeoutExpired``-derived shape, which raises a plain ``RuntimeError`` — a
local generation timeout, not an upstream provider signal). Within that type,
the classifier reads the full, untruncated ``stderr``, case-insensitively,
for either one of the non-numeric markers below or the anchored numeral
pattern (``_GATEWAY_STATUS_RE``) — a bare ``"502"``/``"503"``/``"504"``
substring is not enough on its own (#1938). That marker/regex match is a
best-effort heuristic, not an exhaustive one: it does not yet recognize
``error_code: 503``-style underscore-joined tokens, status 529, or errors
that only appear on stdout — filed and deliberately deferred rather than
fixed in this slice, see #1950.

This module's dependencies on ``mutation_kill_shared`` are
``run_claude_headless``/``resolve_fallback_model`` — both accessed via the
module object (``mutation_kill_shared.run_claude_headless(...)``), not a
``from ... import`` binding, so a test's ``monkeypatch.setattr(mutation_kill_shared,
"run_claude_headless", fake)`` takes effect here too (mirrors the existing
same-module-globals contract ``_mutation_test_helpers.sequenced_run_claude_headless``
already documents) — plus ``HeadlessCallFailed``, referenced only as a type
(``isinstance(exc, mutation_kill_shared.HeadlessCallFailed)``), which carries
no monkeypatch sensitivity of its own since nothing here calls it. (This
mirrors the dependency inventory documented from the other direction in
``mutation_kill_shared.py``'s own module docstring — keep the two in sync.)

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import mutation_kill_shared

_GATEWAY_CLASS_MARKERS = (
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "overloaded_error",
    "upstream connect error",
    "connection reset",
)

# Anchored numeral markers (#1938): a bare "502"/"503"/"504" substring
# false-positives on unrelated numbers (a request id, a byte count). Requires
# a status-context word (status/http/code) within 12 non-digit characters
# before the digits, so "HTTP 502", "status: 503", and "error code 504" all
# match but "request id 502391" does not. Case-insensitive to match the six
# non-numeric markers above.
_GATEWAY_STATUS_RE = re.compile(r"\b(?:status|http|code)[^0-9]{0,12}50[234]\b", re.IGNORECASE)

# 3 consecutive gateway-class failures on the same model earn exactly one
# same-model retry before a downgrade is considered (#1908).
_GATEWAY_FAILURE_THRESHOLD = 3

# Backoff formula for the pre-threshold retries: min(_BACKOFF_BASE **
# (streak - 1), _BACKOFF_CAP_S) seconds (#1908 review).
_BACKOFF_BASE = 2
_BACKOFF_CAP_S = 10


def is_gateway_class_error(exc: BaseException) -> bool:
    """True iff ``exc`` is a :class:`mutation_kill_shared.HeadlessCallFailed`
    raised by :func:`mutation_kill_shared.run_claude_headless`'s non-zero-exit
    shape whose full, untruncated ``stderr``, case-insensitively, contains a
    non-numeric gateway-class marker or matches the anchored numeral pattern
    (#1938).

    Everything else — a plain ``RuntimeError`` (the
    ``subprocess.TimeoutExpired``-derived shape is a local generation
    timeout, not an upstream provider signal, and never raises
    ``HeadlessCallFailed``) and a ``HeadlessCallFailed`` whose stderr matches
    none of the markers — is non-gateway-class.
    """
    if not isinstance(exc, mutation_kill_shared.HeadlessCallFailed):
        return False
    lowered = exc.stderr.lower()
    return any(marker in lowered for marker in _GATEWAY_CLASS_MARKERS) or bool(
        _GATEWAY_STATUS_RE.search(exc.stderr)
    )


# Shared exit code for a clean retry-then-downgrade exhaustion (#1908
# review) — "generation exhausted, not a fatal revert". Used by both
# headless CLIs' main() and stryker_shard_pipeline.py's shard driver so the
# meaning of "5" lives in one place instead of three duplicated literals.
EXIT_GENERATION_EXHAUSTED = 5


class GenerationExhausted(RuntimeError):
    """Raised when the fallback tier's own generation call also exhausts its
    3-consecutive-gateway-class-failures/1-same-model-retry budget (#1908).

    This file gets exactly one downgrade, ever — reaching this exception
    means no second downgrade will be attempted, regardless of whether the
    exhausted tier is the true ladder floor (``haiku``), a mid-ladder tier
    (e.g. ``sonnet``), or an operator override. Callers (the ``--headless``
    CLIs' ``main()``) already catch plain ``RuntimeError`` and report it via
    the existing exit-code taxonomy — this subclass needs no new handling,
    only a message that names the file, round, model, and error class, plus
    an explicit "no further downgrade will be attempted" statement.
    """


@dataclass(frozen=True)
class DowngradeEvent:
    """One downgrade (or final-exhaustion) decision from the
    retry-then-downgrade mechanism (#1908).

    This is the seam Step 3.2b's audit-trail write hangs off of: pass an
    ``on_downgrade`` callback to :func:`make_retrying_headless_call` (or
    :func:`make_headless_generator`) to record this event durably. Nothing
    in this module writes an audit trail itself yet.
    """

    source_file: str
    round_num: int | None
    from_model: str | None
    to_model: str | None
    error_class: str
    exhausted: bool = False


# Models with a defined ladder position — a downgrade that exhausts starting
# from one of these (haiku, the floor; or opus/sonnet, only reachable here
# after this file already spent its one downgrade) genuinely considered a
# downgrade and ran out of ladder, so the "no further downgrade" wording is
# accurate. ``None`` (unresolved) or any other model string (an operator
# override outside the ladder, e.g. an unrecognized --model value) never had
# a ladder position to begin with — a distinct, more honest message (#1908
# review).
_KNOWN_LADDER_MODELS = frozenset({"opus", "sonnet", "haiku"})


def _format_downgrade_message(event: DowngradeEvent) -> str:
    if event.exhausted:
        normalized_from = event.from_model.strip().lower() if event.from_model else None
        model_label = event.from_model if event.from_model is not None else "unspecified"
        if normalized_from in _KNOWN_LADDER_MODELS:
            return (
                f"generation for {event.source_file} (round {event.round_num}) "
                f"exhausted its retry budget on model {model_label!r} after "
                f"a {event.error_class} retry failure — no further downgrade "
                "will be attempted"
            )
        return (
            f"generation for {event.source_file} (round {event.round_num}) "
            f"exhausted its retry budget on model {model_label!r} after a "
            f"{event.error_class} retry failure — no downgrade ladder "
            "position available for this model, surfacing to operator"
        )
    return (
        f"downgrading generation for {event.source_file} (round "
        f"{event.round_num}) from {event.from_model!r} to {event.to_model!r} "
        f"after a {event.error_class} retry failure"
    )


@dataclass
class _RetryState:
    """Mutable per-file retry/downgrade state for one
    :func:`make_retrying_headless_call` closure (#1908 review).

    Replaces an untyped ``dict[str, object]`` that forced
    ``# type: ignore[arg-type]`` at two call sites and an ``int(...)`` cast on
    every streak read — a plain dataclass carries its own types, so neither
    workaround is needed. Not frozen: every field is mutated in place as the
    closure runs.
    """

    model: str | None
    streak: int = 0
    downgraded: bool = False

    def record_gateway_failure(self) -> int:
        """Increment the consecutive-gateway-failure streak and return the
        new count."""
        self.streak += 1
        return self.streak

    def reset_streak(self) -> None:
        """Zero the consecutive-gateway-failure streak."""
        self.streak = 0

    def spend_downgrade(self, to_model: str) -> None:
        """Spend this file's one-and-only downgrade, moving to ``to_model``.

        Raises :class:`RuntimeError` if this state has already spent its one
        downgrade — a file gets exactly one downgrade, ever (#1908).
        """
        if self.downgraded:
            raise RuntimeError(
                f"file already spent its one downgrade (current model {self.model!r})"
            )
        self.model = to_model
        self.downgraded = True


@dataclass(frozen=True)
class _RetryCallContext:
    """Call-invariant collaborators for one file's retry/downgrade closure
    (#1908 review). Bundles ``cwd``/``log``/``on_downgrade`` — none of which
    change between calls or rounds — so :func:`_retry_once_then_maybe_downgrade`
    takes one object instead of three separate keyword parameters."""

    cwd: Path | None
    log: Callable[[str], None]
    on_downgrade: Callable[[DowngradeEvent], None] | None


def _retry_once_then_maybe_downgrade(
    state: _RetryState,
    prompt: str,
    source_file: str,
    round_num: int | None,
    *,
    ctx: _RetryCallContext,
) -> str | None:
    """The 3rd-consecutive-failure branch: exactly one same-model retry, then
    decide downgrade-or-exhausted (#1908). Extracted out of
    :func:`make_retrying_headless_call`'s ``call`` closure to keep it under
    size/nesting/complexity thresholds — ``ctx`` carries the same
    ``on_downgrade``/``log``/``cwd`` the caller already has (passed
    explicitly, not captured by closure, so this function stays testable in
    isolation), and mutates ``state`` in place exactly as the inline branch
    it replaces did.

    Returns the retry's result string on a successful retry. Returns
    ``None`` when a downgrade was applied instead — the caller's
    ``while True`` loop re-enters :func:`mutation_kill_shared.run_claude_headless`
    on the new model. Raises :class:`GenerationExhausted` on exhaustion (no
    fallback tier available, or this file already spent its one downgrade).
    """
    already_downgraded = state.downgraded
    try:
        return mutation_kill_shared.run_claude_headless(prompt, model=state.model, cwd=ctx.cwd)
    except RuntimeError as retry_exc:
        error_class = (
            "gateway-class" if is_gateway_class_error(retry_exc) else "non-gateway-class"
        )
        from_model = state.model
        to_model = (
            None
            if already_downgraded
            else mutation_kill_shared.resolve_fallback_model(from_model)
        )
        event = DowngradeEvent(
            source_file=source_file,
            round_num=round_num,
            from_model=from_model,
            to_model=to_model,
            error_class=error_class,
            exhausted=to_model is None,
        )
        ctx.log(_format_downgrade_message(event))
        if ctx.on_downgrade is not None:
            ctx.on_downgrade(event)
        if to_model is None:
            raise GenerationExhausted(_format_downgrade_message(event)) from retry_exc
        state.spend_downgrade(to_model)
        return None


def make_retrying_headless_call(
    *,
    initial_model: str | None,
    cwd: Path | None = None,
    log: Callable[[str], None] = print,
    on_downgrade: Callable[[DowngradeEvent], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[str, str, int | None], str]:
    """Return a per-file, stateful wrapper around
    :func:`mutation_kill_shared.run_claude_headless` implementing the
    retry-then-downgrade rule (#1908): 3 consecutive gateway-class failures
    on the model in use earn exactly one same-model retry; if that retry
    ALSO fails (of any error class — the retry's own outcome is a plain
    pass/fail, never re-filtered by error class), this file spends its
    one-and-only downgrade and continues on the next ladder tier
    (:func:`mutation_kill_shared.resolve_fallback_model`). A success resets
    the consecutive-failure counter to 0; a non-gateway-class failure also
    resets it to 0 (it never counts toward the threshold, and it breaks an
    in-progress gateway-class streak). If the fallback tier's own budget is
    ALSO exhausted (or there is no fallback tier to move to), this raises
    :class:`GenerationExhausted` — no second downgrade is ever attempted.

    **This is all intra-call, not cross-round (#1908 review, correcting an
    earlier revision of this docstring/the plan).** Every retry and the
    at-most-one downgrade happen inside a single invocation of the returned
    ``call`` — the same ``generate()`` call one round makes. ``state``
    persists across rounds only because the closure itself does; for every
    ``RuntimeError``-mediated exit path (a return, or a raise) the streak is
    reset first, so no round mediated that way ever actually leaves a
    non-zero streak behind. A non-``RuntimeError`` escape from
    :func:`mutation_kill_shared.run_claude_headless` (e.g.
    ``FileNotFoundError``/``OSError`` if the CLI binary disappears mid-run)
    is NOT caught by the ``except RuntimeError`` below, so it skips the
    reset — but that escape is fatal to the process, so a residual streak
    from it is never observed. So while the counter is *structurally*
    shared across a file's rounds, in practice a partial streak never
    survives past one round's call — describing this as "carried across
    rounds" overstates what's observable.

    **Backoff between pre-threshold retries (#1908 review).** Silently
    retrying the 1st and 2nd consecutive gateway-class failures with zero
    delay let one ``generate()`` call fire up to 4 same-model attempts back
    to back at an already-overloaded upstream. ``sleep`` (real
    :func:`time.sleep` by default, injectable for tests) is now called with
    an increasing, capped delay — ``min(2 ** (streak - 1), 10)`` seconds —
    before each of those two retries (streak 1 -> ~1s, streak 2 -> ~2s). The
    3rd-failure same-model retry itself (handled by
    :func:`_retry_once_then_maybe_downgrade`) is unpaced — it already earned
    its attempt via the threshold, and a downgrade beyond it changes model,
    not just repeats the same call.

    **State ownership (Design & Architecture Critic's review, #1908).** The
    consecutive-failure counter, the model currently in use, and whether
    this file has already spent its one downgrade all live in THIS
    closure's :class:`_RetryState` — meant to be constructed once per file,
    inside each language loop's own ``make_headless_generator`` factory —
    never at module scope. :func:`mutation_kill_shared.run_claude_headless`
    itself stays the stateless, language-neutral single-shot call it
    already is; this wrapper adds retry/downgrade semantics entirely from
    the caller's side, so a new file's closure always starts fresh at the
    top of the ladder and concurrent files (each with their own closure)
    never leak state to one another.

    The returned callable takes ``(prompt, source_file, round_num)`` and
    returns the generated text — exactly what a single
    :func:`mutation_kill_shared.run_claude_headless` call would return.
    Every retry and downgrade happens transparently inside one call: neither
    loop's round machinery (``_run_round``/``run_for_file``) needs to
    change, since a call either eventually succeeds or raises (a plain
    ``RuntimeError`` for a non-gateway-class failure, unchanged from today;
    :class:`GenerationExhausted` only once the retry-then-downgrade budget
    is fully spent).
    """
    state = _RetryState(model=initial_model)
    ctx = _RetryCallContext(cwd=cwd, log=log, on_downgrade=on_downgrade)

    def call(prompt: str, source_file: str, round_num: int | None = None) -> str:
        while True:
            try:
                result = mutation_kill_shared.run_claude_headless(
                    prompt, model=state.model, cwd=ctx.cwd
                )
            except RuntimeError as exc:
                if not is_gateway_class_error(exc):
                    # Never counts toward the threshold, and breaks an
                    # in-progress gateway-class streak rather than being
                    # skipped over.
                    state.reset_streak()
                    raise
                current_streak = state.record_gateway_failure()
                if current_streak < _GATEWAY_FAILURE_THRESHOLD:
                    sleep(min(_BACKOFF_BASE ** (current_streak - 1), _BACKOFF_CAP_S))
                    continue  # transparently retry, same model
                # 3rd consecutive gateway-class failure: exactly one
                # same-model retry before considering downgrade.
                state.reset_streak()
                retry_result = _retry_once_then_maybe_downgrade(
                    state,
                    prompt,
                    source_file,
                    round_num,
                    ctx=ctx,
                )
                if retry_result is None:
                    continue  # downgraded — retry the 3-then-1 sequence on the new model
                return retry_result
            else:
                state.reset_streak()
                return result

    return call


def _format_downgrade_label(event: DowngradeEvent) -> str:
    """Compact ``Generator:`` audit-trailer label for a downgrade event
    (#1908 Step 3.2b) — the same four facts as :func:`_format_downgrade_message`
    (source file, round, from-model, to-model, error class), worded for a
    commit trailer rather than a live log line.
    """
    return (
        f"headless (downgraded {event.from_model!r} -> {event.to_model!r} "
        f"for {event.source_file} at round {event.round_num}, "
        f"{event.error_class})"
    )


def make_downgrade_audit_hook() -> (
    tuple[Callable[[DowngradeEvent], None], Callable[[], str | None]]
):
    """Return an ``(on_downgrade, get_label_override)`` pair that carries a
    downgrade event into the commit-message audit trail (#1908 Step 3.2b).

    ``RunContext.generator_label`` is ``frozen=True`` and set once per
    file's run, read unchanged by every round's commit — it cannot carry a
    downgrade's per-round dynamic content (from-model, to-model, round)
    without breaking that invariant. This pair is the seam instead:

    - Pass ``on_downgrade`` straight through as
      :func:`make_retrying_headless_call`'s ``on_downgrade`` kwarg —
      construct both, once per file, inside each language loop's own
      ``make_headless_generator`` factory (never at module scope, matching
      that function's own per-file state-ownership contract).
    - Wire ``get_label_override`` into ``RunContext.label_override_provider``
      so each loop's ``_commit_message`` passes its result to
      :func:`mutation_safety_gate.append_generator_trailer` as
      ``label_override`` — which wins over the frozen ``generator_label``
      whenever it is not ``None``.

    Before any downgrade, ``get_label_override()`` returns ``None`` and the
    frozen ``generator_label`` default is used, unchanged. The "exhausted, no
    further downgrade" event is deliberately NOT recorded here — no round
    ever completes after it (the caller raises :class:`GenerationExhausted`
    before generation returns), so there is nothing left to commit that
    override could ever reach.
    """
    state: dict[str, str | None] = {"label": None}

    def on_downgrade(event: DowngradeEvent) -> None:
        if event.exhausted:
            return
        state["label"] = _format_downgrade_label(event)

    def get_label_override() -> str | None:
        return state["label"]

    return on_downgrade, get_label_override
