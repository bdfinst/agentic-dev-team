#!/usr/bin/env python3
"""Runtime cost/token meter for dispatched work (issues #102, #134).

PostToolUse hooks do NOT carry token usage in Claude Code; the canonical source
is the session transcript JSONL, where each assistant message records a `usage`
block (input/output/cache tokens). Every hook payload includes `transcript_path`,
so a Stop hook can hand this script the transcript to parse. This converts token
usage to dollars via the named instrument knowledge/model-pricing.json (#102 is
why that table exists) and writes an append-only metrics log.

Attribution dimensions (#102, #170, #1094)
------------------------------------------
Attribution is limited to what the harness actually records on transcript
records — verified empirically (#170, re-verified for #1094). Spend is
attributed to:
  * the MODEL (`message.model`),
  * the THREAD: main-loop vs subagent, from the native top-level `isSidechain`
    flag (true on subagent/sidechain turns),
  * the AGENT TYPE (#1094): `main` for main-loop turns; for sidechain turns the
    subagent type (e.g. `security-review`, `general-purpose`) via two
    harness-recorded signals, with an honest `unattributed` bucket when neither
    is present:
      1. the native top-level `attributionAgent` field the harness stamps on
         sidechain records (primary — present on every usage-bearing sidechain
         record in real transcripts), or
      2. the Task/Agent dispatch join: a main-thread `tool_use` block named
         `Task`/`Agent` carries `input.subagent_type` and its paired
         `tool_result` record carries top-level `toolUseResult.agentId`; each
         sidechain record carries the matching `agentId` (fallback).
  * plus the session TOTAL.

Newer harness versions write sidechain turns to sibling per-subagent transcript
files (`<dir>/<session-id>/subagents/agent-<agentId>.jsonl`) instead of inline
`isSidechain` records; the meter scans those siblings so subagent spend stays
visible either way (#1094).

What is deliberately NOT attributed, and why (#170): per-command, per-phase, and
per-fix-loop-iteration attribution were attempted via `attributionSkill` /
`orchestrationPhase` / `fixLoopIteration` markers, but **the Claude Code harness
authors the transcript and exposes none of those fields** (0/312 in a real
transcript), and a plugin has no write-path into the transcript. Those buckets
were therefore always inert ("untagged"/"other"/"unattributed") and have been
removed rather than ship misleading empty dimensions. Re-deriving them would
require fragile heuristics (correlating Stop-hook timestamps with command
boundaries) and is out of scope. The agent-type dimension (#1094) is different
in kind: it reads only fields the harness demonstrably writes.

Privacy boundary
----------------
This meter persists ONLY token counts, dollar amounts, model identifiers, and
the thread/agent-type identifiers. It never reads or records prompt text, code,
file paths, or tool payloads from the transcript — only the `usage`/`model`/
`isSidechain`/`attributionAgent`/`agentId`/`subagent_type` fields and tool-use
ids needed to join them. The append-only metrics log is a metrics-only artifact
by construction.

Subcommands
-----------
report   --transcript T [--json]
         Parse a transcript and print tokens + cost per model and per thread
         (main vs subagent), plus the session total. The acceptance command:
         "after a run, print actual tokens spent."

record   --transcript T --log .claude/metrics/cost-metering.jsonl
         Append one session-summary line to the append-only metrics log
         (follows the .claude/metrics/config-changelog.jsonl convention). Used by the
         Stop hook. Idempotent on directory creation; never errors out loudly.

regression --log .claude/metrics/cost-metering.jsonl [--tolerance 0.5] [--window N]
         Compare the most recent session's total cost against the rolling mean
         of prior sessions; exit 1 if it exceeds mean * (1 + tolerance). With
         --window N the baseline is the mean of only the N most recent prior
         sessions (a windowed rolling baseline) instead of all-time mean.

pace     --log .claude/metrics/cost-metering.jsonl [--budget B] [--period-days 30]
         [--window-days 7]
         Account-level pace guidance (#142): cumulative spend over a rolling
         window, the implied daily rate, and the projected spend for a billing
         period. With --budget it flags when the current pace would exhaust the
         budget and suggests dropping a model tier for the rest of the window.

phase-mark --transcript T --phase LABEL [--log .claude/metrics/phase-markers.jsonl]
         Context-pollution measurement (#1520): append one phase-boundary
         marker capturing the main-loop resident context occupancy and the
         cumulative output spend at a `/handoff` boundary. Fired by the
         `phase_marker.py` PostToolUse hook. Kept in its own log, never folded
         into the incremental `record` state.

phase-report --log .claude/metrics/phase-markers.jsonl [--json]
         Report per-phase resident-vs-spent ratios from the phase markers: for
         each phase, the context still resident at its boundary vs the output
         tokens spent during it. A high ratio distinguishes context that
         lingered (pollution) from one-time cost — a distinction the session
         totals cannot make.

The transcript schema is read defensively (usage may sit on the record or under
`message`; model + agent attribution likewise), so it tolerates schema drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# hooks/lib/cost_meter.py -> plugin root is three parents up.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PRICING = _PLUGIN_ROOT / "knowledge/model-pricing.json"

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from atomic_state import append_line_locked
from pricing import cost as _cost
from pricing import load_pricing as _load_pricing
from pricing import rate as _rate

# ---------------------------------------------------------------------------
# Incremental `record` state — a byte offset + running aggregates, keyed by
# transcript path, so a Stop/SubagentStop hook fire only tails bytes appended
# since the last fire instead of re-parsing the whole transcript (#732).
# Same TTL-purge-on-write pattern as tdd_guard.py / mutation_adapters/lib.py.
# ---------------------------------------------------------------------------

_STATE_TTL_SECONDS = 14400  # 4 hours


def _state_dir() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "dev-team-cost-meter"


def _state_file(transcript_path: Path) -> Path:
    digest = hashlib.sha256(
        str(Path(transcript_path).resolve()).encode("utf-8")
    ).hexdigest()[:12]
    return _state_dir() / f"session-{digest}.json"


def _purge_stale(state_dir: Path) -> None:
    if not state_dir.is_dir():
        return
    now = time.time()
    for path in state_dir.glob("session-*.json"):
        try:
            if now - path.stat().st_mtime > _STATE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def _read_new_lines(path: Path, offset: int) -> tuple[int, list[str]]:
    """Tail `path` from `offset`, returning (new_offset, complete_lines).

    Reads in binary mode and stops at the last full line so a line still
    being written doesn't get parsed half-formed; the trailing partial bytes
    are left unconsumed (picked up on the next fire once complete).
    """
    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
    except OSError:
        return offset, []
    if not chunk:
        return offset, []
    if chunk.endswith(b"\n"):
        consumed = chunk
    else:
        last_newline = chunk.rfind(b"\n")
        consumed = chunk[: last_newline + 1] if last_newline != -1 else b""
    if not consumed:
        return offset, []
    new_offset = offset + len(consumed)
    lines = consumed.decode("utf-8", errors="replace").splitlines()
    return new_offset, lines


def _load_state(state_file: Path) -> dict | None:
    if not state_file.is_file():
        return None
    try:
        data = json.loads(state_file.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _save_state(state_file: Path, payload: dict) -> None:
    try:
        state_file.write_text(json.dumps(payload))
    except OSError:
        pass


def _first_present_field(rec: dict, *keys: str):
    """Return the first present key on rec or rec['message']."""
    for src in (
        rec,
        rec.get("message", {}) if isinstance(rec.get("message"), dict) else {},
    ):
        for k in keys:
            if k in src and src[k] is not None:
                return src[k]
    return None


_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _new_bucket() -> dict:
    bucket = {f: 0 for f in _TOKEN_FIELDS}
    bucket["cost_usd"] = 0.0
    bucket["messages"] = 0
    return bucket


# Tool names the harness uses for subagent dispatch (both spellings appear in
# real transcripts depending on harness version).
_TASK_TOOL_NAMES = ("Task", "Agent")


def _iter_content_blocks(rec: dict):
    """Yield the dict blocks of `message.content` when it is a block list."""
    message = rec.get("message")
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict):
            yield block


def _harvest_agent_dispatch(rec: dict, dispatch_types: dict, agent_types: dict) -> None:
    """Fold subagent-dispatch metadata from one record into the join maps.

    Two harness-recorded halves of the join (#1094):
      * an assistant `tool_use` block named Task/Agent carries
        `input.subagent_type` — keyed here by the block's tool-use id;
      * the paired `tool_result` user record carries top-level
        `toolUseResult.agentId` — completing agentId -> subagent_type.

    Only the identifiers are read; prompts/descriptions are never touched.
    """
    for block in _iter_content_blocks(rec):
        block_type = block.get("type")
        if block_type == "tool_use" and block.get("name") in _TASK_TOOL_NAMES:
            block_id = block.get("id")
            block_input = block.get("input")
            subagent_type = (
                block_input.get("subagent_type")
                if isinstance(block_input, dict)
                else None
            )
            if (
                isinstance(block_id, str)
                and isinstance(subagent_type, str)
                and subagent_type
            ):
                dispatch_types[block_id] = subagent_type
        elif block_type == "tool_result":
            tool_use_id = block.get("tool_use_id")
            tool_use_result = rec.get("toolUseResult")
            agent_id = (
                tool_use_result.get("agentId")
                if isinstance(tool_use_result, dict)
                else None
            )
            if (
                isinstance(tool_use_id, str)
                and isinstance(agent_id, str)
                and tool_use_id in dispatch_types
            ):
                agent_types[agent_id] = dispatch_types[tool_use_id]


def _agent_type_key(rec: dict, agent_types: dict) -> str:
    """Agent-type bucket for one usage-bearing record (#1094).

    `main` for main-loop turns. For sidechain turns: the native
    `attributionAgent` field (primary), else the agentId -> subagent_type join
    built from Task/Agent dispatches (fallback), else the honest
    `unattributed` bucket — never a guess.
    """
    if not rec.get("isSidechain"):
        return "main"
    attribution_agent = rec.get("attributionAgent")
    if isinstance(attribution_agent, str) and attribution_agent:
        return attribution_agent
    agent_id = rec.get("agentId")
    if isinstance(agent_id, str) and agent_id in agent_types:
        return agent_types[agent_id]
    return "unattributed"


def _subagent_files(transcript_path: Path) -> list[Path]:
    """Sibling per-subagent transcript files for a session transcript.

    Newer harness versions store sidechain turns in
    `<dir>/<session-id>/subagents/agent-<agentId>.jsonl` rather than inline
    `isSidechain` records in the session transcript (#1094). Returns [] when
    the layout is absent (older format, or a subagent transcript itself).
    """
    subagents_dir = transcript_path.parent / transcript_path.stem / "subagents"
    try:
        if not subagents_dir.is_dir():
            return []
        return sorted(p for p in subagents_dir.glob("agent-*.jsonl") if p.is_file())
    except OSError:
        return []


def _accumulate_lines(
    lines,
    pricing: dict,
    by_model: dict,
    by_thread: dict,
    by_agent_type: dict,
    totals: dict,
    unpriced_models: set,
    dispatch_types: dict,
    agent_types: dict,
) -> None:
    """Fold `lines` (raw JSONL transcript records) into the given aggregates.

    Mutates the bucket dicts, `totals`, `unpriced_models`, and the
    `dispatch_types`/`agent_types` join maps in place so callers can seed them
    from a persisted running state and only pass in the newly-appended lines
    (#732) — or seed them empty and pass the whole transcript for a one-shot
    full parse.
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Dispatch metadata can sit on records with no usage (tool_use /
        # tool_result turns), so harvest before the usage gate.
        _harvest_agent_dispatch(rec, dispatch_types, agent_types)
        usage = _first_present_field(rec, "usage")
        if not isinstance(usage, dict):
            continue
        model = _first_present_field(rec, "model") or "unknown"
        # Main-loop vs subagent: the native top-level `isSidechain` flag is true
        # on sidechain (subagent) turns.
        thread = "subagent" if rec.get("isSidechain") else "main"
        agent_type = _agent_type_key(rec, agent_types)

        rate = _rate(pricing, model)
        cost = _cost(usage, rate, pricing)
        # Excludes zero-token records from `unpriced_models` (#1830 fix
        # review), not just the literal "unknown" placeholder: the harness
        # writes assistant records with `model: "<synthetic>"` and every usage
        # field zero for interrupt/auth-failure notices (observed in local
        # session transcripts inspected during #1830's investigation; not
        # covered by an automated probe). Those records are not billable —
        # zero tokens cost zero regardless of whether the model has a pricing
        # entry — so flagging them as "unpriced" would fire on nearly every
        # session and bury the real signal (a genuinely billable model with no
        # rate) under permanent noise. Gating on token presence rather than
        # naming "<synthetic>" specifically also covers any future
        # harness-internal pseudo-model without another denylist edit.
        if not rate and model != "unknown" and any(usage.get(f) for f in _TOKEN_FIELDS):
            unpriced_models.add(model)

        for bucket, key in (
            (by_model, model),
            (by_thread, thread),
            (by_agent_type, agent_type),
        ):
            b = bucket.setdefault(key, _new_bucket())
            for f in _TOKEN_FIELDS:
                b[f] += usage.get(f, 0) or 0
            b["cost_usd"] = round(b["cost_usd"] + cost, 6)
            b["messages"] += 1

        for f in _TOKEN_FIELDS:
            totals[f] += usage.get(f, 0) or 0
        totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
        totals["messages"] += 1


def parse_transcript(path: Path, pricing: dict) -> dict:
    """Aggregate transcript usage by model, thread, and agent type.

    Only dimensions the harness actually records are attributed (#170, #1094):
    the model (`message.model`), the main/subagent split (native top-level
    `isSidechain`), and the agent type (`attributionAgent`, or the Task/Agent
    dispatch join — see module docstring), plus the session total. Sibling
    per-subagent transcript files are folded in when present (#1094).

    Full one-shot parse — used by `report`/`regression`/`pace`, which run
    on-demand rather than once per hook fire. `record` (the Stop-hook hot
    path) uses the incremental `_read_new_lines` + `_accumulate_lines` path
    in `cmd_record` instead so it doesn't re-parse the whole transcript on
    every turn (#732).
    """
    by_model: dict[str, dict] = {}
    by_thread: dict[str, dict] = {}
    by_agent_type: dict[str, dict] = {}
    totals = _new_bucket()
    unpriced_models: set[str] = set()
    dispatch_types: dict[str, str] = {}
    agent_types: dict[str, str] = {}

    # Main transcript first so the dispatch join maps are populated before the
    # sibling subagent files (whose records fall back on them) are folded in.
    sources = [path] + _subagent_files(path)
    for source in sources:
        try:
            source_lines = source.read_text().splitlines()
        except OSError:
            if source is path:
                raise
            continue
        _accumulate_lines(
            source_lines,
            pricing,
            by_model,
            by_thread,
            by_agent_type,
            totals,
            unpriced_models,
            dispatch_types,
            agent_types,
        )

    return {
        "by_model": by_model,
        "by_thread": by_thread,
        "by_agent_type": by_agent_type,
        "totals": totals,
        "unpriced_models": sorted(unpriced_models),
    }


def _print_dimension(title: str, bucket: dict) -> None:
    if not bucket:
        return
    print(f"\n{title:<28} {'IN':>10} {'OUT':>10} {'COST $':>10}")
    print("-" * 60)
    for key, b in sorted(bucket.items(), key=lambda kv: -kv[1]["cost_usd"]):
        print(
            f"{key:<28} {b['input_tokens']:>10} {b['output_tokens']:>10} "
            f"{b['cost_usd']:>10.4f}"
        )


def _print_report(summary: dict) -> None:
    t = summary["totals"]
    print(f"# Cost meter — {t['messages']} assistant message(s)")
    _print_dimension("MODEL", summary["by_model"])
    _print_dimension("THREAD (main/subagent)", summary["by_thread"])
    _print_dimension("AGENT TYPE", summary.get("by_agent_type", {}))
    print("-" * 60)
    print(
        f"{'TOTAL':<28} {t['input_tokens']:>10} {t['output_tokens']:>10} "
        f"{t['cost_usd']:>10.4f}"
    )
    if summary["unpriced_models"]:
        print(
            f"\n⚠ no pricing for: {', '.join(summary['unpriced_models'])} "
            f"(add to knowledge/model-pricing.json)"
        )


def cmd_report(args, pricing) -> int:
    summary = parse_transcript(Path(args.transcript), pricing)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_report(summary)
    return 0


def _record_state_is_usable(
    state: dict | None, size: int, subagent_paths: list[Path]
) -> bool:
    """Whether a persisted `record` state can be resumed from (#732, #1094).

    Unusable when: absent/corrupt; the main offset is not an int within the
    current file size (rotation/truncation); the schema predates the
    agent-type dimension (resuming would ship a by_agent_type that no longer
    sums to totals); or a tracked subagent file shrank below its offset.
    """
    if not state:
        return False
    offset = state.get("offset")
    if not isinstance(offset, int) or not 0 <= offset <= size:
        return False
    if "by_agent_type" not in state:
        return False  # pre-#1094 state schema — rebuild from byte 0
    subagent_offsets = state.get("subagent_offsets")
    if subagent_offsets is not None and not isinstance(subagent_offsets, dict):
        return False
    sizes_by_name = {}
    for p in subagent_paths:
        try:
            sizes_by_name[p.name] = p.stat().st_size
        except OSError:
            sizes_by_name[p.name] = 0
    for name, sub_offset in (subagent_offsets or {}).items():
        if not isinstance(sub_offset, int) or sub_offset > sizes_by_name.get(name, 0):
            return False
    return True


def cmd_record(args, pricing) -> int:
    tpath = Path(args.transcript)
    if not tpath.is_file():
        return 0  # fail-open: hook must never break the session

    # Incremental read (#732): persist a byte offset + the running aggregates
    # in a tmp-state file keyed by the transcript path, so this Stop-hook fire
    # only tails bytes appended since the last fire instead of re-parsing the
    # whole transcript every time (O(new content), not O(turns) per fire).
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _purge_stale(state_dir)
    state_file = _state_file(tpath)

    state = _load_state(state_file)
    size = tpath.stat().st_size
    subagent_paths = _subagent_files(tpath)

    if _record_state_is_usable(state, size, subagent_paths):
        offset = state["offset"]
        subagent_offsets = {
            k: v
            for k, v in (state.get("subagent_offsets") or {}).items()
            if isinstance(v, int)
        }
        by_model = state.get("by_model") or {}
        by_thread = state.get("by_thread") or {}
        by_agent_type = state.get("by_agent_type") or {}
        totals = state.get("totals") or _new_bucket()
        for f in _TOKEN_FIELDS:
            totals.setdefault(f, 0)
        totals.setdefault("cost_usd", 0.0)
        totals.setdefault("messages", 0)
        unpriced_models = set(state.get("unpriced_models") or [])
        dispatch_types = state.get("dispatch_types") or {}
        agent_types = state.get("agent_types") or {}
    else:
        # First fire, a pre-#1094 state schema, or a transcript that shrank
        # (rotated/truncated) since the last fire — start fresh rather than
        # seek past a stale offset or ship a partial agent-type dimension.
        offset = 0
        subagent_offsets = {}
        by_model, by_thread, by_agent_type = {}, {}, {}
        totals, unpriced_models = _new_bucket(), set()
        dispatch_types, agent_types = {}, {}

    def _fold(lines) -> None:
        _accumulate_lines(
            lines,
            pricing,
            by_model,
            by_thread,
            by_agent_type,
            totals,
            unpriced_models,
            dispatch_types,
            agent_types,
        )

    # Main transcript first so dispatch joins land before subagent turns that
    # may need them, then each sibling per-subagent transcript (#1094) — each
    # with its own persisted byte offset so every source is tailed, not
    # re-parsed, per fire (#732).
    new_offset, new_lines = _read_new_lines(tpath, offset)
    _fold(new_lines)
    for sub_path in subagent_paths:
        sub_offset = subagent_offsets.get(sub_path.name, 0)
        sub_new_offset, sub_lines = _read_new_lines(sub_path, sub_offset)
        _fold(sub_lines)
        subagent_offsets[sub_path.name] = sub_new_offset

    _save_state(
        state_file,
        {
            "offset": new_offset,
            "subagent_offsets": subagent_offsets,
            "by_model": by_model,
            "by_thread": by_thread,
            "by_agent_type": by_agent_type,
            "totals": totals,
            "unpriced_models": sorted(unpriced_models),
            "dispatch_types": dispatch_types,
            "agent_types": agent_types,
        },
    )

    summary = {
        "by_model": by_model,
        "by_thread": by_thread,
        "by_agent_type": by_agent_type,
        "totals": totals,
        "unpriced_models": sorted(unpriced_models),
    }

    from datetime import datetime, timezone

    def _slim(bucket: dict) -> dict:
        # Persist cost + every token field per bucket (#1513), deriving the
        # token names from _TOKEN_FIELDS (the single source of truth used by
        # _new_bucket/_accumulate_lines) so a future field flows into the
        # durable log automatically. cache_creation is the spawn-floor F
        # component the epic measures — it must live in the log, not only in
        # `report --json`.
        return {
            k: {"cost_usd": b["cost_usd"], **{f: b[f] for f in _TOKEN_FIELDS}}
            for k, b in bucket.items()
        }

    line = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transcript": tpath.name,
        "total": summary["totals"],
        "by_model": _slim(summary["by_model"]),
        "by_thread": _slim(summary["by_thread"]),
        "by_agent_type": _slim(summary["by_agent_type"]),
        # Always present, even when empty (#1830). This field was computed and
        # warned about in `report`, and persisted to the incremental state file,
        # but omitted from the durable line — which is the ONLY thing every
        # downstream consumer reads: /autoship's `--max-cost-usd` gate,
        # `regression`, and `pace`. A model with no pricing entry therefore
        # contributed $0.00 to a budget ceiling and was indistinguishable from
        # one that is genuinely free. Emitting `[]` rather than omitting the key
        # on the clean path matters too: a consumer can then treat absence as
        # "this record predates the check" instead of "nothing was unpriced".
        "unpriced_models": summary["unpriced_models"],
    }
    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    append_line_locked(log, json.dumps(line) + "\n", fail_open=False)
    return 0


def _warn_unpriced(entries: list) -> None:
    """Print a warning naming every model that contributed $0.00 to the records
    being summarized because it has no pricing entry (#1830).

    Any verdict computed over such records understates real spend, so say so
    rather than reporting a number that reads as complete. Records written
    before `unpriced_models` was added to the durable line simply lack the key
    and contribute nothing here — silence means "no unpriced model was seen in
    the records that carry the field", not "every record was checked"."""
    unpriced = sorted(
        {
            model
            for entry in entries
            for model in (entry.get("unpriced_models") or [])
            if isinstance(model, str)
        }
    )
    if not unpriced:
        return
    print(
        f"⚠ model(s) that priced at $0.00 in these records: "
        f"{', '.join(unpriced)} — the figures below UNDERSTATE real cost. If "
        "they are absent from knowledge/model-pricing.json, add them; if they "
        "were added recently, re-record the affected sessions."
    )


def _read_log_entries(log: Path) -> list:
    entries = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def cmd_regression(args, pricing) -> int:
    log = Path(args.log)
    if not log.is_file():
        print("no metrics log yet; nothing to compare")
        return 0
    entries = _read_log_entries(log)
    _warn_unpriced(entries)
    costs = [e.get("total", {}).get("cost_usd", 0.0) for e in entries]
    if len(costs) < 2:
        print(f"only {len(costs)} session(s) logged; need >=2 to compare")
        return 0
    latest = costs[-1]
    prior = costs[:-1]
    # Windowed rolling baseline (#134): mean of only the N most recent priors.
    window = getattr(args, "window", 0) or 0
    if window > 0:
        prior = prior[-window:]
    mean = sum(prior) / len(prior)
    limit = mean * (1 + args.tolerance)
    win_label = f"window {len(prior)}" if window > 0 else f"prior {len(prior)}"
    print(
        f"latest=${latest:.4f}  rolling-mean({win_label})=${mean:.4f}  "
        f"limit(+{int(args.tolerance * 100)}%)=${limit:.4f}"
    )
    if mean > 0 and latest > limit:
        print(f"COST REGRESSION: latest ${latest:.4f} exceeds limit ${limit:.4f}")
        return 1
    print("no cost regression")
    return 0


def _parse_ts(s: str):
    from datetime import datetime, timezone

    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def cmd_pace(args, pricing) -> int:
    """Account-level pace: cumulative spend over a rolling window, projected
    against a budget for a billing period; flags when pace would exhaust it."""
    from datetime import datetime, timedelta, timezone

    log = Path(args.log)
    if not log.is_file():
        print("no metrics log yet; nothing to pace")
        return 0
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.window_days)
    in_window = []
    windowed_entries = []
    for e in _read_log_entries(log):
        ts = _parse_ts(e.get("timestamp", ""))
        cost = e.get("total", {}).get("cost_usd", 0.0)
        if ts is not None and ts >= window_start:
            in_window.append((ts, cost))
            windowed_entries.append(e)

    # Scoped to the window, not the whole log: a budget projection understates
    # only when an unpriced model appears in the records it actually sums (#1830).
    _warn_unpriced(windowed_entries)

    spend = round(sum(c for _, c in in_window), 6)
    print(f"# Account pace — last {args.window_days} day(s)")
    print(f"  sessions in window: {len(in_window)}")
    print(f"  cumulative spend:   ${spend:.4f}")
    if not in_window:
        print("  (no sessions in window; nothing to project)")
        return 0

    earliest = min(ts for ts, _ in in_window)
    elapsed_days = max((now - earliest).total_seconds() / 86400.0, 1e-9)
    daily_rate = spend / elapsed_days
    projected = daily_rate * args.period_days
    print(
        f"  daily rate:         ${daily_rate:.4f}/day "
        f"(over {elapsed_days:.2f} active day(s))"
    )
    print(f"  projected / {args.period_days}d:   ${projected:.4f}")

    if args.budget is not None and args.budget > 0:
        pct = projected / args.budget * 100
        print(
            f"  budget / {args.period_days}d:       ${args.budget:.2f} "
            f"({pct:.0f}% of budget at current pace)"
        )
        if projected > args.budget:
            print(
                f"\n⚠ PACE EXCEEDS BUDGET: at ${daily_rate:.4f}/day you would "
                f"spend ${projected:.2f} over {args.period_days} days, past the "
                f"${args.budget:.2f} budget."
            )
            print(
                "  Consider dropping Opus→Sonnet for the remainder of the "
                "window (see .claude/model-overrides.json / /harness-audit)."
            )
    return 0


def _resident_and_spent(path: Path) -> tuple[int, int]:
    """(resident_tokens, spent_output_cumulative) for the MAIN-LOOP context (#1520).

    Context-pollution measurement is about the *live orchestrating* context —
    the one that "charges rent" every subsequent turn per Martin Fowler's "The
    Orchestrator's Tax" — so both figures are computed over main-loop
    (non-sidechain) turns only; subagent contexts are separate and are
    discarded at their own SubagentStop.

      * resident_tokens = the MOST-RECENT main-loop usage record's context
        occupancy (input + cache_read + cache_creation) — what still occupies
        the window at this point, the same numerator context_ceiling_guard.py
        uses. Overwritten each turn so it ends as the last turn's occupancy.
      * spent_output_cumulative = the sum of output_tokens across all main-loop
        turns so far — the one-time generation bill accrued to this point.

    Read defensively (schema drift tolerated the same way parse_transcript does);
    a missing/unreadable transcript returns (0, 0) rather than raising, so the
    fail-open phase-mark hook never breaks a turn.
    """
    resident = 0
    spent_output = 0
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return 0, 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("isSidechain"):
            continue  # main-loop context only
        usage = _first_present_field(rec, "usage")
        if not isinstance(usage, dict):
            continue
        resident = (
            (usage.get("input_tokens", 0) or 0)
            + (usage.get("cache_read_input_tokens", 0) or 0)
            + (usage.get("cache_creation_input_tokens", 0) or 0)
        )
        spent_output += usage.get("output_tokens", 0) or 0
    return resident, spent_output


def cmd_phase_mark(args, pricing) -> int:
    """Append one phase-boundary marker to the phase-markers log (#1520).

    Fired by the `phase_marker.py` PostToolUse hook when `/handoff` runs (a
    phase boundary). Captures the resident/spent snapshot at the boundary so
    `phase-report` can later derive per-phase context-pollution ratios the
    session totals alone cannot (the harness records no phase marker itself —
    the reason per-phase cost attribution was removed in #170). Kept in its OWN
    log, deliberately NOT folded into the incremental `record` state, so this
    additive dimension never touches that security-sensitive hot path.

    Fail-open: a missing transcript is a no-op success (the hook must never
    break a turn)."""
    tpath = Path(args.transcript)
    if not tpath.is_file():
        return 0
    resident, spent = _resident_and_spent(tpath)
    from datetime import datetime, timezone

    line = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transcript": tpath.name,
        "phase": args.phase or "unlabeled",
        "resident_tokens": resident,
        "spent_output_cumulative": spent,
    }
    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    append_line_locked(log, json.dumps(line) + "\n", fail_open=False)
    return 0


def _phase_rows(entries: list) -> list:
    """Per-phase resident/spent rows from ordered phase markers (#1520).

    `spent_output_cumulative` is monotonic across a session, so a phase's own
    spend is the delta from the prior marker; `resident_tokens` is a snapshot,
    used as-is. `resident_to_spent_ratio = resident / spent_phase` is the
    context-pollution proxy — high means a large resident footprint relative to
    the fresh generation the phase did (context that lingered rather than being
    compacted). `None` when the phase spent nothing new (ratio undefined), never
    a divide-by-zero.
    """
    rows = []
    prev_spent = 0
    for e in entries:
        resident = e.get("resident_tokens", 0) or 0
        spent_cum = e.get("spent_output_cumulative", 0) or 0
        # A cumulative counter can only go up within a session; clamp at 0 so a
        # transcript rotation (counter reset) never yields a negative phase spend.
        spent_phase = max(spent_cum - prev_spent, 0)
        prev_spent = spent_cum
        ratio = round(resident / spent_phase, 2) if spent_phase > 0 else None
        rows.append(
            {
                "phase": e.get("phase", "unlabeled"),
                "resident_tokens": resident,
                "spent_tokens": spent_phase,
                "resident_to_spent_ratio": ratio,
            }
        )
    return rows


def cmd_phase_report(args, pricing) -> int:
    """Print per-phase resident/spent ratios from the phase-markers log (#1520)."""
    log = Path(args.log)
    if not log.is_file():
        print("no phase markers recorded yet; nothing to report")
        return 0
    entries = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows = _phase_rows(entries)
    if getattr(args, "json", False):
        print(json.dumps({"by_phase": rows}, indent=2))
        return 0
    print("# Context pollution — resident vs one-time spend, per phase (#1520)")
    print(f"{'PHASE':<24} {'RESIDENT':>10} {'SPENT':>10} {'RESIDENT/SPENT':>15}")
    print("-" * 62)
    for r in rows:
        ratio = "-" if r["resident_to_spent_ratio"] is None else f"{r['resident_to_spent_ratio']:.2f}"
        print(
            f"{r['phase']:<24} {r['resident_tokens']:>10} {r['spent_tokens']:>10} "
            f"{ratio:>15}"
        )
    print(
        "\nresident = main-loop context occupancy at the phase's /handoff boundary; "
        "spent = output tokens generated during the phase. A high ratio flags a "
        "phase whose context lingered (pollution) rather than being one-time cost. "
        "Session-scoped proxy: resident is sampled at the /handoff marker, the "
        "closest phase boundary the harness exposes."
    )
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pricing", default=str(_DEFAULT_PRICING))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("report")
    p.add_argument("--transcript", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("record")
    p.add_argument("--transcript", required=True)
    p.add_argument("--log", default=str(artifact_paths.metrics_dir() / "cost-metering.jsonl"))
    p = sub.add_parser("regression")
    p.add_argument("--log", default=str(artifact_paths.metrics_dir() / "cost-metering.jsonl"))
    p.add_argument("--tolerance", type=float, default=0.5)
    p.add_argument(
        "--window",
        type=int,
        default=0,
        help="baseline = mean of the N most recent prior sessions (0 = all-time mean)",
    )
    p = sub.add_parser("pace")
    p.add_argument("--log", default=str(artifact_paths.metrics_dir() / "cost-metering.jsonl"))
    p.add_argument(
        "--budget",
        type=float,
        default=None,
        help="account budget for one billing period (dollars)",
    )
    p.add_argument(
        "--period-days",
        type=int,
        default=30,
        help="length of the billing period to project against",
    )
    p.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="rolling lookback used to estimate the current daily rate",
    )
    p = sub.add_parser("phase-mark")
    p.add_argument("--transcript", required=True)
    p.add_argument(
        "--phase",
        default=None,
        help="phase label for this boundary marker (e.g. research/plan/implement)",
    )
    p.add_argument(
        "--log", default=str(artifact_paths.metrics_dir() / "phase-markers.jsonl")
    )
    p = sub.add_parser("phase-report")
    p.add_argument(
        "--log", default=str(artifact_paths.metrics_dir() / "phase-markers.jsonl")
    )
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    pricing = _load_pricing(Path(args.pricing))
    return {
        "report": cmd_report,
        "record": cmd_record,
        "regression": cmd_regression,
        "pace": cmd_pace,
        "phase-mark": cmd_phase_mark,
        "phase-report": cmd_phase_report,
    }[args.cmd](args, pricing)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
