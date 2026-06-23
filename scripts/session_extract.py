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
# Gate signal (#111): a `git commit`, and whether it bypassed the pre-commit
# review gate (--no-verify, or a bare -n in any position) — mirrors the rule in
# hooks/telemetry.sh so the two agree.
_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_BYPASS_RE = re.compile(r"--no-verify|(^|\s)-n(\s|$)")


def _strip_ns(name: str) -> str:
    """Drop known plugin namespace prefixes so invoked names match the registry
    (registry entries are bare dir/file stems). `dev-team:plan` -> `plan`;
    `agentic-dev-team:plan` -> `plan`; other names pass through."""
    for prefix in ("agentic-dev-team:", "dev-team:"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


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
    commit_attempts = 0            # gate (#111): git commit invocations
    commit_bypasses = 0            # gate (#111): commits that bypassed review
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
        # attributionSkill is a legacy/secondary tag — the harness does not emit
        # it on real transcripts (#182), so utilization is driven by the Skill /
        # Agent tool_use below. Kept here only as a fallback for records that do
        # carry it (and per-skill token attribution via by_skill).
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
                    # Utilization (#182): the harness never records attributionSkill,
                    # so skill/agent invocations are read from the tool_use that
                    # actually invokes them — the Skill tool and the Agent/Task tool.
                    if name == "Skill":
                        s = inp.get("skill") or inp.get("name")
                        if isinstance(s, str) and s:
                            skills_invoked[_strip_ns(s)] += 1
                    elif name in ("Agent", "Task"):
                        a = inp.get("subagent_type")
                        if isinstance(a, str) and a:
                            agents_invoked[_strip_ns(a)] += 1
                    if name in _EDIT_TOOLS and inp.get("file_path"):
                        edits_per_file[os.path.basename(str(inp["file_path"]))] += 1
                    if name == "Bash" and isinstance(inp.get("command"), str):
                        cmd = inp["command"].strip()
                        # near-identical retry detection: normalize whitespace
                        norm = re.sub(r"\s+", " ", cmd)
                        bash_commands[norm] += 1
                        if _VERIFY_RE.search(cmd):
                            verify_runs += 1
                        # gate signal (#111): commit + review-gate bypass
                        if _COMMIT_RE.search(cmd):
                            commit_attempts += 1
                            if _BYPASS_RE.search(cmd):
                                commit_bypasses += 1
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
        "gate": {
            "commit_attempts": commit_attempts,
            "commit_bypasses": commit_bypasses,
            "bypass_rate": round(commit_bypasses / commit_attempts, 4) if commit_attempts else 0.0,
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


def resolve_all_transcripts(args) -> list[Path]:
    """Every transcript across ALL projects under projects-root (Delta D, #178).

    Cross-project: unlike resolve_transcripts (which matches one project's cwd),
    this returns one file per session across every project on the machine, so the
    sync can aggregate all of them.
    """
    root = Path(args.projects_root or (Path.home() / ".claude" / "projects"))
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*.jsonl"), key=lambda x: x.name)


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
                project = os.path.basename(os.path.normpath(cwd))
        ts = rec.get("timestamp")
        if isinstance(ts, str) and ts > last_ts:
            last_ts = ts
    return project or "unknown", last_ts


def sync_record(digest: dict, host: str, project: str,
                session_id: str, ts: str) -> dict:
    """One per-session, metrics-only record for cross-machine aggregation (#178).

    Identity (host / project basename / session_id / ts) plus the slim metric
    blocks. Carries model ids and the main/subagent split (non-sensitive) but no
    file names, paths, prompts, or code — same privacy boundary as the digest."""
    base = slim_record(digest)
    tok = digest.get("token", {})
    util = digest.get("utilization", {})
    by_model = {m: dict(sorted(v.items()))
                for m, v in sorted(tok.get("by_model", {}).items())}
    return {
        "schema": "session-sync/v1",
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
        "by_thread": tok.get("by_subagent", {}),
        "rework": base["rework"],
        "accuracy": base["accuracy"],
        "gate": base["gate"],
        # Utilization carries the invoked NAME maps (registry ids, non-sensitive),
        # not slim counts, so a cross-host rollup can compute which skills/agents
        # were never invoked on ANY machine (#178 union read).
        "utilization": {
            "skills_invoked": dict(sorted(util.get("skills_invoked", {}).items())),
            "agents_invoked": dict(sorted(util.get("agents_invoked", {}).items())),
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


def cmd_sync(args, pricing: dict, registry: dict, host: str) -> int:
    """Incremental, cross-project sync (#178): emit one metrics-only record per
    session that is NEW or has grown since the machine's last sync, into the
    host digest file. The watermark dedups by session_id + byte size, so re-runs
    re-emit only changed sessions and skip everything else."""
    out = Path(args.sync_out)
    wm_path = Path(args.watermark) if args.watermark else (
        Path.home() / ".claude" / ".dev-team" / "telemetry-sync.json")
    wm = _load_watermark(wm_path)
    synced = wm["synced"]

    if args.transcript:
        paths = [Path(p) for p in args.transcript]
    elif args.project_dir:
        paths = sorted(Path(args.project_dir).glob("*.jsonl"), key=lambda x: x.name)
    else:
        paths = resolve_all_transcripts(args)

    emitted = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        for path in paths:
            session_id = path.stem
            try:
                size = path.stat().st_size
            except OSError:
                continue
            prev = synced.get(session_id)
            if isinstance(prev, int) and prev >= size:
                continue  # already synced and unchanged
            project, ts = _project_and_ts(path)
            digest = extract([path], pricing, registry)
            rec = sync_record(digest, host, project, session_id, ts)
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
            synced[session_id] = size
            emitted += 1

    wm_path.parent.mkdir(parents=True, exist_ok=True)
    wm_path.write_text(json.dumps(wm, indent=2, sort_keys=True) + "\n")
    print(f"synced {emitted} new/changed session(s) of {len(paths)} considered "
          f"-> {out}")
    return 0


def rollup(digests_root: Path, registry: dict) -> dict:
    """Union read across machines (#178): aggregate every host's per-session
    `session-sync/v1` records under `digests/<host>/session-digest.jsonl` into one
    cross-machine view. Metrics only — sums, ratios, and registry-name maps.

    A session_id seen on multiple host files (or re-emitted after growth) is
    deduped, keeping the LAST record for that id (newest size/sync)."""
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if rec.get("schema") != "session-sync/v1":
                continue
            sid = rec.get("session_id")
            if sid:
                by_id[str(sid)] = rec  # last write wins -> dedup on session_id

    records = list(by_id.values())
    hosts: set[str] = set()
    projects: set[str] = set()
    tok = Counter()
    cost = 0.0
    cr = cc = 0
    rew = Counter()
    tool_calls = 0
    err_weighted = 0.0
    corrections = 0
    skills_invoked = Counter()
    agents_invoked = Counter()
    by_host: dict[str, Counter] = defaultdict(Counter)
    by_project: dict[str, Counter] = defaultdict(Counter)

    for r in records:
        host = r.get("host", "unknown")
        project = r.get("project", "unknown")
        hosts.add(host)
        projects.add(project)
        t = r.get("tokens", {}) if isinstance(r.get("tokens"), dict) else {}
        for k in ("input_tokens", "output_tokens",
                  "cache_creation_input_tokens", "cache_read_input_tokens"):
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
        u = r.get("utilization", {}) if isinstance(r.get("utilization"), dict) else {}
        for name, k in (u.get("skills_invoked", {}) or {}).items():
            skills_invoked[name] += k
        for name, k in (u.get("agents_invoked", {}) or {}).items():
            agents_invoked[name] += k

    never_skills = sorted(set(registry.get("skills", [])) - set(skills_invoked))
    never_agents = sorted(set(registry.get("agents", [])) - set(agents_invoked))

    def _hostmap(d: dict) -> dict:
        return {k: dict(sorted(v.items())) for k, v in sorted(d.items())}

    return {
        "schema": "telemetry-rollup/v1",
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
            "tool_error_rate": round(err_weighted / tool_calls, 4) if tool_calls else 0.0,
            "user_correction_turns": corrections,
        },
        "utilization": {
            "skills_invoked": dict(sorted(skills_invoked.items())),
            "agents_invoked": dict(sorted(agents_invoked.items())),
            "never_observed_skills": never_skills,
            "never_observed_agents": never_agents,
        },
    }


def cmd_rollup(args, registry: dict) -> int:
    root = Path(args.rollup)
    if not root.is_dir():
        print(json.dumps({"schema": "telemetry-rollup/v1", "sessions": 0,
                          "hosts": [], "projects": []}, indent=2, sort_keys=True))
        return 0
    out = json.dumps(rollup(root, registry), indent=2, sort_keys=True)
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

_REWORK_KEYS = ("failed_edits", "repeated_file_edits", "retried_bash_commands",
                "repeated_verify_runs", "permission_denials", "compaction_events")


def _session_rework(rec: dict) -> int:
    rw = rec.get("rework", {}) if isinstance(rec.get("rework"), dict) else {}
    return sum(int(rw.get(k, 0) or 0) for k in _REWORK_KEYS)


def correlate_gate_rework(digests_root: Path) -> dict:
    """Across all sessions that committed, compare mean rework between those that
    bypassed the review gate and those that didn't (#111)."""
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if rec.get("schema") != "session-sync/v1":
                continue
            sid = rec.get("session_id")
            if sid:
                by_id[str(sid)] = rec

    bypass_rework: list[int] = []
    clean_rework: list[int] = []
    for rec in by_id.values():
        gate = rec.get("gate", {}) if isinstance(rec.get("gate"), dict) else {}
        if int(gate.get("commit_attempts", 0) or 0) <= 0:
            continue  # only sessions that actually committed are comparable
        (bypass_rework if int(gate.get("commit_bypasses", 0) or 0) > 0
         else clean_rework).append(_session_rework(rec))

    def _mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    mb, mc = _mean(bypass_rework), _mean(clean_rework)
    if not bypass_rework or not clean_rework:
        interp = "insufficient data — need committing sessions in BOTH groups"
    elif mb > mc:
        interp = ("bypassing the review gate correlates with MORE rework "
                  f"({mb} vs {mc}) — evidence the gate guards real risk")
    elif mb < mc:
        interp = ("bypassing correlates with LESS rework "
                  f"({mb} vs {mc}) — the gate may be ceremony for these cases")
    else:
        interp = "no difference in rework between bypass and non-bypass sessions"

    return {
        "schema": "gate-correlation/v1",
        "committing_sessions": len(bypass_rework) + len(clean_rework),
        "bypass_sessions": len(bypass_rework),
        "clean_sessions": len(clean_rework),
        "mean_rework_when_bypassed": mb,
        "mean_rework_when_gated": mc,
        "interpretation": interp,
    }


def cmd_correlate(args) -> int:
    root = Path(args.correlate)
    result = (correlate_gate_rework(root) if root.is_dir()
              else {"schema": "gate-correlation/v1", "committing_sessions": 0,
                    "interpretation": "no digests directory"})
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
    most recent session against the cross-machine rolling baseline. This reads
    the same `digests/<host>/session-digest.jsonl` union, dedups on session_id
    (last write wins), orders oldest->newest by `ts`, and emits cost-meter
    records: `{"ts": ..., "total": {"cost_usd": ...}}` (extra `ts` is ignored by
    `regression` and used by `pace`)."""
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if rec.get("schema") != "session-sync/v1":
                continue
            sid = rec.get("session_id")
            if sid:
                by_id[str(sid)] = rec  # last write wins -> dedup on session_id
    recs = sorted(by_id.values(),
                  key=lambda r: (r.get("ts") or "", str(r.get("session_id"))))
    return [{"ts": r.get("ts"),
             "total": {"cost_usd": r.get("cost_usd", 0.0) or 0.0}}
            for r in recs]


def cmd_cost_log(args) -> int:
    root = Path(args.cost_log)
    lines = ("\n".join(json.dumps(rec, sort_keys=True) for rec in cost_log(root))
             if root.is_dir() else "")
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


def _lever_for(rate: float, matchable: bool,
               rare_rate: float, frequent_rate: float) -> tuple[str, str]:
    if rate < rare_rate:
        return "hint", "rare — surface as a hint only"
    if matchable and rate >= frequent_rate:
        return "hook", "frequent and deterministically matchable — promote to a hook (validate via /agent-eval)"
    if matchable:
        return "instruction-rule", "recurring and matchable but below the hook threshold — an instruction-file rule for now (/feedback-learning)"
    return "instruction-rule", "recurring but judgment-shaped (no reliable matcher) — an instruction-file rule (/feedback-learning)"


def escalate(roll: dict, rare_rate: float = 0.25,
             frequent_rate: float = 1.0) -> dict:
    """Turn rollup recurrence into ranked lever recommendations (#179)."""
    sessions = max(int(roll.get("sessions", 0)), 0)
    recs = []
    for section, key, matchable, label in _FRICTION_SIGNALS:
        count = roll.get(section, {}).get(key, 0) or 0
        if not count:
            continue
        rate = round(count / sessions, 4) if sessions else 0.0
        lever, rationale = _lever_for(rate, matchable, rare_rate, frequent_rate)
        recs.append({
            "signal": key,
            "label": label,
            "count": count,
            "per_session_rate": rate,
            "matchable": matchable,
            "lever": lever,
            "rationale": rationale,
        })
    # rank by per-session rate (worst first), then count
    recs.sort(key=lambda r: (-r["per_session_rate"], -r["count"]))
    return {
        "schema": "telemetry-escalation/v1",
        "sessions": sessions,
        "thresholds": {"rare_rate": rare_rate, "frequent_rate": frequent_rate},
        "recommendations": recs,
    }


def cmd_escalate(args, registry: dict) -> int:
    root = Path(args.escalate)
    roll = rollup(root, registry) if root.is_dir() else {"sessions": 0}
    out = json.dumps(
        escalate(roll, rare_rate=args.rare_rate, frequent_rate=args.frequent_rate),
        indent=2, sort_keys=True)
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
    ap.add_argument("--append", metavar="LOG",
                    help="append one metrics-only summary record to a trend "
                         "stream (append-only JSONL), e.g. metrics/session-digest.jsonl")
    ap.add_argument("--all-projects", action="store_true",
                    help="aggregate transcripts across ALL projects, not just the "
                         "current cwd's project (Delta D, #178)")
    ap.add_argument("--sync-out", metavar="FILE",
                    help="cross-project incremental SYNC mode (#178): append one "
                         "metrics-only record per new/changed session to FILE "
                         "(the host digest), tracked by --watermark")
    ap.add_argument("--watermark", metavar="FILE",
                    help="watermark JSON for incremental sync "
                         "(default: ~/.claude/.dev-team/telemetry-sync.json)")
    ap.add_argument("--host", help="host label for sync records (default: hostname)")
    ap.add_argument("--rollup", metavar="DIR",
                    help="union read (#178): aggregate all hosts' "
                         "DIR/<host>/session-digest.jsonl into one cross-machine view")
    ap.add_argument("--cost-log", metavar="DIR",
                    help="cost-meter baseline (#171): from DIR/<host>/session-digest.jsonl "
                         "emit a time-ordered per-session cost series "
                         "({\"total\":{\"cost_usd\":..}}) for `cost_meter.py regression`")
    ap.add_argument("--escalate", metavar="DIR",
                    help="Delta C (#179): rank friction signals from DIR's rollup "
                         "and recommend a lever (hint / instruction-rule / hook)")
    ap.add_argument("--correlate", metavar="DIR",
                    help="process eval (#111): from DIR's digests, compare rework "
                         "between review-gate-bypass and non-bypass sessions")
    ap.add_argument("--rare-rate", type=float, default=0.25,
                    help="per-session rate below which a friction is a hint (default 0.25)")
    ap.add_argument("--frequent-rate", type=float, default=1.0,
                    help="per-session rate at/above which a matchable friction "
                         "becomes a hook (default 1.0)")
    args = ap.parse_args(argv)

    pricing_path = Path(args.pricing) if args.pricing else (
        Path(__file__).resolve().parent.parent
        / "plugins/dev-team/knowledge/model-pricing.json")
    pricing = _load_pricing(pricing_path)
    registry = load_registry(Path(args.plugin_root) if args.plugin_root else None)

    # Cross-machine union read (Delta D, #178).
    if args.rollup:
        return cmd_rollup(args, registry)

    # Cross-machine cost baseline for the regression gate (#171).
    if args.cost_log:
        return cmd_cost_log(args)

    # Frequency -> lever escalation (Delta C, #179).
    if args.escalate:
        return cmd_escalate(args, registry)

    # Gate-bypass vs rework correlation (process eval, #111).
    if args.correlate:
        return cmd_correlate(args)

    # Cross-project incremental sync mode (Delta D, #178).
    if args.sync_out:
        import socket
        host = args.host or socket.gethostname()
        return cmd_sync(args, pricing, registry, host)

    paths = (resolve_all_transcripts(args) if args.all_projects
             else resolve_transcripts(args))

    digest = extract(paths, pricing, registry)
    digest["transcripts"] = len(paths)
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
    from datetime import datetime, timezone
    tok = digest.get("token", {})
    rew = digest.get("rework", {})
    acc = digest.get("accuracy", {})
    gate = digest.get("gate", {})
    util = digest.get("utilization", {})
    totals = tok.get("totals", {})
    return {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema": "session-digest/v1",
        "sessions": digest.get("sessions", 0),
        "transcripts": digest.get("transcripts", 0),
        "tokens": {k: totals.get(k, 0) for k in (
            "input_tokens", "output_tokens",
            "cache_creation_input_tokens", "cache_read_input_tokens")},
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
    with log.open("a") as fh:
        fh.write(json.dumps(slim_record(digest), sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
