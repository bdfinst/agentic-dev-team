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

Stdlib only (Python 3.10+) — no third-party dependencies, so it runs from a
bare `python3` with nothing else installed.
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


def extract(paths: list[Path], registry: dict) -> dict:
    """Metrics-only digest for one project's transcript files. Same signal
    classes as session_extract.py's extract(), minus per-model cost (no
    pricing table shipped downstream) and per-skill token attribution (kept
    lean for a report meant to be read by a human, not joined back into the
    monorepo's trend streams)."""
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


def discover_projects(projects_root: Path) -> dict[str, list[Path]]:
    """Group every transcript under `projects_root` by the project cwd
    recorded inside it (matching session_extract.py's own resolution
    strategy — more robust than reconstructing a slug from the directory
    name, which has varied across Claude Code versions)."""
    by_project: dict[str, list[Path]] = defaultdict(list)
    if not projects_root.is_dir():
        return {}
    for jsonl in projects_root.glob("*/*.jsonl"):
        cwd = None
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
                        cwd = rec_cwd
                        break
        except OSError:
            continue
        label = _project_label(cwd) if cwd else jsonl.parent.name
        by_project[label].append(jsonl)
    return dict(by_project)


def resolve_single_project(projects_root: Path, target_cwd: str) -> tuple[str, list[Path]]:
    target_cwd = os.path.abspath(target_cwd)
    by_project = discover_projects(projects_root)
    label = _project_label(target_cwd)
    if label in by_project:
        return label, by_project[label]
    # fall back to an exact cwd match inside the transcripts, in case two
    # different projects share a basename
    matches: list[Path] = []
    if projects_root.is_dir():
        for jsonl in projects_root.glob("*/*.jsonl"):
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
                        if rec_cwd and os.path.abspath(rec_cwd) == target_cwd:
                            matches.append(jsonl)
                            break
            except OSError:
                continue
    return label, sorted(matches, key=lambda x: x.name)


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
        help="output file path (default: session-report-<host>-<timestamp>.json in the current directory)",
    )
    args = ap.parse_args(argv)

    projects_root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    plugin_root = Path(__file__).resolve().parent.parent
    registry = load_registry(plugin_root)
    plugin_version = _load_plugin_version(plugin_root)
    host = socket.gethostname()

    digests: dict[str, dict] = {}

    if args.all_projects:
        by_project = discover_projects(projects_root)
        if not by_project:
            print(f"no session transcripts found under {projects_root}")
            return 1
        for label, paths in sorted(by_project.items()):
            digests[label] = extract(paths, registry)
        mode = "all-projects"
    else:
        target = args.project or os.getcwd()
        label, paths = resolve_single_project(projects_root, target)
        if not paths:
            print(f"no session transcripts found for project matching {target!r} under {projects_root}")
            return 1
        digests[label] = extract(paths, registry)
        mode = "single-project"

    report = {
        "schema": "downstream-session-report/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": host,
        "plugin_version": plugin_version,
        "mode": mode,
        "projects": digests,
        "combined": combine(digests, registry),
    }

    out_path = Path(
        args.out
        or f"session-report-{host}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(digests)} project(s), {report['combined']['sessions']} session(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
