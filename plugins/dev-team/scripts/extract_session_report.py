#!/usr/bin/env python3
"""Downstream session-report extractor.

Standalone, shippable counterpart to the monorepo-only
``scripts/session_extract.py``: any user with the dev-team plugin installed
can run this to produce ONE metrics-only JSON file summarizing their Claude
Code sessions, for a single project or every project on the machine, ready
to hand to the plugin maintainer (e.g. over MS Teams) for harness-effectiveness
analysis.

PRIVACY (non-negotiable, mirrors ``knowledge/telemetry-schema.md``): the
report holds METRICS ONLY — counts, ratios, enum values, and file/skill/
agent NAMES (basenames, never full paths). It never contains prompt text,
code, file contents, or full command strings. Read every session transcript
under ``~/.claude/projects/`` (or ``--projects-root``) that belongs to the
selected project(s); nothing is transmitted anywhere by this script itself —
it only writes the one local output file named by ``--out``. Sending that
file to anyone is a deliberate, separate action the user takes themselves.

DETERMINISM: given the same transcript inputs, every field except
``generated_at`` is byte-identical across runs — no absolute paths, sorted
keys throughout. The one exception is ``--since``, which is resolved
relative to the run's own current time (see below), so its resolved bound
— and therefore the report — legitimately differs between runs.

Usage:
  extract_session_report.py                       current project only
  extract_session_report.py --all-projects         every project on this machine
  extract_session_report.py --project /path/to/dir a specific project's cwd
  extract_session_report.py --out my-report.json   choose the output path
  extract_session_report.py --since 14             scope to the last 14 days
  extract_session_report.py --until 2026-01-31      scope to activity through a date
  extract_session_report.py --plugin-version 1.4.0 scope to a plugin version
                                                    (best-effort, see --help)

Stdlib only (Python 3.10+) — no third-party dependencies, so it runs from a
bare `python3` with nothing else installed. Run with --help for the full
flag reference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- classification vocabularies (counted, never emitted) -------------------
_VERIFY_RE = re.compile(
    r"\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo "
    r"(test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b"
)
_CORRECTION_RE = re.compile(
    r"\b(no|actually|revert|undo|not what i (asked|wanted)|that's wrong|"
    r"that is wrong|wrong|stop|don't|do not)\b"
)
_PERMISSION_RE = re.compile(r"permission|denied|not allowed|blocked by", re.IGNORECASE)
_OLDSTRING_RE = re.compile(r"old_string|not found|no match|string to replace", re.IGNORECASE)
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_BYPASS_RE = re.compile(r"--no-verify|(^|\s)-n(\s|$)")
_VERSION_RE = re.compile(r"^[0-9A-Za-z._+-]{1,32}$")
# Agent transcripts are `agent-<id>.jsonl` (see _is_transcript_path).
_AGENT_TRANSCRIPT_RE = re.compile(r"^agent-[0-9A-Za-z_-]{1,64}\.jsonl$")
# Every string that becomes a REPORT KEY passes _safe_name. The privacy
# guarantee in the module docstring ("names, never full paths"; no prompt text)
# holds only if these really are names, and they arrive from transcript files
# this script does not author — a cloned repo's own `.claude/agents/*.md`
# chooses `attributionAgent`, for instance. Enforce it once at the boundary
# rather than trusting each input site.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_UNSAFE_NAME = "other"
# `attributionAgent` values that name a harness ROLE rather than an agent.
# Every real Workflow-dispatched transcript carries "workflow-subagent"; left
# unfiltered these land in agents_invoked as phantom agents while the agent
# that actually ran stays in never_observed_agents — the #1990 symptom itself.
_HARNESS_ATTRIBUTIONS = frozenset({"workflow-subagent", "claude"})
# Established plugin vocabulary for an agent-keyed map's unresolved bucket
# (knowledge/telemetry-schema.md -> cost-metering `by_agent_type`).
_MAIN_LABEL = "main"
_UNATTRIBUTED_LABEL = "unattributed"


def _basename(path_str: str) -> str:
    """Last component of a path recorded on ANY platform.

    `os.path.basename` splits on `/` only, so a Windows-form `file_path`
    (`C:\\Users\\alice\\proj\\secrets.env`) comes back whole — an absolute
    path, username included, in a field the docstring promises is a basename.
    Reachable whenever Windows-written transcripts are read under WSL, a
    devcontainer, or a bind-mounted `~/.claude`."""
    return re.split(r"[\\/]", path_str)[-1] or path_str


def _safe_name(value: str) -> str:
    """Reduce an input-derived string to something safe to emit as a key."""
    return value if _SAFE_NAME_RE.match(value) else _UNSAFE_NAME


def _strip_ns(name: str) -> str:
    for prefix in ("agentic-dev-team:", "dev-team:"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _text_of(content) -> str:
    """Flatten a message `content` (str or list of blocks) to plain text.
    Used only for keyword CLASSIFICATION; never emitted into the report."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return " ".join(parts)
    return ""


def _iter_file_records(path: Path):
    """Yield every decodable JSON record in one transcript file, in order.

    Streams line by line rather than `read_text().splitlines()`: transcripts
    run to tens of MB, the recursive scan now visits thousands of them, and
    slurping cost ~3x the file's size in peak RSS before yielding anything.
    `_first_cwd` below already used this shape."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def _sorted_paths(paths: list[Path]) -> list[Path]:
    """Total order over transcript paths. Sorting on `Path.name` alone stopped
    being a total order once subagent transcripts (a second directory level)
    joined the scan, which would break the determinism guarantee in the module
    docstring; sort on the full path string instead."""
    return sorted(paths, key=lambda p: str(p))


def _relative_parts(projects_root: Path, path: Path) -> tuple[str, ...]:
    """The path's components BELOW `projects_root`.

    Every layout question here is about the tree under the root, so never ask
    it of the absolute path: `projects_root` defaults to `~/.claude/projects`
    and carries the user's home directory, so a matching segment anywhere in
    that prefix would answer for the whole tree."""
    try:
        return path.relative_to(projects_root).parts
    except ValueError:
        return path.parts


def _is_subagent_transcript(projects_root: Path, path: Path) -> bool:
    """A dispatched agent's own run, as opposed to a main-thread session.

    Depth varies by dispatch route — a plain Agent dispatch writes
    `<project>/<sessionId>/subagents/agent-<id>.jsonl`, while a Workflow's
    agents nest one level further under
    `<project>/<sessionId>/subagents/workflows/<runId>/agent-<id>.jsonl`.
    Match on the `subagents` path segment rather than on a fixed depth, so a
    future layout with another level does not silently go uncounted the way
    the workflow layout did."""
    return "subagents" in _relative_parts(projects_root, path)


def _is_transcript_path(root: Path, path: Path) -> bool:
    """Whether a `.jsonl` under `root` is a transcript this extractor reads.

    Decided by DEPTH, not by filename shape. A `.jsonl` sitting directly in a
    project directory is a main-thread session whatever it is called — the
    harness uses `<sessionId>.jsonl`, but nothing guarantees that and a
    name-shape filter silently drops any session that differs, which is a
    worse failure than the one it prevents.

    Below `subagents/` the rule tightens, because that is the only place the
    harness writes NON-transcript bookkeeping next to transcripts:
    `subagents/workflows/<runId>/journal.jsonl` holds `{"type", "key",
    "agentId"}` records with no `cwd`. Counting it as an agent run inflated the
    run tally and, having no `cwd`, sent project labelling down a fallback that
    leaked a path-derived slug (#1991). Agent transcripts are `agent-<id>.jsonl`.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if len(parts) < 2:
        return False
    if "subagents" in parts:
        return bool(_AGENT_TRANSCRIPT_RE.match(path.name))
    return len(parts) == 2


def _load_plugin_version(plugin_root: Path) -> str:
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
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


def load_registry(plugin_root: Path) -> dict:
    """Enumerate shipped skills/agents so the report can name never-observed
    ones. Best-effort: an unreadable/missing plugin tree just yields an empty
    registry rather than failing the whole extraction."""
    skills_dir = plugin_root / "skills"
    agents_dir = plugin_root / "agents"
    skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    agents = (
        sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    )
    return {"skills": skills, "agents": agents}


# --- per-record signal accumulation (adapted from session_extract.py) -------


def _accumulate_token_signals(usage, model, tokens_total, by_model):
    for f in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        v = usage.get(f, 0) or 0
        tokens_total[f] += v
        if model:
            by_model[model][f] += v


def _accumulate_skill_agent_signals(content, skills_invoked, agent_dispatches):
    """Count `Skill` invocations and `Agent`/`Task` DISPATCHES from tool_use
    blocks. A dispatch is not the same thing as a run: dispatches made from
    inside a subagent are only visible in that subagent's own transcript, and
    a dispatch whose subagent transcript is absent never ran to completion.
    Run counts come from `attributionAgent` instead — see `extract()`."""
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
                skills_invoked[_safe_name(_strip_ns(s))] += 1
        elif name in ("Agent", "Task"):
            a = inp.get("subagent_type")
            if isinstance(a, str) and a:
                agent_dispatches[_safe_name(_strip_ns(a))] += 1


def _track_tool_call(block, pending_tool, tool_calls):
    name = _safe_name(str(block.get("name", "?")))
    tool_calls[name] += 1
    bid = block.get("id")
    if bid:
        pending_tool[bid] = name


def _classify_tool_result(block, pending_tool, tool_errors, error_counts):
    if not block.get("is_error"):
        return
    bid = block.get("tool_use_id")
    tool_name = pending_tool.get(bid, "?")
    tool_errors[tool_name] += 1
    rcontent = _text_of(block.get("content"))
    if tool_name in _EDIT_TOOLS and _OLDSTRING_RE.search(rcontent):
        error_counts["failed_edits"] += 1
    if _PERMISSION_RE.search(rcontent):
        error_counts["permission_denials"] += 1


def _track_edit(block, edits_per_file, thread):
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name in _EDIT_TOOLS and inp.get("file_path"):
        edits_per_file[_safe_name(_basename(str(inp["file_path"])))] += 1
    if name in _EDIT_TOOLS:
        thread["edited_since_verify"] = True


def _track_bash(block, bash_signal_counts, thread):
    """Bash signals are scoped to ONE thread of execution (`thread`, a
    per-transcript dict). Retries and repeated verify runs are only meaningful
    within a thread: a review panel's sibling agents share their parent's
    sessionId, so a session-keyed tally would score fifteen agents each running
    `git diff --cached` once as fourteen retries."""
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name != "Bash" or not isinstance(inp.get("command"), str):
        return
    cmd = inp["command"].strip()
    norm = re.sub(r"\s+", " ", cmd)
    thread["bash_commands"][norm] += 1
    if _VERIFY_RE.search(cmd):
        if thread["last_verify_norm"] == norm and not thread["edited_since_verify"]:
            bash_signal_counts["repeated_verify_runs"] += 1
        thread["last_verify_norm"] = norm
        thread["edited_since_verify"] = False
    if _COMMIT_RE.search(cmd):
        bash_signal_counts["commit_attempts"] += 1
        if _BYPASS_RE.search(cmd):
            bash_signal_counts["commit_bypasses"] += 1


def _new_thread() -> dict:
    return {"bash_commands": Counter(), "last_verify_norm": None, "edited_since_verify": False}


def _detect_correction_turn(rec: dict, content) -> bool:
    if rec.get("type") != "user" or rec.get("isMeta"):
        return False
    utext = _text_of(content)
    if not utext:
        return False
    if isinstance(content, list) and all(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    return bool(_CORRECTION_RE.search(utext.lower()))


def extract(
    paths: list[Path],
    registry: dict,
    projects_root: Path,
    since: str | None = None,
    until: str | None = None,
    allowed_sessions: set[str] | None = None,
) -> dict:
    """Metrics-only digest for one project's transcript files. Same signal
    classes as session_extract.py's extract(), minus per-model cost (no
    pricing table shipped downstream) and per-skill token attribution (kept
    lean for a report meant to be read by a human, not joined back into the
    monorepo's trend streams).

    `since`/`until` (ISO-8601 strings, compared lexicographically against
    each record's own UTC `timestamp`) scope by time; a record with no
    timestamp is excluded whenever either bound is set, rather than assumed
    in-range. `allowed_sessions`, when not None, restricts to records whose
    session_id is in the set (the --plugin-version filter); a record with
    no session_id is excluded, same fail-closed convention."""
    tokens_total = Counter()
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_agent_type = Counter()
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
    # Whether the tree contains the subagent LAYOUT at all — distinct from how
    # many subagent transcripts fell in the reported window. Only the former
    # answers "did an older harness write this tree?".
    subagent_layout_present = False

    # One transcript file is one thread of execution: a main-thread session, or
    # a single dispatched agent's run. Per-thread state (pending tool_use ids,
    # bash history) is scoped here rather than to sessionId, which subagents
    # share with their parent.
    for path in _sorted_paths(paths):
        is_subagent = _is_subagent_transcript(projects_root, path)
        if is_subagent:
            subagent_layout_present = True
        agent_name: str | None = None
        thread = _new_thread()
        pending_tool: dict[str, str] = {}
        thread_msgs = 0
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
                    # A harness ROLE ("workflow-subagent") is not an agent name.
                    # Emitting it would invent an agent while leaving the one
                    # that really ran in never_observed_agents.
                    if stripped not in _HARNESS_ATTRIBUTIONS:
                        agent_name = _safe_name(stripped)
            rtype = rec.get("type")

            if rtype in ("compaction", "summary") or rec.get("isCompactSummary") or rec.get("compactMetadata"):
                compaction_events += 1

            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            usage = (
                msg.get("usage")
                if isinstance(msg.get("usage"), dict)
                else (rec.get("usage") if isinstance(rec.get("usage"), dict) else None)
            )
            model = msg.get("model") or rec.get("model")
            model = _safe_name(model) if isinstance(model, str) and model else None
            if usage:
                thread_msgs += 1
                _accumulate_token_signals(usage, model, tokens_total, by_model)

            content = msg.get("content")
            _accumulate_skill_agent_signals(content, skills_invoked, agent_dispatches)

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

            if _detect_correction_turn(rec, content):
                correction_turns += 1

        # A file's agent name is only known once a record carrying
        # `attributionAgent` has been seen, so thread-level attribution is
        # resolved here rather than per record.
        label = agent_name or (_UNATTRIBUTED_LABEL if is_subagent else _MAIN_LABEL)
        if thread_msgs:  # `+= 0` would materialize a zero-valued key
            by_agent_type[label] += thread_msgs
        # A transcript whose every record fell outside --since/--until did not
        # happen in the reported window, so it is neither a run nor a counted
        # transcript there. Counting files on a different basis from every
        # other figure would let one report state `subagent_transcripts: 400`
        # beside an `agents_invoked` summing to 12, under one `filters` block.
        if records_in_window and is_subagent:
            subagent_transcripts += 1
            agent_runs[label] += 1
        elif records_in_window:
            main_transcripts += 1
        retried_bash += sum(n - 1 for n in thread["bash_commands"].values() if n > 1)

    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}

    # Run counts are ground truth where subagent transcripts exist (one file per
    # run, named by `attributionAgent`). A tree written by an older harness has
    # none, so fall back to dispatch counts rather than reporting zero.
    agents_invoked = agent_runs if subagent_layout_present else agent_dispatches

    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    never_skills = sorted(reg_skills - set(skills_invoked))
    # Observed by EITHER signal counts as observed — an agent that ran but whose
    # dispatch was made from inside another agent, and vice versa.
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
            "by_model": {m: dict(sorted(v.items())) for m, v in sorted(by_model.items())},
            "by_agent_type": dict(sorted(by_agent_type.items())),
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
    by_agent_type = Counter()
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
        _merge_counters(by_agent_type, d["token"]["by_agent_type"])
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
            "by_agent_type": dict(sorted(by_agent_type.items())),
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


# --------------------------------------------------------------------------
# Project discovery.
# --------------------------------------------------------------------------


def _all_transcripts(projects_root: Path) -> list[Path]:
    """Every transcript under `projects_root`, main-thread and subagent alike.

    Several layouts coexist: main-thread sessions at
    `<project>/<sessionId>.jsonl`, a dispatched agent's own run at
    `<project>/<sessionId>/subagents/agent-<id>.jsonl`, and a Workflow's agents
    one level deeper still. Globbing only the first made every subagent
    invisible to the report (issue #1990) — and silently, because subagent
    records ARE marked `isSidechain: true`, they simply live in files nothing
    opened. Recurse rather than enumerate known depths, so the next layout does
    not reintroduce the same silence."""
    return _sorted_paths(
        [
            p
            for p in projects_root.glob("*/**/*.jsonl")
            if p.is_file() and not p.is_symlink() and _is_transcript_path(projects_root, p)
        ]
    )


def _project_dir_name(projects_root: Path, jsonl: Path) -> str:
    """The project directory a transcript belongs to, at any nesting depth."""
    return _relative_parts(projects_root, jsonl)[0]


def _opaque_label(dir_name: str) -> str:
    """Fallback label for a project directory no transcript gave a `cwd`.

    Never the directory name itself: a Claude Code project slug is the
    project's absolute path with separators rewritten, so emitting it would
    disclose the user's home directory and username in a file meant to be
    handed to someone else. A digest keeps such projects distinguishable
    across runs without naming them."""
    return f"unknown-project-{hashlib.sha256(dir_name.encode('utf-8')).hexdigest()[:8]}"


def _project_label(cwd: str) -> str:
    return _safe_name(os.path.basename(os.path.normpath(cwd)) or cwd)


def _first_cwd(jsonl: Path) -> str | None:
    try:
        with jsonl.open(encoding="utf-8") as fh:
            for _ in range(20):  # cwd appears on the earliest records
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
    recorded inside it (matching session_extract.py's own resolution
    strategy — more robust than reconstructing a slug from the directory
    name, which has varied across Claude Code versions). Each value is
    {"cwd": the resolved absolute cwd (or None), "paths": [Path, ...]} —
    the cwd is kept so a plugin-version filter can locate that project's
    local .claude/metrics/boundary-events.jsonl."""
    if not projects_root.is_dir():
        return {}
    # Group by the project DIRECTORY first, then resolve one cwd per group.
    # Labelling each file independently let a single file with no `cwd` (a
    # subagent transcript, or the workflow journal the discovery filter now
    # excludes) split off under a raw slug — and that slug is a losslessly
    # encoded absolute path carrying the user's home directory, in a report
    # the docstring promises holds "basenames, never full paths".
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
    # fall back to an exact cwd match inside the transcripts, in case two
    # different projects share a basename
    matches: list[Path] = []
    if projects_root.is_dir():
        for jsonl in _all_transcripts(projects_root):
            cwd = _first_cwd(jsonl)
            if cwd and os.path.abspath(cwd) == target_cwd:
                matches.append(jsonl)
    return label, (target_cwd if matches else None), _sorted_paths(matches)


def sessions_matching_plugin_version(cwd: str | None, target_version: str) -> set[str]:
    """Best-effort session_id set for a --plugin-version filter (transcripts
    themselves carry no version tag to correlate against). Cross-references
    the project's own local, always-on `.claude/metrics/boundary-events.jsonl`
    (see knowledge/telemetry-schema.md), which DOES stamp `plugin_version`
    per event alongside an optional `session_id`. Fails closed: a session
    with no boundary-events row (e.g. no review-agent dispatch happened) can't
    be attributed to any version and is excluded, same as a missing/unreadable
    file or a project with no known cwd — never silently included."""
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


# --------------------------------------------------------------------------


def _non_negative_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if n < 0:
        raise argparse.ArgumentTypeError(f"{value!r} must not be negative")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--project",
        metavar="PATH",
        help="extract only the project whose cwd is PATH (default: current directory)",
    )
    ap.add_argument(
        "--all-projects",
        action="store_true",
        help="extract every project found under --projects-root",
    )
    ap.add_argument(
        "--projects-root",
        help="root of Claude Code project transcripts (default: ~/.claude/projects)",
    )
    ap.add_argument(
        "-o", "--out",
        help="output file path (default: session-report-<scope>-<timestamp>.json in the "
        "current directory, where <scope> is the project name or 'all')",
    )
    ap.add_argument(
        "--since",
        metavar="DAYS",
        type=_non_negative_int,
        help="only include activity from the last DAYS days (relative to "
        "now, e.g. --since 14 for the last two weeks)",
    )
    ap.add_argument(
        "--until",
        metavar="ISO8601",
        help="only include activity at/before this UTC timestamp or date "
        "(a bare date includes the whole day)",
    )
    ap.add_argument(
        "--plugin-version",
        metavar="VERSION",
        help="best-effort: only include sessions this project's local "
        ".claude/metrics/boundary-events.jsonl recorded under VERSION. "
        "Sessions with no boundary-events row (no review-agent dispatch "
        "happened) can't be attributed to any version and are excluded — "
        "this can undercount sessions that never triggered one",
    )
    args = ap.parse_args(argv)

    since = None
    if args.since is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=args.since)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    until = args.until
    if until and re.fullmatch(r"\d{4}-\d{2}-\d{2}", until):
        until = f"{until}T23:59:59Z"  # bare date as --until means "through end of day"

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
            digests[label] = extract(
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
        digests[label] = extract(
            paths, registry, projects_root, since, until, _allowed_sessions(cwd)
        )
        mode = "single-project"
        scope = label

    report = {
        "schema": "downstream-session-report/v2",
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


if __name__ == "__main__":
    raise SystemExit(main())
