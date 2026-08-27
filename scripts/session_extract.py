#!/usr/bin/env python3
"""Deterministic session-log extractor (issue #127).

Reads Claude Code session transcripts (``~/.claude/projects/<slug>/*.jsonl``)
for the current project and distills MBs of JSONL into a compact, KB-sized JSON
digest. This is the foundation of the ``/session-review`` harness: the model
must never read raw transcripts (that would spend tokens to study token spend),
so ALL heavy parsing happens here, deterministically and with zero model calls.

Four signal classes are captured equally (the report ranks them, not this
extractor):

  token       per-session / per-skill / per-subagent / per-model token + cost,
              and the cache-hit ratio (cache_read vs cache_creation).
  rework      failed Edit/Write ("old_string not found"), repeated edits to the
              same file, retried near-identical Bash, repeated test/build/lint
              runs, permission denials, compaction events.
  accuracy    tool_result is_error counts by tool, failed->retried ratio, and
              user-correction turns (a keyword scan: "no", "actually",
              "revert", "undo", "not what I asked").
  utilization which skills/agents were invoked and how often; and which plugin
              skills/agents were NEVER observed in the logs.

PRIVACY: the digest holds METRICS ONLY — counts, ratios, names, token numbers.
No prompt text, code, file contents, or command strings are ever emitted (file
*paths* are reduced to basenames; correction keywords are counted, not quoted).

DETERMINISM: given the same transcript inputs the output is byte-identical — no
wall-clock timestamps, no absolute paths, sorted keys throughout.

Usage:
  session_extract.py [--transcript F ...] [--project-dir D] [--cwd PATH]
                     [--projects-root R] [--pricing P] [--plugin-root PR]
  (default resolves the current project's transcripts under ~/.claude/projects)

  --all-projects                 aggregate across ALL projects, not just the cwd's.
  --sync-out FILE [--watermark W] [--host H]
                                 Delta D (#178): cross-project INCREMENTAL sync —
                                 append one metrics-only record per new/changed
                                 session to the host digest FILE; the watermark
                                 dedups by session_id+size so re-runs only emit
                                 what changed. project is a basename only.
  --rollup DIR                   Delta D (#178): UNION READ — aggregate every
                                 host's DIR/<host>/session-digest.jsonl into one
                                 cross-machine view (per-host/per-project spend,
                                 summed rework/accuracy, never-invoked-anywhere).
  --escalate DIR                 Delta C (#179): rank friction → recommended lever.
  --correlate DIR                process eval (#111): compare rework between
                                 review-gate-bypass and non-bypass sessions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

# scripts/ (repo root) -> repo root -> plugins/dev-team/scripts/lib. This
# repo-root script already depends on the plugin tree in three other places
# (see ADR 0036); this is the first genuine Python IMPORT of it, mirroring
# the established `sys.path.insert` + `from <pkg> import ...` pattern in
# scripts/test_modernization_review.py.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "plugins" / "dev-team" / "scripts" / "lib"),
)
from session_log import classify, discovery, records, redact, signals

_redact = redact.redact

# The pricing loader/rate-lookup/cost-computation logic lives in hooks/lib
# (#2045) — hooks/lib/cost_meter.py (a real Stop hook) needs the same
# module and must never reach into scripts/, so the dependency direction is
# scripts/ -> hooks/lib/, not the reverse (same rule hooks/lib/
# review_agent_registry.py established for #1461; mirrors
# scripts/check_review_agent_mcp_tools.py's identical import below).
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "plugins" / "dev-team" / "hooks" / "lib")
)
from pricing import cost as _cost
from pricing import load_pricing as _load_pricing
from pricing import rate as _rate

# session_log.classify (issue #2043, epic #2040): the classification
# vocabulary and text/name-handling helpers used to be defined here; they
# are now shared with extract_session_report.py. See
# plugins/dev-team/scripts/lib/session_log/classify.py's module docstring
# for the per-symbol reconciliation table. Aliased under the original
# private names so every internal call site below is unchanged.
_VERIFY_RE = classify.VERIFY_RE
_CORRECTION_RE = classify.CORRECTION_RE
_PERMISSION_RE = classify.PERMISSION_RE
_OLDSTRING_RE = classify.OLDSTRING_RE
# session_log.signals.EDIT_TOOLS (#2044) is this exact set; aliased so no
# call site in this file needs to change.
_EDIT_TOOLS = signals.EDIT_TOOLS
_GIT_GLOBAL_OPTS_WITH_ARG = classify.GIT_GLOBAL_OPTS_WITH_ARG
_COMMIT_BYPASS_TOKENS = classify.COMMIT_BYPASS_TOKENS
_statement_break_newlines = classify.statement_break_newlines
_bash_segments = classify.bash_segments
_is_git_commit_argv = classify.is_git_commit_argv
_SAFE_NAME_RE = classify.SAFE_NAME_RE
_UNSAFE_NAME = classify.UNSAFE_NAME
_HARNESS_ATTRIBUTIONS = classify.HARNESS_ATTRIBUTIONS
_DIGEST_SCHEMA = "session-digest/v2"
_SYNC_SCHEMA = "session-sync/v2"
#: Sync-record schemas a reader accepts. Declared once and imported by
#: scripts/eval_rawlog.py — the v1->v2 bump broke that consumer silently
#: because it exact-matched the old string on its own (#1994 review).
SYNC_SCHEMAS = ("session-sync/v1", "session-sync/v2")
_MAIN_LABEL = "main"
_UNATTRIBUTED_LABEL = "unattributed"
# session_log.discovery (#2042): path classification and enumeration used to
# be defined here; they are now shared with extract_session_report.py.
# Aliased under the original private names so every internal call site below
# is unchanged.
_is_transcript_path = discovery.is_transcript_path
_is_subagent_transcript = discovery.is_subagent_transcript
_all_transcripts_under = discovery.all_transcripts

_strip_ns = classify.strip_ns

# --- gate-run correlation (#2037) -------------------------------------------
# `_BYPASS_RE`/`COMMIT_BYPASS_TOKENS` (see classify.py's module docstring)
# only observes DELIBERATE bypass (`--no-verify`/`-n` on the command line) —
# by construction it is blind to causes 2-4 from #2009's original framing
# (an inert hook, a hook that errors but exits 0, or a commit made through an
# unregistered path), because all three leave a command line that looks
# entirely ordinary. This section inverts the sensor: `.husky/pre-commit`
# (the real git pre-commit gate — see .husky/pre-commit's own comments; NOT
# `pre_commit_review.py`, which #1886 retired to a documented no-op, and NOT
# `pre_pr_review.py`, which gates `gh pr create`, a different question) now
# emits a POSITIVE `gate_ran` boundary event carrying its own verdict every
# time it runs, success or failure alike. A commit attempt with no correlated
# `gate_ran` event is the previously unmeasured "gate_absent" population.
#
# Correlation is by TIME PROXIMITY, not session_id: `.husky/pre-commit` is a
# real git hook invoked by git itself, outside Claude Code's own hook
# machinery entirely, so it has no Claude Code session_id to attach (unlike
# every other `boundary_events.py` emitter, which runs INSIDE a Claude Code
# PreToolUse hook with a stdin JSON payload carrying one). KNOWN RESIDUAL
# GAP, disclosed rather than silently accepted: two commits within the same
# window (or a human's terminal commit alongside a running session) can
# cross-match — acceptable for a first-cut distribution, not a precise
# per-commit audit trail.
_GATE_RAN_HOOK = "pre-commit-gate"
_GATE_RAN_PREFIX = "gate-ran-"
GATE_RAN_WINDOW_SECONDS = 120


def _parse_event_ts(value) -> datetime | None:
    """Parse a `boundary-events.jsonl`/transcript timestamp
    (`boundary_events.TS_FORMAT`, `%Y-%m-%dT%H:%M:%SZ`) into an aware UTC
    `datetime`, or `None` when `value` isn't a string in that exact shape —
    the same "can't determine, don't guess" posture the rest of this
    extractor takes on malformed input."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _read_gate_ran_events(path: Path | None) -> list[tuple[datetime, str]]:
    """Every `gate_ran` boundary event's `(ts, verdict)` pair from
    `boundary-events.jsonl`, oldest first. `path` may be `None` (no
    gate-run instrumentation configured) or point at a file that doesn't
    exist yet (the gate has never run) — both simply yield nothing, the
    same as any other optional signal in this extractor."""
    if path is None or not path.is_file():
        return []
    out: list[tuple[datetime, str]] = []
    for rec in _iter_records([path]):
        if not isinstance(rec, dict) or rec.get("hook") != _GATE_RAN_HOOK:
            continue
        if rec.get("decision") != "record":
            continue
        rule = rec.get("matched_rule")
        if not isinstance(rule, str) or not rule.startswith(_GATE_RAN_PREFIX):
            continue
        ts = _parse_event_ts(rec.get("ts"))
        if ts is None:
            continue
        out.append((ts, rule[len(_GATE_RAN_PREFIX) :]))
    out.sort(key=lambda pair: pair[0])
    return out


def _classify_gate_run(
    commit_ts: datetime | None, gate_events: list[tuple[datetime, str]]
) -> str:
    """Classify one non-bypassed commit attempt against the gate-run event
    timeline: `"absent"` (no correlated `gate_ran` event within
    `GATE_RAN_WINDOW_SECONDS` — the cause-2/3/4 population, previously
    unmeasured), `"errored"` (the nearest correlated event recorded an
    internal failure), or `"clean"` (the gate ran normally, whether it
    allowed or blocked the commit — both are evidence the gate executed)."""
    if commit_ts is None:
        return "absent"
    window = timedelta(seconds=GATE_RAN_WINDOW_SECONDS)
    best_verdict: str | None = None
    best_delta: timedelta | None = None
    for ts, verdict in gate_events:
        delta = abs(ts - commit_ts)
        if delta <= window and (best_delta is None or delta < best_delta):
            best_verdict, best_delta = verdict, delta
    if best_verdict is None:
        return "absent"
    return "errored" if best_verdict == "errored" else "clean"


def _rewrite_name_keys(mapping: dict) -> dict:
    """Rewrite a peer-supplied name-bearing dict's keys to something safe to
    aggregate — a peer record's dict KEYS are as untrusted as any other field
    it carries. Each key is normalized through `_redact(_strip_ns(str(k)))`
    when it's a string; a non-string key (which would otherwise raise
    `AttributeError` the moment a consumer calls `.startswith()` on it) is
    bucketed under `_UNSAFE_NAME` instead of dropped. Values collide-merge by
    summing, matching `_redact`'s own collapse-and-merge convention — a
    normalization collision never silently drops a peer-attributed count. A
    peer-supplied VALUE is as untrusted as the key: it passes through
    `_safe_number` before summing, so a non-numeric value (string/null/list/
    dict) can't raise an uncaught TypeError and abort the caller, and a bool
    or non-finite float can't poison the aggregate."""
    out: dict = {}
    for k, v in mapping.items():
        key = _redact(_strip_ns(str(k))) if isinstance(k, str) else _UNSAFE_NAME
        out[key] = out.get(key, 0) + _safe_number(v)
    return out


_text_of = classify.text_of


# A version string is trusted input only when it's OUR OWN plugin.json (this
# function); everywhere else it arrives from a peer machine's synced digest
# (a different trust domain, #1480 security review). This allowlist bounds
# every plugin_version value to a short semver-ish token on the way IN, so
# nothing larger or differently-shaped ever reaches a persisted stream or a
# numeric parse — see `_normalize_plugin_version` below, the ingestion-side
# twin that applies this same pattern to foreign records.
_VERSION_RE = re.compile(r"^[0-9A-Za-z._+-]{1,32}$")


def _load_plugin_version(plugin_root: Path | None) -> str:
    """Read `.claude-plugin/plugin.json`'s version so every digest/rollup/
    trend record can be tagged with the plugin version active when it was
    produced (#1471) — mirrors the hooks' own `_load_plugin_version` helper
    (`hooks/lib/boundary_events.py` et al.), resolved via --plugin-root since
    session_extract.py already takes that flag for the skills/agents registry."""
    if plugin_root is None:
        plugin_root = Path(__file__).resolve().parent.parent / "plugins" / "dev-team"
    manifest = Path(plugin_root) / ".claude-plugin" / "plugin.json"
    try:
        if manifest.stat().st_size > 64_000:
            return "unknown"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str) and _VERSION_RE.match(version):
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _iter_records(paths: list[Path]):
    """Yield every decodable JSON record across `paths`, in order — a thin
    multi-path wrapper over session_log.records.iter_file_records (#2042);
    every call site in this module passes a single-element list."""
    for path in sorted(paths, key=lambda x: str(x)):
        yield from records.iter_file_records(path)


# session_log.signals (issue #2044, epic #2040): per-record signal
# accumulation used to be defined here; unified with
# extract_session_report.py — see signals.py's module docstring for the
# full per-function reconciliation. THIS SLICE CHANGES OUTPUT on purpose:
# by_agent_type gains the same context_tokens/context_per_dispatch bucket
# shape extract_session_report.py already had (#2029) — see the "Historical
# session-digest.jsonl comparability" note in signals.py's docstring, and
# this slice's own commit body for the enumerated golden diff.
_accumulate_skill_agent_signals = signals.accumulate_skill_agent_signals
_track_tool_call = signals.track_tool_call
_classify_tool_result = signals.classify_tool_result
_detect_correction_turn = signals.detect_correction_turn


def _accumulate_token_signals(
    usage: dict,
    raw_model,
    model,
    skill,
    pricing: dict,
    tokens_total: Counter,
    by_model: dict[str, Counter],
    by_skill: dict[str, Counter],
) -> tuple[float, dict]:
    """Token-accounting concern: usage/cost totals split by model and skill,
    on top of `signals.accumulate_token_signals`'s shared core (tokens_total
    + by_model — no cost, no skill, matching extract_session_report.py's
    exact shape; pricing/cost stays a session_extract.py-only extension per
    ADR 0036). Returns `(cost, safe_usage)` — the caller's `by_agent_type`
    bucket (#2044's context_tokens port) needs the same already-safety-
    clamped usage fields this function computes, so it's returned rather
    than recomputed.

    #2080: `usage` is read from a LOCAL transcript file — a different trust
    domain from the peer-digest path `_safe_number` was written to guard, but
    still "a transcript this script does not author" (per `_iter_records`'s
    own comment): a corrupted or hand-edited file can carry an out-of-range
    or negative token count. Read every field through `_safe_number` once,
    here, so `_cost`'s `inp / 1e6 * ir` never sees a value whose magnitude
    overflows the int-to-float conversion (raising OverflowError and
    aborting the whole run before `round(cost * 1e6)` below is even reached)
    and the running totals can never go negative from one bad record."""
    safe_usage = {f: _safe_number(v) for f, v in records.usage_fields(usage).items()}
    cost = _cost(safe_usage, _rate(pricing, raw_model or ""), pricing)
    signals.accumulate_token_signals(safe_usage, model, tokens_total, by_model)
    if skill:
        for f in records.USAGE_FIELDS:
            by_skill[skill][f] += safe_usage[f]
    if model:
        by_model[model]["cost_micro"] += round(cost * 1e6)
    if skill:
        by_skill[skill]["cost_micro"] += round(cost * 1e6)
    return cost, safe_usage


# signals.track_edit/track_bash operate on a flat per-thread dict
# (signals.new_thread()) rather than this script's former sid-keyed dicts —
# see signals.py's module docstring for why dropping the sid-keying is a
# behavior-preserving simplification, not a regression of the #1991 fix it
# originally existed to prevent.
_track_edit = signals.track_edit
_track_bash = signals.track_bash

# session_log.records.slim_by_name (#2042) is this exact function; aliased
# so the two call sites below are unchanged.
_slim = records.slim_by_name


def extract(
    paths: list[Path],
    pricing: dict,
    registry: dict,
    plugin_version: str = "unknown",
    projects_root: Path | None = None,
    boundary_events_path: Path | None = None,
) -> dict:
    tokens_total = Counter()
    cost_total = 0.0
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_skill: dict[str, Counter] = defaultdict(Counter)
    # Per-agent buckets keyed by AGENT NAME — `main` for the main thread,
    # `unattributed` where no agent is resolvable. Renamed from `by_subagent`
    # (#1994): that name meant "sidechain vs main" here while the shipped
    # report used the same path for agent-name attribution, and `by_agent_type`
    # is the plugin's settled vocabulary for this map
    # (knowledge/telemetry-schema.md, cost-metering). #2044: switched from a
    # bare message-count Counter to signals.new_agent_bucket()'s dict shape —
    # extract_session_report.py's real per-agent context_tokens (#2029),
    # ported here for the first time. See signals.py's module docstring,
    # "Historical session-digest.jsonl comparability".
    by_agent_type: dict[str, dict] = {}
    agent_runs = Counter()  # one subagent transcript is one run
    agent_dispatches = Counter()  # Agent/Task tool_use calls
    subagent_transcripts = 0
    main_transcripts = 0
    subagent_layout_present = False
    sessions: set[str] = set()

    # rework / accuracy
    edits_per_file = Counter()
    retried_bash_total = 0
    # repeated_verify_runs (#708): mirrors verify_guard.py's own stuck-loop
    # detection — a "repeat" is the same normalized verify command run again
    # with NO Edit/Write/NotebookEdit/MultiEdit call since the previous verify
    # run in the same thread (NOT a raw tally of every verify-class command,
    # despite the metric's pre-#708 name — that raw tally double-counted the
    # ordinary RED/GREEN/REFACTOR re-run of the same command after a real
    # edit). #2044: tracked via a flat per-thread dict (signals.new_thread()),
    # reset every file — see signals.py's module docstring for why the prior
    # sid-keying inside an already-per-file-reset dict was redundant.
    bash_signal_counts = Counter()  # repeated_verify_runs, commit_attempts/bypasses
    # gate-run correlation (#2037): every git-commit argv seen, as
    # (record timestamp, was it a deliberate --no-verify/-n bypass) — kept
    # separately from bash_signal_counts because correlating against
    # boundary-events.jsonl needs each attempt's own timestamp, not just a
    # running total. See "gate-run correlation (#2037)" above `extract()`.
    commit_attempt_events: list[tuple[str | None, bool]] = []
    error_counts = Counter()  # failed_edits, permission_denials
    compaction_events = 0
    tool_errors = Counter()  # by tool name
    tool_calls = Counter()  # by tool name (for ratios)
    correction_turns = 0
    correction_by_skill = Counter()  # #711: correction attribution
    correction_by_agent = Counter()

    # utilization
    skills_invoked = Counter()

    # map tool_use id -> tool name, to attribute tool_result errors back
    pending_tool: dict[str, str] = {}
    # #711: most-recently-invoked Skill/Agent on the main thread, sticky until
    # superseded — used to attribute a correction turn to the artifact active
    # when it happened. No "skill ended" event exists in the transcript
    # format, so "most recent invocation" is the only signal available.
    active: dict[str, str | None] = {"skill": None, "agent": None}

    # One transcript file is one thread of execution: a main-thread session, or
    # a single dispatched agent's run. Bash history, verify state, pending
    # tool_use ids and the sticky skill/agent attribution are scoped per FILE
    # rather than per sessionId — subagents share their parent's session, so a
    # session-keyed tally scores a review panel's fifteen siblings each running
    # `git diff --cached` once as fourteen retries (#1994, porting #1991).
    root = projects_root or Path.home() / ".claude" / "projects"
    for path in paths:
        is_subagent = _is_subagent_transcript(root, path)
        if is_subagent:
            subagent_layout_present = True
        agent_name: str | None = None
        thread_msgs = 0
        thread_usage = signals.new_agent_bucket()
        records_seen = 0
        thread = signals.new_thread()
        pending_tool = {}
        active = {"skill": None, "agent": None}

        for rec in _iter_records([path]):
            records_seen += 1
            sid = rec.get("sessionId") or rec.get("session_id")
            if sid:
                sessions.add(str(sid))
            if is_subagent and agent_name is None:
                attributed = rec.get("attributionAgent")
                if isinstance(attributed, str) and attributed:
                    stripped = _strip_ns(attributed)
                    # A harness ROLE is not an agent name. Emitting it would
                    # invent an agent while leaving the one that really ran in
                    # never_observed_agents.
                    if stripped not in _HARNESS_ATTRIBUTIONS:
                        agent_name = _redact(stripped)
            rtype = rec.get("type")
            is_sidechain = bool(rec.get("isSidechain")) or is_subagent
            # attributionSkill is a legacy/secondary tag — the harness does not emit
            # it on real transcripts (#182), so utilization is driven by the Skill /
            # Agent tool_use below. Kept here only as a fallback for records that do
            # carry it (and per-skill token attribution via by_skill).
            raw_skill = rec.get("attributionSkill") or rec.get("attribution_skill")
            skill = (
                _redact(_strip_ns(raw_skill))
                if isinstance(raw_skill, str) and raw_skill
                else None
            )

            # compaction markers
            if (
                rtype in ("compaction", "summary")
                or rec.get("isCompactSummary")
                or rec.get("compactMetadata")
            ):
                compaction_events += 1

            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            usage = records.usage_of(rec)
            raw_model = msg.get("model") or rec.get("model")
            # A non-str `model` would be an unhashable dict key and abort the
            # whole run. Keep the RAW id for the pricing lookup and sanitize
            # only where it becomes a key: `_redact` would collapse a
            # Vertex-style id (`...-v2@20241022`) to "other", miss
            # `pricing["models"]`, and silently bill the session $0.00 — an
            # under-report, which is the failure direction that matters for the
            # cost-regression baseline (#1994 review).
            raw_model = raw_model if isinstance(raw_model, str) and raw_model else None
            model = _redact(raw_model) if raw_model else None

            if usage:
                cost, safe_usage = _accumulate_token_signals(
                    usage,
                    raw_model,
                    model,
                    skill,
                    pricing,
                    tokens_total,
                    by_model,
                    by_skill,
                )
                cost_total += cost
                if is_subagent:
                    # The whole file is one agent's run; its label is resolved
                    # once, at end of file, from `attributionAgent` — so the
                    # per-record usage accumulates into `thread_usage` and is
                    # folded into the file's bucket at file-end (#2044).
                    thread_msgs += 1
                    thread_usage["messages"] += 1
                    for f in signals.CONTEXT_TOKEN_FIELDS:
                        thread_usage[f] += safe_usage[f]
                    thread_usage["output_tokens"] += safe_usage["output_tokens"]
                else:
                    # A MAIN transcript. An older harness inlined sidechain
                    # turns here rather than in their own file, and
                    # `isSidechain` is the only attribution those carry — so
                    # bucket per record. Labelling the whole file from one
                    # inlined record would retitle the main thread (#1991).
                    rec_agent = rec.get("attributionAgent")
                    if isinstance(rec_agent, str) and rec_agent:
                        stripped_rec = _strip_ns(rec_agent)
                        inline_label = (
                            _UNATTRIBUTED_LABEL
                            if stripped_rec in _HARNESS_ATTRIBUTIONS
                            else _redact(stripped_rec)
                        )
                    elif is_sidechain:
                        inline_label = "sidechain"
                    else:
                        inline_label = _MAIN_LABEL
                    bucket = by_agent_type.setdefault(inline_label, signals.new_agent_bucket())
                    bucket["messages"] += 1
                    for f in signals.CONTEXT_TOKEN_FIELDS:
                        bucket[f] += safe_usage[f]
                    bucket["output_tokens"] += safe_usage["output_tokens"]

            content = msg.get("content")
            _accumulate_skill_agent_signals(
                skill, content, skills_invoked, agent_dispatches, active
            )

            # walk content blocks for tool_use / tool_result
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        _track_tool_call(block, pending_tool, tool_calls)
                        _track_edit(block, edits_per_file, thread)
                        _track_bash(block, bash_signal_counts, thread)
                        # gate-run correlation (#2037): re-invokes the same
                        # classify.bash_segments()/is_git_commit_argv() calls
                        # signals.track_bash() already made above — not
                        # duplicated logic, just a second call so this
                        # extractor-only concern (boundary-events.jsonl
                        # correlation has no shipped-extractor use) doesn't
                        # need to widen signals.track_bash()'s shared
                        # signature. See ADR 0036's monorepo-only precedent.
                        bblock_input = (
                            block.get("input", {})
                            if isinstance(block.get("input"), dict)
                            else {}
                        )
                        if block.get("name") == "Bash" and isinstance(
                            bblock_input.get("command"), str
                        ):
                            for segment in _bash_segments(bblock_input["command"].strip()):
                                if _is_git_commit_argv(segment):
                                    is_bypass = any(
                                        tok in _COMMIT_BYPASS_TOKENS for tok in segment[1:]
                                    )
                                    commit_attempt_events.append(
                                        (rec.get("timestamp"), is_bypass)
                                    )
                    elif btype == "tool_result":
                        _classify_tool_result(
                            block, pending_tool, tool_errors, error_counts
                        )

            # Only a MAIN transcript carries human turns. A dispatched
            # agent's transcript opens with the parent's task prompt as a
            # `type: "user"` record, and `_CORRECTION_RE` matches the ordinary
            # phrasing of one ("do not", "no", "wrong") — 287 of 400 sampled
            # real dispatch prompts scored as corrections, which would rank
            # this signal first in escalate() off the harness talking to
            # itself (#1994 review).
            if not is_subagent and _detect_correction_turn(rec, content):
                correction_turns += 1
                correction_by_skill[active["skill"] or "unattributed"] += 1
                correction_by_agent[active["agent"] or "unattributed"] += 1

        # A file's agent name is only known once a record carrying
        # `attributionAgent` has been seen, so thread-level attribution is
        # resolved here rather than per record.
        label = agent_name or (_UNATTRIBUTED_LABEL if is_subagent else _MAIN_LABEL)
        if thread_msgs:  # a zero-message file must not materialize a bucket
            bucket = by_agent_type.setdefault(label, signals.new_agent_bucket())
            bucket["messages"] += thread_usage["messages"]
            for f in signals.CONTEXT_TOKEN_FIELDS:
                bucket[f] += thread_usage[f]
            bucket["output_tokens"] += thread_usage["output_tokens"]
            # One subagent transcript is one dispatch, so dispatches are
            # counted here rather than inferred from message volume.
            if is_subagent:
                bucket["dispatches"] += 1
        if records_seen and is_subagent:
            subagent_transcripts += 1
            agent_runs[label] += 1
        elif records_seen:
            main_transcripts += 1
        retried_bash_total += sum(n - 1 for n in thread["bash_commands"].values() if n > 1)

    # repeated edits (project-wide: a file is shared state) / retried bash
    # (per thread: a retry is a property of one agent's own loop).
    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    retried_bash = retried_bash_total
    failed_edits = error_counts["failed_edits"]
    permission_denials = error_counts["permission_denials"]
    repeated_verify_runs = bash_signal_counts["repeated_verify_runs"]
    commit_attempts = bash_signal_counts["commit_attempts"]
    commit_bypasses = bash_signal_counts["commit_bypasses"]

    # gate-run correlation (#2037): classify every NON-bypassed commit
    # attempt (a deliberate --no-verify/-n bypass is already fully explained
    # by commit_bypasses above — git itself skips the gate entirely when
    # that flag is set, so there is nothing to correlate) against the
    # gate_ran event timeline.
    gate_ran_events = _read_gate_ran_events(boundary_events_path)
    gate_ran_absent = gate_ran_errored = gate_ran_clean = 0
    for ts_str, is_bypass in commit_attempt_events:
        if is_bypass:
            continue
        outcome = _classify_gate_run(_parse_event_ts(ts_str), gate_ran_events)
        if outcome == "absent":
            gate_ran_absent += 1
        elif outcome == "errored":
            gate_ran_errored += 1
        else:
            gate_ran_clean += 1

    # never-observed registry items
    # Run counts are ground truth where subagent transcripts exist (one file
    # per run, named by `attributionAgent`). A tree written by an older harness
    # has none, so fall back to dispatch counts rather than reporting zero.
    agents_invoked = agent_runs if subagent_layout_present else agent_dispatches
    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    never_skills = sorted(reg_skills - set(skills_invoked))
    # Observed by EITHER signal counts as observed — an agent that ran but
    # whose dispatch came from inside another agent, and vice versa.
    never_agents = sorted(reg_agents - set(agents_invoked) - set(agent_dispatches))

    cr = tokens_total["cache_read_input_tokens"]
    cc = tokens_total["cache_creation_input_tokens"]
    cache_hit_ratio = round(cr / (cr + cc), 4) if (cr + cc) else 0.0

    total_errors = sum(tool_errors.values())
    total_calls = sum(tool_calls.values())

    return {
        # v2 (#1994): subagent transcripts are counted for the first time, so
        # token/tool-call/rework totals all jump, and retried_bash_commands /
        # repeated_verify_runs changed basis from session-keyed to per-thread.
        # Correct, but NOT comparable with any v1 record already in a trend
        # stream — a consumer has to be able to tell the two eras apart.
        "schema": _DIGEST_SCHEMA,
        "plugin_version": plugin_version,
        "sessions": len(sessions),
        "transcripts": main_transcripts,
        "subagent_transcripts": subagent_transcripts,
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cost_usd": round(cost_total, 4),
            "cache_hit_ratio": cache_hit_ratio,
            "by_model": _slim(by_model),
            "by_skill": _slim(by_skill),
            "by_agent_type": signals.finalize_agent_buckets(by_agent_type),
        },
        "rework": {
            "failed_edits": failed_edits,
            "repeated_file_edits": dict(sorted(repeated_file_edits.items())),
            "retried_bash_commands": retried_bash,
            "repeated_verify_runs": repeated_verify_runs,
            "permission_denials": permission_denials,
            "compaction_events": compaction_events,
        },
        "accuracy": {
            "tool_errors_by_tool": dict(sorted(tool_errors.items())),
            "tool_calls": total_calls,
            "tool_error_rate": round(total_errors / total_calls, 4)
            if total_calls
            else 0.0,
            "user_correction_turns": correction_turns,
            "by_skill": dict(sorted(correction_by_skill.items())),
            "by_agent": dict(sorted(correction_by_agent.items())),
        },
        "gate": {
            "commit_attempts": commit_attempts,
            "commit_bypasses": commit_bypasses,
            "bypass_rate": round(commit_bypasses / commit_attempts, 4)
            if commit_attempts
            else 0.0,
            # #2037: the three-way cause distribution `_BYPASS_RE` alone
            # cannot see. `commit_bypasses` above IS the "deliberate" count
            # (cause 1); these three cover the previously-unmeasured
            # cause-2/3/4 population, now split by correlated gate_ran
            # evidence — "absent" (no gate_ran event found: inert hook or an
            # unregistered commit path), "errored" (the gate ran but
            # recorded an internal failure), "clean" (the gate ran normally).
            "gate_ran_absent": gate_ran_absent,
            "gate_ran_errored": gate_ran_errored,
            "gate_ran_clean": gate_ran_clean,
        },
        "utilization": {
            "skills_invoked": dict(sorted(skills_invoked.items())),
            "agents_invoked": dict(sorted(agents_invoked.items())),
            "agent_dispatches": dict(sorted(agent_dispatches.items())),
            "never_observed_skills": never_skills,
            "never_observed_agents": never_agents,
        },
    }


# --------------------------------------------------------------------------
# Transcript-directory resolution.
# --------------------------------------------------------------------------


def resolve_transcripts(args) -> list[Path]:
    """Robustly find the current project's transcript files.

    Preference order:
      1. explicit --transcript files,
      2. an explicit --project-dir of *.jsonl,
      3. scan --projects-root (default ~/.claude/projects) for any *.jsonl
         whose records' `cwd` matches --cwd — matching the cwd INSIDE the
         JSONL is more robust than reconstructing the slug, which has varied
         across Claude Code versions.
    """
    if args.transcript:
        return [Path(p) for p in args.transcript]
    if args.project_dir:
        return sorted(Path(args.project_dir).glob("*.jsonl"))

    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    target_cwd = os.path.abspath(args.cwd or os.getcwd())
    if not root.is_dir():
        return []
    matches: list[Path] = []
    for jsonl in _all_transcripts_under(root):
        try:
            with jsonl.open(encoding="utf-8", errors="replace") as fh:
                for _ in range(20):  # cwd appears on the earliest records
                    line = fh.readline()
                    if not line:
                        break
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rec_cwd = rec.get("cwd")
                    if rec_cwd and os.path.abspath(rec_cwd) == target_cwd:
                        matches.append(jsonl)
                        break
        # UnicodeDecodeError is a ValueError: a transcript truncated
        # mid-character aborted the DEFAULT resolution path (#1994 review).
        except (OSError, ValueError):
            continue
    return sorted(matches, key=lambda x: str(x))


def resolve_all_transcripts(args) -> list[Path]:
    """Every transcript across ALL projects under projects-root (Delta D, #178).

    Cross-project: unlike resolve_transcripts (which matches one project's cwd),
    this returns one file per session across every project on the machine, so the
    sync can aggregate all of them.
    """
    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    if not root.is_dir():
        return []
    return _all_transcripts_under(root)


def _opaque_session_id(session_id: str) -> str:
    """A safe session id that stays UNIQUE.

    Collapsing every unsafe id to the single literal `other` would make two
    such sessions collide in `_read_synced_records`' last-write-wins dedup, so
    one silently vanishes from `rollup()`'s session count — the denominator
    `escalate()` divides friction by. Same construction the shipped twin uses
    for project labels (#1994 review).
    """
    safe = _redact(session_id)
    if safe != _UNSAFE_NAME:
        return safe
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]
    return f"other-{digest}"


def _owning_session_dir(root: Path, path: Path) -> str:
    """The session a transcript belongs to, as a stable id.

    A main transcript IS its session (`<project>/<sessionId>.jsonl` -> stem).
    A dispatched agent's transcript belongs to the session whose directory
    contains its `subagents/` — `<project>/<sessionId>/subagents/agent-*.jsonl`,
    and one level deeper for Workflow agents.

    Without this, `cmd_sync` emitted one record per FILE and labelled each
    `session_id = path.stem`, so an agent transcript became a fabricated
    session called `agent-<id>`. `rollup()` counts `len(records)` as sessions,
    so a review panel of fifteen scored sixteen sessions — inflating the
    denominator `escalate()` divides friction by and the `--cost-log` series
    the CI cost-regression gate baselines against (#1994 review).
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    if "subagents" in parts:
        i = parts.index("subagents")
        # i == 0 would wrap to parts[-1] — the filename — recreating the
        # fabricated-session shape this function exists to prevent.
        return parts[i - 1] if i > 0 else path.stem
    return path.stem


def _project_and_ts(path: Path) -> tuple[str, str]:
    """Project label (basename of the recorded cwd) and the latest record
    timestamp, both from transcript DATA — never wall-clock, never a full path.
    The basename is the only project identifier emitted (privacy boundary)."""
    project = ""
    last_ts = ""
    for rec in _iter_records([path]):
        if not project:
            cwd = rec.get("cwd")
            if isinstance(cwd, str) and cwd:
                project = _redact(str(cwd).rstrip("/\\"), from_path=True)
        ts = rec.get("timestamp")
        if isinstance(ts, str) and ts > last_ts:
            last_ts = ts
    return project or "unknown", last_ts


def sync_record(
    digest: dict, host: str, project: str, session_id: str, ts: str
) -> dict:
    """One per-session, metrics-only record for cross-machine aggregation (#178).

    Identity (host / project basename / session_id / ts) plus the slim metric
    blocks. Carries model ids and the main/subagent split (non-sensitive) but no
    file names, paths, prompts, or code — same privacy boundary as the digest."""
    base = slim_record(digest)
    tok = digest.get("token", {})
    acc = digest.get("accuracy", {})
    util = digest.get("utilization", {})
    by_model = {
        m: dict(sorted(v.items())) for m, v in sorted(tok.get("by_model", {}).items())
    }
    return {
        "schema": _SYNC_SCHEMA,
        "plugin_version": digest.get("plugin_version", "unknown"),
        "host": host,
        "project": project,
        "session_id": session_id,
        "ts": ts,
        "synced_at": base["recorded_at"],
        "sessions": digest.get("sessions", 0),
        "tokens": base["tokens"],
        "cost_usd": base["cost_usd"],
        "cache_hit_ratio": base["cache_hit_ratio"],
        "by_model": by_model,
        # `by_thread` on the sync record has always meant "message counts per
        # thread"; extract() now supplies them keyed by AGENT NAME rather than
        # by "sidechain"/"main" (#1994), which is strictly more information at
        # the same field. The v1 fallback keeps a pre-#1994 digest readable.
        "by_thread": tok.get("by_agent_type", tok.get("by_subagent", {})),
        "rework": base["rework"],
        # #711: by_skill/by_agent correction attribution comes from the FULL
        # digest (not slim_record, which deliberately drops per-name maps) —
        # same pattern already used above for by_thread.
        "accuracy": {
            **base["accuracy"],
            "by_skill": dict(sorted(acc.get("by_skill", {}).items())),
            "by_agent": dict(sorted(acc.get("by_agent", {}).items())),
        },
        "gate": base["gate"],
        # Utilization carries the invoked NAME maps (registry ids, non-sensitive),
        # not slim counts, so a cross-host rollup can compute which skills/agents
        # were never invoked on ANY machine (#178 union read).
        "utilization": {
            "skills_invoked": dict(sorted(util.get("skills_invoked", {}).items())),
            "agents_invoked": dict(sorted(util.get("agents_invoked", {}).items())),
            "agent_dispatches": dict(
                sorted(util.get("agent_dispatches", {}).items())
            ),
        },
    }


def _load_watermark(path: Path) -> dict:
    """Read the sync watermark (session_id -> bytes already synced). Missing or
    malformed -> a fresh empty watermark (fail-open)."""
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict) and isinstance(data.get("synced"), dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"synced": {}}


def cmd_sync(
    args, pricing: dict, registry: dict, host: str, plugin_version: str
) -> int:
    """Incremental, cross-project sync (#178): emit one metrics-only record per
    session that is NEW or has grown since the machine's last sync, into the
    host digest file. The watermark dedups by session_id + byte size, so re-runs
    re-emit only changed sessions and skip everything else."""
    out = Path(args.sync_out)
    wm_path = (
        Path(args.watermark)
        if args.watermark
        else (Path.home() / ".claude" / ".dev-team" / "telemetry-sync.json")
    )
    wm = _load_watermark(wm_path)
    synced = wm["synced"]

    if args.transcript:
        paths = [Path(p) for p in args.transcript]
    elif args.project_dir:
        paths = sorted(Path(args.project_dir).glob("*.jsonl"), key=lambda x: x.name)
    else:
        paths = resolve_all_transcripts(args)

    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))

    # One record per SESSION, not per file: a session's dispatched agents are
    # part of that session's cost and rework, not sessions of their own.
    by_session: dict[str, list[Path]] = {}
    for path in paths:
        by_session.setdefault(_owning_session_dir(root, path), []).append(path)

    emitted = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for session_id, session_paths in sorted(by_session.items()):
            session_paths = sorted(session_paths, key=lambda p: str(p))
            size = 0
            for p in session_paths:
                try:
                    size += p.stat().st_size
                except OSError:
                    continue
            if not size:
                continue
            prev = synced.get(session_id)
            # Watermark on the session's TOTAL bytes, so a session re-syncs
            # when any of its agent transcripts grows, not only its main one.
            if isinstance(prev, int) and prev >= size:
                continue  # already synced and unchanged
            main = next(
                (p for p in session_paths if not _is_subagent_transcript(root, p)),
                session_paths[0],
            )
            project, ts = _project_and_ts(main)
            digest = extract(
                session_paths, pricing, registry, plugin_version, projects_root=root
            )
            rec = sync_record(digest, host, project, _opaque_session_id(session_id), ts)
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            synced[session_id] = size
            emitted += 1

    wm_path.parent.mkdir(parents=True, exist_ok=True)
    wm_path.write_text(json.dumps(wm, indent=2, sort_keys=True) + "\n")
    print(
        f"synced {emitted} new/changed session(s) of {len(by_session)} considered -> {out}"
    )
    return 0


def _normalize_plugin_version(value) -> str | None:
    """Bound + validate a `plugin_version` read back from a PEER's synced
    digest — a different trust domain than our own plugin.json (#1480
    security review): any host that can write to the shared telemetry repo
    controls this value. Anything that isn't a short semver-ish token (not a
    string, wrong charset, or longer than `_VERSION_RE` allows) collapses to
    None, same as a genuinely-missing field — so a malicious or malformed
    peer record can never reach a numeric parse (`_parse_semver_key`) or get
    persisted unbounded into a rollup/escalation output."""
    return value if isinstance(value, str) and _VERSION_RE.match(value) else None


# The magnitude bound `_safe_number` enforces. Deliberately `2**53` (the
# largest integer a double can represent exactly), not `sys.float_info.max`:
# downstream callers multiply or accumulate this value — `rollup()` does
# `round(c * 1e6)` for `cost_micro` and `(tool_error_rate or 0.0) * n` for
# `err_weighted` — and a value near `sys.float_info.max` overflows to `inf`
# under either operation, raising an uncaught `OverflowError` from
# `round(inf)` or silently poisoning the aggregate with `inf`. `2**53` is
# small enough that no realistic downstream multiply-by-a-few-million or
# cross-record accumulation can reach `inf`, and large enough for any
# legitimate token count or cost figure.
#
# #2080: `_accumulate_token_signals` also routes the LOCAL-transcript token
# fields through `_safe_number` before `_cost`'s `inp / 1e6 * ir` runs, for
# the same reason in a different trust domain — an out-of-range int raises
# `OverflowError` on the int-to-float conversion `/` performs, which aborts
# `extract` before `round(cost * 1e6)` (below, at the peer-digest path) is
# ever reached. Both `round(cost * 1e6)` call sites are protected by the
# same bound now, not just the peer-ingestion one.
_NUM_MAX = 2**53


def _safe_number(value) -> int | float:
    """Bound a peer-supplied numeric field read back from a synced digest —
    the same trust boundary as `_normalize_plugin_version` above, applied to
    `int(...)`/`+=` sites instead of a semver parse. Returns `0` for anything
    that isn't a plain `int`/`float` (a `bool` included: it's an `int`
    subclass in Python, so `True` would otherwise silently become `1`), for a
    non-finite `float` (`NaN`/`Infinity`, which would poison a running `+=`
    aggregate for every OTHER host's data in the same run), for anything
    whose magnitude exceeds `_NUM_MAX` (see above), and for anything
    **negative** (#2079). Every field that ever reaches this function is a
    count or a cost — skill/agent invocation counts, `cost_usd`, rework
    counts — none of which is ever legitimately negative, so a negative
    value is exactly as untrusted as a non-numeric one. Left unclamped, a
    single hostile peer's `{"code-review": -999}` could drive a CROSS-HOST
    Counter negative: combined with the `c > 0` gate `rollup()` uses for
    `never_observed_skills`/`never_observed_agents`, that silently rewrites
    another host's genuine invocation out of `invoked_skills`. An `int` is
    never cast to `float` to check finiteness or magnitude —
    `math.isfinite(float(v))` raises `OverflowError` once `v`'s magnitude
    exceeds `sys.float_info.max`, a legal JSON integer with no wire-size
    limit, so a hostile peer can trivially send one and abort the run for
    every host. Comparing magnitude directly instead is safe for arbitrary
    precision: Python's int/float rich comparison never converts `value`
    through `float()`."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    if value < 0 or abs(value) > _NUM_MAX:
        return 0
    return value


def _normalize_name_dicts(container: dict, fields: tuple) -> None:
    """Rewrite each named dict-valued field of `container` through
    `_rewrite_name_keys`, in place. A field that's absent or not a dict is
    coerced to an empty dict — a peer-supplied non-dict value (e.g. a string
    or list) is as untrusted as any other field it carries, and left
    unrewritten it reaches `rollup()`'s unguarded `.items()` calls
    (`(acc.get("by_skill", {}) or {}).items()` and friends) and raises an
    uncaught AttributeError, aborting the caller for every host."""
    for field in fields:
        value = container.get(field)
        container[field] = _rewrite_name_keys(value) if isinstance(value, dict) else {}


def _normalize_numeric_fields(container: dict, fields: tuple) -> None:
    """Coerce each named field of `container` that's present through
    `_safe_number`, in place. A field that's absent is left untouched, same
    as the inline `if field in container:` guard this was extracted from."""
    for field in fields:
        if field in container:
            container[field] = _safe_number(container[field])


def _read_synced_records(digests_root: Path) -> list[dict]:
    """Union read + dedup (#178): every host's per-session record (schema-
    versioned, see `SYNC_SCHEMAS`) under `digests_root/<host>/session-digest.jsonl`,
    keeping the LAST record for a session_id seen on multiple host files (or
    re-emitted after growth). Shared by `rollup()`, `correlate_gate_rework()`,
    and `cost_log()`
    so the dedup logic lives in one place. Each record's `plugin_version`,
    `host`, `project`, `ts`, the name-bearing dicts under
    `utilization`/`accuracy`, every peer-supplied numeric field a downstream
    consumer reads with `int(...)`/`+=` (`cost_usd`; `tokens.{input_tokens,
    output_tokens,cache_creation_input_tokens,cache_read_input_tokens}`;
    `rework.*` restricted to `_REWORK_KEYS`; `accuracy.{tool_calls,
    tool_error_rate,user_correction_turns}`;
    `gate.{commit_attempts,commit_bypasses,gate_ran_absent,gate_ran_errored,
    gate_ran_clean}`), and the shape of the
    `tokens`/`rework`/`accuracy`/`utilization`/`gate` containers themselves
    are normalized on the way in (`_normalize_plugin_version`, `_redact`,
    `_rewrite_name_keys`, `_safe_number`, `_normalize_name_dicts`,
    `_normalize_numeric_fields`) since a record originates on a peer
    machine, not this one."""
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if not isinstance(rec, dict):
                # A peer's digest line can decode to any JSON value (a bare
                # array/string/number/null) — `_iter_records` only excludes
                # undecodable lines. `.get()` below would raise on anything
                # else, aborting the run for every host over one line.
                continue
            if rec.get("schema") not in SYNC_SCHEMAS:
                continue
            sid = rec.get("session_id")
            if not sid:
                continue
            rec["plugin_version"] = _normalize_plugin_version(
                rec.get("plugin_version")
            )
            rec["host"] = _redact(str(rec.get("host") or "unknown"))
            rec["project"] = _redact(str(rec.get("project") or "unknown"))
            rec["ts"] = _redact(rec["ts"]) if isinstance(rec.get("ts"), str) else ""
            rec["cost_usd"] = _safe_number(rec.get("cost_usd", 0))
            utilization = (
                rec.get("utilization") if isinstance(rec.get("utilization"), dict) else {}
            )
            accuracy = rec.get("accuracy") if isinstance(rec.get("accuracy"), dict) else {}
            tokens = rec.get("tokens") if isinstance(rec.get("tokens"), dict) else {}
            rework = rec.get("rework") if isinstance(rec.get("rework"), dict) else {}
            gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}

            _normalize_name_dicts(
                utilization, ("skills_invoked", "agents_invoked", "agent_dispatches")
            )
            _normalize_name_dicts(accuracy, ("by_skill", "by_agent"))
            _normalize_numeric_fields(
                tokens,
                (
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                ),
            )
            # rework is restricted to the known `_REWORK_KEYS` schema, not
            # just value-coerced — an unknown/hostile key is the same
            # key-leak class `host`/`project` sanitization closes above, and
            # `_session_rework()` already reads only `_REWORK_KEYS`, so
            # nothing legitimate is dropped by excluding the rest.
            rework = {k: _safe_number(v) for k, v in rework.items() if k in _REWORK_KEYS}
            _normalize_numeric_fields(
                accuracy, ("tool_calls", "tool_error_rate", "user_correction_turns")
            )
            _normalize_numeric_fields(
                gate,
                (
                    "commit_attempts",
                    "commit_bypasses",
                    "gate_ran_absent",
                    "gate_ran_errored",
                    "gate_ran_clean",
                ),
            )

            rec["utilization"] = utilization
            rec["accuracy"] = accuracy
            rec["tokens"] = tokens
            rec["rework"] = rework
            rec["gate"] = gate
            by_id[str(sid)] = rec  # last write wins -> dedup on session_id
    return list(by_id.values())


def _filter_by_version(
    records: list[dict], version_window: set[str] | None
) -> list[dict]:
    """Drop records whose `plugin_version` isn't in `version_window` (#1480).
    `None` means unscoped — every record passes through unchanged. A record
    with no `plugin_version` (pre-#1471 data, or a foreign value normalized
    away by `_normalize_plugin_version`) never matches a concrete window —
    it can't be proven current, so it can't be included either."""
    if version_window is None:
        return records
    return [r for r in records if r.get("plugin_version") in version_window]


def _parse_semver_key(version: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d{1,9}", version or "")) or (0,)


def compute_version_window(records: list[dict], current: str) -> set[str]:
    """The current plugin version plus the newest version OBSERVED in
    `records` that is strictly OLDER than it (#1480). session_extract.py has
    no access to the plugin's release history, so "previous" means the most
    recent `plugin_version` actually present in the telemetry being scoped
    that predates `current` — never a lookup against CHANGELOG/git tags, and
    never a version that happens to be newer (a host or peer ahead of this
    one must not count as "previous").

    The `"unknown"` sentinel (an unreadable local manifest) is never treated
    as a real version on either side: if `current` itself is `"unknown"` the
    window is empty rather than silently admitting every peer record that is
    equally unattributable — an indeterminate current version can't prove
    anything else is current either."""
    if current == "unknown":
        return set()
    current_key = _parse_semver_key(current)
    older = sorted(
        (
            r.get("plugin_version")
            for r in records
            if r.get("plugin_version")
            and r.get("plugin_version") != "unknown"
            and _parse_semver_key(r.get("plugin_version")) < current_key
        ),
        key=_parse_semver_key,
    )
    window = {current}
    if older:
        window.add(older[-1])
    return window


def rollup(
    records: list[dict], registry: dict, version_window: set[str] | None = None
) -> dict:
    """Aggregate cross-machine `session-sync` records (schema-versioned, see
    `SYNC_SCHEMAS`; #178) — callers pass
    the already union-read + deduped list from `_read_synced_records()` (so a
    caller that also needs `compute_version_window()` reads the digests
    directory only once, #1480). Metrics only — sums, ratios, and
    registry-name maps. When `version_window` is given, only records tagged
    with a `plugin_version` in the window are aggregated."""
    records = _filter_by_version(records, version_window)
    hosts: set[str] = set()
    projects: set[str] = set()
    tok = Counter()
    cost = 0.0
    cr = cc = 0
    rew = Counter()
    tool_calls = 0
    err_weighted = 0.0
    corrections = 0
    correction_by_skill = Counter()  # #711
    correction_by_agent = Counter()
    skills_invoked = Counter()
    agents_invoked = Counter()
    agent_dispatches = Counter()
    by_host: dict[str, Counter] = defaultdict(Counter)
    by_project: dict[str, Counter] = defaultdict(Counter)

    for r in records:
        host = r.get("host")
        project = r.get("project")
        hosts.add(host)
        projects.add(project)
        t = r.get("tokens", {}) if isinstance(r.get("tokens"), dict) else {}
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            tok[k] += t.get(k, 0) or 0
        cr += t.get("cache_read_input_tokens", 0) or 0
        cc += t.get("cache_creation_input_tokens", 0) or 0
        c = r.get("cost_usd", 0.0) or 0.0
        cost += c
        for hk, agg in ((host, by_host), (project, by_project)):
            agg[hk]["sessions"] += 1
            agg[hk]["cost_micro"] += round(c * 1e6)
            agg[hk]["input_tokens"] += t.get("input_tokens", 0) or 0
            agg[hk]["output_tokens"] += t.get("output_tokens", 0) or 0
        rwk = r.get("rework", {}) if isinstance(r.get("rework"), dict) else {}
        for k, v in rwk.items():
            if isinstance(v, (int, float)):
                rew[k] += v
        acc = r.get("accuracy", {}) if isinstance(r.get("accuracy"), dict) else {}
        n = acc.get("tool_calls", 0) or 0
        tool_calls += n
        err_weighted += (acc.get("tool_error_rate", 0.0) or 0.0) * n
        corrections += acc.get("user_correction_turns", 0) or 0
        for name, k in (acc.get("by_skill", {}) or {}).items():
            correction_by_skill[name] += k
        for name, k in (acc.get("by_agent", {}) or {}).items():
            correction_by_agent[name] += k
        u = r.get("utilization", {}) if isinstance(r.get("utilization"), dict) else {}
        # Re-strip namespace prefixes at rollup time too: historical per-session
        # digests may have been written before `_strip_ns` existed (or before a
        # given prefix was added to its known list), so a raw `agentic-dev-team:x`
        # key can coexist with an already-stripped `x` key across different hosts'
        # digest files. Without renormalizing here, `x` is undercounted and can
        # wrongly surface in never_observed_* even though it was actually invoked
        # (#712).
        for name, k in (u.get("skills_invoked", {}) or {}).items():
            skills_invoked[_strip_ns(name)] += k
        for name, k in (u.get("agents_invoked", {}) or {}).items():
            agents_invoked[_strip_ns(name)] += k
        for name, k in (u.get("agent_dispatches", {}) or {}).items():
            agent_dispatches[_strip_ns(name)] += k

    # Membership, not count: a name coerced to a real key at count 0 (e.g. a
    # malformed peer value that `_safe_number` reduced to 0 rather than
    # aborting the run) must not read as "invoked" here -- only a positive
    # count counts as observed (#2016 closing-pass finding 2).
    invoked_skills = {n for n, c in skills_invoked.items() if c > 0}
    invoked_agents = {n for n, c in agents_invoked.items() if c > 0}
    dispatched_agents = {n for n, c in agent_dispatches.items() if c > 0}
    never_skills = sorted(set(registry.get("skills", [])) - invoked_skills)
    never_agents = sorted(
        set(registry.get("agents", [])) - invoked_agents - dispatched_agents
    )

    def _hostmap(d: dict) -> dict:
        return {k: dict(sorted(v.items())) for k, v in sorted(d.items())}

    return {
        "schema": "telemetry-rollup/v1",
        "version_window": sorted(version_window) if version_window is not None else [],
        "hosts": sorted(hosts),
        "projects": sorted(projects),
        "sessions": len(records),
        "tokens": dict(sorted(tok.items())),
        "cost_usd": round(cost, 4),
        "cache_hit_ratio": round(cr / (cr + cc), 4) if (cr + cc) else 0.0,
        "by_host": _hostmap(by_host),
        "by_project": _hostmap(by_project),
        "rework": dict(sorted(rew.items())),
        "accuracy": {
            "tool_calls": tool_calls,
            "tool_error_rate": round(err_weighted / tool_calls, 4)
            if tool_calls
            else 0.0,
            "user_correction_turns": corrections,
            "by_skill": dict(sorted(correction_by_skill.items())),
            "by_agent": dict(sorted(correction_by_agent.items())),
        },
        "utilization": {
            "skills_invoked": dict(sorted(skills_invoked.items())),
            "agents_invoked": dict(sorted(agents_invoked.items())),
            "agent_dispatches": dict(sorted(agent_dispatches.items())),
            "never_observed_skills": never_skills,
            "never_observed_agents": never_agents,
        },
    }


def _resolve_version_window(
    args, records: list[dict], plugin_root: Path | None
) -> set[str] | None:
    """#1480: only when --version-scope current-and-previous is requested,
    compute the window from the CURRENT plugin.json version plus whichever
    version immediately precedes it among `records` (already read by the
    caller — this is a pure computation, no I/O, so the digests directory is
    read exactly once per invocation regardless of whether scoping is on).
    Default (`all`) returns None — unscoped, unbounded history — so existing
    callers of --rollup/--escalate/--correlate keep their prior behavior."""
    if args.version_scope != "current-and-previous":
        return None
    current = _load_plugin_version(plugin_root)
    return compute_version_window(records, current)


def cmd_rollup(args, registry: dict, plugin_root: Path | None) -> int:
    root = Path(args.rollup)
    if not root.is_dir():
        print(
            json.dumps(
                {
                    "schema": "telemetry-rollup/v1",
                    "version_window": [],
                    "sessions": 0,
                    "hosts": [],
                    "projects": [],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    records = _read_synced_records(root)
    window = _resolve_version_window(args, records, plugin_root)
    out = json.dumps(rollup(records, registry, window), indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


# --------------------------------------------------------------------------
# Process eval (#111): does bypassing the review gate correlate with rework?
#
# Narrowed from "A/B the whole ceremony" to a question the trend stream can
# already answer: across real sessions, do the ones that bypassed the pre-commit
# review gate (git commit --no-verify) carry MORE rework than the ones that
# didn't? Correlation, not causation — but it's the evidence #112 needs to decide
# whether that gate earns its place.
# --------------------------------------------------------------------------

_REWORK_KEYS = (
    "failed_edits",
    "repeated_file_edits",
    "retried_bash_commands",
    "repeated_verify_runs",
    "permission_denials",
    "compaction_events",
)


def _session_rework(rec: dict) -> int:
    rw = rec.get("rework", {}) if isinstance(rec.get("rework"), dict) else {}
    return sum(int(rw.get(k, 0) or 0) for k in _REWORK_KEYS)


def correlate_gate_rework(
    records: list[dict], version_window: set[str] | None = None
) -> dict:
    """Across all sessions that committed, compare mean rework between those that
    bypassed the review gate and those that didn't (#111). `records` is the
    already union-read + deduped list from `_read_synced_records()`.
    `version_window` (#1480) scopes the comparison to a set of
    `plugin_version` values."""
    records = _filter_by_version(records, version_window)

    bypass_rework: list[int] = []
    clean_rework: list[int] = []
    for rec in records:
        gate = rec.get("gate", {}) if isinstance(rec.get("gate"), dict) else {}
        if int(gate.get("commit_attempts", 0) or 0) <= 0:
            continue  # only sessions that actually committed are comparable
        (
            bypass_rework
            if int(gate.get("commit_bypasses", 0) or 0) > 0
            else clean_rework
        ).append(_session_rework(rec))

    def _mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    mb, mc = _mean(bypass_rework), _mean(clean_rework)
    if not bypass_rework or not clean_rework:
        interp = "insufficient data — need committing sessions in BOTH groups"
    elif mb > mc:
        interp = (
            "bypassing the review gate correlates with MORE rework "
            f"({mb} vs {mc}) — evidence the gate guards real risk"
        )
    elif mb < mc:
        interp = (
            "bypassing correlates with LESS rework "
            f"({mb} vs {mc}) — the gate may be ceremony for these cases"
        )
    else:
        interp = "no difference in rework between bypass and non-bypass sessions"

    return {
        "schema": "gate-correlation/v1",
        "version_window": sorted(version_window) if version_window is not None else [],
        "committing_sessions": len(bypass_rework) + len(clean_rework),
        "bypass_sessions": len(bypass_rework),
        "clean_sessions": len(clean_rework),
        "mean_rework_when_bypassed": mb,
        "mean_rework_when_gated": mc,
        "interpretation": interp,
    }


def cmd_correlate(args, plugin_root: Path | None) -> int:
    root = Path(args.correlate)
    if root.is_dir():
        records = _read_synced_records(root)
        window = _resolve_version_window(args, records, plugin_root)
        result = correlate_gate_rework(records, window)
    else:
        result = {
            "schema": "gate-correlation/v1",
            "version_window": [],
            "committing_sessions": 0,
            "interpretation": "no digests directory",
        }
    out = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


def cost_log(digests_root: Path) -> list[dict]:
    """Per-session cost SERIES for the cost-meter regression gate (#171).

    `rollup()` returns one aggregate; the regression check in `cost_meter.py`
    instead needs a time-ordered list of per-session costs so it can compare the
    most recent session against the cross-machine rolling baseline. This reuses
    `_read_synced_records()`'s union read + dedup, orders oldest->newest by
    `ts`, and emits cost-meter records: `{"ts": ..., "total": {"cost_usd":
    ...}}` (extra `ts` is ignored by `regression` and used by `pace`)."""
    recs = sorted(
        _read_synced_records(digests_root),
        key=lambda r: (r.get("ts") or "", str(r.get("session_id"))),
    )
    return [
        {"ts": r.get("ts"), "total": {"cost_usd": r.get("cost_usd", 0.0) or 0.0}}
        for r in recs
    ]


def cmd_cost_log(args) -> int:
    root = Path(args.cost_log)
    lines = (
        "\n".join(json.dumps(rec, sort_keys=True) for rec in cost_log(root))
        if root.is_dir()
        else ""
    )
    if args.out:
        Path(args.out).write_text(lines + ("\n" if lines else ""))
    elif lines:
        print(lines)
    return 0


# --------------------------------------------------------------------------
# Delta C (#179): frequency -> lever-strength escalation.
#
# Each known friction signal is tagged with whether a deterministic guard could
# match it (the "hook-matchable" property). Combined with how often the friction
# recurs (per-session rate across the rollup), this yields the recommended lever:
#   rare                       -> hint (surface only)
#   recurring, not matchable   -> instruction-file rule (/feedback-learning)
#   frequent AND matchable     -> promote to a hook (validate via /agent-eval)
# "matchable" is the deterministic side of the rules-vs-prompts <=10% FP policy.
# --------------------------------------------------------------------------

# signal -> (rollup section, key, hook-matchable?, human label)
_FRICTION_SIGNALS = [
    ("rework", "permission_denials", True, "permission denials"),
    ("rework", "retried_bash_commands", True, "retried bash commands"),
    ("rework", "repeated_verify_runs", True, "repeated verify runs"),
    ("rework", "failed_edits", False, "failed edits (old_string not found)"),
    ("rework", "compaction_events", False, "context compaction events"),
    ("accuracy", "user_correction_turns", False, "user-correction turns"),
]


def _lever_for(
    rate: float, matchable: bool, rare_rate: float, frequent_rate: float
) -> tuple[str, str]:
    if rate < rare_rate:
        return "hint", "rare — surface as a hint only"
    if matchable and rate >= frequent_rate:
        return (
            "hook",
            "frequent and deterministically matchable — promote to a hook (validate via /agent-eval)",
        )
    if matchable:
        return (
            "instruction-rule",
            "recurring and matchable but below the hook threshold — an instruction-file rule for now (/feedback-learning)",
        )
    return (
        "instruction-rule",
        "recurring but judgment-shaped (no reliable matcher) — an instruction-file rule (/feedback-learning)",
    )


def escalate(roll: dict, rare_rate: float = 0.25, frequent_rate: float = 1.0) -> dict:
    """Turn rollup recurrence into ranked lever recommendations (#179)."""
    sessions = max(int(roll.get("sessions", 0)), 0)
    recs = []
    for section, key, matchable, label in _FRICTION_SIGNALS:
        count = roll.get(section, {}).get(key, 0) or 0
        if not count:
            continue
        rate = round(count / sessions, 4) if sessions else 0.0
        lever, rationale = _lever_for(rate, matchable, rare_rate, frequent_rate)
        recs.append(
            {
                "signal": key,
                "label": label,
                "count": count,
                "per_session_rate": rate,
                "matchable": matchable,
                "lever": lever,
                "rationale": rationale,
            }
        )
    # rank by per-session rate (worst first), then count
    recs.sort(key=lambda r: (-r["per_session_rate"], -r["count"]))
    return {
        "schema": "telemetry-escalation/v1",
        "sessions": sessions,
        "version_window": roll.get("version_window", []),
        "thresholds": {"rare_rate": rare_rate, "frequent_rate": frequent_rate},
        "recommendations": recs,
    }


def cmd_escalate(args, registry: dict, plugin_root: Path | None) -> int:
    root = Path(args.escalate)
    if root.is_dir():
        records = _read_synced_records(root)
        window = _resolve_version_window(args, records, plugin_root)
        roll = rollup(records, registry, window)
    else:
        roll = {"sessions": 0, "version_window": []}
    out = json.dumps(
        escalate(roll, rare_rate=args.rare_rate, frequent_rate=args.frequent_rate),
        indent=2,
        sort_keys=True,
    )
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


def load_registry(plugin_root: Path | None) -> dict:
    """Enumerate shipped skills/agents so we can report never-observed ones."""
    if plugin_root is None:
        # scripts/ -> repo root -> plugins/dev-team
        plugin_root = Path(__file__).resolve().parent.parent / "plugins" / "dev-team"
    skills_dir = plugin_root / "skills"
    agents_dir = plugin_root / "agents"
    skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    agents = (
        sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    )
    return {"skills": skills, "agents": agents}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--transcript",
        action="append",
        help="explicit transcript JSONL file(s); repeatable",
    )
    ap.add_argument("--project-dir", help="a directory of *.jsonl transcripts")
    ap.add_argument("--cwd", help="project cwd to match (default: $PWD)")
    ap.add_argument(
        "--projects-root",
        help="root of Claude Code project transcripts (default: ~/.claude/projects)",
    )
    ap.add_argument("--pricing", help="model-pricing.json for cost (optional)")
    ap.add_argument("--plugin-root", help="dev-team plugin root for the registry")
    ap.add_argument("-o", "--out", help="write digest here (default: stdout)")
    ap.add_argument(
        "--append",
        metavar="LOG",
        help="append one metrics-only summary record to a trend "
        "stream (append-only JSONL), e.g. metrics/session-digest.jsonl",
    )
    ap.add_argument(
        "--all-projects",
        action="store_true",
        help="aggregate transcripts across ALL projects, not just the "
        "current cwd's project (Delta D, #178)",
    )
    ap.add_argument(
        "--sync-out",
        metavar="FILE",
        help="cross-project incremental SYNC mode (#178): append one "
        "metrics-only record per new/changed session to FILE "
        "(the host digest), tracked by --watermark",
    )
    ap.add_argument(
        "--watermark",
        metavar="FILE",
        help="watermark JSON for incremental sync "
        "(default: ~/.claude/.dev-team/telemetry-sync.json)",
    )
    ap.add_argument("--host", help="host label for sync records (default: hostname)")
    ap.add_argument(
        "--rollup",
        metavar="DIR",
        help="union read (#178): aggregate all hosts' "
        "DIR/<host>/session-digest.jsonl into one cross-machine view",
    )
    ap.add_argument(
        "--cost-log",
        metavar="DIR",
        help="cost-meter baseline (#171): from DIR/<host>/session-digest.jsonl "
        "emit a time-ordered per-session cost series "
        '({"total":{"cost_usd":..}}) for `cost_meter.py regression`',
    )
    ap.add_argument(
        "--escalate",
        metavar="DIR",
        help="Delta C (#179): rank friction signals from DIR's rollup "
        "and recommend a lever (hint / instruction-rule / hook)",
    )
    ap.add_argument(
        "--correlate",
        metavar="DIR",
        help="process eval (#111): from DIR's digests, compare rework "
        "between review-gate-bypass and non-bypass sessions",
    )
    ap.add_argument(
        "--rare-rate",
        type=float,
        default=0.25,
        help="per-session rate below which a friction is a hint (default 0.25)",
    )
    ap.add_argument(
        "--frequent-rate",
        type=float,
        default=1.0,
        help="per-session rate at/above which a matchable friction "
        "becomes a hook (default 1.0)",
    )
    ap.add_argument(
        "--version-scope",
        choices=["all", "current-and-previous"],
        default="all",
        help="scope --rollup/--escalate/--correlate to plugin_version-tagged "
        "records (#1480): 'all' (default, unbounded history) or "
        "'current-and-previous' (only the current + immediately previous "
        "plugin_version observed in the digests being read)",
    )
    ap.add_argument(
        "--boundary-events",
        metavar="FILE",
        help="gate-run correlation (#2037): boundary-events.jsonl to read "
        "gate_ran events from (default: <cwd>/.claude/metrics/"
        "boundary-events.jsonl)",
    )
    args = ap.parse_args(argv)

    pricing_path = (
        Path(args.pricing)
        if args.pricing
        else (
            Path(__file__).resolve().parent.parent
            / "plugins/dev-team/knowledge/model-pricing.json"
        )
    )
    pricing = _load_pricing(pricing_path)
    plugin_root = Path(args.plugin_root) if args.plugin_root else None
    registry = load_registry(plugin_root)
    version = _load_plugin_version(plugin_root)

    # Cross-machine union read (Delta D, #178).
    if args.rollup:
        return cmd_rollup(args, registry, plugin_root)

    # Cross-machine cost baseline for the regression gate (#171).
    if args.cost_log:
        return cmd_cost_log(args)

    # Frequency -> lever escalation (Delta C, #179).
    if args.escalate:
        return cmd_escalate(args, registry, plugin_root)

    # Gate-bypass vs rework correlation (process eval, #111).
    if args.correlate:
        return cmd_correlate(args, plugin_root)

    # Cross-project incremental sync mode (Delta D, #178).
    if args.sync_out:
        import socket

        host = args.host or socket.gethostname()
        return cmd_sync(args, pricing, registry, host, version)

    paths = (
        resolve_all_transcripts(args)
        if args.all_projects
        else resolve_transcripts(args)
    )

    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    boundary_events_path = (
        Path(args.boundary_events)
        if args.boundary_events
        else Path(os.path.abspath(args.cwd or os.getcwd()))
        / ".claude"
        / "metrics"
        / "boundary-events.jsonl"
    )
    digest = extract(
        paths,
        pricing,
        registry,
        version,
        projects_root=root,
        boundary_events_path=boundary_events_path,
    )
    # `transcripts` is set by extract() and counts MAIN-thread sessions only;
    # `subagent_transcripts` counts dispatched agent runs. Overwriting it with
    # len(paths) here would report every file as a session (#1994).
    out = json.dumps(digest, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)

    if args.append:
        _append_trend(Path(args.append), digest)
    return 0


def slim_record(digest: dict) -> dict:
    """A compact, AGGREGATE-COUNTS-ONLY trend record (#129).

    Deliberately drops the per-name maps (by_skill/by_model/repeated_file_edits)
    so the persisted trend stream carries no file names — strictly metrics, no
    raw prompt/code content. `recorded_at` is the only wall-clock field and lives
    on the trend log, never in the deterministic digest output."""

    tok = digest.get("token", {})
    rew = digest.get("rework", {})
    acc = digest.get("accuracy", {})
    gate = digest.get("gate", {})
    util = digest.get("utilization", {})
    totals = tok.get("totals", {})
    return {
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema": _DIGEST_SCHEMA,
        "plugin_version": digest.get("plugin_version", "unknown"),
        "sessions": digest.get("sessions", 0),
        "transcripts": digest.get("transcripts", 0),
        "tokens": {
            k: totals.get(k, 0)
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        },
        "cost_usd": tok.get("cost_usd", 0.0),
        "cache_hit_ratio": tok.get("cache_hit_ratio", 0.0),
        "rework": {
            "failed_edits": rew.get("failed_edits", 0),
            "repeated_file_edits": len(rew.get("repeated_file_edits", {})),
            "retried_bash_commands": rew.get("retried_bash_commands", 0),
            "repeated_verify_runs": rew.get("repeated_verify_runs", 0),
            "permission_denials": rew.get("permission_denials", 0),
            "compaction_events": rew.get("compaction_events", 0),
        },
        "accuracy": {
            "tool_calls": acc.get("tool_calls", 0),
            "tool_error_rate": acc.get("tool_error_rate", 0.0),
            "user_correction_turns": acc.get("user_correction_turns", 0),
        },
        "gate": {
            "commit_attempts": gate.get("commit_attempts", 0),
            "commit_bypasses": gate.get("commit_bypasses", 0),
            "bypass_rate": gate.get("bypass_rate", 0.0),
            "gate_ran_absent": gate.get("gate_ran_absent", 0),
            "gate_ran_errored": gate.get("gate_ran_errored", 0),
            "gate_ran_clean": gate.get("gate_ran_clean", 0),
        },
        "utilization": {
            "skills_invoked": len(util.get("skills_invoked", {})),
            "agents_invoked": len(util.get("agents_invoked", {})),
            "never_observed_skills": len(util.get("never_observed_skills", [])),
            "never_observed_agents": len(util.get("never_observed_agents", [])),
        },
    }


def _append_trend(log: Path, digest: dict) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(slim_record(digest), sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
