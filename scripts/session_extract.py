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
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

# --- verification / classification vocabularies (counted, never emitted) -----
_VERIFY_RE = re.compile(
    r"\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo "
    r"(test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b"
)
_CORRECTION_RE = re.compile(
    r"\b(no|actually|revert|undo|not what i (asked|wanted)|that's wrong|"
    r"that is wrong|wrong|stop|don't|do not)\b"
)
_PERMISSION_RE = re.compile(r"permission|denied|not allowed|blocked by", re.I)
_OLDSTRING_RE = re.compile(r"old_string|not found|no match|string to replace", re.I)
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def _text_of(content) -> str:
    """Flatten a message ``content`` (str or list of blocks) to plain text.
    Used only for keyword CLASSIFICATION; never emitted into the digest."""
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


def _load_pricing(path: Path | None) -> dict:
    if path and path.is_file():
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _rate(pricing: dict, model: str):
    models = pricing.get("models", {})
    if model in models:
        return models[model]
    alias = pricing.get("aliases", {}).get(model)
    if alias and alias in models:
        return models[alias]
    return None


def _cost(usage: dict, rate: dict, pricing: dict) -> float:
    if not rate:
        return 0.0
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    ir = rate.get("input", 0)
    return (inp / 1e6 * ir + out / 1e6 * rate.get("output", 0)
            + cw / 1e6 * ir * pricing.get("cache_write_multiplier", 1.25)
            + cr / 1e6 * ir * pricing.get("cache_read_multiplier", 0.1))


def _iter_records(paths: list[Path]):
    for p in sorted(paths, key=lambda x: x.name):
        try:
            lines = p.read_text().splitlines()
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


def extract(paths: list[Path], pricing: dict, registry: dict) -> dict:
    tokens_total = Counter()
    cost_total = 0.0
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_skill: dict[str, Counter] = defaultdict(Counter)
    by_subagent = Counter()        # main-thread vs sidechain message counts
    sessions: set[str] = set()

    # rework / accuracy
    failed_edits = 0
    edits_per_file = Counter()
    bash_commands = Counter()
    verify_runs = 0
    permission_denials = 0
    compaction_events = 0
    tool_errors = Counter()        # by tool name
    tool_calls = Counter()         # by tool name (for ratios)
    correction_turns = 0

    # utilization
    skills_invoked = Counter()
    agents_invoked = Counter()

    # map tool_use id -> tool name, to attribute tool_result errors back
    pending_tool: dict[str, str] = {}

    for rec in _iter_records(paths):
        sid = rec.get("sessionId") or rec.get("session_id")
        if sid:
            sessions.add(str(sid))
        rtype = rec.get("type")
        is_sidechain = bool(rec.get("isSidechain"))
        skill = rec.get("attributionSkill") or rec.get("attribution_skill")
        if skill:
            skills_invoked[skill] += 1

        # compaction markers
        if (rtype in ("compaction", "summary") or rec.get("isCompactSummary")
                or rec.get("compactMetadata")):
            compaction_events += 1

        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else \
            (rec.get("usage") if isinstance(rec.get("usage"), dict) else None)
        model = msg.get("model") or rec.get("model")

        if usage:
            by_subagent["sidechain" if is_sidechain else "main"] += 1
            fields = ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens")
            cost = _cost(usage, _rate(pricing, model or ""), pricing)
            cost_total += cost
            for f in fields:
                v = usage.get(f, 0) or 0
                tokens_total[f] += v
                if model:
                    by_model[model][f] += v
                if skill:
                    by_skill[skill][f] += v
            if model:
                by_model[model]["cost_micro"] += round(cost * 1e6)
            if skill:
                by_skill[skill]["cost_micro"] += round(cost * 1e6)

        # walk content blocks for tool_use / tool_result
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name", "?")
                    tool_calls[name] += 1
                    bid = block.get("id")
                    if bid:
                        pending_tool[bid] = name
                    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
                    if name in _EDIT_TOOLS and inp.get("file_path"):
                        edits_per_file[os.path.basename(str(inp["file_path"]))] += 1
                    if name == "Bash" and isinstance(inp.get("command"), str):
                        cmd = inp["command"].strip()
                        # near-identical retry detection: normalize whitespace
                        norm = re.sub(r"\s+", " ", cmd)
                        bash_commands[norm] += 1
                        if _VERIFY_RE.search(cmd):
                            verify_runs += 1
                elif btype == "tool_result":
                    bid = block.get("tool_use_id")
                    tool_name = pending_tool.get(bid, "?")
                    rcontent = _text_of(block.get("content"))
                    if block.get("is_error"):
                        tool_errors[tool_name] += 1
                        if tool_name in _EDIT_TOOLS and _OLDSTRING_RE.search(rcontent):
                            failed_edits += 1
                        if _PERMISSION_RE.search(rcontent):
                            permission_denials += 1

        # user-correction turns (real user messages only, not tool_results)
        if rtype == "user" and not rec.get("isMeta"):
            utext = _text_of(content)
            # skip pure tool_result envelopes (no free-text user prompt)
            if utext and not (isinstance(content, list)
                              and all(isinstance(b, dict)
                                      and b.get("type") == "tool_result"
                                      for b in content)):
                if _CORRECTION_RE.search(utext.lower()):
                    correction_turns += 1

    # repeated edits / retried bash (>1 occurrence)
    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    retried_bash = sum(n - 1 for n in bash_commands.values() if n > 1)

    # never-observed registry items
    reg_skills = set(registry.get("skills", []))
    reg_agents = set(registry.get("agents", []))
    never_skills = sorted(reg_skills - set(skills_invoked))
    never_agents = sorted(reg_agents - set(agents_invoked))

    cr = tokens_total["cache_read_input_tokens"]
    cc = tokens_total["cache_creation_input_tokens"]
    cache_hit_ratio = round(cr / (cr + cc), 4) if (cr + cc) else 0.0

    total_errors = sum(tool_errors.values())
    total_calls = sum(tool_calls.values())

    def _slim(d: dict) -> dict:
        return {k: dict(sorted(v.items())) for k, v in sorted(d.items())}

    return {
        "schema": "session-digest/v1",
        "sessions": len(sessions),
        "token": {
            "totals": dict(sorted(tokens_total.items())),
            "cost_usd": round(cost_total, 4),
            "cache_hit_ratio": cache_hit_ratio,
            "by_model": _slim(by_model),
            "by_skill": _slim(by_skill),
            "by_subagent": dict(sorted(by_subagent.items())),
        },
        "rework": {
            "failed_edits": failed_edits,
            "repeated_file_edits": dict(sorted(repeated_file_edits.items())),
            "retried_bash_commands": retried_bash,
            "repeated_verify_runs": verify_runs,
            "permission_denials": permission_denials,
            "compaction_events": compaction_events,
        },
        "accuracy": {
            "tool_errors_by_tool": dict(sorted(tool_errors.items())),
            "tool_calls": total_calls,
            "tool_error_rate": round(total_errors / total_calls, 4) if total_calls else 0.0,
            "user_correction_turns": correction_turns,
        },
        "utilization": {
            "skills_invoked": dict(sorted(skills_invoked.items())),
            "agents_invoked": dict(sorted(agents_invoked.items())),
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
    for jsonl in root.glob("*/*.jsonl"):
        try:
            with jsonl.open() as fh:
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
        except OSError:
            continue
    return sorted(matches, key=lambda x: x.name)


def load_registry(plugin_root: Path | None) -> dict:
    """Enumerate shipped skills/agents so we can report never-observed ones."""
    if plugin_root is None:
        # scripts/ -> repo root -> plugins/dev-team
        plugin_root = Path(__file__).resolve().parent.parent / "plugins" / "dev-team"
    skills_dir = plugin_root / "skills"
    agents_dir = plugin_root / "agents"
    skills = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
    agents = sorted(p.stem for p in agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    return {"skills": skills, "agents": agents}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", action="append",
                    help="explicit transcript JSONL file(s); repeatable")
    ap.add_argument("--project-dir", help="a directory of *.jsonl transcripts")
    ap.add_argument("--cwd", help="project cwd to match (default: $PWD)")
    ap.add_argument("--projects-root",
                    help="root of Claude Code project transcripts "
                         "(default: ~/.claude/projects)")
    ap.add_argument("--pricing", help="model-pricing.json for cost (optional)")
    ap.add_argument("--plugin-root", help="dev-team plugin root for the registry")
    ap.add_argument("-o", "--out", help="write digest here (default: stdout)")
    args = ap.parse_args(argv)

    paths = resolve_transcripts(args)
    pricing_path = Path(args.pricing) if args.pricing else (
        Path(__file__).resolve().parent.parent
        / "plugins/dev-team/knowledge/model-pricing.json")
    pricing = _load_pricing(pricing_path)
    registry = load_registry(Path(args.plugin_root) if args.plugin_root else None)

    digest = extract(paths, pricing, registry)
    digest["transcripts"] = len(paths)
    out = json.dumps(digest, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(out + "\n")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
