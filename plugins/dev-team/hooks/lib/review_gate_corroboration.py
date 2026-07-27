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

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple, Optional

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths  # noqa: E402
import metrics_query  # noqa: E402

_LEDGER_STREAM_NAME = "boundary-events.jsonl"
_EVENT_TYPE = "agent_dispatch_ledger"
_DECISION = "record"

# The doc-only short-circuit's exemption event (#1461): emitted directly by
# `skills/code-review/SKILL.md`'s doc-only write site via
# `boundary_events.py`'s CLI, not by a PreToolUse hook — see that module's
# `_main()` docstring.
_DOC_ONLY_HOOK = "code-review"
_DOC_ONLY_DECISION = "bypass"
_DOC_ONLY_RULE = "doc-only-review-exempt"

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class LedgerEvidence(NamedTuple):
    """Full corroboration-read result — everything a caller needs to pick
    the correct one of the pinned rejection messages (Step 1.3, #1461).

    Attributes:
        agents_in_window: distinct registered review-agent names
            (`matched_rule` values) dispatched inside the recency window.
            Empty on any read failure or when nothing qualifies.
        any_dispatch_ever: True if at least one genuine `"record"` event
            exists anywhere in the ledger, regardless of the recency
            window — lets the caller tell "stale evidence" (dispatches
            happened, just outside the window) apart from "no dispatch
            evidence" (none ever recorded). False on any read failure.
        read_failure_reason: `None` when the ledger was read successfully
            (whether or not it has qualifying entries); `"missing"` or
            `"unreadable"` when it could not be read at all — see module
            docstring for what each means.
    """

    agents_in_window: frozenset
    any_dispatch_ever: bool
    read_failure_reason: Optional[str]


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


def evaluate(cwd, before_ts: str, window_seconds: int) -> LedgerEvidence:
    """Single-read-pass corroboration evaluation — the primary entry point.

    `before_ts` anchors the recency window (typically the gate file's own
    mtime, converted via `mtime_to_iso`); qualifying dispatches must fall in
    `(before_ts - window_seconds, before_ts]`, inclusive of both bounds via
    `metrics_query.filter_entries`'s `since`/`until` semantics.
    """
    entries, failure = _read_ledger(cwd)
    if failure is not None:
        return LedgerEvidence(frozenset(), False, failure)

    dispatches = list(
        metrics_query.filter_entries(entries, event_type=_EVENT_TYPE, gate_outcome=_DECISION)
    )
    any_ever = any(isinstance(e.get("matched_rule"), str) for e in dispatches)

    since = _since_bound(before_ts, window_seconds)
    in_window = metrics_query.filter_entries(dispatches, since=since, until=before_ts)
    agents = frozenset(
        e["matched_rule"] for e in in_window if isinstance(e.get("matched_rule"), str)
    )
    return LedgerEvidence(agents, any_ever, None)


def distinct_review_agent_dispatches(cwd, before_ts: str, window_seconds: int) -> set:
    """Distinct registered review-agent names dispatched inside the recency
    window before `before_ts`. Pinned convenience signature (#1461 plan) —
    see `evaluate()` for the fuller result a caller needs to distinguish a
    "ledger read failure" rejection from a "no dispatch evidence" or "stale
    evidence" one.

    Fails CLOSED: any read failure returns an empty set — see module
    docstring.
    """
    return set(evaluate(cwd, before_ts, window_seconds).agents_in_window)


def has_doc_only_exemption(cwd, before_ts: str, window_seconds: int) -> bool:
    """True if the doc-only short-circuit's `"doc-only-review-exempt"`
    bypass event was recorded inside the recency window before `before_ts`
    — the doc-only path's auditable alternative to dispatch-ledger evidence
    (#1461). Fails CLOSED like every other read in this module: any read
    failure returns False, same as "no exemption found".
    """
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
    return any(e.get("matched_rule") == _DOC_ONLY_RULE for e in matched)


__all__ = (
    "LedgerEvidence",
    "distinct_review_agent_dispatches",
    "evaluate",
    "has_doc_only_exemption",
    "mtime_to_iso",
)
