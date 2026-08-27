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
no monkeypatch sensitivity of its own since nothing here calls it.
``run_claude_headless`` is reached on every generation attempt unless the
caller injects ``call_headless`` (#1918), in which case it is never reached —
see :meth:`_RetryCallContext.resolve_call_headless`. (This
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

# Anchored numeral markers (#1938, widened by #1950): a bare "502"/"503"/"504"
# substring false-positives on unrelated numbers (a request id, a byte count).
# Requires a status-context word (status/http/code) close before the digits, so
# "HTTP 502", "status: 503", and "error code 504" all match but
# "request id 502391" does not.
#
# Three #1950 corrections to the original `\b(?:status|http|code)[^0-9]{0,12}50[234]\b`:
#
# 1. `\b` REJECTED UNDERSCORE-JOINED KEYS. `_` is a `\w` character, so `\b`
#    requires a NON-word character immediately before status/http/code — and
#    the `_c` in `error_code: 503` and the `rC` in `errorCode=504` are both
#    word-to-word transitions. Underscore- and camel-joined status keys are
#    routine in real provider payloads. The lookbehind is now
#    `(?<![A-Za-z0-9])`, which treats `_` (and a camel boundary) as a
#    separator while still refusing to match inside a longer alphanumeric run.
# 2. `HTTP/1.1 502` FAILED because the version token puts digits in the gap,
#    which `[^0-9]{0,12}` forbids. An optional `/<major>[.<minor>]` is now
#    consumed explicitly rather than by widening the gap to allow digits —
#    widening would have re-admitted exactly the "request id 502391" class
#    #1938 anchored the pattern to exclude.
# 3. STATUS 529 (Anthropic's own overload code) was absent from the numeral
#    alternation. The downgrade ladder this policy drives is Anthropic-specific,
#    so 529 is plausibly the most common real "retry me" signal this classifier
#    will ever see. It was covered only via the `overloaded_error` marker
#    string, which a rendered `API Error: 529 Overloaded` does not contain
#    verbatim.
#
# The trailing `(?![0-9])` replaces `\b` for the same reason as the lookbehind,
# and still rejects "502391" (the `2` is followed by `3`).
#
# 4. A CAMEL-JOINED key (`errorCode=504`) still fails a plain lookbehind: the
#    `rC` transition is letter-to-letter, and the pattern is IGNORECASE so the
#    lookbehind cannot itself distinguish case. Rather than relaxing the
#    lookbehind to allow any preceding letter — which would admit "barcode 502"
#    and "decode 503" — camel humps are split to `_` first, reducing the camel
#    case to the underscore case already handled.
# 5. `error` joins the context words so a rendered `API Error: 529 Overloaded`
#    anchors at all; it carries none of status/http/code. The trailing
#    `(?![0-9])` keeps this from admitting "error after 5024 ms".
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_GATEWAY_STATUS_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:status|http|code|error)(?:/\d+(?:\.\d+)?)?"
    r"[^0-9]{0,12}(?:50[234]|529)(?![0-9])",
    re.IGNORECASE,
)


def _anchorable(text: str) -> str:
    """Normalize camel humps to `_` so a camel-joined status key anchors.

    Pure and deterministic: `errorCode=504` -> `error_Code=504`, which the
    pattern's `(?<![A-Za-z0-9])` lookbehind then accepts.
    """
    return _CAMEL_SPLIT_RE.sub("_", text)

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
    # #1950: classify over stderr AND stdout. The claude CLI renders some
    # upstream failures to stdout while stderr carries only a generic
    # non-zero-exit line; a stderr-only classifier calls those non-gateway-class
    # and spends the file's whole budget on a genuinely retryable overload.
    # `getattr` rather than attribute access so a HeadlessCallFailed built by
    # an older two-argument call site (or a test fake) still classifies.
    combined = f"{exc.stderr}\n{getattr(exc, 'stdout', '') or ''}"
    lowered = combined.lower()
    return any(marker in lowered for marker in _GATEWAY_CLASS_MARKERS) or bool(
        _GATEWAY_STATUS_RE.search(_anchorable(combined))
    )


# Shared exit code for the clean-continuable outcome class (#1908 review):
# either a fully spent retry-then-downgrade budget (GenerationExhausted) or
# any other provably-clean-of-inserted-content generation/infrastructure
# failure that isn't a failed revert. Used by both headless CLIs' main() and
# stryker_shard_pipeline.py's shard driver so the meaning of "5" lives in one
# place instead of three duplicated literals.
#
# EXIT_CLEAN_UNFIXED is the primary, outcome-shaped name (#1956): the value
# has named two distinct causes since #1939 (true GenerationExhausted, or any
# other clean RuntimeError such as a generation timeout), and the original
# name only describes one of them. EXIT_GENERATION_EXHAUSTED is kept as an
# alias — same value, zero behavior change — because every existing call
# site (stryker_shard_pipeline.py, mutation_kill_headless.py,
# mutation_kill_loop_python.py) and their tests already import it by that
# name; renaming those call sites too was judged not worth the diff for a
# purely cosmetic rename with no behavior change (#1956 explicitly frames
# this as "consider," not a mandate). New code should prefer
# EXIT_CLEAN_UNFIXED.
EXIT_CLEAN_UNFIXED = 5
EXIT_GENERATION_EXHAUSTED = EXIT_CLEAN_UNFIXED

# Shared exit code for the fatal, working-tree-possibly-mutated outcome class
# (#1930): a failed revert (or a failed-commit round-abandonment's own
# revert) leaves the tree in an unknown state. Used by both headless CLIs'
# main() functions so the meaning of "4" lives in one place instead of two
# duplicated literals. stryker_shard_pipeline.py's shard driver never
# imports this constant — it decodes exit 4 by exclusion (any non-zero,
# non-EXIT_GENERATION_EXHAUSTED exit is treated as fatal) and only names "4"
# in prose/log wording.
EXIT_REVERT_FAILED = 4


class GenerationExhausted(RuntimeError):
    """Raised when the fallback tier's own generation call also exhausts its
    3-consecutive-gateway-class-failures/1-same-model-retry budget (#1908).

    This file gets exactly one downgrade, ever — reaching this exception
    means no second downgrade will be attempted, regardless of whether the
    exhausted tier is the true ladder floor (``haiku``), a mid-ladder tier
    (e.g. ``sonnet``), or an operator override. Callers (the ``--headless``
    CLIs' ``main()``) catch this subclass ahead of ``RevertFailed`` and the
    generic ``RuntimeError`` and report it via the existing exit-code
    taxonomy — the message names the file, round, model, and error class,
    plus an explicit "no further downgrade will be attempted" statement.
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
    #: Whether this file had ALREADY spent its one downgrade before this
    #: failure. #1952: on an exhausted event this is the actual reason the
    #: caller computed and then discarded, forcing
    #: :func:`_format_downgrade_message` to re-infer it from a proxy (is
    #: ``from_model`` a known ladder model?) that a valid non-ladder
    #: ``--model``/``DEV_TEAM_MUTATION_FALLBACK_MODEL`` override defeats.
    #: Defaulted so every existing construction keeps working; the one
    #: internal call site sets it explicitly.
    already_downgraded: bool = False

    @property
    def exhausted(self) -> bool:
        """True iff no fallback tier was available — derived from
        ``to_model`` rather than stored separately, so the two can never
        disagree (#1918 Step 2.3)."""
        return self.to_model is None


def _format_downgrade_message(event: DowngradeEvent) -> str:
    source_file = " ".join(str(event.source_file).split())
    if event.exhausted:
        model_label = event.from_model if event.from_model is not None else "unspecified"
        # #1952: branch on the reason the caller actually computed, not on
        # whether from_model happens to be a ladder name. `fable` is a VALID
        # --model / DEV_TEAM_MUTATION_FALLBACK_MODEL override that deliberately
        # has no _MODEL_DOWNGRADE_LADDER entry, so a file that started on opus,
        # downgraded once to fable, and then exhausted was reported as "no
        # downgrade ladder position available for this model" when the true
        # cause was "this file already spent its one downgrade".
        if event.already_downgraded:
            return (
                f"generation for {source_file} (round {event.round_num}) "
                f"exhausted its retry budget on model {model_label!r} after "
                f"a {event.error_class} retry failure — no further downgrade "
                "will be attempted"
            )
        return (
            f"generation for {source_file} (round {event.round_num}) "
            f"exhausted its retry budget on model {model_label!r} after a "
            f"{event.error_class} retry failure — no downgrade ladder "
            "position available for this model, surfacing to operator"
        )
    return (
        f"downgrading generation for {source_file} (round "
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
    takes one object instead of three separate keyword parameters.

    ``call_headless`` is ``None`` when the caller didn't inject a transport
    (#1918 Step 2.2) — :meth:`resolve_call_headless` looks up
    ``mutation_kill_shared.run_claude_headless`` fresh on every actual call,
    not once here at construction time, so a test that monkeypatches the
    module attribute *after* constructing the closure (but before invoking
    it) still observes the patch — exactly the dynamic-lookup contract the
    pre-injection code had via its direct
    ``mutation_kill_shared.run_claude_headless(...)`` call sites."""

    cwd: Path | None
    log: Callable[[str], None]
    on_downgrade: Callable[[DowngradeEvent], None] | None
    call_headless: Callable[..., str] | None

    def resolve_call_headless(self) -> Callable[..., str]:
        """Return the injected transport, or
        ``mutation_kill_shared.run_claude_headless`` looked up dynamically
        via the module object when none was injected."""
        return (
            self.call_headless
            if self.call_headless is not None
            else mutation_kill_shared.run_claude_headless
        )

    def invoke(self, prompt: str, model: str | None) -> str:
        """Call the resolved transport with this context's ``cwd`` — the one
        call expression both :func:`_retry_once_then_maybe_downgrade` and
        :func:`make_retrying_headless_call`'s ``call`` closure need, so it's
        defined once instead of duplicated verbatim at both sites (#1938
        review)."""
        return self.resolve_call_headless()(prompt, model=model, cwd=self.cwd)


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
        return ctx.invoke(prompt, state.model)
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
            already_downgraded=already_downgraded,
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
    call_headless: Callable[..., str] | None = None,
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

    **Injectable transport (#1918 Step 2.2).** ``call_headless`` defaults to
    ``None``, resolved by :meth:`_RetryCallContext.resolve_call_headless` to
    :func:`mutation_kill_shared.run_claude_headless` fresh on every actual
    generation attempt rather than once here at construction time — a
    signature-level default (``call_headless: Callable[..., str] =
    mutation_kill_shared.run_claude_headless``) would bind that reference
    once, at module-import time, and a construction-time resolution would
    still be a single stale snapshot; either way, a test's
    ``monkeypatch.setattr(mutation_kill_shared, "run_claude_headless", fake)``
    made after this factory returns its closure (but before the closure is
    invoked) would silently miss the patch (this module's own docstring
    dependency-inventory note above depends on the module-attribute lookup
    staying dynamic on every call, matching the pre-injection code's direct
    ``mutation_kill_shared.run_claude_headless(...)`` call sites). Every
    generation attempt this closure makes — the initial attempt and the
    3rd-failure same-model retry — goes through ``call_headless``, so a test
    can also substitute a fake transport directly via this parameter without
    monkeypatching the shared module at all. ``resolve_fallback_model`` is
    unaffected — it stays a direct
    :func:`mutation_kill_shared.resolve_fallback_model` reference.
    """
    state = _RetryState(model=initial_model)
    ctx = _RetryCallContext(cwd=cwd, log=log, on_downgrade=on_downgrade, call_headless=call_headless)

    def call(prompt: str, source_file: str, round_num: int | None = None) -> str:
        while True:
            try:
                result = ctx.invoke(prompt, state.model)
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
