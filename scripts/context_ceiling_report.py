#!/usr/bin/env python3
"""Measure whether the context ceiling is set where it should be (#2056 follow-up).

ADR 0038 raised `DEV_TEAM_CONTEXT_ABS_CEILING` from 150K to 350K, and named
its own weakest link in the revisit trigger:

    The turn-count estimate above is the weakest link in this reasoning — it
    is an inference from a token ratio, not a recorded count. If per-session
    peak occupancy is ever instrumented directly, re-derive the threshold
    from the actual distribution.

This is that instrument. It replays real session transcripts, reconstructs the
occupancy the guard *would have measured* at every capability load, and sweeps
candidate ceilings to show what each one would have done. It answers "should
the ceiling move, and which way" from recorded data rather than from a ratio.

Why replay rather than sample occupancy
---------------------------------------
The ceiling only binds at a gated call — an `Agent`/`Task` dispatch or a
`Skill` invocation. A session can sit at 600K forever without the guard ever
firing, if it never loads a capability while up there. So "peak occupancy per
session" systematically OVERSTATES how often the ceiling bites, and any
threshold derived from occupancy alone is derived from the wrong distribution.
This tool conditions on gated calls, which is where the guard actually lives.

Narrower still since ADR 0039: of the gated tools, only `Skill` BLOCKS. An
`Agent`/`Task` dispatch warns but proceeds, because it runs in its own context
and blocking it would push the work inline and grow occupancy further. So the
sweep's block columns count Skill invocations only; agent dispatches are
reported separately as advisory fires. Counting them as blocks would overstate
every candidate's block rate and argue for a higher ceiling than the evidence
supports.

The two failure directions, and the metric for each
---------------------------------------------------
A ceiling can be wrong in two directions, and a single "block rate" number
cannot tell them apart. Each gets its own signal:

* **Too low** — it blocks sessions that were essentially finished. ADR 0037's
  revisit trigger names this case exactly ("blocked at 150K on work that would
  have finished in another two turns"). Signal: `near_done_blocked_pct`, the
  share of blocked sessions whose first block landed within
  `--near-done-turns` assistant turns of the end.
* **Too high** — it lets the expensive tail run. This is the case that
  justified #2000 in the first place. Signal: `prompt_tokens_after_first_block`
  as a share of the corpus total: the tokens spent while over the ceiling,
  which is what enforcement would have cut into.

A good ceiling drives the first toward zero without letting the second grow.
Neither number is a verdict on its own; the report prints both per candidate
and leaves the trade-off visible rather than collapsing it into a score.

Anti-drift
----------
Every policy decision — which tools are gated, which skills are exempt, how a
model maps to a window, how occupancy is summed, what counts as a sidechain
row — is IMPORTED from `plugins/dev-team/hooks/context_ceiling_guard.py`
rather than restated here. A validator that measured the ceiling slightly
differently from the guard would validate a threshold nobody ships.
`tests/scripts/test_context_ceiling_report.py` additionally pins this module's
occupancy walk against the hook's own `_measure_occupancy` on shared fixtures,
so the two cannot diverge silently.

Usage
-----
    # default corpus: ~/.claude/projects/**/*.jsonl
    python3 scripts/context_ceiling_report.py

    # explicit paths, custom sweep, machine-readable output
    python3 scripts/context_ceiling_report.py \
        --transcripts ~/.claude/projects \
        --ceilings 150000,250000,350000,450000 \
        --json /tmp/ceiling-report.json

Stdlib-only. Repo-root dev tooling — not shipped with the plugin.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

# The guard is the source of truth for every policy constant below. See the
# "Anti-drift" note in the module docstring.
from datetime import UTC

import context_ceiling_guard as guard  # type: ignore[import-not-found]

#: Candidate ceilings swept when `--ceilings` is not given. Brackets the
#: shipped 350K default on both sides so the report can argue for moving it in
#: either direction rather than only confirming it.
DEFAULT_CEILINGS = (150_000, 200_000, 250_000, 300_000, 350_000, 450_000, 600_000)

#: An assistant turn count at or below which a blocked session counts as
#: "near done" — the over-blocking signal. Deliberately generous: the argument
#: against a ceiling is strongest when it stopped work that was visibly
#: finishing, and a loose threshold makes that case harder to overstate.
DEFAULT_NEAR_DONE_TURNS = 5


def _occupancy_of(usage: dict) -> int | None:
    """Prompt-side token total for one usage block, or None if unusable.

    Mirrors the guard's own summation (input + cache_read + cache_creation)
    including its non-integer rejection. Kept as a function rather than
    inlined so the equality test has something to pin.
    """
    if not isinstance(usage, dict):
        return None
    input_t = usage.get("input_tokens") or 0
    cache_read = usage.get("cache_read_input_tokens") or 0
    cache_creation = usage.get("cache_creation_input_tokens") or 0
    if not all(isinstance(x, int) for x in (input_t, cache_read, cache_creation)):
        return None
    total = int(input_t) + int(cache_read) + int(cache_creation)
    return total if total > 0 else None


def _gated_calls_in(record: dict) -> list[tuple[str, str]]:
    """Every gated capability load in one record, as (tool, label, blocks).

    Recovery skills are dropped here rather than counted and filtered later:
    they are never gated at any occupancy, so counting them would inflate
    every block rate in the sweep.
    """
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    calls: list[tuple[str, str, bool]] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name")
        if name not in guard._GATED_TOOLS:
            continue
        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        if name == "Skill":
            skill = guard._extract_skill_name(tool_input)
            if skill in guard._RECOVERY_SKILLS:
                continue
            calls.append((name, skill or "?", name in guard._BLOCKING_TOOLS))
        else:
            agent = tool_input.get("subagent_type")
            calls.append(
                (
                    name,
                    agent if isinstance(agent, str) and agent else "?",
                    name in guard._BLOCKING_TOOLS,
                )
            )
    return calls


@dataclass
class GateEvent:
    """One capability load, with the occupancy the guard would have seen."""

    occupancy: int
    tool: str
    label: str
    turn_index: int
    #: Whether the guard would BLOCK this call over the ceiling, as opposed
    #: to warning and proceeding. Derived from `guard._BLOCKING_TOOLS` rather
    #: than restated, so the split cannot drift from the shipped policy.
    blocks: bool


@dataclass
class SessionReplay:
    """One transcript, replayed."""

    path: Path
    window: int
    window_matched: bool
    peak_occupancy: int = 0
    final_occupancy: int = 0
    assistant_turns: int = 0
    prompt_tokens_total: int = 0
    #: Prompt tokens per assistant turn, in order — used to compute how much
    #: was spent after a candidate ceiling's first block.
    turn_prompt_tokens: list[int] = field(default_factory=list)
    gates: list[GateEvent] = field(default_factory=list)

    @property
    def session_id(self) -> str:
        return self.path.stem


def replay_transcript(path: Path) -> SessionReplay | None:
    """Reconstruct occupancy over one transcript. None if it carries no usage.

    Sidechain rows are skipped exactly as the guard skips them: a subagent
    turn's usage describes the subagent's context, not the main thread's
    (see `guard._is_sidechain`).
    """
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    last_model: str | None = None
    current_occupancy = 0
    replay: SessionReplay | None = None
    records: list[tuple[int, dict]] = []

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(record, dict) or guard._is_sidechain(record):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        model = message.get("model")
        if isinstance(model, str) and model:
            last_model = model
        occupancy = _occupancy_of(message.get("usage"))
        if occupancy is not None:
            current_occupancy = occupancy
        records.append((current_occupancy, record))

    if not records or all(occ == 0 for occ, _ in records):
        return None

    window = guard._window_for_model(last_model or "")
    matched = bool(
        last_model
        and (guard._HAIKU_RE.search(last_model) or guard._LARGE_WINDOW_RE.search(last_model))
    )
    replay = SessionReplay(path=path, window=window, window_matched=matched)

    for occupancy, record in records:
        usage_occ = _occupancy_of(
            record.get("message", {}).get("usage")  # type: ignore[union-attr]
        )
        if usage_occ is not None:
            replay.assistant_turns += 1
            replay.prompt_tokens_total += usage_occ
            replay.turn_prompt_tokens.append(usage_occ)
            replay.peak_occupancy = max(replay.peak_occupancy, usage_occ)
            replay.final_occupancy = usage_occ
        for tool, label, blocks in _gated_calls_in(record):
            replay.gates.append(
                GateEvent(
                    occupancy=occupancy,
                    tool=tool,
                    label=label,
                    turn_index=max(0, replay.assistant_turns - 1),
                    blocks=blocks,
                )
            )
    return replay


def effective_threshold(window: int, ceiling_pct: int, abs_ceiling: int) -> int:
    """`min(pct% of window, abs_ceiling)` — the guard's own formula."""
    return min((ceiling_pct * window) // 100, abs_ceiling)


def evaluate_ceiling(
    replays: list[SessionReplay],
    abs_ceiling: int,
    ceiling_pct: int,
    near_done_turns: int,
) -> dict:
    """What one candidate ceiling would have done to this corpus."""
    blocked_sessions = 0
    near_done_blocked = 0
    first_block_occupancies: list[int] = []
    remaining_turns_at_block: list[int] = []
    tokens_after_first_block = 0
    total_blocks = 0
    clamped_sessions = 0
    advisory_fires = 0

    for replay in replays:
        threshold = effective_threshold(replay.window, ceiling_pct, abs_ceiling)
        # The candidate never took effect here: `ceiling_pct` of this window is
        # lower, so raising the absolute cap changed nothing. Tracked because a
        # sweep row that silently equals its neighbour is worse than no row —
        # it reads as "the ceiling made no difference" when the truth is "this
        # candidate was never applied".
        if threshold < abs_ceiling:
            clamped_sessions += 1
        over = [g for g in replay.gates if g.occupancy >= threshold]
        # ADR 0039: an Agent/Task dispatch over the ceiling warns and
        # proceeds. Counting it as a block would overstate every candidate's
        # block rate and argue for a higher ceiling than the evidence
        # supports.
        advisory_fires += sum(1 for g in over if not g.blocks)
        over = [g for g in over if g.blocks]
        total_blocks += len(over)
        if not over:
            continue
        blocked_sessions += 1
        first = over[0]
        first_block_occupancies.append(first.occupancy)
        remaining_turns = replay.assistant_turns - 1 - first.turn_index
        remaining_turns_at_block.append(remaining_turns)
        if remaining_turns <= near_done_turns:
            near_done_blocked += 1
        tokens_after_first_block += sum(replay.turn_prompt_tokens[first.turn_index + 1 :])

    # Denominator is sessions that could have been blocked at all — one with
    # only agent dispatches never can be, and including it would dilute every
    # block rate toward zero.
    sessions_with_gates = sum(1 for r in replays if any(g.blocks for g in r.gates))
    corpus_prompt_tokens = sum(r.prompt_tokens_total for r in replays)
    return {
        "abs_ceiling": abs_ceiling,
        "advisory_fires": advisory_fires,
        "clamped_sessions": clamped_sessions,
        "clamped_pct": _pct(clamped_sessions, len(replays)),
        "sessions_blocked": blocked_sessions,
        "sessions_blocked_pct": _pct(blocked_sessions, sessions_with_gates),
        "blocks_total": total_blocks,
        "median_occupancy_at_first_block": (
            int(statistics.median(first_block_occupancies))
            if first_block_occupancies
            else None
        ),
        "near_done_blocked": near_done_blocked,
        "near_done_blocked_pct": _pct(near_done_blocked, blocked_sessions),
        # `near_done_blocked_pct` is a THRESHOLD on this distribution, and the
        # first real corpus showed the threshold alone cannot adjudicate a
        # ceiling: it sat at 0-6% across every candidate from 150K to 600K,
        # which reads as "no candidate over-blocks" and would argue for
        # lowering the ceiling without limit. It only ever detected one
        # failure shape — blocked AT the finish line. A session blocked at 20%
        # done is not near-done, yet blocking it still costs a handoff and the
        # re-establishment of everything it had loaded. The median says how
        # much work was actually left, which is the quantity the threshold was
        # standing in for.
        "median_remaining_turns_at_first_block": (
            int(statistics.median(remaining_turns_at_block))
            if remaining_turns_at_block
            else None
        ),
        "prompt_tokens_after_first_block": tokens_after_first_block,
        "prompt_tokens_after_first_block_pct": _pct(
            tokens_after_first_block, corpus_prompt_tokens
        ),
    }


def _pct(numerator: int, denominator: int) -> float | None:
    """Percentage, or None when the denominator is zero.

    None rather than 0.0 deliberately: "no sessions to divide by" and "0% of
    sessions" are different findings, and rendering the first as the second
    would read as evidence the ceiling is fine.
    """
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def trend_record(replays: list[SessionReplay], sweep: list[dict], args) -> dict:
    """A compact, AGGREGATE-COUNTS-ONLY record for the ceiling trend stream.

    Mirrors `scripts/session_extract.py`'s `slim_record` convention (#129):
    the trend stream carries metrics only — no transcript paths, no session
    ids, no prompt or code content — because it is the artifact that
    accumulates across rounds and outlives any single review. `recorded_at`
    is the only wall-clock field and lives on the trend log, never in the
    deterministic report output, so two runs over the same corpus produce
    identical reports.
    """
    from datetime import datetime

    peaks = sorted(r.peak_occupancy for r in replays)

    def _pctile(fraction: float) -> int | None:
        if not peaks:
            return None
        return peaks[min(len(peaks) - 1, int(len(peaks) * fraction))]

    return {
        "schema": "context-ceiling-trend/v1",
        # `%Y-%m-%dT%H:%M:%SZ`, matching `session_extract.py` and the rest of
        # the repo's metrics streams — the playbook reads both streams'
        # timestamps side by side, so two spellings of UTC would be a
        # gratuitous difference at exactly the point of comparison.
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ceiling_pct": args.ceiling_pct,
        "shipped_ceiling": args.shipped,
        "near_done_turns": args.near_done_turns,
        "sessions": len(replays),
        "sessions_with_blockable_calls": sum(
            1 for r in replays if any(g.blocks for g in r.gates)
        ),
        "gated_calls": sum(len(r.gates) for r in replays),
        "blocking_calls": sum(1 for r in replays for g in r.gates if g.blocks),
        "unrecognized_model_sessions": sum(1 for r in replays if not r.window_matched),
        "peak_occupancy": {
            "p50": _pctile(0.5),
            "p90": _pctile(0.9),
            "max": peaks[-1] if peaks else None,
        },
        "sweep": [
            {
                k: row[k]
                for k in (
                    "abs_ceiling",
                    # Without the clamp the persisted stream cannot explain why
                    # two rows are identical — the first real corpus produced a
                    # 450K row and a 600K row with every field equal, because
                    # both clamp to 40% of a 1M window. The terminal report
                    # marks that with a dagger; the trend record was dropping
                    # the only field that carries it.
                    "clamped_sessions",
                    "sessions_blocked",
                    "sessions_blocked_pct",
                    "blocks_total",
                    "advisory_fires",
                    "median_occupancy_at_first_block",
                    "near_done_blocked_pct",
                    "median_remaining_turns_at_first_block",
                    "prompt_tokens_after_first_block_pct",
                )
            }
            for row in sweep
        ],
    }


def append_trend(path: Path, record: dict) -> None:
    """Append one record to the append-only trend stream, creating it if new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def discover_transcripts(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".jsonl":
            found.append(root)
        elif root.is_dir():
            found.extend(sorted(root.rglob("*.jsonl")))
    return found


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:g}%"
    return f"{value:,}"


def render_report(replays: list[SessionReplay], sweep: list[dict], args) -> str:
    lines: list[str] = []
    sessions_with_gates = sum(
        1 for r in replays if any(g.blocks for g in r.gates)
    )
    total_gates = sum(len(r.gates) for r in replays)
    blocking_gates = sum(1 for r in replays for g in r.gates if g.blocks)
    peaks = sorted(r.peak_occupancy for r in replays)

    lines.append("Context ceiling validation")
    lines.append("=" * 74)
    lines.append(f"transcripts replayed      : {len(replays):,}")
    lines.append(f"  with >=1 blockable call : {sessions_with_gates:,}")
    lines.append(f"  gated calls total       : {total_gates:,}")
    lines.append(
        f"    of which blockable    : {blocking_gates:,} "
        f"(Skill; ADR 0039 — Agent/Task warns, never blocks)"
    )
    lines.append(f"  unrecognized model      : {sum(1 for r in replays if not r.window_matched):,}")
    if peaks:
        lines.append("")
        lines.append("Peak main-thread occupancy per session:")
        for label, value in (
            ("min", peaks[0]),
            ("p50", int(statistics.median(peaks))),
            ("p90", peaks[min(len(peaks) - 1, int(len(peaks) * 0.9))]),
            ("max", peaks[-1]),
        ):
            lines.append(f"  {label:>5} : {value:>12,}")
        lines.append(
            "  (occupancy alone is NOT the block rate — the ceiling only binds"
        )
        lines.append("   at a gated call; see the sweep below.)")

    lines.append("")
    lines.append(
        f"Candidate ceilings (ceiling_pct={args.ceiling_pct}, "
        f"near-done <= {args.near_done_turns} turns remaining):"
    )
    header = (
        f"{'ceiling':>9} | {'sessions':>9} | {'blocked':>8} | {'blocks':>7} | "
        f"{'median@1st':>11} | {'near-done':>10} | {'turns left':>10} | "
        f"{'tokens over':>12}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    any_clamped = False
    for row in sweep:
        marker = " *" if row["abs_ceiling"] == args.shipped else "  "
        if row["clamped_sessions"]:
            any_clamped = True
            marker = marker.rstrip() + "†"
        lines.append(
            f"{row['abs_ceiling']:>9,} | "
            f"{_fmt(row['sessions_blocked']):>9} | "
            f"{_fmt(row['sessions_blocked_pct']):>8} | "
            f"{_fmt(row['blocks_total']):>7} | "
            f"{_fmt(row['median_occupancy_at_first_block']):>11} | "
            f"{_fmt(row['near_done_blocked_pct']):>10} | "
            f"{_fmt(row['median_remaining_turns_at_first_block']):>10} | "
            f"{_fmt(row['prompt_tokens_after_first_block_pct']):>12}{marker}"
        )
    lines.append("")
    lines.append("  * = the shipped default")
    if any_clamped:
        lines.append(
            "  † = clamped for at least one session: ceiling_pct of that window is"
        )
        lines.append(
            f"      lower than the candidate, so raising the cap past "
            f"{args.ceiling_pct}% of the window"
        )
        lines.append(
            "      changes nothing there. To test a higher ceiling on those sessions,"
        )
        lines.append("      raise --ceiling-pct as well.")
    lines.append("  blocked     : share of blockable sessions the ceiling would stop")
    lines.append("                (Skill invocations only — agent dispatches warn)")
    lines.append("  near-done   : share of BLOCKED sessions that were nearly finished")
    lines.append("                — one over-blocking shape, not the only one")
    lines.append("  turns left  : median assistant turns still to come when the block")
    lines.append("                landed — how much work a block actually interrupts.")
    lines.append("                Read WITH near-done: a near-done of 0 next to a large")
    lines.append("                turns-left means blocks land mid-flight, not at the end")
    lines.append("  tokens over : share of corpus prompt tokens spent past the first")
    lines.append("                block — the under-blocking signal; what enforcement")
    lines.append("                would have cut into")
    lines.append("")
    lines.append(_verdict(sweep, args))
    return "\n".join(lines)


def _verdict(sweep: list[dict], args) -> str:
    """State what the numbers support, or say the corpus is too thin.

    This deliberately does not pick a number: it reports which direction the
    two signals point and leaves the decision to a human, because the cost of
    a wrong ceiling is asymmetric in a way no single statistic captures.
    """
    shipped = next((r for r in sweep if r["abs_ceiling"] == args.shipped), None)
    if shipped is None:
        return "No shipped-default row in the sweep; nothing to compare against."
    if shipped["sessions_blocked"] == 0:
        return (
            f"VERDICT: inconclusive at {args.shipped:,}. No session in this corpus "
            "reached the ceiling at a gated call, so the data neither supports nor\n"
            "         challenges the current value. Re-run against a larger corpus "
            "(more projects, or a longer window of sessions)."
        )
    parts = [f"VERDICT at the shipped {args.shipped:,}:"]
    near_done = shipped["near_done_blocked_pct"]
    tokens_over = shipped["prompt_tokens_after_first_block_pct"]
    if near_done is not None and near_done >= 50:
        parts.append(
            f"  - OVER-BLOCKING: {near_done:g}% of blocked sessions were near done. "
            "ADR 0037's revisit\n    trigger names this case; the response is to raise "
            "the ceiling, not to warn."
        )
    elif near_done is not None:
        parts.append(
            f"  - {near_done:g}% of blocked sessions were near done — not the dominant case."
        )
    if tokens_over is not None:
        parts.append(
            f"  - {tokens_over:g}% of corpus prompt tokens were spent past the first block "
            "— what\n    enforcement reclaims."
        )
    parts.append(
        "  Compare the rows above: a better ceiling lowers near-done without letting\n"
        "  tokens-over climb. Both columns must be read together."
    )
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the context ceiling against recorded session transcripts.",
    )
    parser.add_argument(
        "--transcripts",
        nargs="*",
        type=Path,
        default=[Path.home() / ".claude" / "projects"],
        help="transcript files or directories (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--ceilings",
        type=str,
        default=",".join(str(c) for c in DEFAULT_CEILINGS),
        help="comma-separated candidate absolute ceilings to sweep",
    )
    parser.add_argument(
        "--ceiling-pct",
        type=int,
        default=40,
        help="percentage-of-window bound, matching DEV_TEAM_CONTEXT_CEILING_PCT",
    )
    parser.add_argument(
        "--near-done-turns",
        type=int,
        default=DEFAULT_NEAR_DONE_TURNS,
        help="assistant turns remaining at/below which a blocked session is 'near done'",
    )
    parser.add_argument(
        "--shipped",
        type=int,
        default=350_000,
        help="the shipped default, marked and summarized in the report",
    )
    parser.add_argument("--json", type=Path, help="also write the full result as JSON")
    parser.add_argument(
        "--append",
        type=Path,
        metavar="LOG",
        help="append one metrics-only summary record to a trend stream "
        "(append-only JSONL), so successive rounds are comparable",
    )
    args = parser.parse_args(argv)

    try:
        ceilings = sorted({int(c) for c in args.ceilings.split(",") if c.strip()})
    except ValueError:
        print(f"error: --ceilings must be comma-separated integers: {args.ceilings}", file=sys.stderr)
        return 2
    if not ceilings:
        print("error: --ceilings resolved to an empty sweep", file=sys.stderr)
        return 2

    paths = discover_transcripts(list(args.transcripts))
    if not paths:
        print(
            f"error: no .jsonl transcripts found under {[str(p) for p in args.transcripts]}",
            file=sys.stderr,
        )
        return 2

    replays = [r for r in (replay_transcript(p) for p in paths) if r is not None]
    if not replays:
        print(
            f"error: {len(paths)} transcript(s) found, none carrying usable usage data",
            file=sys.stderr,
        )
        return 2

    sweep = [
        evaluate_ceiling(replays, c, args.ceiling_pct, args.near_done_turns)
        for c in ceilings
    ]
    print(render_report(replays, sweep, args))

    if args.json:
        payload = {
            "schema": "context-ceiling-report/v1",
            "ceiling_pct": args.ceiling_pct,
            "near_done_turns": args.near_done_turns,
            "sessions": [
                {
                    "session_id": r.session_id,
                    "path": str(r.path),
                    "window": r.window,
                    "window_matched": r.window_matched,
                    "peak_occupancy": r.peak_occupancy,
                    "final_occupancy": r.final_occupancy,
                    "assistant_turns": r.assistant_turns,
                    "prompt_tokens_total": r.prompt_tokens_total,
                    "gated_calls": len(r.gates),
                }
                for r in replays
            ],
            "sweep": sweep,
        }
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")

    if args.append:
        append_trend(args.append, trend_record(replays, sweep, args))
        print(f"appended a trend record to {args.append}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
