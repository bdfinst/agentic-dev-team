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
from datetime import UTC
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
_PERMISSION_RE = re.compile(r"permission|denied|not allowed|blocked by", re.IGNORECASE)
_OLDSTRING_RE = re.compile(r"old_string|not found|no match|string to replace", re.IGNORECASE)
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
# Gate signal (#111): a `git commit`, and whether it bypassed the pre-commit
# review gate (--no-verify, or a bare -n in any position) — mirrors the rule in
# hooks/telemetry.sh so the two agree.
_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_BYPASS_RE = re.compile(r"--no-verify|(^|\s)-n(\s|$)")


# Agent transcripts are `agent-<id>.jsonl` (see _is_transcript_path).
_AGENT_TRANSCRIPT_RE = re.compile(r"^agent-[0-9A-Za-z_-]{1,64}\.jsonl$")
# Every string that becomes a digest KEY passes _safe_name: these arrive from
# transcript files this script does not author, and the digest's own privacy
# contract is names-only.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_UNSAFE_NAME = "other"
# `attributionAgent` values naming a harness ROLE rather than an agent. Every
# real Workflow-dispatched transcript carries "workflow-subagent"; unfiltered
# they become phantom agents while the agent that actually ran stays in
# never_observed_agents — the #1990 symptom itself.
_HARNESS_ATTRIBUTIONS = frozenset({"workflow-subagent", "claude"})
_DIGEST_SCHEMA = "session-digest/v2"
_SYNC_SCHEMA = "session-sync/v2"
#: Sync-record schemas a reader accepts. Declared once and imported by
#: scripts/eval_rawlog.py — the v1->v2 bump broke that consumer silently
#: because it exact-matched the old string on its own (#1994 review).
SYNC_SCHEMAS = ("session-sync/v1", "session-sync/v2")
_MAIN_LABEL = "main"
_UNATTRIBUTED_LABEL = "unattributed"


def _basename(path_str: str) -> str:
    """Last component of a path recorded on ANY platform.

    `os.path.basename` splits on `/` only, so a Windows-form path comes back
    whole — an absolute path, username included, in a field this module's
    docstring promises is a basename. Reachable whenever Windows-written
    transcripts are read under WSL, a devcontainer, or a bind-mounted
    `~/.claude`. The shipped twin already had this; the #1994 port left it
    behind, which is the same defect class crossing the fork twice.
    """
    return re.split(r"[\\/]", path_str)[-1] or path_str


def _safe_name(value: str) -> str:
    """Reduce an input-derived string to something safe to emit as a key."""
    # fullmatch, not match: `$` also matches immediately BEFORE a single
    # trailing newline, so `.match()` admitted "name\n" through the allowlist
    # and split the key space (#1994 review).
    return value if _SAFE_NAME_RE.fullmatch(value) else _UNSAFE_NAME


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


def _is_subagent_transcript(root: Path, path: Path) -> bool:
    """A dispatched agent's own run, at any nesting depth below `root`.

    A plain Agent dispatch writes `<project>/<sessionId>/subagents/agent-*.jsonl`;
    a Workflow's agents nest one level further under `subagents/workflows/<runId>/`.
    Ask the path BELOW the root: `projects_root` defaults to `~/.claude/projects`
    and carries the user's home directory, so a matching segment in that prefix
    would answer for the whole tree.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    return "subagents" in parts


def _all_transcripts_under(root: Path) -> list[Path]:
    """Every transcript under `root`, main-thread and subagent alike.

    Globbing only `*/*.jsonl` made every dispatched agent invisible (#1990) —
    silently, since subagent records ARE marked `isSidechain: true`; they simply
    live in files nothing opened. Recurse rather than enumerate known depths.
    """
    return sorted(
        (
            p
            for p in root.glob("*/**/*.jsonl")
            if p.is_file() and not p.is_symlink() and _is_transcript_path(root, p)
        ),
        key=lambda p: str(p),
    )


def _strip_ns(name: str) -> str:
    """Drop known plugin namespace prefixes so invoked names match the registry
    (registry entries are bare dir/file stems). `dev-team:plan` -> `plan`;
    `agentic-dev-team:plan` -> `plan`; other names pass through."""
    for prefix in ("agentic-dev-team:", "dev-team:"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _rewrite_name_keys(mapping: dict) -> dict:
    """Rewrite a peer-supplied name-bearing dict's keys to something safe to
    aggregate — a peer record's dict KEYS are as untrusted as any other field
    it carries. Each key is normalized through `_safe_name(_strip_ns(str(k)))`
    when it's a string; a non-string key (which would otherwise raise
    `AttributeError` the moment a consumer calls `.startswith()` on it) is
    bucketed under `_UNSAFE_NAME` instead of dropped. Values collide-merge by
    summing, matching `_safe_name`'s own collapse-and-merge convention — a
    normalization collision never silently drops a peer-attributed count."""
    out: dict = {}
    for k, v in mapping.items():
        key = _safe_name(_strip_ns(str(k))) if isinstance(k, str) else _UNSAFE_NAME
        out[key] = out.get(key, 0) + v
    return out


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
    return (
        inp / 1e6 * ir
        + out / 1e6 * rate.get("output", 0)
        + cw / 1e6 * ir * pricing.get("cache_write_multiplier", 1.25)
        + cr / 1e6 * ir * pricing.get("cache_read_multiplier", 0.1)
    )


def _iter_records(paths: list[Path]):
    """Yield every decodable JSON record across `paths`, in order.

    Streams line by line: transcripts run to tens of MB and the recursive scan
    now visits thousands of them, where `read_text().splitlines()` cost ~3x the
    file's size in peak RSS before yielding anything. `ValueError` is caught
    alongside `OSError` because `UnicodeDecodeError` is a ValueError — a
    transcript truncated mid-character by a crashed session used to abort the
    whole run (#1994 review).
    """
    for path in sorted(paths, key=lambda x: str(x)):
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
        except (OSError, ValueError):
            continue


def _accumulate_token_signals(
    usage: dict,
    raw_model,
    model,
    skill,
    pricing: dict,
    tokens_total: Counter,
    by_model: dict[str, Counter],
    by_skill: dict[str, Counter],
) -> float:
    """Token-accounting concern: usage/cost totals split by model and skill.
    Returns this record's cost (added to the running cost_total by the caller).
    Thread attribution moved to the caller's `by_agent_type` bucketing (#1994)."""
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    cost = _cost(usage, _rate(pricing, raw_model or ""), pricing)
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
    return cost


def _accumulate_skill_agent_signals(
    skill,
    content,
    skills_invoked: Counter,
    agent_dispatches: Counter,
    active: dict[str, str | None],
) -> None:
    """Skill/agent-detection concern. `skill` is the legacy attributionSkill
    tag (kept as a fallback — real transcripts don't emit it, #182);
    `content`'s tool_use blocks are the primary signal: the Skill tool and the
    Agent/Task tool that actually invoke them (#182). `active` tracks the
    most-recently-invoked skill/agent (#711), sticky until superseded, for the
    correction-turn concern to attribute against.

    Counts DISPATCHES, not runs: a dispatch made from inside a subagent is
    only visible in that subagent's own transcript, and a dispatch whose
    transcript is absent never ran. Run counts come from `attributionAgent`
    (#1994)."""
    if skill:
        skills_invoked[_safe_name(skill)] += 1
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
                active["skill"] = _safe_name(_strip_ns(s))
        elif name in ("Agent", "Task"):
            a = inp.get("subagent_type")
            if isinstance(a, str) and a:
                agent_dispatches[_safe_name(_strip_ns(a))] += 1
                active["agent"] = _safe_name(_strip_ns(a))


def _track_tool_call(
    block: dict, pending_tool: dict[str, str], tool_calls: Counter
) -> None:
    """Error-classification bookkeeping: count every tool invocation (the
    error-rate denominator) and remember its id -> name so a later
    tool_result can be attributed back to the tool that produced it."""
    name = _safe_name(str(block.get("name", "?")))
    tool_calls[name] += 1
    bid = block.get("id")
    if isinstance(bid, str) and bid:
        pending_tool[bid] = name


def _classify_tool_result(
    block: dict,
    pending_tool: dict[str, str],
    tool_errors: Counter,
    error_counts: Counter,
) -> None:
    """Error-classification concern: tally errors by tool, and detect the two
    rework sub-signals (failed edits via old_string mismatches, and
    permission denials) from a tool_result block."""
    if not block.get("is_error"):
        return
    bid = block.get("tool_use_id")
    tool_name = pending_tool.get(bid, "?") if isinstance(bid, str) else "?"
    tool_errors[tool_name] += 1
    rcontent = _text_of(block.get("content"))
    if tool_name in _EDIT_TOOLS and _OLDSTRING_RE.search(rcontent):
        error_counts["failed_edits"] += 1
    if _PERMISSION_RE.search(rcontent):
        error_counts["permission_denials"] += 1


def _track_edit(
    block: dict, sid, edits_per_file: Counter, verify_edited_since: dict[str, bool]
) -> None:
    """Edit-tracking concern: count Edit/Write/... calls per file basename,
    so repeated edits to the same file (a rework signal) can be derived. Also
    marks this session's pending stuck-verify-loop streak (#708) as
    consumed — an edit resets it, same as verify_guard.py's own reset."""
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name in _EDIT_TOOLS and inp.get("file_path"):
        edits_per_file[_safe_name(_basename(str(inp["file_path"])))] += 1
    if name in _EDIT_TOOLS:
        verify_edited_since[str(sid or "")] = True


def _track_bash(
    block: dict,
    sid,
    bash_commands: Counter,
    bash_signal_counts: Counter,
    last_verify_norm: dict[str, str],
    verify_edited_since: dict[str, bool],
) -> None:
    """Bash-retry / commit-bypass / stuck-verify-loop concern (#111, #708):
    normalize the command for near-identical retry detection, detect a
    stuck-verify-loop repeat (the same normalized verify command run again
    with no Edit/Write/... call since the previous run in this session), and
    detect the review-gate bypass signal on `git commit` invocations."""
    name = block.get("name", "?")
    inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
    if name != "Bash" or not isinstance(inp.get("command"), str):
        return
    cmd = inp["command"].strip()
    # near-identical retry detection: normalize whitespace
    norm = re.sub(r"\s+", " ", cmd)
    bash_commands[norm] += 1
    if _VERIFY_RE.search(cmd):
        skey = str(sid or "")
        if last_verify_norm.get(skey) == norm and not verify_edited_since.get(
            skey, False
        ):
            bash_signal_counts["repeated_verify_runs"] += 1
        last_verify_norm[skey] = norm
        verify_edited_since[skey] = False
    # gate signal (#111): commit + review-gate bypass
    if _COMMIT_RE.search(cmd):
        bash_signal_counts["commit_attempts"] += 1
        if _BYPASS_RE.search(cmd):
            bash_signal_counts["commit_bypasses"] += 1


def _detect_correction_turn(rec: dict, content) -> bool:
    """Correction-turn concern: a real user message (not a tool_result
    envelope) containing a correction keyword ("no", "actually", "revert",
    ...)."""
    if rec.get("type") != "user" or rec.get("isMeta"):
        return False
    utext = _text_of(content)
    if not utext:
        return False
    # skip pure tool_result envelopes (no free-text user prompt)
    if isinstance(content, list) and all(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    ):
        return False
    return bool(_CORRECTION_RE.search(utext.lower()))


def _slim(d: dict) -> dict:
    return {k: dict(sorted(v.items())) for k, v in sorted(d.items())}


def extract(
    paths: list[Path],
    pricing: dict,
    registry: dict,
    plugin_version: str = "unknown",
    projects_root: Path | None = None,
) -> dict:
    tokens_total = Counter()
    cost_total = 0.0
    by_model: dict[str, Counter] = defaultdict(Counter)
    by_skill: dict[str, Counter] = defaultdict(Counter)
    # Message counts keyed by AGENT NAME — `main` for the main thread,
    # `unattributed` where no agent is resolvable. Renamed from `by_subagent`
    # (#1994): that name meant "sidechain vs main" here while the shipped
    # report used the same path for agent-name attribution, and `by_agent_type`
    # is the plugin's settled vocabulary for this map
    # (knowledge/telemetry-schema.md, cost-metering).
    by_agent_type = Counter()
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
    # run in the same session (NOT a raw tally of every verify-class command,
    # despite the metric's pre-#708 name — that raw tally double-counted the
    # ordinary RED/GREEN/REFACTOR re-run of the same command after a real
    # edit). Tracked per-session so interleaved transcripts (--all-projects)
    # don't cross-contaminate each other's state.
    last_verify_norm: dict[str, str] = {}
    verify_edited_since: dict[str, bool] = {}
    bash_signal_counts = Counter()  # repeated_verify_runs, commit_attempts/bypasses
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
        records_seen = 0
        bash_commands = Counter()
        last_verify_norm = {}
        verify_edited_since = {}
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
                        agent_name = _safe_name(stripped)
            rtype = rec.get("type")
            is_sidechain = bool(rec.get("isSidechain")) or is_subagent
            # attributionSkill is a legacy/secondary tag — the harness does not emit
            # it on real transcripts (#182), so utilization is driven by the Skill /
            # Agent tool_use below. Kept here only as a fallback for records that do
            # carry it (and per-skill token attribution via by_skill).
            raw_skill = rec.get("attributionSkill") or rec.get("attribution_skill")
            skill = (
                _safe_name(_strip_ns(raw_skill))
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
            usage = (
                msg.get("usage")
                if isinstance(msg.get("usage"), dict)
                else (rec.get("usage") if isinstance(rec.get("usage"), dict) else None)
            )
            raw_model = msg.get("model") or rec.get("model")
            # A non-str `model` would be an unhashable dict key and abort the
            # whole run. Keep the RAW id for the pricing lookup and sanitize
            # only where it becomes a key: `_safe_name` would collapse a
            # Vertex-style id (`...-v2@20241022`) to "other", miss
            # `pricing["models"]`, and silently bill the session $0.00 — an
            # under-report, which is the failure direction that matters for the
            # cost-regression baseline (#1994 review).
            raw_model = raw_model if isinstance(raw_model, str) and raw_model else None
            model = _safe_name(raw_model) if raw_model else None

            if usage:
                if is_subagent:
                    # The whole file is one agent's run; its label is resolved
                    # once, at end of file, from `attributionAgent`.
                    thread_msgs += 1
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
                            else _safe_name(stripped_rec)
                        )
                    elif is_sidechain:
                        inline_label = "sidechain"
                    else:
                        inline_label = _MAIN_LABEL
                    by_agent_type[inline_label] += 1
                cost_total += _accumulate_token_signals(
                    usage,
                    raw_model,
                    model,
                    skill,
                    pricing,
                    tokens_total,
                    by_model,
                    by_skill,
                )

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
                        _track_edit(block, sid, edits_per_file, verify_edited_since)
                        _track_bash(
                            block,
                            sid,
                            bash_commands,
                            bash_signal_counts,
                            last_verify_norm,
                            verify_edited_since,
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
        if thread_msgs:  # `+= 0` would materialize a zero-valued key
            by_agent_type[label] += thread_msgs
        if records_seen and is_subagent:
            subagent_transcripts += 1
            agent_runs[label] += 1
        elif records_seen:
            main_transcripts += 1
        retried_bash_total += sum(n - 1 for n in bash_commands.values() if n > 1)

    # repeated edits (project-wide: a file is shared state) / retried bash
    # (per thread: a retry is a property of one agent's own loop).
    repeated_file_edits = {f: n for f, n in edits_per_file.items() if n > 1}
    retried_bash = retried_bash_total
    failed_edits = error_counts["failed_edits"]
    permission_denials = error_counts["permission_denials"]
    repeated_verify_runs = bash_signal_counts["repeated_verify_runs"]
    commit_attempts = bash_signal_counts["commit_attempts"]
    commit_bypasses = bash_signal_counts["commit_bypasses"]

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
            "by_agent_type": dict(sorted(by_agent_type.items())),
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
    safe = _safe_name(session_id)
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
                project = _safe_name(_basename(str(cwd).rstrip("/\\")))
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


def _safe_number(v) -> int | float:
    """Bound a peer-supplied numeric field read back from a synced digest —
    the same trust boundary as `_normalize_plugin_version` above, applied to
    `int(...)`/`+=` sites instead of a semver parse. Returns `0` for anything
    that isn't a plain `int`/`float` (a `bool` included: it's an `int`
    subclass in Python, so `True` would otherwise silently become `1`) and
    for a non-finite `float` (`NaN`/`Infinity`, which would poison a running
    `+=` aggregate for every OTHER host's data in the same run). An `int` is
    never cast to `float` to check finiteness — `math.isfinite(float(v))`
    raises `OverflowError` once `v`'s magnitude exceeds `sys.float_info.max`,
    a legal JSON integer with no wire-size limit, so a hostile peer can
    trivially send one and abort the run for every host. Comparing magnitude
    directly instead is safe for arbitrary precision: Python's int/float rich
    comparison never converts `v` through `float()`."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    if isinstance(v, float):
        return v if math.isfinite(v) else 0
    return 0 if abs(v) > sys.float_info.max else v


def _read_synced_records(digests_root: Path) -> list[dict]:
    """Union read + dedup (#178): every host's per-session `session-sync/v1`
    record under `digests_root/<host>/session-digest.jsonl`, keeping the LAST
    record for a session_id seen on multiple host files (or re-emitted after
    growth). Shared by `rollup()`, `correlate_gate_rework()`, and `cost_log()`
    so the dedup logic lives in one place. Each record's `plugin_version`,
    `host`, `project`, the name-bearing dicts under `utilization`/`accuracy`,
    every peer-supplied numeric field a downstream consumer reads with
    `int(...)`/`+=` (`cost_usd`; `tokens.{input_tokens,output_tokens,
    cache_creation_input_tokens,cache_read_input_tokens}`; `rework.*` via
    `_REWORK_KEYS`; `accuracy.{tool_calls,tool_error_rate,
    user_correction_turns}`; `gate.{commit_attempts,commit_bypasses}`), and
    the shape of the `tokens`/`rework`/`accuracy`/`utilization`/`gate`
    containers themselves are normalized on the way in
    (`_normalize_plugin_version`, `_safe_name`, `_rewrite_name_keys`,
    `_safe_number`) since a record originates on a peer machine, not this
    one."""
    by_id: dict[str, dict] = {}
    for f in sorted(digests_root.glob("*/session-digest.jsonl")):
        for rec in _iter_records([f]):
            if rec.get("schema") not in SYNC_SCHEMAS:
                continue
            sid = rec.get("session_id")
            if sid:
                rec["plugin_version"] = _normalize_plugin_version(
                    rec.get("plugin_version")
                )
                rec["host"] = _safe_name(str(rec.get("host") or "unknown"))
                rec["project"] = _safe_name(str(rec.get("project") or "unknown"))
                rec["cost_usd"] = _safe_number(rec.get("cost_usd", 0))
                utilization = (
                    rec.get("utilization")
                    if isinstance(rec.get("utilization"), dict)
                    else {}
                )
                accuracy = (
                    rec.get("accuracy")
                    if isinstance(rec.get("accuracy"), dict)
                    else {}
                )
                tokens = (
                    rec.get("tokens") if isinstance(rec.get("tokens"), dict) else {}
                )
                rework = (
                    rec.get("rework") if isinstance(rec.get("rework"), dict) else {}
                )
                gate = rec.get("gate") if isinstance(rec.get("gate"), dict) else {}
                for field in ("skills_invoked", "agents_invoked", "agent_dispatches"):
                    value = utilization.get(field)
                    if isinstance(value, dict):
                        utilization[field] = _rewrite_name_keys(value)
                for field in ("by_skill", "by_agent"):
                    value = accuracy.get(field)
                    if isinstance(value, dict):
                        accuracy[field] = _rewrite_name_keys(value)
                for field in (
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                ):
                    if field in tokens:
                        tokens[field] = _safe_number(tokens[field])
                for field in _REWORK_KEYS:
                    if field in rework:
                        rework[field] = _safe_number(rework[field])
                for field in (
                    "tool_calls",
                    "tool_error_rate",
                    "user_correction_turns",
                ):
                    if field in accuracy:
                        accuracy[field] = _safe_number(accuracy[field])
                for field in ("commit_attempts", "commit_bypasses"):
                    if field in gate:
                        gate[field] = _safe_number(gate[field])
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
    """Aggregate cross-machine `session-sync/v1` records (#178) — callers pass
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

    never_skills = sorted(set(registry.get("skills", [])) - set(skills_invoked))
    never_agents = sorted(
        set(registry.get("agents", [])) - set(agents_invoked) - set(agent_dispatches)
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
    digest = extract(paths, pricing, registry, version, projects_root=root)
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
    from datetime import datetime

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
