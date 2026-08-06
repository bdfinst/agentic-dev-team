"""hooks/lib/review_gate_corroboration.py — fail-CLOSED dispatch-ledger
corroboration reader for the review-corroboration gate (#1461).

Read by `hooks/pre_pr_review.py`'s `.pr-review-passed` gate (#1886) — the
gate's hash-match check alone proves the branch-diff content hasn't changed
since that file was written; it does NOT prove an independent review
actually produced that write (see `hooks/lib/review_gate_hash.py`'s own
docstring for the full account of that residual gap). This module reads
`hooks/agent_dispatch_ledger.py`'s `"record"` events from
`.claude/metrics/boundary-events.jsonl` to corroborate that a hash-matching
write was backed by genuine, recent, distinct review-agent dispatches.
(`hooks/pre_commit_review.py`'s own `.review-passed` gate was this module's
original consumer at #1461; that hook is now a documented no-op — see its
own module docstring — following #1886's PR-time gate migration. This
module's own `evaluate()`/`has_doc_only_exemption()`/
`has_single_agent_exemption()` transferred to the new gate as-is; the
cosmetic-delta carry-forward machinery specific to the old commit-time gate
— `evaluate_cosmetic_carry_forward()`, `distinct_normalized_dispatches()`,
`distinct_review_agent_dispatches()`, `CosmeticCarryForwardEvidence` — was
deleted in #1904 once confirmed to have zero remaining production callers.)

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
hooks (destructive_guard, verify_guard, pre_pr_review, telemetry,
context_ceiling_guard, ...), so in any real session that reaches a `gh pr
create` attempt the file will almost always already exist — its total absence is
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

# `dispatch_failure_agents` (#1904 item 2) is modeled as `frozenset | None` —
# `None` means "cannot prove no dispatch failure exists" (a ledger or
# registry read failure); a `frozenset()` means "provably no dispatch
# failures"; a non-empty frozenset names the failing agents. Prior to this,
# the unprovable case was smuggled into the frozenset value space as a fake
# sentinel MEMBER (`_UNPROVABLE_DISPATCH_FAILURE`, a string no real agent
# name could equal) — a control state encoded inside the value type, guarded
# only by an `==`/`any(...)` check and caller convention rather than the type
# system. Modeling it as `None` instead mirrors `_registered_agents()`'s own
# `frozenset | None` pattern (#1461/#1866) and makes "cannot prove this" and
# "no registered review agents" the same *shape* of unprovable-ness, checked
# with `is None` rather than an equality comparison against a magic value.

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
            dispatch clears it, never the clock. Empty `frozenset()` on a
            successful read with no qualifying dispatch-failure events.
            `None` on a ledger OR registry READ FAILURE (#1904 item 2) —
            "cannot prove no dispatch failure exists" — never collapsed to
            an empty/all-clear set.

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
    dispatch_failure_agents: frozenset | None


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


def _registered_agents() -> frozenset | None:
    """Re-validate against the live registry at READ time too (#1461 security
    review), not just at write time in `agent_dispatch_ledger.py` — defense
    in depth against a stale ledger (written by an older plugin version, or
    copied from another checkout) supplying names no longer registered.

    Delegates to `review_agent_registry.read_registered_review_agent_names()`
    (#1904 item 1), which owns the read-failure-vs-empty distinction this
    function used to implement locally — see that function's own docstring
    for the full "why `None` vs `frozenset()`" account. `None` on any read
    error, never an empty frozenset (#1763 correctness/security review):
    "registry read failed" and "registry read fine, genuinely zero agents
    registered" require OPPOSITE treatment depending on which side of the
    evidence they narrow (see `_agents_with_unsuperseded_failure`, which
    checks for `None` explicitly rather than treating it as "no agents
    registered").
    """
    return review_agent_registry.read_registered_review_agent_names(
        review_agent_registry.default_agents_dir()
    )


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


def _extract_timeline_entries(entries: list, decision: str, ts_sentinel: str) -> list:
    """Build `(ts, agent, decision)` tuples for one entry kind — shared by
    both loops in `_agents_with_unsuperseded_failure` (#1799), which
    duplicated this exact loop body twice, differing only in the ts-less
    sentinel default and the `decision` constant.

    `ts_sentinel` is the value substituted when an entry has no usable
    `ts` (resolved via `metrics_query`'s own `_TS_FIELDS` fallback, never a
    bare `entry.get("ts")`, and never a raw non-str value). Records and
    failures pass opposite sentinels on purpose — see
    `_agents_with_unsuperseded_failure`'s own docstring for the rationale;
    this helper is deliberately unopinionated about which sentinel is
    "correct" and just applies whatever the caller passes.
    """
    result = []
    for entry in entries:
        agent = entry.get("matched_rule")
        if not isinstance(agent, str):
            continue
        ts = metrics_query._first_present(entry, metrics_query._TS_FIELDS)
        ts = ts if isinstance(ts, str) else ts_sentinel
        result.append((ts, agent, decision))
    return result


def _agents_with_unsuperseded_failure(
    records: list, failures: list, registered: frozenset | None
) -> frozenset | None:
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
    is a real `frozenset()`) fails CLOSED by returning `None` immediately
    (#1904 item 2: modeled as `frozenset | None` rather than a fake sentinel
    MEMBER of the frozenset value space), without inspecting `records`/
    `failures` at all (#1763 security/correctness review). Filtering
    negative evidence through an empty set here — the same collapse that
    safely narrows `agents_in_window` — would instead WIDEN the gate: every
    genuine dispatch-failure would be excluded by "not in an empty set",
    producing an all-clear indistinguishable from "provably no failures".

    An entry with no usable `ts` (checked via `metrics_query`'s own
    `_TS_FIELDS` fallback, the same resolution `filter_entries` already
    applies elsewhere in this module — not a bare `entry.get("ts")`, which
    would silently miss a `timestamp`-keyed entry, and never a raw non-str
    value, which would otherwise crash the sort below on a mixed-type
    comparison) is likewise never dropped, and the two entry KINDS are
    defaulted in OPPOSITE directions on purpose: a ts-less **failure**
    sorts as `"￿"` (after every real ISO timestamp), so it can never
    be superseded by anything — the safe default for negative evidence we
    cannot chronologically place. A ts-less **record** sorts as `""`
    (before every real timestamp), so it can never supersede a real
    failure — the safe default for positive evidence we cannot place. Do
    NOT default both kinds to the same sentinel (an earlier draft used
    `ts or ""` for both, which let ANY ts-bearing record silently supersede
    a ts-less failure — the opposite of "ordered last, never superseded"
    this docstring promises; #1763 correctness review).

    Live-registry re-validated (`registered`) exactly like `agents_in_window`
    — an unregistered/fabricated agent name is excluded, so a forged event
    can only ever narrow evidence, never widen it.
    """
    if registered is None:
        return None

    # A ts-less (or non-str-ts) RECORD defaults to the minimum sort key
    # ("") — it can never supersede a real failure, the safe default for
    # positive evidence we cannot chronologically place. A ts-less FAILURE
    # defaults to the maximum sort key ("￿" sorts after every real
    # ISO-8601 timestamp string) — it can never be superseded, the safe
    # default for negative evidence we cannot chronologically place.
    # Deliberately the OPPOSITE default from the record case.
    timeline = _extract_timeline_entries(records, _DECISION, "")
    timeline += _extract_timeline_entries(failures, _DISPATCH_FAILURE_DECISION, "￿")
    timeline.sort(key=lambda item: item[0])

    latest_decision: dict = {}
    for _ts, agent, decision in timeline:
        latest_decision[agent] = decision

    return frozenset(
        agent
        for agent, decision in latest_decision.items()
        if decision == _DISPATCH_FAILURE_DECISION and agent in registered
    )


def _binding_evidence(
    dispatches: list,
    failures: list,
    since: str,
    before_ts: str,
    registered: frozenset | None,
) -> tuple:
    """Compute `(agents_in_window, dispatch_failure_agents)` from dispatch/
    failure entries ALREADY narrowed to one hash binding by the caller.

    Shared by `evaluate()` and `evaluate_cosmetic_carry_forward()` (once per
    hash binding it evaluates) — each independently re-implemented this exact
    window-filter + positive-frozenset + `_agents_with_unsuperseded_failure`
    sequence before this extraction (#1836 perf finding), which risked the
    fail-closed positive/negative asymmetry — `registered_for_positive`'s
    `None`-to-empty collapse is safe ONLY for positive evidence, never for
    negative — silently drifting out of sync across independently
    maintained copies.
    """
    in_window = metrics_query.filter_entries(dispatches, since=since, until=before_ts)
    registered_for_positive = registered if registered is not None else frozenset()
    agents = frozenset(
        e["matched_rule"]
        for e in in_window
        if isinstance(e.get("matched_rule"), str) and e["matched_rule"] in registered_for_positive
    )
    dispatch_failure_agents = _agents_with_unsuperseded_failure(dispatches, failures, registered)
    return agents, dispatch_failure_agents


def _load_ledger_pipeline(cwd, before_ts: str, window_seconds: int) -> tuple:
    """Shared read-ledger -> since-bound -> registered-agents -> filtered-
    dispatches/failures pipeline (#1799) — `evaluate()` and
    `evaluate_cosmetic_carry_forward()` each independently re-implemented
    this exact sequence before this extraction.

    Returns `(failure, since, registered, all_dispatches, all_failures)`.
    `failure` is `None` on a successful ledger read; when it is non-`None`
    (`"missing"`/`"unreadable"` — see `_read_ledger`'s own docstring), every
    other element is `None` and the caller must build its own fail-closed
    result immediately, matching each function's own `LedgerEvidence`/
    `CosmeticCarryForwardEvidence` shape — this helper does not build either
    result type itself, since the two callers' failure shapes differ.
    """
    entries, failure = _read_ledger(cwd)
    if failure is not None:
        return failure, None, None, None, None
    since = _since_bound(before_ts, window_seconds)
    registered = _registered_agents()
    all_dispatches = list(
        metrics_query.filter_entries(entries, event_type=_EVENT_TYPE, gate_outcome=_DECISION)
    )
    all_failures = list(
        metrics_query.filter_entries(
            entries, event_type=_DISPATCH_FAILURE_HOOK, gate_outcome=_DISPATCH_FAILURE_DECISION
        )
    )
    return None, since, registered, all_dispatches, all_failures


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
    failure, since, registered, all_dispatches, all_failures = _load_ledger_pipeline(
        cwd, before_ts, window_seconds
    )
    if failure is not None:
        return LedgerEvidence(frozenset(), False, False, failure, None)

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

    # Dispatch-failure negative evidence (#1763) — unbounded by the recency
    # window, per the field's own docstring. `dispatches` above is already
    # narrowed to THIS subject_hash and carries every qualifying "record"
    # regardless of age, so it doubles as the "records" side of the
    # supersession comparison with no extra filtering needed.
    same_subject_failures = [e for e in all_failures if e.get("subject_hash") == subject_hash]
    agents, dispatch_failure_agents = _binding_evidence(
        dispatches, same_subject_failures, since, before_ts, registered
    )

    return LedgerEvidence(agents, any_ever, same_subject_ever, None, dispatch_failure_agents)


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
    "evaluate",
    "has_doc_only_exemption",
    "has_single_agent_exemption",
    "mtime_to_iso",
)
