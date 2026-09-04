"""session_report_downstream.py — the downstream profile of
session_report.py (predecessor: plugins/dev-team/scripts/extract_session_report.py).

Split out of session_report.py (issue #2098): everything specific to
`--profile downstream` — the standalone, shippable report any dev-team user
can hand to the plugin maintainer, with no monorepo dependency. Emits the
per-project digest (`extract_downstream`) and the cross-project total
(`combine`); the top-level `downstream-session-report/v4` report shape
itself is assembled by `_main_downstream()` in session_report.py.

DEDUP (issue #2098 acceptance): `extract_downstream()` and `combine()`
independently shaped near-identical "rework"/"gate"/"utilization"/"accuracy"
sub-objects — the same keys and formulas, just sourced from a per-transcript
accumulation in one case and a cross-project merge in the other. The
`_shape_*` helpers below are the single place each of those shapes is now
built; only "token" stays unshared, since the two callers genuinely differ
there (combine() has no by_model breakdown — it never merges per-model
totals across projects).

PATH RESOLUTION (ADR 0032): this module lives at
plugins/dev-team/scripts/lib/, one level deeper than session_report.py
itself, so its own __file__-relative path resolution needs one more
`.parent` than the top-level CLI's did before the split.

Stdlib only (Python 3.10+ floor, ADR 0031).
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
from session_report_shared import (
    _CONTEXT_TOKEN_FIELDS,
    _HARNESS_ATTRIBUTIONS,
    _MAIN_LABEL,
    _UNATTRIBUTED_LABEL,
    _VERSION_RE,
    _all_transcripts,
    _classify_tool_result,
    _correction_rate_map,
    _detect_correction_turn,
    _finalize_agent_buckets,
    _finalize_correction_causes,
    _first_cwd,
    _is_subagent_transcript,
    _iter_file_records,
    _merge_agent_buckets,
    _new_agent_bucket,
    _new_correction_causes_state,
    _new_correction_context,
    _new_thread,
    _observe_assistant_turn,
    _record_correction_cause,
    _redact,
    _relative_parts,
    _sorted_paths,
    _strip_ns,
    _text_of,
    _track_bash,
    _track_edit,
    _track_tool_call,
    records,
    signals,
)


def _accumulate_skill_agent_signals_downstream(content, skills_invoked, agent_dispatches, active):
    """Thin wrapper over the shared signals.accumulate_skill_agent_signals:
    this profile has no `attributionSkill` legacy-fallback concept, so
    `skill` is always None. `active` (#2013) IS read back here, unlike
    before #2013 -- the correction cause-data classifier's `component`
    field needs the same sticky skill/agent pointer the maintainer profile
    already tracked for its `by_skill`/`by_agent` correction breakdown."""
    signals.accumulate_skill_agent_signals(
        None, content, skills_invoked, agent_dispatches, active
    )


# --------------------------------------------------------------------------
# Shared output shaping (issue #2098) -- see module docstring.
# --------------------------------------------------------------------------


def _shape_rework(
    failed_edits: int,
    repeated_file_edits: dict,
    retried_bash_by_skill: Counter,
    retried_bash_by_agent: Counter,
    repeated_verify_runs: int,
    permission_denials: int,
    compaction_events: int,
) -> dict:
    """The `rework` sub-object's shape -- identical between
    `extract_downstream()`'s per-transcript accumulation and `combine()`'s
    cross-project merge, previously duplicated verbatim in both.

    `retried_bash_commands` (#2110) is derived from `retried_bash_by_skill`
    rather than passed separately -- a single source of truth, matching
    #2108's own lesson about a scalar and its breakdown drifting apart."""
    return {
        "failed_edits": failed_edits,
        "repeated_file_edits": dict(sorted(repeated_file_edits.items())),
        "retried_bash_commands": sum(retried_bash_by_skill.values()),
        "retried_bash_commands_by_skill": dict(sorted(retried_bash_by_skill.items())),
        "retried_bash_commands_by_agent": dict(sorted(retried_bash_by_agent.items())),
        "repeated_verify_runs": repeated_verify_runs,
        "permission_denials": permission_denials,
        "compaction_events": compaction_events,
    }


def _shape_gate(commit_attempts: int, commit_bypasses: int) -> dict:
    """The `gate` sub-object's shape -- identical between
    `extract_downstream()` and `combine()` (unlike the maintainer profile's
    `gate`, this profile tracks no gate_ran_*/#2037 correlation),
    previously duplicated verbatim in both."""
    return {
        "commit_attempts": commit_attempts,
        "commit_bypasses": commit_bypasses,
        "bypass_rate": round(commit_bypasses / commit_attempts, 4)
        if commit_attempts
        else 0.0,
    }


def _shape_utilization(
    skills_invoked: Counter,
    agents_invoked: Counter,
    agent_dispatches: Counter,
    registry: dict,
) -> dict:
    """The `utilization` sub-object's shape, including the
    never-observed-skill/agent set math -- identical between
    `extract_downstream()` and `combine()`, previously duplicated verbatim
    in both."""
    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    return {
        "skills_invoked": dict(sorted(skills_invoked.items())),
        "agents_invoked": dict(sorted(agents_invoked.items())),
        "agent_dispatches": dict(sorted(agent_dispatches.items())),
        "never_observed_skills": sorted(reg_skills - set(skills_invoked)),
        "never_observed_agents": sorted(
            reg_agents - set(agents_invoked) - set(agent_dispatches)
        ),
    }


def _shape_accuracy(
    tool_errors_by_tool: dict,
    tool_calls: int,
    tool_error_rate: float,
    user_correction_turns: int,
    correction_by_skill: Counter,
    correction_by_agent: Counter,
    skills_invoked: Counter,
    agent_dispatches: Counter,
    correction_causes: dict,
) -> dict:
    """The `accuracy` sub-object's OUTER shape -- identical between
    `extract_downstream()` and `combine()`, previously duplicated verbatim
    in both. Only `correction_causes` itself is computed differently by
    each caller (finalizing a fresh per-transcript tally vs. re-aggregating
    already-finalized per-project tallies), so it's passed in already
    shaped rather than unified here."""
    return {
        "tool_errors_by_tool": dict(sorted(tool_errors_by_tool.items())),
        "tool_calls": tool_calls,
        "tool_error_rate": tool_error_rate,
        "user_correction_turns": user_correction_turns,
        "by_skill": dict(sorted(correction_by_skill.items())),
        "by_agent": dict(sorted(correction_by_agent.items())),
        "correction_rate_by_skill": _correction_rate_map(correction_by_skill, skills_invoked),
        "correction_rate_by_agent": _correction_rate_map(
            correction_by_agent, agent_dispatches
        ),
        "correction_causes": correction_causes,
    }


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
    correction_by_skill = Counter()
    correction_by_agent = Counter()
    correction_causes = _new_correction_causes_state()
    retried_bash_by_skill = Counter()
    retried_bash_by_agent = Counter()

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
        active: dict[str, str | None] = {"skill": None, "agent": None}
        turn_context = _new_correction_context()

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
            observed_turn = _observe_assistant_turn(rec, content)
            if observed_turn is not None:
                turn_context = observed_turn
            _accumulate_skill_agent_signals_downstream(
                content, skills_invoked, agent_dispatches, active
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
                    elif btype == "tool_result":
                        _classify_tool_result(block, pending_tool, tool_errors, error_counts)

            if not is_subagent and _detect_correction_turn(rec, content):
                correction_turns += 1
                correction_by_skill[active["skill"] or "unattributed"] += 1
                correction_by_agent[active["agent"] or "unattributed"] += 1
                _record_correction_cause(
                    correction_causes, turn_context, active.get("last"), _text_of(content)
                )

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

    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    agents_invoked = agent_runs if subagent_layout_present else agent_dispatches

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
        "rework": _shape_rework(
            error_counts["failed_edits"],
            repeated_file_edits,
            retried_bash_by_skill,
            retried_bash_by_agent,
            bash_signal_counts["repeated_verify_runs"],
            error_counts["permission_denials"],
            compaction_events,
        ),
        "accuracy": _shape_accuracy(
            tool_errors,
            total_calls,
            round(total_errors / total_calls, 4) if total_calls else 0.0,
            correction_turns,
            correction_by_skill,
            correction_by_agent,
            skills_invoked,
            agent_dispatches,
            _finalize_correction_causes(correction_causes, correction_turns),
        ),
        "gate": _shape_gate(
            bash_signal_counts["commit_attempts"], bash_signal_counts["commit_bypasses"]
        ),
        "utilization": _shape_utilization(
            skills_invoked, agents_invoked, agent_dispatches, registry
        ),
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
    correction_by_skill = Counter()
    correction_by_agent = Counter()
    correction_by_what = Counter()
    correction_by_component = Counter()
    correction_by_shape = Counter()
    commit_attempts = commit_bypasses = 0
    skills_invoked = Counter()
    agents_invoked = Counter()
    agent_dispatches = Counter()
    retried_bash_by_skill = Counter()
    retried_bash_by_agent = Counter()

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
        _merge_counters(retried_bash_by_skill, rw.get("retried_bash_commands_by_skill", {}))
        _merge_counters(retried_bash_by_agent, rw.get("retried_bash_commands_by_agent", {}))
        rework["repeated_verify_runs"] += rw["repeated_verify_runs"]
        rework["permission_denials"] += rw["permission_denials"]
        rework["compaction_events"] += rw["compaction_events"]

        acc = d["accuracy"]
        _merge_counters(accuracy_tool_errors, acc["tool_errors_by_tool"])
        n = acc["tool_calls"]
        tool_calls += n
        err_weighted += acc["tool_error_rate"] * n
        corrections += acc["user_correction_turns"]
        _merge_counters(correction_by_skill, acc.get("by_skill", {}))
        _merge_counters(correction_by_agent, acc.get("by_agent", {}))
        causes = acc.get("correction_causes", {})
        _merge_counters(correction_by_what, causes.get("by_what", {}))
        _merge_counters(correction_by_component, causes.get("by_component", {}))
        _merge_counters(correction_by_shape, causes.get("by_shape", {}))

        gate = d["gate"]
        commit_attempts += gate["commit_attempts"]
        commit_bypasses += gate["commit_bypasses"]

        util = d["utilization"]
        _merge_counters(skills_invoked, util["skills_invoked"])
        _merge_counters(agents_invoked, util["agents_invoked"])
        _merge_counters(agent_dispatches, util.get("agent_dispatches", {}))

    return {
        "sessions": sessions,
        "transcripts": transcripts,
        "subagent_transcripts": subagent_transcripts,
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cache_hit_ratio": round(cr / (cr + cc), 4) if (cr + cc) else 0.0,
            "by_agent_type": _finalize_agent_buckets(by_agent_type),
        },
        "rework": _shape_rework(
            rework["failed_edits"],
            repeated_file_edits,
            retried_bash_by_skill,
            retried_bash_by_agent,
            rework["repeated_verify_runs"],
            rework["permission_denials"],
            rework["compaction_events"],
        ),
        "accuracy": _shape_accuracy(
            accuracy_tool_errors,
            tool_calls,
            round(err_weighted / tool_calls, 4) if tool_calls else 0.0,
            corrections,
            correction_by_skill,
            correction_by_agent,
            skills_invoked,
            agent_dispatches,
            {
                "by_what": dict(sorted(correction_by_what.items())),
                "by_component": dict(sorted(correction_by_component.items())),
                "by_shape": dict(sorted(correction_by_shape.items())),
                "ambiguous_share": round(
                    correction_by_shape.get("ambiguous", 0) / corrections, 4
                )
                if corrections
                else 0.0,
            },
        ),
        "gate": _shape_gate(commit_attempts, commit_bypasses),
        "utilization": _shape_utilization(
            skills_invoked, agents_invoked, agent_dispatches, registry
        ),
    }


def _project_dir_name(projects_root: Path, jsonl: Path) -> str:
    """The project directory a transcript belongs to, at any nesting depth."""
    return _relative_parts(projects_root, jsonl)[0]


def _opaque_label(dir_name: str) -> str:
    """Fallback label for a project directory no transcript gave a `cwd`."""
    return f"unknown-project-{hashlib.sha256(dir_name.encode('utf-8')).hexdigest()[:8]}"


def _project_label(cwd: str) -> str:
    return _redact(cwd, from_path=True)


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
    """Best-effort session_id set for a --plugin-version filter. Starting
    point for `resolve_session_plugin_version` (session_report_shared.py),
    which correlates one session_id at a time rather than filtering a whole
    set to one version."""
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


def _sessions_with_known_plugin_version(cwd: str | None) -> set[str]:
    """Every session_id in `cwd`'s boundary-events.jsonl carrying ANY
    resolvable `plugin_version` tag, regardless of its value (#2018
    coverage precision). A --plugin-version-filtered report's coverage
    figure must distinguish two different reasons a session lands outside
    `sessions_matching_plugin_version`'s result: (1) the session WAS
    attributed, just to a version other than the one requested -- the
    filter working as intended, not a data gap -- versus (2) the session
    has no resolvable version at all, because it never dispatched through
    anything that stamps `session_id`+`plugin_version` onto
    boundary-events.jsonl. Conflating the two under one "unattributed"
    count would misrepresent (1) as a data-quality problem it is not."""
    known: set[str] = set()
    if not cwd:
        return known
    path = Path(cwd) / ".claude" / "metrics" / "boundary-events.jsonl"
    for rec in _iter_file_records(path):
        version = rec.get("plugin_version")
        if not (isinstance(version, str) and _VERSION_RE.match(version)):
            continue
        sid = rec.get("session_id")
        if sid:
            known.add(str(sid))
    return known


def _scan_all_session_ids(
    paths: list[Path], since: str | None = None, until: str | None = None
) -> set[str]:
    """Every distinct session_id observed in `paths`, honoring the same
    since/until window `extract_downstream` applies, but ignoring any
    --plugin-version filter. Used ONLY to size a version-filtered report's
    own coverage figure (#2018) — "how many sessions did this report's
    window even contain, before the version filter dropped any of them" —
    never to build the digest itself."""
    ids: set[str] = set()
    for path in _sorted_paths(paths):
        for rec in _iter_file_records(path):
            sid = rec.get("sessionId") or rec.get("session_id")
            if since is not None or until is not None:
                ts = rec.get("timestamp")
                if not isinstance(ts, str):
                    continue
                if since is not None and ts < since:
                    continue
                if until is not None and ts > until:
                    continue
            if sid:
                ids.add(str(sid))
    return ids
