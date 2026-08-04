"""hooks/lib/review_gate_corroboration.py — fail-CLOSED dispatch-ledger
corroboration reader for the `.review-passed` gate (#1461).

`hooks/pre_commit_review.py`'s existing hash-match check proves the staged
content hasn't changed since `.review-passed` was written — it does NOT
prove an independent review actually produced that write (see
`hooks/lib/review_gate_hash.py`'s own docstring for the full account of that
residual gap). This module reads `hooks/agent_dispatch_ledger.py`'s
`"record"` events from `.claude/metrics/boundary-events.jsonl` to
corroborate that a hash-matching write was backed by genuine, recent,
distinct review-agent dispatches.

Kept as a separate sibling module rather than folded into
`review_gate_hash.py` (design feedback, #1461): `review_gate_hash.py` is
deliberately minimal — a single pure hash function with no registry or
metrics-stream knowledge. This module's registry-cross-referencing,
metrics-reading responsibility is a different concern and belongs on its own;
each module's docstring names the other so the split stays intentional, not
accidental.

Built on `hooks/lib/metrics_query.py`'s existing generic JSONL
reader/filter (`load_stream` + `filter_entries`) rather than a bespoke
second parser — this repo already has one malformed-line-tolerant reader for
exactly this metrics-directory shape.

FAIL-CLOSED (the deliberate opposite of `hooks/lib/boundary_events.py`'s own
fail-open write side): any inability to prove genuine dispatch happened —
a missing ledger file, an unreadable one, or genuinely no qualifying
entries — is treated the same way a security gate must treat "can't prove
it" — as "didn't happen". `boundary_events.py` fails open on the *write*
side because a broken telemetry write must never block a real tool call;
this module fails closed on the *read* side because a broken/absent
corroboration read must never let an uncorroborated `.review-passed` write
pass the gate. Do not "fix" this asymmetry to match the write side — it is
intentional; see `boundary_events.py`'s own module docstring for its side of
the contrast.

A missing `boundary-events.jsonl` is bucketed as a **read failure**, not as
"genuinely no entries": that stream is written by many always-on guard
hooks (destructive_guard, verify_guard, pre_commit_review, telemetry,
context_ceiling_guard, ...), so in any real session that reaches a commit
attempt the file will almost always already exist — its total absence is
itself a signal that hook registration is broken, which is an infra
problem the caller should surface distinctly from "the ledger is fine, it
just has no qualifying dispatches". Malformed *individual* JSON lines are
NOT a read failure here — matching `metrics_query.load_stream`'s own
documented precedent, a single corrupt line is skipped, never fatal, and
every other consumer of that stream relies on the same tolerance. "Unreadable"
covers a ledger file that exists but can't be read as text at all (permission
error, undecodable bytes, or the path is not a regular file).

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import metrics_query
import review_agent_registry
from boundary_events import TS_FORMAT as _TS_FORMAT

_LEDGER_STREAM_NAME = "boundary-events.jsonl"
_EVENT_TYPE = "agent_dispatch_ledger"
_DECISION = "record"

# Dispatch-failure negative evidence (#1763): emitted by
# `hooks/lib/boundary_events.py`'s `--event dispatch-failure` CLI (a
# different hook/tool/decision tuple than the "record" events above — see
# that module's `_CLI_AGENT_EVENTS`) when a dispatched review agent still
# fails to return a contract-valid result after its single retry.
_DISPATCH_FAILURE_HOOK = "code-review"
_DISPATCH_FAILURE_DECISION = "dispatch-failure"

# Fail-CLOSED sentinel for `dispatch_failure_agents` on a ledger READ
# FAILURE (missing/unreadable): an empty frozenset there would read as
# "provably no dispatch failures" — the opposite of what a read failure
# actually tells us. "Cannot prove no failure exists" is treated the same
# as "a failure exists", matching this module's own fail-closed contract
# for positive evidence. Not a real registered agent name — a placeholder
# that can never equal a genuine `matched_rule` value, so downstream
# consumers can only ever over-block on it, never mistake it for a
# legitimate named agent.
_UNPROVABLE_DISPATCH_FAILURE = frozenset(
    {"<ledger-read-failure: cannot prove no dispatch failure>"}
)

# The doc-only / single-agent short-circuit exemption events (#1461): emitted
# directly by `skills/code-review/SKILL.md`'s write sites via
# `boundary_events.py`'s purpose-locked CLI (`--event doc-only` /
# `--event single-agent`), not by a PreToolUse hook — see that module's
# `_main()` docstring and its `_CLI_EVENTS` mapping.
_DOC_ONLY_HOOK = "code-review"
_DOC_ONLY_DECISION = "bypass"
_DOC_ONLY_RULE = "doc-only-review-exempt"
_SINGLE_AGENT_RULE = "single-agent-review-exempt"


class LedgerEvidence(NamedTuple):
    """Full corroboration-read result — everything a caller needs to pick
    the correct one of the pinned rejection messages (Step 1.3, #1461).

    Attributes:
        agents_in_window: distinct registered review-agent names
            (`matched_rule` values) dispatched inside the recency window,
            for THIS subject_hash. Empty on any read failure or when
            nothing qualifies.
        any_dispatch_ever: True if at least one genuine `"record"` event
            exists anywhere in the ledger, for ANY subject_hash, regardless
            of the recency window. False on any read failure.
        same_subject_dispatch_ever: True if at least one genuine `"record"`
            event exists anywhere in the ledger for THIS SAME subject_hash,
            regardless of the recency window (#1461 second security
            re-review) — distinguishes genuinely STALE evidence (a review
            of this exact content happened, just too long ago) from
            evidence that only exists for DIFFERENT staged content
            (`any_dispatch_ever` true but this one false): the caller picks
            the "outside the window" message only when this is true, and a
            "reviewed different content" message when it's false but
            `any_dispatch_ever` is true — otherwise "outside the window"
            would misreport a same-window dispatch for unrelated content as
            if it were this content, just late. False on any read failure.
        read_failure_reason: `None` when the ledger was read successfully
            (whether or not it has qualifying entries); `"missing"` or
            `"unreadable"` when it could not be read at all — see module
            docstring for what each means.
        dispatch_failure_agents: registered review-agent names (live-
            registry re-validated, same as `agents_in_window`) whose MOST
            RECENT qualifying event for THIS `subject_hash` — comparing
            "record" events against "dispatch-failure" events (#1763) by
            each event's own `ts` — is a dispatch-failure rather than a
            later "record"; a later "record" for that same agent+hash
            supersedes and removes it from this set, regardless of either
            event's age. Deliberately UNBOUNDED by `window_seconds`, unlike
            `agents_in_window`: a genuine, never-fixed dispatch-failure
            coverage gap for this exact staged content must not silently
            expire just because time passed — only a genuine superseding
            dispatch clears it, never the clock. Empty on a successful read
            with no qualifying dispatch-failure events. On a ledger READ
            FAILURE, this is the non-empty `_UNPROVABLE_DISPATCH_FAILURE`
            sentinel, never an empty/all-clear set — see that constant.

            KNOWN RESIDUAL GAP (#1763 security review, same class as
            `agent_dispatch_ledger.py`'s own disclosed gap): the superseding
            "record" is a PreToolUse dispatch-START signal, not proof the
            new dispatch itself returned a valid result — `record` events
            fire before any result exists, the same property that made the
            original dispatch-failure mechanism necessary in the first
            place. A gate check that lands in the narrow window between a
            re-dispatch's own "record" and its eventual outcome (success:
            nothing new emitted; failure: a fresh dispatch-failure event)
            could therefore see a stale failure as already-superseded. Not
            fixed here: doing so would need a completion signal this
            harness has no way to emit today, and the plan's own adversarial
            review (three rounds) deliberately chose "superseded by ANY
            later record, regardless of age" as this field's semantics —
            narrowing it now would reopen a settled design decision, not
            fix an implementation bug. Disclosed rather than silently
            assumed away, matching this codebase's own convention for a
            residual gap that raises the bar without claiming to close it.
    """

    agents_in_window: frozenset
    any_dispatch_ever: bool
    same_subject_dispatch_ever: bool
    read_failure_reason: str | None
    dispatch_failure_agents: frozenset


def mtime_to_iso(mtime: float) -> str:
    """Convert a `Path.stat().st_mtime` epoch float to this stream's
    `%Y-%m-%dT%H:%M:%SZ` UTC timestamp format.

    Shared here (rather than duplicated in `pre_commit_review.py`) so the
    gate hook and this module never drift on timestamp formatting — the
    hook anchors `before_ts` on `.claude/memory/.review-passed`'s own mtime
    and must format it identically to how every emitter in this repo
    stamps `ts` (confirmed against `boundary_events.py`).
    """
    return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(_TS_FORMAT)


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, _TS_FORMAT).replace(tzinfo=timezone.utc)


def _since_bound(before_ts: str, window_seconds: int) -> str:
    return (_parse_ts(before_ts) - timedelta(seconds=window_seconds)).strftime(_TS_FORMAT)


def _ledger_path(cwd) -> Path:
    base = Path(cwd) if cwd else Path.cwd()
    # Read-only: migrate=False so a corroboration read never migrates a
    # legacy file or creates .claude/metrics/ as a side effect.
    return artifact_paths.resolve_file("metrics", _LEDGER_STREAM_NAME, base, migrate=False)


def _agents_dir() -> Path:
    # hooks/lib/review_gate_corroboration.py -> hooks/lib -> hooks -> plugin
    # root -> agents. Matches `agent_dispatch_ledger.py`'s own
    # `_agents_dir_default()` exactly — the review-agent roster lives in the
    # plugin's own fixed file set, not in the target project's `cwd`.
    return _LIB_DIR.parent.parent / "agents"


def _registered_agents() -> frozenset | None:
    """Re-validate against the live registry at READ time too (#1461 security
    review), not just at write time in `agent_dispatch_ledger.py` — defense
    in depth against a stale ledger (written by an older plugin version, or
    copied from another checkout) supplying names no longer registered.

    Returns `None` on any read error — deliberately NOT an empty frozenset
    (#1763 correctness/security review). "Registry read failed" and
    "registry read fine, genuinely zero agents registered" must stay
    distinguishable to callers, because the two require OPPOSITE treatment
    depending on which side of the evidence they narrow: for POSITIVE
    evidence (`agents_in_window`), a caller may safely collapse `None` to an
    empty set — narrowing corroboration can only ever narrow, never widen,
    what counts as a passing gate. For NEGATIVE evidence
    (`dispatch_failure_agents`), collapsing `None` to empty would WIDEN the
    gate instead — every genuine dispatch-failure would be filtered out by
    an empty "registered" set, producing an all-clear indistinguishable from
    "provably no dispatch failures", exactly the reading
    `_UNPROVABLE_DISPATCH_FAILURE` exists to prevent. See
    `_agents_with_unsuperseded_failure`, which checks for `None` explicitly
    rather than treating it as "no agents registered".
    """
    try:
        return review_agent_registry.registered_review_agent_names(_agents_dir())
    except Exception:  # noqa: BLE001 - caller decides how to fail closed for its own evidence direction
        return None


def _read_ledger(cwd) -> tuple:
    """Return `(entries, failure_reason)`.

    `failure_reason` is `None` on a successful read (file exists and is
    decodable — even if it yields zero entries); `"missing"` when the
    ledger file does not exist; `"unreadable"` when it exists but raised on
    read. See module docstring for the missing-vs-unreadable rationale and
    why malformed individual lines are not a failure here.
    """
    path = _ledger_path(cwd)
    if not path.is_file():
        return [], "missing"
    try:
        entries = list(metrics_query.load_stream(path))
    except (OSError, UnicodeDecodeError):
        return [], "unreadable"
    return entries, None


def _agents_with_unsuperseded_failure(
    records: list, failures: list, registered: frozenset | None
) -> frozenset:
    """Per agent, compare the most recent qualifying event — a "record" from
    `records` or a "dispatch-failure" from `failures`, both already narrowed
    to the SAME `subject_hash` by the caller — by each event's own `ts`,
    unbounded by any recency window (#1763; see `LedgerEvidence.
    dispatch_failure_agents` for the rationale). Returns the agents whose
    most-recent event is a dispatch-failure; a later "record" for that same
    agent removes it, regardless of either event's age. On an exact `ts` tie
    the dispatch-failure wins (fail CLOSED), since `records` is folded into
    the timeline before `failures` and Python's sort is stable.

    `registered` being `None` (a registry READ FAILURE, per
    `_registered_agents()` — never "genuinely zero agents registered", which
    is a real `frozenset()`) fails CLOSED by returning
    `_UNPROVABLE_DISPATCH_FAILURE` immediately, without inspecting `records`/
    `failures` at all (#1763 security/correctness review). Filtering
    negative evidence through an empty set here — the same collapse that
    safely narrows `agents_in_window` — would instead WIDEN the gate: every
    genuine dispatch-failure would be excluded by "not in an empty set",
    producing an all-clear indistinguishable from "provably no failures".

    An entry with no usable `ts` (checked via `metrics_query`'s own
    `_TS_FIELDS` fallback, the same resolution `filter_entries` already
    applies elsewhere in this module — not a bare `entry.get("ts")`, which
    would silently miss a `timestamp`-keyed entry) is likewise never
    dropped: it is treated as unsuperseded evidence (ordered last, so it
    can never itself be superseded within this call) rather than excluded
    from the timeline, so a malformed line degrades negative evidence
    toward "more failures visible", never fewer.

    Live-registry re-validated (`registered`) exactly like `agents_in_window`
    — an unregistered/fabricated agent name is excluded, so a forged event
    can only ever narrow evidence, never widen it.
    """
    if registered is None:
        return _UNPROVABLE_DISPATCH_FAILURE

    timeline = []
    for entry in records:
        agent = entry.get("matched_rule")
        if not isinstance(agent, str):
            continue
        ts = metrics_query._first_present(entry, metrics_query._TS_FIELDS) or ""
        timeline.append((ts, agent, _DECISION))
    for entry in failures:
        agent = entry.get("matched_rule")
        if not isinstance(agent, str):
            continue
        ts = metrics_query._first_present(entry, metrics_query._TS_FIELDS) or ""
        timeline.append((ts, agent, _DISPATCH_FAILURE_DECISION))
    # A missing ts sorts as "" (before every real timestamp), which alone
    # would make it easy to supersede rather than hard to — but paired with
    # placing failures after records in the append order above and Python's
    # stable sort, a ts-less failure still lands after any ts-less record
    # for the same agent, so it is never silently superseded by one.
    timeline.sort(key=lambda item: item[0])

    latest_decision: dict = {}
    for _ts, agent, decision in timeline:
        latest_decision[agent] = decision

    return frozenset(
        agent
        for agent, decision in latest_decision.items()
        if decision == _DISPATCH_FAILURE_DECISION and agent in registered
    )


def evaluate(cwd, before_ts: str, window_seconds: int, subject_hash: str) -> LedgerEvidence:
    """Single-read-pass corroboration evaluation — the primary entry point.

    `before_ts` anchors the recency window (typically the gate file's own
    mtime, converted via `mtime_to_iso`); qualifying dispatches must fall in
    `(before_ts - window_seconds, before_ts]`, inclusive of both bounds via
    `metrics_query.filter_entries`'s `since`/`until` semantics.

    `subject_hash` (#1461 security review) is `.review-passed`'s own
    `review_gate_hash()` value — required, not optional. Dispatch events are
    stamped with the `review_gate_hash()` value in effect at dispatch time
    (`agent_dispatch_ledger.py`); only events whose `subject_hash` matches
    THIS gate's current hash count as evidence. Without this, a genuine
    review of one changeset (file A) would satisfy the gate for an unrelated
    later changeset (file B) staged and self-hashed within the same recency
    window — this binds "a review happened recently" to "a review of THIS
    staged content happened recently". An event missing `subject_hash`
    entirely (e.g. written before this field existed) never matches.

    Also re-validates each dispatch's `matched_rule` against the LIVE
    registered-agent set (`_registered_agents()`), not just trusting
    whatever the ledger says — defense in depth against a stale or
    hand-edited ledger.
    """
    entries, failure = _read_ledger(cwd)
    if failure is not None:
        return LedgerEvidence(frozenset(), False, False, failure, _UNPROVABLE_DISPATCH_FAILURE)

    all_dispatches = list(
        metrics_query.filter_entries(entries, event_type=_EVENT_TYPE, gate_outcome=_DECISION)
    )
    # `any_ever` intentionally reads the UNFILTERED dispatch set (#1461
    # security review) — it means "a genuine dispatch exists somewhere in
    # the ledger, for ANY subject", which is what `_STALE_MESSAGE` vs
    # `_NO_DISPATCH_MESSAGE` needs to distinguish. Computing it after the
    # subject_hash narrowing below would silently redefine it to "a
    # dispatch for THIS exact hash exists somewhere" — collapsing the
    # common, legitimate case (a real review of slightly different staged
    # content) into the same "no dispatch ever" message a genuinely
    # unreviewed changeset gets.
    any_ever = any(isinstance(e.get("matched_rule"), str) for e in all_dispatches)
    dispatches = [e for e in all_dispatches if e.get("subject_hash") == subject_hash]
    # Same-subject existence, independent of the recency window (#1461
    # second security re-review) — see the LedgerEvidence docstring for why
    # this must be tracked separately from `any_ever`.
    same_subject_ever = any(isinstance(e.get("matched_rule"), str) for e in dispatches)

    since = _since_bound(before_ts, window_seconds)
    in_window = metrics_query.filter_entries(dispatches, since=since, until=before_ts)
    registered = _registered_agents()
    # `registered_for_positive`: a registry-read failure (`None`) collapses
    # to empty here — safe for POSITIVE evidence, since narrowing can only
    # ever narrow (never widen) what counts as corroboration. `registered`
    # itself (possibly `None`) is passed through unchanged to
    # `_agents_with_unsuperseded_failure` below, which needs to distinguish
    # "read failed" from "genuinely zero agents" for NEGATIVE evidence.
    registered_for_positive = registered if registered is not None else frozenset()
    agents = frozenset(
        e["matched_rule"]
        for e in in_window
        if isinstance(e.get("matched_rule"), str) and e["matched_rule"] in registered_for_positive
    )

    # Dispatch-failure negative evidence (#1763) — unbounded by the recency
    # window, per the field's own docstring. `dispatches` above is already
    # narrowed to THIS subject_hash and carries every qualifying "record"
    # regardless of age, so it doubles as the "records" side of the
    # supersession comparison with no extra filtering needed.
    same_subject_failures = [
        e
        for e in metrics_query.filter_entries(
            entries, event_type=_DISPATCH_FAILURE_HOOK, gate_outcome=_DISPATCH_FAILURE_DECISION
        )
        if e.get("subject_hash") == subject_hash
    ]
    dispatch_failure_agents = _agents_with_unsuperseded_failure(
        dispatches, same_subject_failures, registered
    )

    return LedgerEvidence(agents, any_ever, same_subject_ever, None, dispatch_failure_agents)


def distinct_review_agent_dispatches(
    cwd, before_ts: str, window_seconds: int, subject_hash: str
) -> set:
    """Distinct registered review-agent names dispatched inside the recency
    window before `before_ts`, bound to `subject_hash`. Pinned convenience
    signature (#1461 plan) — see `evaluate()` for the fuller result a caller
    needs to distinguish a "ledger read failure" rejection from a "no
    dispatch evidence" or "stale evidence" one.

    Fails CLOSED: any read failure returns an empty set — see module
    docstring.
    """
    return set(evaluate(cwd, before_ts, window_seconds, subject_hash).agents_in_window)


def distinct_normalized_dispatches(
    cwd, before_ts: str, window_seconds: int, subject_hash_normalized: str
) -> tuple:
    """Distinct registered review-agent names dispatched inside the recency
    window before `before_ts` whose `subject_hash_normalized` matches (#1627),
    paired with the unbounded-by-window dispatch-failure agent set for that
    same normalized hash (#1763).

    Returns `(agents_in_window, dispatch_failure_agents)`, both `frozenset` —
    a PUBLIC, `__all__`-exported interface change from the prior bare `set`
    return; the sole caller (`pre_commit_review.py`'s
    `_cosmetic_carry_forward_verdict`) unpacks the tuple.

    Same fail-CLOSED posture and same live-registry re-validation as
    `evaluate()` — this is the raw-hash query with one field swapped, not a
    weaker check. An empty or falsy `subject_hash_normalized` matches nothing:
    events written before that field existed carry no value for it, and
    treating "both sides absent" as a match would let any pre-#1627 ledger
    corroborate any changeset. A ledger read failure returns
    `(frozenset(), _UNPROVABLE_DISPATCH_FAILURE)` — fail CLOSED on the
    negative-evidence side exactly like `evaluate()`.

    `boundary_events.py`'s `--event dispatch-failure` CLI stamps both
    `subject_hash` and `subject_hash_normalized` on the events it writes
    (`SKILL.md` Step 4 and `sliced-mode.md` both compute and pass the
    normalized hash alongside the raw one), so `dispatch_failure_agents`
    here reflects genuine data on this path, not only the read-failure
    sentinel.
    """
    if not subject_hash_normalized:
        return frozenset(), frozenset()
    entries, failure = _read_ledger(cwd)
    if failure is not None:
        return frozenset(), _UNPROVABLE_DISPATCH_FAILURE
    dispatches = [
        e
        for e in metrics_query.filter_entries(
            entries, event_type=_EVENT_TYPE, gate_outcome=_DECISION
        )
        if e.get("subject_hash_normalized") == subject_hash_normalized
    ]
    since = _since_bound(before_ts, window_seconds)
    in_window = metrics_query.filter_entries(dispatches, since=since, until=before_ts)
    registered = _registered_agents()
    # `registered_for_positive`: a registry-read failure (`None`) collapses
    # to empty here — safe for POSITIVE evidence, since narrowing can only
    # ever narrow (never widen) what counts as corroboration. `registered`
    # itself (possibly `None`) is passed through unchanged to
    # `_agents_with_unsuperseded_failure` below, which needs to distinguish
    # "read failed" from "genuinely zero agents" for NEGATIVE evidence.
    registered_for_positive = registered if registered is not None else frozenset()
    agents = frozenset(
        e["matched_rule"]
        for e in in_window
        if isinstance(e.get("matched_rule"), str) and e["matched_rule"] in registered_for_positive
    )

    same_subject_failures = [
        e
        for e in metrics_query.filter_entries(
            entries, event_type=_DISPATCH_FAILURE_HOOK, gate_outcome=_DISPATCH_FAILURE_DECISION
        )
        if e.get("subject_hash_normalized") == subject_hash_normalized
    ]
    dispatch_failure_agents = _agents_with_unsuperseded_failure(
        dispatches, same_subject_failures, registered
    )

    return agents, dispatch_failure_agents


def _has_exemption(cwd, before_ts: str, window_seconds: int, subject_hash: str, rule: str) -> bool:
    entries, failure = _read_ledger(cwd)
    if failure is not None:
        return False
    since = _since_bound(before_ts, window_seconds)
    matched = metrics_query.filter_entries(
        entries,
        event_type=_DOC_ONLY_HOOK,
        gate_outcome=_DOC_ONLY_DECISION,
        since=since,
        until=before_ts,
    )
    return any(
        e.get("matched_rule") == rule and e.get("subject_hash") == subject_hash for e in matched
    )


def has_doc_only_exemption(cwd, before_ts: str, window_seconds: int, subject_hash: str) -> bool:
    """True if the doc-only short-circuit's `"doc-only-review-exempt"`
    bypass event was recorded inside the recency window before `before_ts`,
    bound to `subject_hash` — the doc-only path's auditable alternative to
    dispatch-ledger evidence (#1461). Fails CLOSED like every other read in
    this module: any read failure returns False, same as "no exemption
    found". The `subject_hash` requirement means an exemption emitted for
    one changeset cannot be replayed to pass the gate for a different one.
    """
    return _has_exemption(cwd, before_ts, window_seconds, subject_hash, _DOC_ONLY_RULE)


def has_single_agent_exemption(cwd, before_ts: str, window_seconds: int, subject_hash: str) -> bool:
    """True if `--agent <name>`'s `"single-agent-review-exempt"` bypass
    event was recorded inside the recency window before `before_ts`, bound
    to `subject_hash` (#1461) — a sanctioned single-agent `/code-review`
    run only ever dispatches 1 distinct agent, which can never clear the
    `>= 2` distinct-dispatch floor on its own; this exemption keeps that
    documented workflow from regressing to an always-blocked gate. Fails
    CLOSED like every other read in this module.
    """
    return _has_exemption(cwd, before_ts, window_seconds, subject_hash, _SINGLE_AGENT_RULE)


__all__ = (
    "LedgerEvidence",
    "distinct_normalized_dispatches",
    "distinct_review_agent_dispatches",
    "evaluate",
    "has_doc_only_exemption",
    "has_single_agent_exemption",
    "mtime_to_iso",
)
