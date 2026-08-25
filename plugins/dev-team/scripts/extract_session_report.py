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
keys throughout.

Usage:
  extract_session_report.py                       current project only
  extract_session_report.py --all-projects         every project on this machine
  extract_session_report.py --project /path/to/dir a specific project's cwd
  extract_session_report.py --out my-report.json   choose the output path
  extract_session_report.py --since 2026-01-01 --until 2026-01-31
                                                    scope to a time range
  extract_session_report.py --plugin-version 1.4.0 scope to a plugin version
                                                    (best-effort, see --help)

Stdlib only (Python 3.10+) — no third-party dependencies, so it runs from a
bare `python3` with nothing else installed. Run with --help for the full
flag reference.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
from collections import Counter, defaultdict
from datetime import datetime, timezone
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


def _iter_records(paths: list[Path]):
    for p in sorted(paths, key=lambda x: x.name):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


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


def _accumulate_token_signals(usage, model, is_sidechain, tokens_total, by_model, by_subagent):
    by_subagent["sidechain" if is_sidechain else "main"] += 1
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


def _accumulate_skill_agent_signals(content, skills_invoked, agents_invoked):
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
                skills_invoked[_strip_ns(s)] += 1
        elif name in ("Agent", "Task"):
            a = inp.get("subagent_type")
            if isinstance(a, str) and a:
                agents_invoked[_strip_ns(a)] += 1


def _track_tool_call(block, pending_tool, tool_calls):
    name = block.get("name", "?")
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


def _track_edit(block, sid, edits_per_file, verify_edited_since):
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name in _EDIT_TOOLS and inp.get("file_path"):
        edits_per_file[os.path.basename(str(inp["file_path"]))] += 1
    if name in _EDIT_TOOLS:
        verify_edited_since[str(sid or "")] = True


def _track_bash(block, sid, bash_commands, bash_signal_counts, last_verify_norm, verify_edited_since):
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name != "Bash" or not isinstance(inp.get("command"), str):
        return
    cmd = inp["command"].strip()
    norm = re.sub(r"\s+", " ", cmd)
    bash_commands[norm] += 1
    if _VERIFY_RE.search(cmd):
        skey = str(sid or "")
        if last_verify_norm.get(skey) == norm and not verify_edited_since.get(skey, False):
            bash_signal_counts["repeated_verify_runs"] += 1
        last_verify_norm[skey] = norm
        verify_edited_since[skey] = False
    if _COMMIT_RE.search(cmd):
        bash_signal_counts["commit_attempts"] += 1
        if _BYPASS_RE.search(cmd):
            bash_signal_counts["commit_bypasses"] += 1


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
    by_subagent = Counter()
    sessions: set[str] = set()

    edits_per_file = Counter()
    bash_commands = Counter()
    last_verify_norm: dict[str, str] = {}
    verify_edited_since: dict[str, bool] = {}
    bash_signal_counts = Counter()
    error_counts = Counter()
    compaction_events = 0
    tool_errors = Counter()
    tool_calls = Counter()
    correction_turns = 0

    skills_invoked = Counter()
    agents_invoked = Counter()

    pending_tool: dict[str, str] = {}

    for rec in _iter_records(paths):
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

        if sid:
            sessions.add(str(sid))
        rtype = rec.get("type")
        is_sidechain = bool(rec.get("isSidechain"))

        if rtype in ("compaction", "summary") or rec.get("isCompactSummary") or rec.get("compactMetadata"):
            compaction_events += 1

        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        usage = (
            msg.get("usage")
            if isinstance(msg.get("usage"), dict)
            else (rec.get("usage") if isinstance(rec.get("usage"), dict) else None)
        )
        model = msg.get("model") or rec.get("model")
        if usage:
            _accumulate_token_signals(usage, model, is_sidechain, tokens_total, by_model, by_subagent)

        content = msg.get("content")
        _accumulate_skill_agent_signals(content, skills_invoked, agents_invoked)

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    _track_tool_call(block, pending_tool, tool_calls)
                    _track_edit(block, sid, edits_per_file, verify_edited_since)
                    _track_bash(
                        block, sid, bash_commands, bash_signal_counts,
                        last_verify_norm, verify_edited_since,
                    )
                elif btype == "tool_result":
                    _classify_tool_result(block, pending_tool, tool_errors, error_counts)

        if _detect_correction_turn(rec, content):
            correction_turns += 1

    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    retried_bash = sum(n - 1 for n in bash_commands.values() if n > 1)

    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    never_skills = sorted(reg_skills - set(skills_invoked))
    never_agents = sorted(reg_agents - set(agents_invoked))

    cr = tokens_total["cache_read_input_tokens"]
    cc = tokens_total["cache_creation_input_tokens"]
    cache_hit_ratio = round(cr / (cr + cc), 4) if (cr + cc) else 0.0

    total_errors = sum(tool_errors.values())
    total_calls = sum(tool_calls.values())

    return {
        "sessions": len(sessions),
        "transcripts": len(paths),
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cache_hit_ratio": cache_hit_ratio,
            "by_model": {m: dict(sorted(v.items())) for m, v in sorted(by_model.items())},
            "by_subagent": dict(sorted(by_subagent.items())),
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
    tokens_total = Counter()
    by_subagent = Counter()
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

    for d in digests.values():
        sessions += d["sessions"]
        transcripts += d["transcripts"]
        _merge_counters(tokens_total, d["token"]["totals"])
        _merge_counters(by_subagent, d["token"]["by_subagent"])
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

    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))

    return {
        "sessions": sessions,
        "transcripts": transcripts,
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cache_hit_ratio": round(cr / (cr + cc), 4) if (cr + cc) else 0.0,
            "by_subagent": dict(sorted(by_subagent.items())),
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
            "never_observed_skills": sorted(reg_skills - set(skills_invoked)),
            "never_observed_agents": sorted(reg_agents - set(agents_invoked)),
        },
    }


# --------------------------------------------------------------------------
# Project discovery.
# --------------------------------------------------------------------------


def _project_label(cwd: str) -> str:
    return os.path.basename(os.path.normpath(cwd)) or cwd


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
    by_project: dict[str, dict] = defaultdict(lambda: {"cwd": None, "paths": []})
    if not projects_root.is_dir():
        return {}
    for jsonl in projects_root.glob("*/*.jsonl"):
        cwd = _first_cwd(jsonl)
        label = _project_label(cwd) if cwd else jsonl.parent.name
        entry = by_project[label]
        if cwd and not entry["cwd"]:
            entry["cwd"] = os.path.abspath(cwd)
        entry["paths"].append(jsonl)
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
        for jsonl in projects_root.glob("*/*.jsonl"):
            cwd = _first_cwd(jsonl)
            if cwd and os.path.abspath(cwd) == target_cwd:
                matches.append(jsonl)
    return label, (target_cwd if matches else None), sorted(matches, key=lambda x: x.name)


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
    for rec in _iter_records([path]):
        if rec.get("plugin_version") != target_version:
            continue
        sid = rec.get("session_id")
        if sid:
            matches.add(str(sid))
    return matches


# --------------------------------------------------------------------------


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
        metavar="ISO8601",
        help="only include activity at/after this UTC timestamp or date, "
        "e.g. 2026-01-15 or 2026-01-15T00:00:00Z",
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

    since = args.since
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
                entry["paths"], registry, since, until, _allowed_sessions(entry["cwd"])
            )
        mode = "all-projects"
        scope = "all"
    else:
        target = args.project or os.getcwd()
        label, cwd, paths = resolve_single_project(projects_root, target)
        if not paths:
            print(f"no session transcripts found for project matching {target!r} under {projects_root}")
            return 1
        digests[label] = extract(paths, registry, since, until, _allowed_sessions(cwd))
        mode = "single-project"
        scope = label

    report = {
        "schema": "downstream-session-report/v1",
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
