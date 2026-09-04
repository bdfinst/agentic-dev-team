"""session_report_maintainer.py — the maintainer profile of session_report.py
(predecessor: scripts/session_extract.py).

Split out of session_report.py (issue #2098): everything specific to
`--profile maintainer` — monorepo-only developer tooling that feeds
`/session-review` and the `session-digest.jsonl` trend stream this repo uses
to judge its own harness. Emits `session-digest/v4` (`extract_maintainer`)
plus the `--rollup`/`--cost-log`/`--escalate`/`--correlate`/`--sync-out`
modes. See session_report.py's own module docstring for the full profile
contract; this module holds the implementation, not the CLI surface.

PATH RESOLUTION (ADR 0032): this module lives at
plugins/dev-team/scripts/lib/, one level deeper than session_report.py
itself, so its own __file__-relative path resolution needs one more
`.parent` than the top-level CLI's did before the split.

Stdlib only (Python 3.10+ floor, ADR 0031). Deliberately uses
`timezone.utc`, not `datetime.UTC` (a 3.11+ addition) — see
session_report.py's module docstring for why.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from session_report_shared import (
    _COMMIT_BYPASS_TOKENS,
    _DIGEST_SCHEMA,
    _HARNESS_ATTRIBUTIONS,
    _MAIN_LABEL,
    _SYNC_SCHEMA,
    _UNATTRIBUTED_LABEL,
    _UNSAFE_NAME,
    _VERSION_RE,
    SYNC_SCHEMAS,
    _accumulate_skill_agent_signals,
    _all_transcripts_under,
    _bash_segments,
    _classify_tool_result,
    _correction_rate_map,
    _detect_correction_turn,
    _finalize_correction_causes,
    _first_cwd,
    _is_git_commit_argv,
    _is_subagent_transcript,
    _load_plugin_version,
    _new_correction_causes_state,
    _new_correction_context,
    _observe_assistant_turn,
    _record_correction_cause,
    _redact,
    _slim,
    _strip_ns,
    _text_of,
    _track_bash,
    _track_edit,
    _track_tool_call,
    records,
    resolve_session_plugin_version,
    signals,
)

# hooks/lib/pricing.py, not session_log/pricing.py (see hooks/lib/cost_meter.py's
# established rule, #1461/#2045): a hook must be import-safe without any
# scripts/ module on its path, so the dependency direction is scripts/ ->
# hooks/lib/, never the reverse. This module lives at plugins/dev-team/
# scripts/lib/, so parent.parent.parent is plugins/dev-team/, then hooks/lib.
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "hooks" / "lib")
)
from pricing import cost as _cost
from pricing import rate as _rate

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
    retried_bash_by_skill = Counter()
    retried_bash_by_agent = Counter()
    bash_signal_counts = Counter()
    commit_attempt_events: list[tuple[str | None, bool]] = []
    error_counts = Counter()
    compaction_events = 0
    tool_errors = Counter()
    tool_calls = Counter()
    correction_turns = 0
    correction_by_skill = Counter()
    correction_by_agent = Counter()
    correction_causes = _new_correction_causes_state()

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
        turn_context = _new_correction_context()

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
            observed_turn = _observe_assistant_turn(rec, content)
            if observed_turn is not None:
                turn_context = observed_turn
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
                        _track_bash(
                            block,
                            bash_signal_counts,
                            thread,
                            active=active,
                            retried_by_skill=retried_bash_by_skill,
                            retried_by_agent=retried_bash_by_agent,
                        )
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
                _record_correction_cause(
                    correction_causes, turn_context, active.get("last"), _text_of(content)
                )

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

    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    # Single source of truth (#2110): the scalar is the sum of the live,
    # per-event attribution below, not a second independent computation —
    # the two could otherwise drift the way the churn-report window key did
    # (#2108).
    retried_bash = sum(retried_bash_by_skill.values())
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
            "retried_bash_commands_by_skill": dict(sorted(retried_bash_by_skill.items())),
            "retried_bash_commands_by_agent": dict(sorted(retried_bash_by_agent.items())),
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
            "correction_rate_by_skill": _correction_rate_map(correction_by_skill, skills_invoked),
            "correction_rate_by_agent": _correction_rate_map(
                correction_by_agent, agent_dispatches
            ),
            "correction_causes": _finalize_correction_causes(correction_causes, correction_turns),
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
    rew = digest.get("rework", {})
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
        "rework": {
            **base["rework"],
            "retried_bash_commands_by_skill": dict(
                sorted(rew.get("retried_bash_commands_by_skill", {}).items())
            ),
            "retried_bash_commands_by_agent": dict(
                sorted(rew.get("retried_bash_commands_by_agent", {}).items())
            ),
        },
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
            # The session's own .claude/metrics/boundary-events.jsonl -- used
            # below both to correlate `gate_ran` events against this
            # session's commit attempts (#2106: omitting this argument here
            # left EVERY synced session's gate_ran_events read as `None` ->
            # `[]`, so every non-bypassed commit attempt classified
            # "absent" regardless of whether the git-native pre-commit hook
            # actually ran -- the digest's "100% gate_ran_absent" reflected
            # this sync path never looking, not the gate never firing) and
            # to resolve the session's own plugin_version below (#2018).
            raw_cwd = _first_cwd(main)
            boundary_events_path = (
                Path(raw_cwd) / ".claude" / "metrics" / "boundary-events.jsonl"
                if raw_cwd
                else None
            )
            digest = extract_maintainer(
                session_paths,
                pricing,
                registry,
                plugin_version,
                projects_root=root,
                boundary_events_path=boundary_events_path,
            )
            # #2018: this per-session sync record is what durably archives
            # onto .claude/metrics/session-digest.jsonl at every
            # SessionStart (.claude/ensure_session_archive.py) -- exactly
            # the path where extraction-time `plugin_version` (the value
            # threaded through as the `plugin_version` parameter above)
            # mislabels a historical session with today's checked-out
            # version. Override the digest's own field with the SESSION's
            # resolved version -- its own project's boundary-events.jsonl,
            # keyed by this loop's raw session_id -- before building the
            # sync record; falls back to "unknown" when the session's real
            # cwd can't be determined or has no matching boundary event.
            digest["plugin_version"] = (
                resolve_session_plugin_version(session_id, boundary_events_path)
                if raw_cwd
                else "unknown"
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
            _normalize_name_dicts(
                rework,
                ("retried_bash_commands_by_skill", "retried_bash_commands_by_agent"),
            )
            _normalize_numeric_fields(
                tokens,
                (
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                ),
            )
            # The two dict-valued fields just sanitized above are captured
            # before the numeric-only comprehension below, which would
            # otherwise drop them (`_REWORK_KEYS` is numeric-scalar-only,
            # like `repeated_file_edits`'s already-summarized length) or
            # crash `_safe_number` on a dict value.
            retried_by_skill = rework["retried_bash_commands_by_skill"]
            retried_by_agent = rework["retried_bash_commands_by_agent"]
            rework = {k: _safe_number(v) for k, v in rework.items() if k in _REWORK_KEYS}
            rework["retried_bash_commands_by_skill"] = retried_by_skill
            rework["retried_bash_commands_by_agent"] = retried_by_agent
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
    retried_bash_by_skill = Counter()
    retried_bash_by_agent = Counter()
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
        for name, k in (rwk.get("retried_bash_commands_by_skill", {}) or {}).items():
            retried_bash_by_skill[name] += k
        for name, k in (rwk.get("retried_bash_commands_by_agent", {}) or {}).items():
            retried_bash_by_agent[name] += k
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
        "rework": {
            **dict(sorted(rew.items())),
            "retried_bash_commands_by_skill": dict(sorted(retried_bash_by_skill.items())),
            "retried_bash_commands_by_agent": dict(sorted(retried_bash_by_agent.items())),
        },
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
