"""Per-record signal accumulation shared by both session-log extractors
(issue #2044, epic #2040) — the six drifted-furthest accumulator functions
plus one more that does the same job under a different name (`detect_
correction_turn`; the issue's own table names 7 functions while its prose
says "six", the issue is transparent about this discrepancy — the seventh is
the accuracy signal's "was this a correction turn" classifier, drifted right
alongside the other six).

Unlike session_log.discovery/records/classify (slices #2042/#2043), THIS
slice is not behavior-preserving on purpose — see the module-level and
per-function notes below for what changed, in which direction, for which
extractor, and the historical-comparability consequence. A distilled
enumeration also lives in this slice's commit body; this docstring is the
canonical, in-code record of the same decisions.

The four signal classes `/session-review`'s contract defines (docstring of
scripts/session_extract.py, mirrored in
plugins/dev-team/knowledge/telemetry-schema.md's `session-digest.jsonl`
section):

  token      per-session / per-skill / per-subagent / per-model token +
             cost, and the cache-hit ratio.
  rework     failed edits, repeated file edits, retried bash, repeated
             verify-loop runs, permission denials, compaction events.
  accuracy   tool_result is_error counts by tool, failed->retried ratio,
             and user-correction turns.
  utilization which skills/agents were invoked and how often, and which
             registered skills/agents were never observed.

## Per-function reconciliation

- **accumulate_token_signals** (0.10 similarity). The CORE accumulation —
  sum the 4 usage fields into `tokens_total` and `by_model[model]` — is
  identical in effect between the two copies; kept as the shared function,
  matching `extract_session_report.py`'s existing shape exactly (no cost, no
  skill). Cost computation and per-skill attribution are session_extract.py-
  only EXTENSIONS layered on top by that script's own wrapper (pricing/cost
  stays forked per ADR 0036) — not duplicated here.

- **The per-agent CONTEXT_TOKEN bucket (`new_agent_bucket`/
  `merge_agent_buckets`/`finalize_agent_buckets`)** — not one of the 7 named
  functions, but the mechanism #2029 added to `extract_session_report.py`
  ONLY, giving its `by_agent_type` entries real per-agent `context_tokens`/
  `context_per_dispatch` figures. `scripts/session_extract.py` had no
  equivalent — its `by_agent_type` was a bare message-count `Counter`. This
  slice ports the bucket machinery here and switches `session_extract.py`'s
  `by_agent_type` onto it too, so **the maintainer profile gains
  `context_tokens`/`context_per_dispatch`** — the deliberate, expected
  output change issue #2044 calls the "clearest example of why the fork
  costs something."

- **accumulate_skill_agent_signals** (0.19 similarity). session_extract.py's
  copy is a strict superset: it also tracks `active` (the #711 sticky
  skill/agent pointer the correction-turn signal attributes against) and
  reads a legacy `attributionSkill` fallback via a `skill` parameter.
  `extract_session_report.py` has neither concern (no by_skill/by_agent
  correction breakdown in its report shape). The superset function is kept
  as canonical; `extract_session_report.py` calls it with `skill=None` and a
  throwaway `active` dict it never reads back — with `skill=None` the
  legacy-fallback branch never fires, so its own `skills_invoked`/
  `agent_dispatches` accumulation is unchanged (verified by golden diff
  absence on that specific field).

- **track_tool_call** (0.11 similarity) and **classify_tool_result** (0.50).
  Real difference: session_extract.py guards a `tool_use`/`tool_result`
  block's `id`/`tool_use_id` with `isinstance(..., str)` before using it as
  a dict key; extract_session_report.py's pre-#2044 copies did a bare
  `.get(bid, ...)`/dict assignment, which works for any hashable `bid` but
  raises `TypeError` for an unhashable one (a list or dict — a malformed or
  adversarial transcript field). The safer, guarded form is kept as
  canonical; extract_session_report.py gains the guard. No golden diff: the
  corpus's `tool_use`/`tool_result` blocks all carry string ids.

- **track_edit** (0.58) and **track_bash** (0.42), plus the `EDIT_TOOLS`
  constant both need. session_extract.py's copies keyed `verify_edited_since`/
  `last_verify_norm` by `sid` inside a dict that is itself RESET at the top
  of every per-file loop iteration — session-keying inside an already-
  per-file-reset dict is redundant: exactly one `sessionId` ever appears in
  one transcript file (the #1991 bug the sid-keying was originally built to
  prevent — a review panel's siblings sharing their parent's `sessionId` and
  scoring each other's retries — is already fully prevented by the per-file
  reset alone, verified by `tests/repo/test_session_extract_subagents.py::
  test_sibling_agents_running_one_command_are_not_retries`, which stays
  green under this simplification). `extract_session_report.py`'s copies
  already used the simpler flat per-thread dict
  (`{"bash_commands", "last_verify_norm", "edited_since_verify"}`, built by
  `new_thread()` below) with the same per-file-reset discipline. The simpler
  form is kept as canonical (Simplicity First: no observable behavior
  difference on any realistic transcript, confirmed by the golden harness);
  `session_extract.py` drops its `sid`-keyed dicts and adopts `new_thread()`.

- **detect_correction_turn** (0.78 — closest of the seven). Logic identical
  between the two copies; moved verbatim.

## Historical `session-digest.jsonl` comparability

`by_agent_type`'s value shape changes from a bare integer (message count) to
the same bucket-dict shape `extract_session_report.py` already emitted:
`{input_tokens, cache_creation_input_tokens, cache_read_input_tokens,
output_tokens, messages, dispatches, context_tokens, context_per_dispatch}`.
Any historical `session-digest.jsonl` row is NOT comparable on
`token.by_agent_type` (and the derived `session-sync` `by_thread` field)
against a row produced after this change — a consumer doing
`by_agent_type[x] == N` or arithmetic on the value breaks. This is the same
shape of jump `session-digest/v2` (#1994) already made once. The formal
schema-version bump (`session-digest/v3`) and any migration/split-on-schema
consumer update is explicitly issue #2045's job, not this slice's — this
slice only flags it, per its own acceptance criteria.
"""

from __future__ import annotations

import re
from collections import Counter

from session_log import classify, redact

#: Tools whose `tool_use` counts as an "edit" for rework tracking. Not one
#: of ADR 0036's 14 classify.py symbols, but tightly coupled to the edit/
#: bash signal functions below, so it lives here rather than in classify.py.
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

#: The usage fields that make up a dispatch's CONTEXT — what it carried in,
#: as opposed to what it generated. Session telemetry puts ~90% of spend
#: here (cache read + cache write), which is why per-agent context is the
#: figure a panel-cost decision needs and `output_tokens` is tracked
#: separately. Ported verbatim from extract_session_report.py (#2029).
CONTEXT_TOKEN_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

#: Mirrors `hooks/lib/cost_meter.py`'s `_new_bucket()` shape (#1094) so the
#: per-agent breakdowns agree on field names across the plugin. They stay
#: separate implementations — cost_meter runs live per turn, this runs over
#: a whole transcript tree.
AGENT_BUCKET_FIELDS = (*CONTEXT_TOKEN_FIELDS, "output_tokens")


def new_agent_bucket() -> dict:
    bucket = {f: 0 for f in AGENT_BUCKET_FIELDS}
    bucket["messages"] = 0
    bucket["dispatches"] = 0
    return bucket


def merge_agent_buckets(dest: dict, src: dict) -> None:
    """Fold one project's per-agent buckets into cross-project totals.

    Re-sums the raw fields rather than the derived ones: adding two
    projects' `context_per_dispatch` values would produce a number that is
    not a mean of anything. The derived figures are recomputed once, after
    the merge."""
    for label, bucket in (src or {}).items():
        if not isinstance(bucket, dict):
            # A digest written before this port (or before #2010 downstream)
            # carries an int (a message count). Merging it as tokens would
            # silently corrupt the total, so the label is preserved at zero
            # rather than guessed at.
            dest.setdefault(label, new_agent_bucket())
            continue
        into = dest.setdefault(label, new_agent_bucket())
        for field in (*AGENT_BUCKET_FIELDS, "messages", "dispatches"):
            into[field] += bucket.get(field, 0) or 0


def finalize_agent_buckets(by_agent_type: dict) -> dict:
    """Add the derived per-dispatch figure each bucket exists to answer.

    `context_tokens` is the sum a dispatch is charged for carrying;
    `context_per_dispatch` divides it by real dispatch count, which is why
    dispatches are counted from subagent transcripts rather than messages.
    It is `None` for `main` and for any agent with no counted dispatch — a
    division that has no meaning must read as absent, not as 0, which would
    rank a never-dispatched agent as the cheapest in the table."""
    out = {}
    for label, b in sorted(by_agent_type.items()):
        context = sum(b[f] for f in CONTEXT_TOKEN_FIELDS)
        entry = dict(b)
        entry["context_tokens"] = context
        entry["context_per_dispatch"] = (
            round(context / b["dispatches"]) if b["dispatches"] else None
        )
        out[label] = entry
    return out


def accumulate_token_signals(usage_fields: dict, model, tokens_total, by_model) -> None:
    """Token-accounting CORE: sum `usage_fields` (already read through
    `session_log.records.usage_fields`) into `tokens_total` and
    `by_model[model]`. No cost, no skill attribution — those stay
    session_extract.py-only extensions (pricing/cost stays forked, ADR
    0036); see this module's docstring."""
    for f, v in usage_fields.items():
        tokens_total[f] += v
        if model:
            by_model[model][f] += v


def accumulate_skill_agent_signals(
    skill,
    content,
    skills_invoked: Counter,
    agent_dispatches: Counter,
    active: dict[str, str | tuple[str, str] | None],
) -> None:
    """Skill/agent-detection concern. `skill` is the legacy attributionSkill
    tag (kept as a fallback — real transcripts don't emit it, #182);
    `content`'s tool_use blocks are the primary signal: the Skill tool and
    the Agent/Task tool that actually invoke them (#182). `active` tracks
    the most-recently-invoked skill/agent (#711), sticky until superseded,
    for the correction-turn concern to attribute against. `active["last"]`
    (#2013) is the same pointer collapsed to a single `(kind, name)` tuple
    (or absent, before any dispatch) -- the ONE most-recently-dispatched
    entity between the two, for `session_log.corrections`' `component`
    field, which needs a single answer rather than two independently-sticky
    ones.

    Counts DISPATCHES, not runs: a dispatch made from inside a subagent is
    only visible in that subagent's own transcript, and a dispatch whose
    transcript is absent never ran. Run counts come from `attributionAgent`
    (#1994)."""
    if skill:
        skills_invoked[redact.redact(skill)] += 1
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name", "?")
        inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
        if name == "Skill":
            s = inp.get("skill") or inp.get("name")
            if isinstance(s, str) and s:
                active["skill"] = redact.redact(classify.strip_ns(s))
                skills_invoked[active["skill"]] += 1
                active["last"] = ("skill", active["skill"])
        elif name in ("Agent", "Task"):
            a = inp.get("subagent_type")
            if isinstance(a, str) and a:
                active["agent"] = redact.redact(classify.strip_ns(a))
                agent_dispatches[active["agent"]] += 1
                active["last"] = ("agent", active["agent"])


def track_tool_call(block: dict, pending_tool: dict[str, str], tool_calls: Counter) -> None:
    """Error-classification bookkeeping: count every tool invocation (the
    error-rate denominator) and remember its id -> name so a later
    tool_result can be attributed back to the tool that produced it."""
    name = redact.redact(str(block.get("name", "?")))
    tool_calls[name] += 1
    bid = block.get("id")
    if isinstance(bid, str) and bid:
        pending_tool[bid] = name


def classify_tool_result(
    block: dict,
    pending_tool: dict[str, str],
    tool_errors: Counter,
    error_counts: Counter,
) -> None:
    """Error-classification concern: tally errors by tool, and detect the
    two rework sub-signals (failed edits via old_string mismatches, and
    permission denials) from a tool_result block."""
    if not block.get("is_error"):
        return
    bid = block.get("tool_use_id")
    tool_name = pending_tool.get(bid, "?") if isinstance(bid, str) else "?"
    tool_errors[tool_name] += 1
    rcontent = classify.text_of(block.get("content"))
    if tool_name in EDIT_TOOLS and classify.OLDSTRING_RE.search(rcontent):
        error_counts["failed_edits"] += 1
    if classify.PERMISSION_RE.search(rcontent):
        error_counts["permission_denials"] += 1


def new_thread() -> dict:
    """Per-transcript-file state for `track_edit`/`track_bash`. One
    transcript file is one thread of execution: a main-thread session, or a
    single dispatched agent's run. Reset at the top of each file's
    processing loop."""
    return {"bash_commands": Counter(), "last_verify_norm": None, "edited_since_verify": False}


def track_edit(block: dict, edits_per_file: Counter, thread: dict) -> None:
    """Edit-tracking concern: count Edit/Write/... calls per file basename,
    so repeated edits to the same file (a rework signal) can be derived.
    Also marks this thread's pending stuck-verify-loop streak (#708) as
    consumed — an edit resets it, same as verify_guard.py's own reset."""
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name in EDIT_TOOLS and inp.get("file_path"):
        edits_per_file[redact.redact(str(inp["file_path"]), from_path=True)] += 1
    if name in EDIT_TOOLS:
        thread["edited_since_verify"] = True


def track_bash(block: dict, bash_signal_counts: Counter, thread: dict) -> None:
    """Bash-retry / commit-bypass / stuck-verify-loop concern (#111, #708):
    normalize the command for near-identical retry detection, detect a
    stuck-verify-loop repeat (the same normalized verify command run again
    with no Edit/Write/... call since the previous run in this thread), and
    detect the review-gate bypass signal on `git commit` invocations.

    Bash signals are scoped to ONE thread of execution (`thread`, a
    per-transcript-file dict). Retries and repeated verify runs are only
    meaningful within a thread: a review panel's sibling agents share their
    parent's sessionId, so a session-keyed tally would score fifteen agents
    each running `git diff --cached` once as fourteen retries."""
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name != "Bash" or not isinstance(inp.get("command"), str):
        return
    cmd = inp["command"].strip()
    # near-identical retry detection: normalize whitespace
    norm = re.sub(r"\s+", " ", cmd)
    thread["bash_commands"][norm] += 1
    if classify.VERIFY_RE.search(cmd):
        if thread["last_verify_norm"] == norm and not thread["edited_since_verify"]:
            bash_signal_counts["repeated_verify_runs"] += 1
        thread["last_verify_norm"] = norm
        thread["edited_since_verify"] = False
    # gate signal (#111): commit + review-gate bypass, scoped to the
    # git-commit argv (#2036) — see classify.bash_segments()/is_git_commit_argv().
    for segment in classify.bash_segments(cmd):
        if classify.is_git_commit_argv(segment):
            bash_signal_counts["commit_attempts"] += 1
            if any(tok in classify.COMMIT_BYPASS_TOKENS for tok in segment[1:]):
                bash_signal_counts["commit_bypasses"] += 1


def detect_correction_turn(rec: dict, content) -> bool:
    """Correction-turn concern: a real user message (not a tool_result
    envelope) containing a correction keyword ("no", "actually", "revert",
    ...)."""
    if rec.get("type") != "user" or rec.get("isMeta"):
        return False
    utext = classify.text_of(content)
    if not utext:
        return False
    # skip pure tool_result envelopes (no free-text user prompt)
    if isinstance(content, list) and all(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    return bool(classify.CORRECTION_RE.search(utext.lower()))
