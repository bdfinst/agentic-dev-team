#!/usr/bin/env python3
"""Unified session-log report CLI (epic #2040, issue #2046).

One shipped entry point over the ``session_log`` package, with two profiles
selected by ``--profile``:

``--profile maintainer``
    Replaces ``scripts/session_extract.py`` (monorepo-only developer
    tooling: feeds ``/session-review`` and the ``session-digest.jsonl``
    trend stream this repo uses to judge its own harness). Emits
    ``session-digest/v3``. Retains every mode that exists nowhere else:
    ``--sync-out``/``--watermark``/``--host``, ``--rollup``, ``--cost-log``,
    ``--escalate``, ``--correlate``, ``--append``, ``--all-projects``,
    ``--transcript``, ``--project-dir``, ``--cwd``, ``--pricing``,
    ``--plugin-root``.

``--profile downstream``
    Replaces ``plugins/dev-team/scripts/extract_session_report.py`` (the
    standalone, shippable report any dev-team user can hand to the plugin
    maintainer). Emits ``downstream-session-report/v3``. Retains
    ``--project``, ``--all-projects``, ``--since DAYS``, ``--until``,
    ``--plugin-version``, ``--out``.

Because this script ships under ``plugins/dev-team/scripts/`` (unlike its
monorepo-only predecessor), the maintainer profile is now available to a
normally-installed plugin — closing #1779 at the root instead of guarding it
per-invocation as PR #1820 did.

SCHEMA VERSIONING: both profiles bump to v3 (from v2) purely as a version
label on this new, unified entry point — the still-present, still-working
predecessor scripts (retired in #2048) are UNCHANGED and continue emitting
v2. ``SYNC_SCHEMAS`` is the one exported constant naming every sync-record
schema a reader (``_read_synced_records``/``rollup``) accepts; no call site
literal-matches a schema string. See ADR 0036 for why a half-applied bump
(a writer stamping a new version while a reader still exact-matches the old
one) silently drops data rather than erroring.

PATH RESOLUTION (ADR 0032): this script is Category 1 (shipped and
portable) in both profiles — every path it touches (``session_log``,
``hooks/lib/pricing``, its own ``knowledge/model-pricing.json``, its own
``skills``/``agents`` directories for the default registry) resolves
relative to its own location inside ``plugins/dev-team/``, with no
dependency on a monorepo checkout.

Stdlib only (Python 3.10+ floor, ADR 0031) — deliberately uses
``timezone.utc``, not ``datetime.UTC`` (a 3.11+ addition that
``scripts/session_extract.py`` could use only because that monorepo-only
script isn't subject to the shipped-tree floor).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import socket
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# This script ships at plugins/dev-team/scripts/session_report.py — a
# sibling of plugins/dev-team/scripts/lib/, so no parent.parent indirection
# is needed (unlike scripts/session_extract.py, which reaches across from
# the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from session_log import classify, discovery, records, redact, signals

_redact = redact.redact

# hooks/lib/pricing.py, not session_log/pricing.py (see hooks/lib/cost_meter.py's
# established rule, #1461/#2045): a hook must be import-safe without any
# scripts/ module on its path, so the dependency direction is scripts/ ->
# hooks/lib/, never the reverse. This script lives at plugins/dev-team/
# scripts/, so parent.parent is plugins/dev-team/, then hooks/lib.
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "hooks" / "lib")
)
from pricing import cost as _cost
from pricing import load_pricing as _load_pricing
from pricing import rate as _rate

# --------------------------------------------------------------------------
# Shared classification/signal vocabulary (session_log.classify/.signals,
# issues #2042-#2044). Identical aliases in both predecessor scripts;
# defined once here and used, unmodified, by both profiles' extract logic.
# --------------------------------------------------------------------------
_VERIFY_RE = classify.VERIFY_RE
_CORRECTION_RE = classify.CORRECTION_RE
_PERMISSION_RE = classify.PERMISSION_RE
_OLDSTRING_RE = classify.OLDSTRING_RE
_EDIT_TOOLS = signals.EDIT_TOOLS
_GIT_GLOBAL_OPTS_WITH_ARG = classify.GIT_GLOBAL_OPTS_WITH_ARG
_COMMIT_BYPASS_TOKENS = classify.COMMIT_BYPASS_TOKENS
_statement_break_newlines = classify.statement_break_newlines
_bash_segments = classify.bash_segments
_is_git_commit_argv = classify.is_git_commit_argv
_SAFE_NAME_RE = classify.SAFE_NAME_RE
_UNSAFE_NAME = classify.UNSAFE_NAME
_HARNESS_ATTRIBUTIONS = classify.HARNESS_ATTRIBUTIONS
_MAIN_LABEL = "main"
_UNATTRIBUTED_LABEL = "unattributed"
_strip_ns = classify.strip_ns
_text_of = classify.text_of

_is_transcript_path = discovery.is_transcript_path
_is_subagent_transcript = discovery.is_subagent_transcript
# Two alias names for the same function (discovery.all_transcripts),
# matching each predecessor's own naming so each profile's body below is
# otherwise unmodified.
_all_transcripts_under = discovery.all_transcripts
_all_transcripts = discovery.all_transcripts
_sorted_paths = discovery.sorted_paths
_relative_parts = discovery.relative_parts

_track_tool_call = signals.track_tool_call
_classify_tool_result = signals.classify_tool_result
_track_edit = signals.track_edit
_track_bash = signals.track_bash
_new_thread = signals.new_thread
_detect_correction_turn = signals.detect_correction_turn
_new_agent_bucket = signals.new_agent_bucket
_merge_agent_buckets = signals.merge_agent_buckets
_finalize_agent_buckets = signals.finalize_agent_buckets
_CONTEXT_TOKEN_FIELDS = signals.CONTEXT_TOKEN_FIELDS
_AGENT_BUCKET_FIELDS = signals.AGENT_BUCKET_FIELDS
_accumulate_skill_agent_signals = signals.accumulate_skill_agent_signals
_slim = records.slim_by_name
_iter_file_records = records.iter_file_records

_VERSION_RE = re.compile(r"^[0-9A-Za-z._+-]{1,32}$")

# --------------------------------------------------------------------------
# Schema versioning. See module docstring: both profiles bump to v3; the
# still-present predecessor scripts keep emitting v2 unchanged.
# --------------------------------------------------------------------------
_DIGEST_SCHEMA = "session-digest/v3"
_SYNC_SCHEMA = "session-sync/v3"
#: Sync-record schemas a reader accepts, oldest first. Exported so
#: scripts/eval_rawlog.py (and any other reader) imports this constant
#: instead of literal-matching a schema string — the ADR 0036 failure mode
#: this guards against is a writer bumping the stamped schema while a
#: reader still exact-matches the old one, which silently drops every
#: record instead of erroring.
SYNC_SCHEMAS = ("session-sync/v1", "session-sync/v2", "session-sync/v3")
_DOWNSTREAM_SCHEMA = "downstream-session-report/v3"


def _load_plugin_version(plugin_root: Path | None = None) -> str:
    """Read `.claude-plugin/plugin.json`'s version. `plugin_root` defaults
    to this script's own plugin root (`plugins/dev-team/`) since this
    script now lives inside the plugin tree in both profiles — unlike the
    predecessor scripts, neither profile needs a different default."""
    if plugin_root is None:
        plugin_root = Path(__file__).resolve().parent.parent
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


def load_registry(plugin_root: Path | None = None) -> dict:
    """Enumerate shipped skills/agents so a digest/report can name
    never-observed ones. `plugin_root` defaults the same way as
    `_load_plugin_version` above."""
    if plugin_root is None:
        plugin_root = Path(__file__).resolve().parent.parent
    skills_dir = Path(plugin_root) / "skills"
    agents_dir = Path(plugin_root) / "agents"
    skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    agents = (
        sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    )
    return {"skills": skills, "agents": agents}


# ==========================================================================
# MAINTAINER PROFILE (predecessor: scripts/session_extract.py)
# ==========================================================================

# --- gate-run correlation (#2037) -------------------------------------------
_GATE_RAN_HOOK = "pre-commit-gate"
_GATE_RAN_PREFIX = "gate-ran-"
GATE_RAN_WINDOW_SECONDS = 120


def _parse_event_ts(value) -> datetime | None:
    """Parse a `boundary-events.jsonl`/transcript timestamp
    (`%Y-%m-%dT%H:%M:%SZ`) into an aware UTC `datetime`, or `None` when
    `value` isn't a string in that exact shape."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _read_gate_ran_events(path: Path | None) -> list[tuple[datetime, str]]:
    """Every `gate_ran` boundary event's `(ts, verdict)` pair from
    `boundary-events.jsonl`, oldest first."""
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
    timeline: `"absent"`, `"errored"`, or `"clean"`."""
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
    aggregate. See scripts/session_extract.py's original docstring for the
    full rationale — unchanged here."""
    out: dict = {}
    for k, v in mapping.items():
        key = _redact(_strip_ns(str(k))) if isinstance(k, str) else _UNSAFE_NAME
        out[key] = out.get(key, 0) + _safe_number(v)
    return out


def _iter_records(paths: list[Path]):
    """Yield every decodable JSON record across `paths`, in order."""
    for path in sorted(paths, key=lambda x: str(x)):
        yield from records.iter_file_records(path)


def _accumulate_token_signals_maintainer(
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
    on top of `signals.accumulate_token_signals`'s shared core. Returns
    `(cost, safe_usage)`."""
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


def extract_maintainer(
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
    by_agent_type: dict[str, dict] = {}
    agent_runs = Counter()
    agent_dispatches = Counter()
    subagent_transcripts = 0
    main_transcripts = 0
    subagent_layout_present = False
    sessions: set[str] = set()

    edits_per_file = Counter()
    retried_bash_total = 0
    bash_signal_counts = Counter()
    commit_attempt_events: list[tuple[str | None, bool]] = []
    error_counts = Counter()
    compaction_events = 0
    tool_errors = Counter()
    tool_calls = Counter()
    correction_turns = 0
    correction_by_skill = Counter()
    correction_by_agent = Counter()

    skills_invoked = Counter()

    pending_tool: dict[str, str] = {}
    active: dict[str, str | None] = {"skill": None, "agent": None}

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
                    if stripped not in _HARNESS_ATTRIBUTIONS:
                        agent_name = _redact(stripped)
            rtype = rec.get("type")
            is_sidechain = bool(rec.get("isSidechain")) or is_subagent
            raw_skill = rec.get("attributionSkill") or rec.get("attribution_skill")
            skill = (
                _redact(_strip_ns(raw_skill))
                if isinstance(raw_skill, str) and raw_skill
                else None
            )

            if (
                rtype in ("compaction", "summary")
                or rec.get("isCompactSummary")
                or rec.get("compactMetadata")
            ):
                compaction_events += 1

            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            usage = records.usage_of(rec)
            raw_model = msg.get("model") or rec.get("model")
            raw_model = raw_model if isinstance(raw_model, str) and raw_model else None
            model = _redact(raw_model) if raw_model else None

            if usage:
                cost, safe_usage = _accumulate_token_signals_maintainer(
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
                    thread_msgs += 1
                    thread_usage["messages"] += 1
                    for f in signals.CONTEXT_TOKEN_FIELDS:
                        thread_usage[f] += safe_usage[f]
                    thread_usage["output_tokens"] += safe_usage["output_tokens"]
                else:
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

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        _track_tool_call(block, pending_tool, tool_calls)
                        _track_edit(block, edits_per_file, thread)
                        _track_bash(block, bash_signal_counts, thread)
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

            if not is_subagent and _detect_correction_turn(rec, content):
                correction_turns += 1
                correction_by_skill[active["skill"] or "unattributed"] += 1
                correction_by_agent[active["agent"] or "unattributed"] += 1

        label = agent_name or (_UNATTRIBUTED_LABEL if is_subagent else _MAIN_LABEL)
        if thread_msgs:
            bucket = by_agent_type.setdefault(label, signals.new_agent_bucket())
            bucket["messages"] += thread_usage["messages"]
            for f in signals.CONTEXT_TOKEN_FIELDS:
                bucket[f] += thread_usage[f]
            bucket["output_tokens"] += thread_usage["output_tokens"]
            if is_subagent:
                bucket["dispatches"] += 1
        if records_seen and is_subagent:
            subagent_transcripts += 1
            agent_runs[label] += 1
        elif records_seen:
            main_transcripts += 1
        retried_bash_total += sum(n - 1 for n in thread["bash_commands"].values() if n > 1)

    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    retried_bash = retried_bash_total
    failed_edits = error_counts["failed_edits"]
    permission_denials = error_counts["permission_denials"]
    repeated_verify_runs = bash_signal_counts["repeated_verify_runs"]
    commit_attempts = bash_signal_counts["commit_attempts"]
    commit_bypasses = bash_signal_counts["commit_bypasses"]

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

    agents_invoked = agent_runs if subagent_layout_present else agent_dispatches
    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    never_skills = sorted(reg_skills - set(skills_invoked))
    never_agents = sorted(reg_agents - set(agents_invoked) - set(agent_dispatches))

    cr = tokens_total["cache_read_input_tokens"]
    cc = tokens_total["cache_creation_input_tokens"]
    cache_hit_ratio = round(cr / (cr + cc), 4) if (cr + cc) else 0.0

    total_errors = sum(tool_errors.values())
    total_calls = sum(tool_calls.values())

    return {
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


def resolve_transcripts(args) -> list[Path]:
    """Robustly find the current project's transcript files."""
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
                for _ in range(20):
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
        except (OSError, ValueError):
            continue
    return sorted(matches, key=lambda x: str(x))


def resolve_all_transcripts(args) -> list[Path]:
    """Every transcript across ALL projects under projects-root (Delta D, #178)."""
    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    if not root.is_dir():
        return []
    return _all_transcripts_under(root)


def _opaque_session_id(session_id: str) -> str:
    """A safe session id that stays UNIQUE."""
    safe = _redact(session_id)
    if safe != _UNSAFE_NAME:
        return safe
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:8]
    return f"other-{digest}"


def _owning_session_dir(root: Path, path: Path) -> str:
    """The session a transcript belongs to, as a stable id."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    if "subagents" in parts:
        i = parts.index("subagents")
        return parts[i - 1] if i > 0 else path.stem
    return path.stem


def _project_and_ts(path: Path) -> tuple[str, str]:
    """Project label (basename of the recorded cwd) and the latest record
    timestamp, both from transcript DATA."""
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
    """One per-session, metrics-only record for cross-machine aggregation (#178)."""
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
        "by_thread": tok.get("by_agent_type", tok.get("by_subagent", {})),
        "rework": base["rework"],
        "accuracy": {
            **base["accuracy"],
            "by_skill": dict(sorted(acc.get("by_skill", {}).items())),
            "by_agent": dict(sorted(acc.get("by_agent", {}).items())),
        },
        "gate": base["gate"],
        "utilization": {
            "skills_invoked": dict(sorted(util.get("skills_invoked", {}).items())),
            "agents_invoked": dict(sorted(util.get("agents_invoked", {}).items())),
            "agent_dispatches": dict(
                sorted(util.get("agent_dispatches", {}).items())
            ),
        },
    }


def _load_watermark(path: Path) -> dict:
    """Read the sync watermark. Missing or malformed -> a fresh empty watermark."""
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
    """Incremental, cross-project sync (#178)."""
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
            if isinstance(prev, int) and prev >= size:
                continue
            main = next(
                (p for p in session_paths if not _is_subagent_transcript(root, p)),
                session_paths[0],
            )
            project, ts = _project_and_ts(main)
            digest = extract_maintainer(
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
    """Bound + validate a `plugin_version` read back from a PEER's synced digest."""
    return value if isinstance(value, str) and _VERSION_RE.match(value) else None


_NUM_MAX = 2**53


def _safe_number(value) -> int | float:
    """Bound a peer-supplied numeric field read back from a synced digest."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    if value < 0 or abs(value) > _NUM_MAX:
        return 0
    return value


def _normalize_name_dicts(container: dict, fields: tuple) -> None:
    """Rewrite each named dict-valued field of `container` through
    `_rewrite_name_keys`, in place."""
    for field in fields:
        value = container.get(field)
        container[field] = _rewrite_name_keys(value) if isinstance(value, dict) else {}


def _normalize_numeric_fields(container: dict, fields: tuple) -> None:
    """Coerce each named field of `container` that's present through `_safe_number`."""
    for field in fields:
        if field in container:
            container[field] = _safe_number(container[field])


def _read_synced_records(digests_root: Path) -> list[dict]:
    """Union read + dedup (#178): every host's per-session record (schema-
    versioned, see `SYNC_SCHEMAS`) under
    `digests_root/<host>/session-digest.jsonl`, keeping the LAST record for
    a session_id seen on multiple host files."""
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if not isinstance(rec, dict):
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
            by_id[str(sid)] = rec
    return list(by_id.values())


def _filter_by_version(
    records: list[dict], version_window: set[str] | None
) -> list[dict]:
    """Drop records whose `plugin_version` isn't in `version_window` (#1480)."""
    if version_window is None:
        return records
    return [r for r in records if r.get("plugin_version") in version_window]


def _parse_semver_key(version: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d{1,9}", version or "")) or (0,)


def compute_version_window(records: list[dict], current: str) -> set[str]:
    """The current plugin version plus the newest version OBSERVED in
    `records` that is strictly OLDER than it (#1480)."""
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
    `SYNC_SCHEMAS`; #178)."""
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
    correction_by_skill = Counter()
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
        for name, k in (u.get("skills_invoked", {}) or {}).items():
            skills_invoked[_strip_ns(name)] += k
        for name, k in (u.get("agents_invoked", {}) or {}).items():
            agents_invoked[_strip_ns(name)] += k
        for name, k in (u.get("agent_dispatches", {}) or {}).items():
            agent_dispatches[_strip_ns(name)] += k

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
    version immediately precedes it among `records`."""
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
    """Across all sessions that committed, compare mean rework between those
    that bypassed the review gate and those that didn't (#111)."""
    records = _filter_by_version(records, version_window)

    bypass_rework: list[int] = []
    clean_rework: list[int] = []
    for rec in records:
        gate = rec.get("gate", {}) if isinstance(rec.get("gate"), dict) else {}
        if int(gate.get("commit_attempts", 0) or 0) <= 0:
            continue
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
    """Per-session cost SERIES for the cost-meter regression gate (#171)."""
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


def slim_record(digest: dict) -> dict:
    """A compact, AGGREGATE-COUNTS-ONLY trend record (#129)."""
    tok = digest.get("token", {})
    rew = digest.get("rework", {})
    acc = digest.get("accuracy", {})
    gate = digest.get("gate", {})
    util = digest.get("utilization", {})
    totals = tok.get("totals", {})
    return {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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


# ==========================================================================
# DOWNSTREAM PROFILE (predecessor: plugins/dev-team/scripts/extract_session_report.py)
# ==========================================================================


def _accumulate_skill_agent_signals_downstream(content, skills_invoked, agent_dispatches):
    """Thin wrapper over the shared signals.accumulate_skill_agent_signals:
    this profile has no `attributionSkill` legacy-fallback concept and no
    by_skill/by_agent correction-turn breakdown, so `skill` is always None
    and `active` is a throwaway dict this profile never reads back."""
    signals.accumulate_skill_agent_signals(
        None, content, skills_invoked, agent_dispatches, {}
    )


def extract_downstream(
    paths: list[Path],
    registry: dict,
    projects_root: Path,
    since: str | None = None,
    until: str | None = None,
    allowed_sessions: set[str] | None = None,
) -> dict:
    """Metrics-only digest for one project's transcript files. Same signal
    classes as extract_maintainer(), minus per-model cost (no pricing table
    shipped downstream) and per-skill token attribution."""
    tokens_total = Counter()
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_agent_type = {}
    sessions: set[str] = set()

    edits_per_file = Counter()
    bash_signal_counts = Counter()
    error_counts = Counter()
    compaction_events = 0
    tool_errors = Counter()
    tool_calls = Counter()
    correction_turns = 0
    retried_bash = 0

    skills_invoked = Counter()
    agent_dispatches = Counter()
    agent_runs = Counter()
    subagent_transcripts = 0
    main_transcripts = 0
    subagent_layout_present = False

    for path in _sorted_paths(paths):
        is_subagent = _is_subagent_transcript(projects_root, path)
        if is_subagent:
            subagent_layout_present = True
        agent_name: str | None = None
        thread = _new_thread()
        pending_tool: dict[str, str] = {}
        thread_msgs = 0
        thread_usage = _new_agent_bucket()
        records_in_window = 0

        for rec in _iter_file_records(path):
            sid = rec.get("sessionId") or rec.get("session_id")

            if allowed_sessions is not None and str(sid or "") not in allowed_sessions:
                continue
            if since is not None or until is not None:
                ts = rec.get("timestamp")
                if not isinstance(ts, str):
                    continue
                if since is not None and ts < since:
                    continue
                if until is not None and ts > until:
                    continue

            records_in_window += 1
            if sid:
                sessions.add(str(sid))
            if is_subagent and agent_name is None:
                attributed = rec.get("attributionAgent")
                if isinstance(attributed, str) and attributed:
                    stripped = _strip_ns(attributed)
                    if stripped not in _HARNESS_ATTRIBUTIONS:
                        agent_name = _redact(stripped)
            rtype = rec.get("type")

            if rtype in ("compaction", "summary") or rec.get("isCompactSummary") or rec.get("compactMetadata"):
                compaction_events += 1

            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            usage = records.usage_of(rec)
            model = msg.get("model") or rec.get("model")
            model = _redact(model) if isinstance(model, str) and model else None
            if usage:
                thread_msgs += 1
                signals.accumulate_token_signals(usage, model, tokens_total, by_model)
                thread_usage["messages"] += 1
                for field in _CONTEXT_TOKEN_FIELDS:
                    thread_usage[field] += usage.get(field, 0) or 0

            content = msg.get("content")
            _accumulate_skill_agent_signals_downstream(content, skills_invoked, agent_dispatches)

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        _track_tool_call(block, pending_tool, tool_calls)
                        _track_edit(block, edits_per_file, thread)
                        _track_bash(block, bash_signal_counts, thread)
                    elif btype == "tool_result":
                        _classify_tool_result(block, pending_tool, tool_errors, error_counts)

            if not is_subagent and _detect_correction_turn(rec, content):
                correction_turns += 1

        label = agent_name or (_UNATTRIBUTED_LABEL if is_subagent else _MAIN_LABEL)
        if thread_msgs:
            bucket = by_agent_type.setdefault(label, _new_agent_bucket())
            bucket["messages"] += thread_usage["messages"]
            for field in _CONTEXT_TOKEN_FIELDS:
                bucket[field] += thread_usage[field]
            if is_subagent:
                bucket["dispatches"] += 1
        if records_in_window and is_subagent:
            subagent_transcripts += 1
            agent_runs[label] += 1
        elif records_in_window:
            main_transcripts += 1
        retried_bash += sum(n - 1 for n in thread["bash_commands"].values() if n > 1)

    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}

    agents_invoked = agent_runs if subagent_layout_present else agent_dispatches

    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    never_skills = sorted(reg_skills - set(skills_invoked))
    never_agents = sorted(reg_agents - set(agents_invoked) - set(agent_dispatches))

    cr = tokens_total["cache_read_input_tokens"]
    cc = tokens_total["cache_creation_input_tokens"]
    cache_hit_ratio = round(cr / (cr + cc), 4) if (cr + cc) else 0.0

    total_errors = sum(tool_errors.values())
    total_calls = sum(tool_calls.values())

    return {
        "sessions": len(sessions),
        "transcripts": main_transcripts,
        "subagent_transcripts": subagent_transcripts,
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cache_hit_ratio": cache_hit_ratio,
            "by_model": records.slim_by_name(by_model),
            "by_agent_type": _finalize_agent_buckets(by_agent_type),
        },
        "rework": {
            "failed_edits": error_counts["failed_edits"],
            "repeated_file_edits": dict(sorted(repeated_file_edits.items())),
            "retried_bash_commands": retried_bash,
            "repeated_verify_runs": bash_signal_counts["repeated_verify_runs"],
            "permission_denials": error_counts["permission_denials"],
            "compaction_events": compaction_events,
        },
        "accuracy": {
            "tool_errors_by_tool": dict(sorted(tool_errors.items())),
            "tool_calls": total_calls,
            "tool_error_rate": round(total_errors / total_calls, 4) if total_calls else 0.0,
            "user_correction_turns": correction_turns,
        },
        "gate": {
            "commit_attempts": bash_signal_counts["commit_attempts"],
            "commit_bypasses": bash_signal_counts["commit_bypasses"],
            "bypass_rate": round(
                bash_signal_counts["commit_bypasses"] / bash_signal_counts["commit_attempts"], 4
            )
            if bash_signal_counts["commit_attempts"]
            else 0.0,
        },
        "utilization": {
            "skills_invoked": dict(sorted(skills_invoked.items())),
            "agents_invoked": dict(sorted(agents_invoked.items())),
            "agent_dispatches": dict(sorted(agent_dispatches.items())),
            "never_observed_skills": never_skills,
            "never_observed_agents": never_agents,
        },
    }


def _merge_counters(dst: Counter, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, (int, float)):
            dst[k] += v


def combine(digests: dict[str, dict], registry: dict) -> dict:
    """Sum every project's digest into one cross-project total."""
    sessions = 0
    transcripts = 0
    subagent_transcripts = 0
    tokens_total = Counter()
    by_agent_type = {}
    cr = cc = 0
    rework = Counter()
    repeated_file_edits: Counter = Counter()
    accuracy_tool_errors = Counter()
    tool_calls = 0
    err_weighted = 0.0
    corrections = 0
    commit_attempts = commit_bypasses = 0
    skills_invoked = Counter()
    agents_invoked = Counter()
    agent_dispatches = Counter()

    for d in digests.values():
        sessions += d["sessions"]
        transcripts += d["transcripts"]
        subagent_transcripts += d.get("subagent_transcripts", 0)
        _merge_counters(tokens_total, d["token"]["totals"])
        _merge_agent_buckets(by_agent_type, d["token"]["by_agent_type"])
        cr += d["token"]["totals"].get("cache_read_input_tokens", 0)
        cc += d["token"]["totals"].get("cache_creation_input_tokens", 0)

        rw = d["rework"]
        rework["failed_edits"] += rw["failed_edits"]
        for f, n in rw["repeated_file_edits"].items():
            repeated_file_edits[f] += n
        rework["retried_bash_commands"] += rw["retried_bash_commands"]
        rework["repeated_verify_runs"] += rw["repeated_verify_runs"]
        rework["permission_denials"] += rw["permission_denials"]
        rework["compaction_events"] += rw["compaction_events"]

        acc = d["accuracy"]
        _merge_counters(accuracy_tool_errors, acc["tool_errors_by_tool"])
        n = acc["tool_calls"]
        tool_calls += n
        err_weighted += acc["tool_error_rate"] * n
        corrections += acc["user_correction_turns"]

        gate = d["gate"]
        commit_attempts += gate["commit_attempts"]
        commit_bypasses += gate["commit_bypasses"]

        util = d["utilization"]
        _merge_counters(skills_invoked, util["skills_invoked"])
        _merge_counters(agents_invoked, util["agents_invoked"])
        _merge_counters(agent_dispatches, util.get("agent_dispatches", {}))

    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))

    return {
        "sessions": sessions,
        "transcripts": transcripts,
        "subagent_transcripts": subagent_transcripts,
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cache_hit_ratio": round(cr / (cr + cc), 4) if (cr + cc) else 0.0,
            "by_agent_type": _finalize_agent_buckets(by_agent_type),
        },
        "rework": {
            "failed_edits": rework["failed_edits"],
            "repeated_file_edits": dict(sorted(repeated_file_edits.items())),
            "retried_bash_commands": rework["retried_bash_commands"],
            "repeated_verify_runs": rework["repeated_verify_runs"],
            "permission_denials": rework["permission_denials"],
            "compaction_events": rework["compaction_events"],
        },
        "accuracy": {
            "tool_errors_by_tool": dict(sorted(accuracy_tool_errors.items())),
            "tool_calls": tool_calls,
            "tool_error_rate": round(err_weighted / tool_calls, 4) if tool_calls else 0.0,
            "user_correction_turns": corrections,
        },
        "gate": {
            "commit_attempts": commit_attempts,
            "commit_bypasses": commit_bypasses,
            "bypass_rate": round(commit_bypasses / commit_attempts, 4) if commit_attempts else 0.0,
        },
        "utilization": {
            "skills_invoked": dict(sorted(skills_invoked.items())),
            "agents_invoked": dict(sorted(agents_invoked.items())),
            "agent_dispatches": dict(sorted(agent_dispatches.items())),
            "never_observed_skills": sorted(reg_skills - set(skills_invoked)),
            "never_observed_agents": sorted(
                reg_agents - set(agents_invoked) - set(agent_dispatches)
            ),
        },
    }


def _project_dir_name(projects_root: Path, jsonl: Path) -> str:
    """The project directory a transcript belongs to, at any nesting depth."""
    return _relative_parts(projects_root, jsonl)[0]


def _opaque_label(dir_name: str) -> str:
    """Fallback label for a project directory no transcript gave a `cwd`."""
    return f"unknown-project-{hashlib.sha256(dir_name.encode('utf-8')).hexdigest()[:8]}"


def _project_label(cwd: str) -> str:
    return _redact(cwd, from_path=True)


def _first_cwd(jsonl: Path) -> str | None:
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for _ in range(20):
                line = fh.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec_cwd = rec.get("cwd")
                if isinstance(rec_cwd, str) and rec_cwd:
                    return rec_cwd
    except OSError:
        pass
    return None


def discover_projects(projects_root: Path) -> dict[str, dict]:
    """Group every transcript under `projects_root` by the project cwd
    recorded inside it."""
    if not projects_root.is_dir():
        return {}
    by_dir: dict[str, dict] = defaultdict(lambda: {"cwd": None, "paths": []})
    for jsonl in _all_transcripts(projects_root):
        entry = by_dir[_project_dir_name(projects_root, jsonl)]
        entry["paths"].append(jsonl)
        if not entry["cwd"]:
            cwd = _first_cwd(jsonl)
            if cwd:
                entry["cwd"] = os.path.abspath(cwd)

    by_project: dict[str, dict] = defaultdict(lambda: {"cwd": None, "paths": []})
    for dir_name, entry in by_dir.items():
        label = _project_label(entry["cwd"]) if entry["cwd"] else _opaque_label(dir_name)
        merged = by_project[label]
        if entry["cwd"] and not merged["cwd"]:
            merged["cwd"] = entry["cwd"]
        merged["paths"].extend(entry["paths"])
    return dict(by_project)


def resolve_single_project(
    projects_root: Path, target_cwd: str
) -> tuple[str, str | None, list[Path]]:
    target_cwd = os.path.abspath(target_cwd)
    by_project = discover_projects(projects_root)
    label = _project_label(target_cwd)
    if label in by_project:
        return label, by_project[label]["cwd"], by_project[label]["paths"]
    matches: list[Path] = []
    if projects_root.is_dir():
        for jsonl in _all_transcripts(projects_root):
            cwd = _first_cwd(jsonl)
            if cwd and os.path.abspath(cwd) == target_cwd:
                matches.append(jsonl)
    return label, (target_cwd if matches else None), _sorted_paths(matches)


def sessions_matching_plugin_version(cwd: str | None, target_version: str) -> set[str]:
    """Best-effort session_id set for a --plugin-version filter."""
    matches: set[str] = set()
    if not cwd:
        return matches
    path = Path(cwd) / ".claude" / "metrics" / "boundary-events.jsonl"
    for rec in _iter_file_records(path):
        if rec.get("plugin_version") != target_version:
            continue
        sid = rec.get("session_id")
        if sid:
            matches.add(str(sid))
    return matches


def _non_negative_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if n < 0:
        raise argparse.ArgumentTypeError(f"{value!r} must not be negative")
    return n


# ==========================================================================
# Unified CLI
# ==========================================================================


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--profile",
        choices=["maintainer", "downstream"],
        required=True,
        help="maintainer: scripts/session_extract.py's replacement "
        "(monorepo developer tooling). downstream: "
        "extract_session_report.py's replacement (shippable, hand-to-"
        "maintainer report).",
    )

    # --- maintainer-only flags ---
    ap.add_argument(
        "--transcript",
        action="append",
        help="[maintainer] explicit transcript JSONL file(s); repeatable",
    )
    ap.add_argument(
        "--project-dir", help="[maintainer] a directory of *.jsonl transcripts"
    )
    ap.add_argument("--cwd", help="[maintainer] project cwd to match (default: $PWD)")
    ap.add_argument("--pricing", help="[maintainer] model-pricing.json for cost (optional)")
    ap.add_argument(
        "--plugin-root", help="[maintainer] dev-team plugin root for the registry"
    )
    ap.add_argument(
        "--append",
        metavar="LOG",
        help="[maintainer] append one metrics-only summary record to a trend "
        "stream (append-only JSONL), e.g. metrics/session-digest.jsonl",
    )
    ap.add_argument(
        "--sync-out",
        metavar="FILE",
        help="[maintainer] cross-project incremental SYNC mode (#178)",
    )
    ap.add_argument(
        "--watermark",
        metavar="FILE",
        help="[maintainer] watermark JSON for incremental sync",
    )
    ap.add_argument("--host", help="[maintainer] host label for sync records")
    ap.add_argument(
        "--rollup",
        metavar="DIR",
        help="[maintainer] union read (#178): aggregate all hosts' "
        "DIR/<host>/session-digest.jsonl into one cross-machine view",
    )
    ap.add_argument(
        "--cost-log",
        metavar="DIR",
        help="[maintainer] cost-meter baseline (#171)",
    )
    ap.add_argument(
        "--escalate",
        metavar="DIR",
        help="[maintainer] Delta C (#179): rank friction signals and recommend a lever",
    )
    ap.add_argument(
        "--correlate",
        metavar="DIR",
        help="[maintainer] process eval (#111): compare rework between "
        "review-gate-bypass and non-bypass sessions",
    )
    ap.add_argument(
        "--rare-rate",
        type=float,
        default=0.25,
        help="[maintainer] per-session rate below which a friction is a hint (default 0.25)",
    )
    ap.add_argument(
        "--frequent-rate",
        type=float,
        default=1.0,
        help="[maintainer] per-session rate at/above which a matchable friction "
        "becomes a hook (default 1.0)",
    )
    ap.add_argument(
        "--version-scope",
        choices=["all", "current-and-previous"],
        default="all",
        help="[maintainer] scope --rollup/--escalate/--correlate to plugin_version-tagged records (#1480)",
    )
    ap.add_argument(
        "--boundary-events",
        metavar="FILE",
        help="[maintainer] gate-run correlation (#2037): boundary-events.jsonl to read gate_ran events from",
    )

    # --- downstream-only flags ---
    ap.add_argument(
        "--project",
        metavar="PATH",
        help="[downstream] extract only the project whose cwd is PATH (default: current directory)",
    )
    ap.add_argument(
        "--since",
        metavar="DAYS",
        type=_non_negative_int,
        help="[downstream] only include activity from the last DAYS days",
    )
    ap.add_argument(
        "--until",
        metavar="ISO8601",
        help="[downstream] only include activity at/before this UTC timestamp or date",
    )
    ap.add_argument(
        "--plugin-version",
        metavar="VERSION",
        help="[downstream] best-effort: only include sessions this project's "
        "local .claude/metrics/boundary-events.jsonl recorded under VERSION",
    )

    # --- shared flags ---
    ap.add_argument(
        "--projects-root",
        help="root of Claude Code project transcripts (default: ~/.claude/projects)",
    )
    ap.add_argument(
        "--all-projects",
        action="store_true",
        help="aggregate/extract across ALL projects, not just the current cwd's",
    )
    ap.add_argument(
        "-o", "--out", help="output file path (meaning is profile-specific; see docstring)"
    )
    return ap


def _main_maintainer(args) -> int:
    pricing_path = (
        Path(args.pricing)
        if args.pricing
        else (Path(__file__).resolve().parent.parent / "knowledge" / "model-pricing.json")
    )
    pricing = _load_pricing(pricing_path)
    plugin_root = Path(args.plugin_root) if args.plugin_root else None
    registry = load_registry(plugin_root)
    version = _load_plugin_version(plugin_root)

    if args.rollup:
        return cmd_rollup(args, registry, plugin_root)
    if args.cost_log:
        return cmd_cost_log(args)
    if args.escalate:
        return cmd_escalate(args, registry, plugin_root)
    if args.correlate:
        return cmd_correlate(args, plugin_root)
    if args.sync_out:
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
    digest = extract_maintainer(
        paths,
        pricing,
        registry,
        version,
        projects_root=root,
        boundary_events_path=boundary_events_path,
    )
    out = json.dumps(digest, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)

    if args.append:
        _append_trend(Path(args.append), digest)
    return 0


def _main_downstream(args) -> int:
    since = None
    if args.since is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=args.since)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    until = args.until
    if until and re.fullmatch(r"\d{4}-\d{2}-\d{2}", until):
        until = f"{until}T23:59:59Z"

    projects_root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    plugin_root = Path(__file__).resolve().parent.parent
    registry = load_registry(plugin_root)
    plugin_version = _load_plugin_version(plugin_root)
    host = socket.gethostname()

    def _allowed_sessions(cwd: str | None) -> set[str] | None:
        return (
            sessions_matching_plugin_version(cwd, args.plugin_version)
            if args.plugin_version
            else None
        )

    digests: dict[str, dict] = {}

    if args.all_projects:
        by_project = discover_projects(projects_root)
        if not by_project:
            print(f"no session transcripts found under {projects_root}")
            return 1
        for label, entry in sorted(by_project.items()):
            digests[label] = extract_downstream(
                entry["paths"], registry, projects_root, since, until,
                _allowed_sessions(entry["cwd"]),
            )
        mode = "all-projects"
        scope = "all"
    else:
        target = args.project or os.getcwd()
        label, cwd, paths = resolve_single_project(projects_root, target)
        if not paths:
            print(f"no session transcripts found for project matching {target!r} under {projects_root}")
            return 1
        digests[label] = extract_downstream(
            paths, registry, projects_root, since, until, _allowed_sessions(cwd)
        )
        mode = "single-project"
        scope = label

    report = {
        "schema": _DOWNSTREAM_SCHEMA,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": host,
        "plugin_version": plugin_version,
        "mode": mode,
        "filters": {
            "since": since,
            "until": until,
            "plugin_version": args.plugin_version,
        },
        "projects": digests,
        "combined": combine(digests, registry),
    }

    out_path = Path(
        args.out
        or f"session-report-{scope}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(digests)} project(s), {report['combined']['sessions']} session(s))")
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    if args.profile == "maintainer":
        return _main_maintainer(args)
    return _main_downstream(args)


if __name__ == "__main__":
    raise SystemExit(main())
