#!/usr/bin/env python3
"""measure_full_file_duplication.py — quantify duplicate full-file-read token
cost across same-round review-agent dispatches (#1618, the measurement
follow-up to #1611).

#1611 observed that a large `/code-review` panel dispatches N agents in one
round, several of which independently read the same large, unchanged file in
full. #1618's own investigation confirmed the harness's prompt caching cannot
help (the cache key hashes the entire cumulative prefix, which differs
agent-to-agent from the first block since each agent carries its own system
prompt). This script quantifies how much of a round's real token spend is
attributable to that duplication, before any fix is designed.

Two independent legs, matching #1618's Approach section:

1. **Theoretical floor** (`theoretical` subcommand, no transcript needed).
   Reuses `plugins/dev-team/scripts/select_lenses.py`'s Scope-based roster
   resolution (the same gate `/code-review` step 3 applies) plus a local
   `Context needs:` parser to compute, for a given file, how many applicable
   review agents would receive it as a `full-file` payload.
   `file_token_estimate` is a rough bytes/`BYTES_PER_TOKEN_ESTIMATE`
   approximation — never a billing figure, only used to size a duplication
   estimate proportionally.

2. **Empirical validation** (`rounds` / `report` subcommands, transcript
   required). Detects same-round agent dispatches from a session transcript
   by clustering `Task`/`Agent` dispatch timestamps, then sums each
   dispatched agent's real input-side tokens from its own sidechain
   transcript. Two harness layouts exist: the newer `<session>/subagents/
   agent-<id>.jsonl` + `.meta.json` sibling-file layout (empirically
   confirmed against this repo's own live session transcript while writing
   this script — 137/137 `.meta.json` files carried a populated `agentType`
   field, #1629's executable-claims convention satisfied by that probe
   rather than an assumption), and the older inline-`isSidechain`-record
   layout `plugins/dev-team/hooks/lib/cost_meter.py` was written against.
   `report` combines the two legs: for given `--target-files` args, it
   computes the theoretical avoidable-token estimate, then expresses it as a
   percentage of each detected round's REAL total input spend.

Validation run (#1618's acceptance criterion): this session's own live
transcript is the only real `/code-review`-equivalent transcript available
in this environment, but it contains 9 real, independently-dispatched
multi-agent rounds (>=2 qualifying agents each) spanning two different
units of work — this session's own `correctness-review.md` edit (2 rounds)
and an earlier PR's `project-init/SKILL.md` + 4 sibling files fix cycle (7
rounds). Measured `avoidable_pct_of_round_total_estimate` across all 9:
min 0.38%, median 0.8%, max 4.86%. Full per-round output posted as a
comment to #1611 alongside the PR that adds this script.

Provenance note: only the join-map algorithm for the older inline layout is
reused from `cost_meter.py` (reimplemented locally here rather than imported,
since that algorithm's own module keeps it private — see
`_join_dispatch_agent_ids`'s docstring); the newer sibling-file layout is
independently derived, not reused, because it needs per-INSTANCE granularity
`cost_meter.parse_transcript`'s aggregated `by_agent_type` breakdown does not
expose.

Deliberately out of scope (tracked as follow-ups, not fixed here): this
script counts an agent as a potential duplicate reader once it is DISPATCHED
into a role whose `Context needs:` declares `full-file` — it does not
cross-reference each agent's own `Read` tool-use blocks to confirm it
actually read the target file, so `avoidable_tokens_estimate` is a ceiling,
not an observed count. It also uses its own `Context needs:` parser rather
than the one `tests/agents/test_agent_effort_frontmatter.py`'s
`_context_needs_value` (or `plugins/dev-team/hooks/eval_compliance_check.py`'s
separate, looser one) already implements — reconciling three parsers of the
same repo-wide declaration into one shared `hooks/lib/` module is real
cleanup, but changes `eval_compliance_check.py`'s own behavior, which this
measurement-only issue's scope explicitly excludes.

Privacy boundary: mirrors `cost_meter.py`'s own convention. This script reads
only `timestamp`, numeric `message.usage.*` fields, `isSidechain`, `agentId`,
`attributionAgent`, and `meta.agentType` from transcripts — never prompt
text, code, or tool payloads — and persists nothing; every subcommand prints
to stdout only. `TestPrivacyBoundary` in the paired test file pins this with
a sentinel-prompt-text transcript.

"round" here means a timestamp-clustered burst of dispatches inferred from
gaps in a transcript — a different, narrower concept than
`plugins/dev-team/skills/code-review/scripts/review_round_log.py`'s own
caller-numbered `/code-review` round identity. The two are not currently
joinable; do not conflate them.

Monorepo-only by design (ADR 0032 category 2, docs/adr/0032-shipped-script-
path-resolution-taxonomy.md): this is a one-off measurement tool for this
marketplace repo's own `/code-review` cost question, not `/code-review`-
invoked skill machinery, so it lives here under repo-root `scripts/` rather
than a shipped skill's `scripts/` directory.

Import boundary: this repo-root script adds `plugins/dev-team/scripts/` to
`sys.path` to import `select_lenses` rather than duplicating its
Scope-resolution logic — the estimate is only meaningful if it uses the
SAME gate `/code-review` itself applies. The dependency runs non-shipped
tooling -> shipped module (never the reverse, which would make plugin code
depend on unshipped repo-root files), and touches only `select_lenses`'
public `applicable_lenses`/`build_review_roster` — it does not repeat the
private-surface reach `_join_dispatch_agent_ids` documents above.
`tests/scripts/test_measure_full_file_duplication.py` exercises the import
directly, so a `select_lenses` signature change fails the pytest gate
rather than silently breaking this tool.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_PLUGIN_SCRIPTS_DIR = _PLUGIN_ROOT / "scripts"
if str(_PLUGIN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_SCRIPTS_DIR))

import select_lenses

FULL_FILE_TOKEN = "full-file"

# Rough, documented order-of-magnitude heuristic (English/code prose is
# commonly approximated at ~4 bytes/token). Never used for billing — only to
# size a duplication estimate proportionally to file size. Per #1629's
# executable-claims convention this is a stated approximation, not an
# adjudicated runtime claim, and is capped accordingly (see the module
# docstring's provenance note).
BYTES_PER_TOKEN_ESTIMATE = 4

# Dispatch records within this many seconds of the previous one are treated
# as the same round (a single parallel-dispatch message's Task/Agent blocks
# land seconds apart in real transcripts; distinct rounds are minutes apart —
# observed directly against this repo's own session transcript while writing
# this script: one round's 16 dispatches spanned ~51s, the next round started
# ~14 minutes later). Exposed as --gap-seconds for callers whose dispatch
# cadence differs.
DEFAULT_ROUND_GAP_SECONDS = 90.0

DEFAULT_MIN_AGENTS = 2

_INPUT_SIDE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

# Matches the same repo-wide convention `tests/agents/test_agent_effort_
# frontmatter.py`'s own `_context_needs_value` anchors on, so a prose line
# merely mentioning "Context needs" doesn't false-match.
_CONTEXT_NEEDS_RE = re.compile(r"^\s*Context needs\s*:\s*(.*)$", re.IGNORECASE)


def parse_context_needs_tokens(text: str) -> set[str]:
    """Lowercase `Context needs:` tokens declared in an agent file's body.

    Handles the three shapes seen across `agents/*.md`: a single value
    (`full-file`), a comma-separated combination (`artifact-stream,
    diff-only`), and a value with a trailing parenthetical aside (`full-file
    (reads plan + git state)`) — the aside is stripped before splitting.
    Returns an empty set when no `Context needs:` line is present.
    """
    for line in text.splitlines():
        match = _CONTEXT_NEEDS_RE.match(line)
        if not match:
            continue
        value = match.group(1)
        paren = value.find("(")
        if paren != -1:
            value = value[:paren]
        return {tok.strip().lower() for tok in value.split(",") if tok.strip()}
    return set()


def estimate_tokens(byte_count: int) -> int:
    return max(1, byte_count // BYTES_PER_TOKEN_ESTIMATE)


def theoretical_full_file_agents(
    file_path: Path, roster, agents_dir: Path
) -> tuple[list[str], int, list[str], bool]:
    """Which review agents in `roster` would receive `file_path` as a
    `full-file` payload for a single-file changeset, the file's own token
    estimate, any roster-resolution warnings, and whether the file itself
    could not be stat()'d.

    `roster` is `select_lenses.build_review_roster(agents_dir, ...)`'s own
    output — callers building a report across several files pass the SAME
    roster each time (built once) rather than re-reading the registry/agent
    files per file, which the pre-refactor version of this function did (an
    N+1 file-I/O pattern a review round on this script caught). `agents_dir`
    must be the SAME directory that roster was built from — passed
    separately rather than hardcoded to this repo's own `agents/`, so a
    synthetic roster (as this module's own tests use) resolves against its
    own fixture agents, not this plugin's real ones.
    """
    lenses, lens_warnings = select_lenses.applicable_lenses([str(file_path)], roster)
    full_file_agents = []
    for name in lenses:
        try:
            agent_text = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        except OSError:
            continue
        if FULL_FILE_TOKEN in parse_context_needs_tokens(agent_text):
            full_file_agents.append(name)
    try:
        byte_count = file_path.stat().st_size
        file_missing = False
    except OSError:
        byte_count = 0
        file_missing = True
    tokens = 0 if file_missing else estimate_tokens(byte_count)
    return full_file_agents, tokens, lens_warnings, file_missing


def avoidable_tokens_estimate(file_tokens: int, n_full_file_agents: int) -> int:
    """The `file_tokens x (n-1)` formula #1618 specifies, in one named place
    so `cmd_theoretical` and `cmd_report` can't drift apart on it."""
    return file_tokens * max(0, n_full_file_agents - 1)


# ---------------------------------------------------------------------------
# Empirical leg: detect same-round dispatches from a real transcript.
# ---------------------------------------------------------------------------


def _iter_jsonl(path: Path):
    """Stream a JSONL file line by line (not loaded fully into memory —
    transcripts from long sessions can be large). Malformed lines are
    skipped, matching `hooks/lib/cost_meter.py`'s own tolerant-parsing
    convention for the same reason: a transcript being actively appended to
    by a live session can carry a partial trailing line, and this script (a
    manual, on-demand diagnostic, not a hot-path hook) accepts the same
    trade-off cost_meter.py's own JSONDecodeError guards already make
    rather than adding file locking no other tool in this repo uses either."""
    try:
        f = path.open(encoding="utf-8")
    except OSError:
        return
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _usage_from_record(rec: dict) -> dict | None:
    """Usage dict from a record, checking both top-level and `message.usage`
    (matching `cost_meter._first_present_field`'s own two-site check — an
    earlier version of this script checked only `message.usage`)."""
    message = rec.get("message")
    if isinstance(message, dict) and isinstance(message.get("usage"), dict):
        return message["usage"]
    usage = rec.get("usage")
    return usage if isinstance(usage, dict) else None


def _input_side_spend(usage: dict) -> int:
    return sum(usage.get(f, 0) or 0 for f in _INPUT_SIDE_FIELDS)


def _agent_input_spend(agent_jsonl: Path) -> tuple[int, str | None, str | None]:
    """Sum input-side usage across one agent's own sidechain transcript, its
    first record's timestamp (for round clustering), and the first
    `attributionAgent` value seen (fallback agent-type source when a
    `.meta.json` sidecar lacks `agentType`)."""
    total = 0
    first_ts: str | None = None
    attribution_agent: str | None = None
    for rec in _iter_jsonl(agent_jsonl):
        ts = rec.get("timestamp")
        if first_ts is None and isinstance(ts, str):
            first_ts = ts
        if attribution_agent is None and isinstance(rec.get("attributionAgent"), str):
            attribution_agent = rec["attributionAgent"]
        usage = _usage_from_record(rec)
        if usage is not None:
            total += _input_side_spend(usage)
    return total, first_ts, attribution_agent


def _dispatches_from_sibling_files(subagents_dir: Path) -> list[dict]:
    """Newer harness layout: one `agent-<id>.jsonl` per dispatched subagent,
    discovered by globbing `agent-*.jsonl` directly (not gated on a
    `.meta.json` sidecar existing, which an earlier version of this function
    did — silently returning zero dispatches for any session where a sidecar
    happens to be absent). `.meta.json`'s `agentType` is the primary
    agent-type source when present; a record's own `attributionAgent` is the
    fallback, mirroring `cost_meter._agent_type_key`'s documented precedence
    (primary: native `attributionAgent`; fallback: the Task/Agent dispatch
    join)."""
    dispatches: list[dict] = []
    for agent_jsonl in sorted(subagents_dir.glob("agent-*.jsonl")):
        agent_id = agent_jsonl.stem.removeprefix("agent-")
        meta_path = subagents_dir / f"agent-{agent_id}.meta.json"
        agent_type = None
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                agent_type = meta.get("agentType")
            except (OSError, json.JSONDecodeError):
                agent_type = None
        spend, first_ts, attribution_agent = _agent_input_spend(agent_jsonl)
        agent_type = agent_type or attribution_agent
        if not agent_type or first_ts is None:
            continue
        dispatches.append(
            {"agent_type": agent_type, "timestamp": first_ts, "input_spend": spend}
        )
    return dispatches


def _join_dispatch_agent_ids(rec: dict, dispatch_types: dict, agent_types: dict) -> None:
    """Join a main-thread `Task`/`Agent` dispatch block's `subagent_type` to
    its paired `tool_result`'s `agentId`, mutating the two maps in place.

    Reimplements (rather than imports) `cost_meter._harvest_agent_dispatch`'s
    algorithm: that function is underscore-prefixed — internal to its own
    module — and a review round on this script found it to be the only
    production (non-test) cross-module reach into a private helper anywhere
    in this plugin. The join is ~15 lines and stable (it reads only the
    harness-recorded `tool_use`/`tool_result` block shape `cost_meter.py`'s
    own module docstring documents), so reimplementing it locally avoids an
    undeclared dependency on another module's private surface without
    requiring a change to `cost_meter.py` itself (out of scope for this
    measurement-only issue).
    """
    message = rec.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") in ("Task", "Agent"):
            block_id = block.get("id")
            block_input = block.get("input")
            subagent_type = (
                block_input.get("subagent_type")
                if isinstance(block_input, dict)
                else None
            )
            if isinstance(block_id, str) and isinstance(subagent_type, str):
                dispatch_types[block_id] = subagent_type
        elif block.get("type") == "tool_result":
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


def _dispatches_from_inline_sidechain(transcript_path: Path) -> list[dict]:
    """Older harness layout: sidechain turns recorded inline in the main
    transcript with `isSidechain: true`. Prefers a record's own
    `attributionAgent` (cost_meter's documented primary signal); falls back
    to the Task/Agent dispatch join otherwise — an earlier version of this
    function used the join exclusively, silently dropping any agent
    attributed only via `attributionAgent`."""
    dispatch_types: dict[str, str] = {}
    agent_types: dict[str, str] = {}
    per_agent_spend: dict[str, int] = {}
    per_agent_first_ts: dict[str, str] = {}
    per_agent_attribution: dict[str, str] = {}
    for rec in _iter_jsonl(transcript_path):
        _join_dispatch_agent_ids(rec, dispatch_types, agent_types)
        if not rec.get("isSidechain"):
            continue
        agent_id = rec.get("agentId")
        ts = rec.get("timestamp")
        if isinstance(agent_id, str) and isinstance(ts, str):
            per_agent_first_ts.setdefault(agent_id, ts)
        if isinstance(agent_id, str) and isinstance(rec.get("attributionAgent"), str):
            per_agent_attribution.setdefault(agent_id, rec["attributionAgent"])
        usage = _usage_from_record(rec)
        if isinstance(agent_id, str) and usage is not None:
            per_agent_spend[agent_id] = per_agent_spend.get(agent_id, 0) + _input_side_spend(
                usage
            )

    dispatches: list[dict] = []
    for agent_id, first_ts in per_agent_first_ts.items():
        agent_type = per_agent_attribution.get(agent_id) or agent_types.get(agent_id)
        if not agent_type:
            continue
        dispatches.append(
            {
                "agent_type": agent_type,
                "timestamp": first_ts,
                "input_spend": per_agent_spend.get(agent_id, 0),
            }
        )
    return dispatches


def _parse_iso(ts: str) -> float:
    """Seconds-since-epoch for a `...Z`-suffixed ISO8601 timestamp, stdlib
    only (`datetime.fromisoformat` predates `Z` support before Python 3.11,
    so the suffix is normalized to `+00:00` first for the 3.10 floor)."""
    normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    return datetime.fromisoformat(normalized).timestamp()


def collect_agent_dispatches(transcript_path: Path) -> list[dict]:
    """One entry per dispatched subagent instance: `{agent_type, timestamp,
    input_spend}`, sorted chronologically (parsed, not lexicographic — an
    earlier version sorted the raw timestamp strings, which silently
    diverges from chronological order under mixed UTC-offset spellings).

    Tries the newer sibling-file layout (`<transcript-stem>/subagents/`)
    first; falls back to the older inline-`isSidechain` layout only when no
    `subagents/` directory exists at all (not merely when it yields zero
    dispatches, which would otherwise mask a real parsing gap as "no
    dispatches this session")."""
    subagents_dir = transcript_path.parent / transcript_path.stem / "subagents"
    if subagents_dir.is_dir():
        dispatches = _dispatches_from_sibling_files(subagents_dir)
    else:
        dispatches = _dispatches_from_inline_sidechain(transcript_path)
    return sorted(dispatches, key=lambda d: _parse_iso(d["timestamp"]))


def cluster_rounds(dispatches: list[dict], gap_seconds: float) -> list[list[dict]]:
    """Group dispatches (already timestamp-sorted) into rounds: a new round
    starts whenever the gap since the previous dispatch exceeds
    `gap_seconds`."""
    rounds: list[list[dict]] = []
    current: list[dict] = []
    prev_t: float | None = None
    for d in dispatches:
        t = _parse_iso(d["timestamp"])
        if current and prev_t is not None and (t - prev_t) > gap_seconds:
            rounds.append(current)
            current = []
        current.append(d)
        prev_t = t
    if current:
        rounds.append(current)
    return rounds


def round_summary(round_dispatches: list[dict]) -> dict:
    total = sum(d["input_spend"] for d in round_dispatches)
    return {
        "n_agents": len(round_dispatches),
        "agent_types": [d["agent_type"] for d in round_dispatches],
        "start": round_dispatches[0]["timestamp"],
        "end": round_dispatches[-1]["timestamp"],
        "round_total_input_tokens": total,
    }


def _short_name(subagent_type: str) -> str:
    """`dev-team:correctness-review` -> `correctness-review` — dispatch
    records carry the plugin-qualified subagent_type; agent-file names
    (and this script's theoretical roster) are unqualified."""
    return subagent_type.rsplit(":", 1)[-1]


def _percentile_distribution(percentages: list[float]) -> dict | None:
    """min/median/max across a round-level percentage sample, or `None` if
    empty. Uses `statistics.median` rather than a hand-rolled sort+midpoint
    calculation (a review round on this script flagged the reinvented
    built-in)."""
    if not percentages:
        return None
    sorted_pct = sorted(percentages)
    return {
        "min_pct": sorted_pct[0],
        "median_pct": median(sorted_pct),
        "max_pct": sorted_pct[-1],
        "n_rounds_sampled": len(sorted_pct),
    }


def _round_report_row(round_dispatches: list[dict], per_file: dict) -> dict:
    """One `report` row: a round's summary plus, per target file, how many
    of the round's DISPATCHED AGENT INSTANCES are in that file's theoretical
    full-file-agent set and the resulting avoidable-token estimate.

    Counts instances, not distinct agent TYPES (an earlier version built a
    `set()` of dispatched types and intersected it with the theoretical set
    — so two same-type dispatches in one round, each independently a fresh
    full-file re-read, only ever counted as one).
    """
    summary = round_summary(round_dispatches)
    dispatched_short = [_short_name(a) for a in summary["agent_types"]]

    total_avoidable = 0
    total_file_tokens = 0
    per_file_rows = []
    for file_str, (
        full_file_agents,
        file_tokens,
        _warnings,
        file_missing,
    ) in per_file.items():
        full_file_set = set(full_file_agents)
        n = sum(1 for a in dispatched_short if a in full_file_set)
        avoidable = avoidable_tokens_estimate(file_tokens, n)
        total_avoidable += avoidable
        total_file_tokens += file_tokens
        per_file_rows.append(
            {
                "file": file_str,
                "file_missing": file_missing,
                "n_full_file_agents_dispatched": n,
                "file_token_estimate": file_tokens,
                "avoidable_tokens_estimate": avoidable,
            }
        )

    total = summary["round_total_input_tokens"]
    pct = round(100 * total_avoidable / total, 2) if total else None
    row = dict(summary)
    row["files"] = per_file_rows
    row["total_file_token_estimate"] = total_file_tokens
    row["total_avoidable_tokens_estimate"] = total_avoidable
    row["avoidable_pct_of_round_total_estimate"] = pct
    return row


def _filter_since(dispatches: list[dict], since: str | None) -> list[dict]:
    """Drop dispatches earlier than `since` (an ISO8601 timestamp) — lets a
    caller scope rounds/report to one unit of work in a transcript that
    spans many (e.g. an entire session covering several unrelated PRs)."""
    if not since:
        return dispatches
    since_t = _parse_iso(since)
    return [d for d in dispatches if _parse_iso(d["timestamp"]) >= since_t]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_theoretical(args) -> int:
    roster, roster_warnings = select_lenses.build_review_roster(
        args.agents_dir, args.registry
    )
    rows = []
    total_avoidable = 0
    for f in args.files:
        path = Path(f)
        agents, file_tokens, lens_warnings, file_missing = theoretical_full_file_agents(
            path, roster, args.agents_dir
        )
        n = len(agents)
        avoidable = avoidable_tokens_estimate(file_tokens, n)
        total_avoidable += avoidable
        rows.append(
            {
                "file": f,
                "file_missing": file_missing,
                "full_file_agents": agents,
                "n_full_file_agents": n,
                "file_token_estimate": file_tokens,
                "avoidable_tokens_estimate": avoidable,
                "warnings": lens_warnings,
            }
        )
    print(
        json.dumps(
            {
                "files": rows,
                "total_avoidable_tokens_estimate": total_avoidable,
                "roster_warnings": roster_warnings,
            },
            indent=2,
        )
    )
    return 0


def cmd_rounds(args) -> int:
    dispatches = _filter_since(collect_agent_dispatches(args.transcript), args.since)
    rounds = cluster_rounds(dispatches, args.gap_seconds)
    summaries = [round_summary(r) for r in rounds if len(r) >= args.min_agents]
    print(json.dumps({"rounds": summaries}, indent=2))
    return 0


def cmd_report(args) -> int:
    dispatches = _filter_since(collect_agent_dispatches(args.transcript), args.since)
    rounds = cluster_rounds(dispatches, args.gap_seconds)

    roster, roster_warnings = select_lenses.build_review_roster(
        args.agents_dir, args.registry
    )
    # Per-file theoretical estimate — a round's diff may span several files,
    # each with its own applicable-lens set (Scope: globs differ per file),
    # so this is computed independently per target rather than once. Roster
    # is built ONCE above and passed in, not rebuilt per file (a review
    # round on this script found the per-file rebuild to be an N+1 file-I/O
    # pattern — the registry and every agent file were being re-read once
    # per target file instead of once per invocation).
    per_file = {
        str(f): theoretical_full_file_agents(f, roster, args.agents_dir)
        for f in args.target_files
    }

    rows = [
        _round_report_row(r, per_file) for r in rounds if len(r) >= args.min_agents
    ]
    percentages = [
        row["avoidable_pct_of_round_total_estimate"]
        for row in rows
        if row["avoidable_pct_of_round_total_estimate"] is not None
        and max((f["n_full_file_agents_dispatched"] for f in row["files"]), default=0) >= 2
    ]

    print(
        json.dumps(
            {
                "target_files": list(per_file.keys()),
                "per_file_theoretical": {
                    f: {
                        "full_file_agents": agents,
                        "file_token_estimate": tokens,
                        "file_missing": file_missing,
                    }
                    for f, (agents, tokens, _warnings, file_missing) in per_file.items()
                },
                "roster_warnings": roster_warnings,
                "rounds": rows,
                "distribution": _percentile_distribution(percentages),
            },
            indent=2,
        )
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_theoretical = sub.add_parser(
        "theoretical", help="Theoretical full-file-agent count per file, no transcript needed"
    )
    p_theoretical.add_argument("--files", nargs="+", required=True)
    p_theoretical.add_argument(
        "--agents-dir", type=Path, default=_PLUGIN_ROOT / "agents"
    )
    p_theoretical.add_argument(
        "--registry", type=Path, default=_PLUGIN_ROOT / "knowledge" / "agent-registry.md"
    )
    p_theoretical.set_defaults(func=cmd_theoretical)

    p_rounds = sub.add_parser(
        "rounds", help="Detect same-round agent dispatches from a real transcript"
    )
    p_rounds.add_argument("--transcript", type=Path, required=True)
    p_rounds.add_argument("--gap-seconds", type=float, default=DEFAULT_ROUND_GAP_SECONDS)
    p_rounds.add_argument("--min-agents", type=int, default=DEFAULT_MIN_AGENTS)
    p_rounds.add_argument(
        "--since", default=None, help="ISO8601 timestamp; drop earlier dispatches"
    )
    p_rounds.set_defaults(func=cmd_rounds)

    p_report = sub.add_parser(
        "report",
        help="Combine the theoretical estimate with real round totals as a percentage",
    )
    p_report.add_argument("--transcript", type=Path, required=True)
    p_report.add_argument("--target-files", type=Path, nargs="+", required=True)
    p_report.add_argument("--gap-seconds", type=float, default=DEFAULT_ROUND_GAP_SECONDS)
    p_report.add_argument("--min-agents", type=int, default=DEFAULT_MIN_AGENTS)
    p_report.add_argument(
        "--since", default=None, help="ISO8601 timestamp; drop earlier dispatches"
    )
    p_report.add_argument(
        "--agents-dir", type=Path, default=_PLUGIN_ROOT / "agents"
    )
    p_report.add_argument(
        "--registry", type=Path, default=_PLUGIN_ROOT / "knowledge" / "agent-registry.md"
    )
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
