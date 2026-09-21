#!/usr/bin/env python3
"""subagent_completion_guard.py — SubagentStop transcript-tail classifier (#2188).

Step 2.1a's research findings (below, preserved verbatim as the source citation
for the classifier Step 2.1b implements after them) confirmed the real
transcript-level shape of a subagent's completion against 70 real subagent
transcripts from this session. Step 2.1b (this implementation) turns those
findings into `classify_stop()`.

## Contract (docs/python-hook-contract.md)

    Input : SubagentStop JSON on stdin (`transcript_path`, `session_id`, `cwd`)
    Output: one `boundary-events.jsonl` "warn" record via
        `hooks/lib/boundary_events.emit_boundary_event` for the two
        non-clean, explainable classifications (`empty-final-turn`,
        `truncated-final-turn`); nothing emitted for `clean` or
        `unreadable` (Step 2.2, see `_EMIT_CLASSIFICATIONS`).
    Posture: record-only and fail-open. Any error -> exit 0 silently.

Stdlib-only (json/pathlib/sys). See ADR 0014, ADR 0015.

## What was confirmed, and how

Primary source: this session's own subagent dispatch transcripts on disk at
    ~/.claude/projects/<project-slug>/<session-id>/subagents/agent-<hash>.jsonl
(+ a sibling agent-<hash>.meta.json per dispatch). 70 completed subagent transcripts were
inspected directly (not recalled/guessed) — this is real, live harness output from
Claude Code 2.1.278, not documentation. No web-doc citation was needed or used since a
real transcript was reachable, per this step's own instructions.

Compared against `hooks/cost_meter.py` (reads `transcript_path` from the hook payload,
checks `.is_file()`, does not itself parse rows — delegates to
`hooks/lib/cost_meter.py record`) and `hooks/task_completion_metrics.py` (reads
`payload.get("stop_reason")` — informational only, never branches on it) for how
existing SubagentStop hooks already touch this payload, and against
`hooks/context_ceiling_guard.py`'s `_tail_lines`/`_is_sidechain`/`_measure_occupancy`
(lines 270-424) for the tail-reading and sidechain-row pattern.

## Finding 1 — where a subagent's own transcript lives, and what "sidechain" means here

A subagent's transcript is a SEPARATE file from the orchestrator/main-thread session
file, not inlined into it: `<session>.jsonl` (main thread) has a sibling
`<session>/subagents/agent-<hash>.jsonl` per dispatched subagent (confirmed: the main
thread's own `<session>.jsonl` had zero `"isSidechain":true` rows across 7798 lines,
while every row inside a per-agent `subagents/agent-*.jsonl` file is
`"isSidechain":true`). This matches Step 2.1b's own plan text precisely: for a
SubagentStop payload, the "sidechain" rows `context_ceiling_guard.py` excludes when
scanning the MAIN thread are exactly the subagent's own transcript rows when read from
its own file — nothing needs excluding when reading a subagent's transcript directly.

## Finding 2 — message.stop_reason IS present, but is null far more often than not

`message.stop_reason` uses the same field name and the same Anthropic Messages API
values (`end_turn` | `max_tokens` | `stop_sequence` | `tool_use`) as main-thread rows —
confirmed directly (e.g. a mid-turn row with `stop_reason:"tool_use"` on a finalized
tool_use block). However, across the true LAST row of 70 completed subagent transcripts:

    stop_reason == null        -> 61/70 (87%)
    stop_reason == "end_turn"  -> 8/70  (11%)
    stop_reason == "tool_use"  -> 1/70  (this session's own still-in-progress transcript
                                          at the time of sampling, not a stopped turn)
    stop_reason == "max_tokens" or "stop_sequence" -> 0/70 (no real example seen either
                                          way; both remain unverified against a real
                                          transcript — Anthropic's documented contract is
                                          the only source for those two values)

All 61 `null` cases were genuinely clean, complete hand-backs (e.g. "Report delivered.",
"Report delivered to caller.", "Handed back: skip — no `.feature` files..."), not
truncated or errored ones — content was well-formed, non-empty text every time. A
classifier that treats "clean" as `stop_reason in ("end_turn", "tool_use")` on the final
row alone will misclassify the large majority of real clean completions. Step 2.1b's
classifier needs "non-empty content AND stop_reason != 'max_tokens'" as the clean
signal, not a stop_reason allow-list — `null` must be treated as equivalent to clean,
not as an unhandled case. (This finding was outside Step 2.1a's edit mandate, which was
scoped to the malformed-hand-back scenario only, so the plan's Gherkin "Clean
completion" `Given` clause text was left unedited — flagged here and in the plan's
Risks & Open Questions section for Step 2.1b to account for.)

## Finding 3 — SubagentHandback is a real, distinguishable tool_use block

`SubagentHandback` (the tool a dispatched subagent calls to report back to its caller,
per this session's own system-prompt tool description) shows up as a genuine
`{"type":"tool_use","name":"SubagentHandback","input":{"message": "..."}}` block — 69
real occurrences found across the 70 transcripts. It is a real, greppable signal beyond
bare stop_reason+content.

It is essentially NEVER the transcript's true final row, though: every real example
followed the same shape — `tool_use` (SubagentHandback, stop_reason "tool_use") ->
`tool_result` (ack) -> one more short assistant text turn (stop_reason usually null, see
Finding 2) such as "Report delivered." That final wrap-up turn, not the SubagentHandback
call itself, is the transcript's real last row on a clean path.

## Finding 4 — "malformed hand-back" has no reliable, unique transcript-level signal

Zero of the 69 real `SubagentHandback` calls were malformed (none missing/empty the
required `message` field), and zero `tool_result` rows tied to a `SubagentHandback`
`tool_use_id` were flagged `is_error`. Structurally: the tool schema requires `message`
as a string parameter, so a call missing it would almost certainly be rejected at the
tool-call-validation layer before ever being persisted as a "call with a missing
field" — producing a generic `is_error` tool_result indistinguishable in shape from any
other tool's error (a bad `Read` path, a failed `Bash` command, etc.), not a
hand-back-specific signature. Combined with Finding 3 (the call is essentially never the
final row anyway, so "final turn contains a hand-back-shaped call" doesn't match the
real shape), there is no way to build the plan's original "Malformed hand-back" scenario
against real evidence rather than a guess.

**Decision (per this step's own instruction): the "Malformed hand-back" Gherkin
scenario and its corresponding Acceptance Criteria bullet are DROPPED, not rescoped.**
Recorded against issue #2188 (epic #2172) — its Gherkin block, Acceptance Criteria
bullet, and Risks & Open Questions entry were revised to match, in the same commit-set
as this file's header.

## Classification precedence (#2188 Step 2.1b — stated explicitly here so two
## implementers can't disagree)

1. Unreadable/missing transcript, or a readable transcript whose last row is
   missing an expected `message`/`content` field entirely (structurally
   malformed, not just "empty") -> fail-open, `"unreadable"`, no event.
2. `message.stop_reason == "max_tokens"` -> `"truncated-final-turn"`. Checked
   BEFORE the empty-content check: a token-limit cutoff can itself produce
   empty/near-empty content (Finding 2 notes no real `max_tokens` example was
   seen, but the Messages API contract still governs it), and `stop_reason` is
   the more specific, intentional signal, so it wins the overlap case.
3. Empty/whitespace-only final assistant content, with `stop_reason` anything
   other than `"max_tokens"` (including the common `null` case, per Finding 2)
   -> `"empty-final-turn"`.
4. Otherwise (including `stop_reason: null` with non-empty content, and
   `stop_reason: "end_turn"`/`"tool_use"` with non-empty content) -> `"clean"`.

No "malformed hand-back" branch: Finding 4 above found no reliable,
uniquely-identifying transcript-level signal for it, and the plan's Gherkin
scenario for it was dropped rather than built against a guess.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event  # type: ignore[import-not-found]
from stdin_json import read_stdin_json  # type: ignore[import-not-found]

StopClassification = Literal[
    "clean", "empty-final-turn", "truncated-final-turn", "unreadable"
]

# Classifications that warrant a boundary event (#2188 Step 2.2). "clean" and
# "unreadable" are both no-ops: "clean" is the expected happy path (nothing to
# record), and "unreadable" has no reliable transcript-level signal to name a
# rule for (see Finding 4 above) -- emitting a matched_rule for a case this
# hook itself can't explain would be a fabricated-confidence event, so it
# stays silent like every other fail-open path in this hook.
_EMIT_CLASSIFICATIONS: frozenset[StopClassification] = frozenset(
    {"empty-final-turn", "truncated-final-turn"}
)


def _tail_lines(path: Path, n: int = 50) -> list[str]:
    """Read the last `n` lines of `path`. Fail-safe: [] on any IO error.

    Deliberately a small, private, inline copy for this hook rather than
    `hooks/lib/context_ceiling_guard.py`'s private `_tail_lines`, or
    `scripts/lib/session_log/records.py`'s `iter_file_records` (the
    sanctioned shared transcript-row reader two sibling hooks already use
    over the documented hooks/ -> scripts/lib/session_log/ edge — see
    `context_ceiling_guard.py`'s own "why this is safe" note). Not reused
    here because the semantics genuinely differ: `iter_file_records` streams
    forward and silently skips an undecodable line, continuing to the next
    one, while this hook needs "the transcript's true LAST line is malformed
    JSON" to classify as its own distinct outcome (`"unreadable"`, see
    `_last_row` below) rather than silently falling back to an earlier valid
    row. A skip-and-continue streaming reader cannot express that
    distinction, so this hook keeps its own minimal last-row reader (#2188
    Step 2.1b).
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    return lines[-n:] if len(lines) > n else lines


def _last_row(transcript_path: str) -> dict | None:
    """Return the transcript's true last JSON row as a dict, or None.

    None covers every fail-open case this hook treats identically: a missing
    file, an unreadable file, an empty file, or a last non-blank line that
    isn't valid JSON / isn't a JSON object. Per Finding 1, a subagent's own
    transcript file needs no sidechain filtering — every row in it already
    belongs to this subagent.
    """
    lines = _tail_lines(Path(transcript_path))
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        return row if isinstance(row, dict) else None
    return None


def _is_empty_content(content: object) -> bool:
    """True when an assistant message's `content` carries no real text.

    A plain string is checked directly. A content-block list (the normal
    Messages API shape) is empty when every block is a `text` block and their
    concatenated text is blank; a list containing any non-text block (e.g. a
    `tool_use` block) is never considered empty here.
    """
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        if not content:
            return True
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            else:
                return False
        return not "".join(text_parts).strip()
    return True


def classify_stop(transcript_path: str) -> StopClassification:
    """Classify a subagent's SubagentStop transcript tail.

    See the module-level "Classification precedence" section above for the
    full rule order and citations. Pure function: no I/O beyond reading
    `transcript_path`, no side effects — `main()` wires the result to
    `hooks/lib/boundary_events.emit_boundary_event` (Step 2.2).
    """
    row = _last_row(transcript_path)
    if row is None:
        return "unreadable"

    message = row.get("message")
    if not isinstance(message, dict) or "content" not in message:
        return "unreadable"

    if message.get("stop_reason") == "max_tokens":
        return "truncated-final-turn"

    if _is_empty_content(message.get("content")):
        return "empty-final-turn"

    return "clean"


def main() -> int:
    """Fail-open SubagentStop entry point.

    Reads the hook payload, classifies the transcript tail, and emits a
    `boundary-events.jsonl` "warn" record for the two non-clean, explainable
    outcomes (`empty-final-turn`, `truncated-final-turn`) via
    `hooks/lib/boundary_events.emit_boundary_event` — see
    `_EMIT_CLASSIFICATIONS` above for why `clean`/`unreadable` stay silent.
    `emit_boundary_event` is already fail-open internally (module docstring,
    `boundary_events.py`); this function's own try/except is the same
    outer safety net every other hook in this plugin wraps its entire
    `main()` in (e.g. `context_ceiling_guard.py`), so a failure anywhere in
    this hook — payload parsing, classification, or emission — degrades to a
    silent no-op, never a crash or a non-zero exit.
    """
    try:
        payload = read_stdin_json() or {}
        transcript_path = payload.get("transcript_path")
        if isinstance(transcript_path, str) and transcript_path:
            classification = classify_stop(transcript_path)
            if classification in _EMIT_CLASSIFICATIONS:
                emit_boundary_event(
                    payload.get("cwd"),
                    "subagent_completion_guard",
                    "SubagentStop",
                    "warn",
                    classification,
                    payload.get("session_id"),
                )
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
