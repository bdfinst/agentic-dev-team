"""Tests for scripts/context_ceiling_report.py — the context-ceiling validator.

The load-bearing test in this file is `test_final_occupancy_equals_the_guards_
own_measurement`: a validator that measured occupancy even slightly differently
from `hooks/context_ceiling_guard.py` would be validating a threshold nobody
ships. That test pins the two together on shared fixtures, in the same spirit
as the hook suite's utilization-formula equality test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

_SCRIPTS = REPO_ROOT / "scripts"
_HOOKS = REPO_ROOT / "plugins" / "dev-team" / "hooks"
for _p in (_SCRIPTS, _HOOKS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import context_ceiling_guard as guard  # type: ignore[import-not-found]
import context_ceiling_report as report  # type: ignore[import-not-found]

_SCRIPT = _SCRIPTS / "context_ceiling_report.py"


# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------


def _assistant(
    occupancy: int,
    *,
    model: str = "claude-opus-5",
    sidechain: bool = False,
    tool_uses: list[dict] | None = None,
) -> dict:
    content: list[dict] = [{"type": "text", "text": "..."}]
    for tu in tool_uses or []:
        content.append({"type": "tool_use", **tu})
    return {
        "isSidechain": sidechain,
        "message": {
            "model": model,
            "content": content,
            "usage": {
                "input_tokens": 2,
                "cache_read_input_tokens": occupancy - 2,
                "cache_creation_input_tokens": 0,
            },
        },
    }


def _skill(name: str) -> dict:
    return {"name": "Skill", "input": {"skill": name}}


def _agent(name: str) -> dict:
    return {"name": "Agent", "input": {"subagent_type": name}}


def _write(path: Path, *records: dict) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# anti-drift: the validator must measure what the guard measures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "records",
    [
        pytest.param([_assistant(120_000)], id="single-turn"),
        pytest.param([_assistant(50_000), _assistant(400_000)], id="rising"),
        pytest.param([_assistant(400_000), _assistant(50_000)], id="falling-after-compact"),
        pytest.param(
            [_assistant(400_000), _assistant(9_000, sidechain=True)],
            id="trailing-sidechain",
        ),
        pytest.param(
            [_assistant(80_000), {"message": {"model": "claude-opus-5"}}],
            id="trailing-row-without-usage",
        ),
    ],
)
def test_final_occupancy_equals_the_guards_own_measurement(
    tmp_path: Path, records: list[dict]
) -> None:
    """The validator and the guard must agree on occupancy, byte for byte.

    If these ever diverge, the sweep is measuring a quantity the shipped guard
    does not enforce on, and every threshold recommendation drawn from it is
    unsound. Fixtures stay under the guard's 400-line tail window so the two
    read the same rows.
    """
    tr = _write(tmp_path / "t.jsonl", *records)
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert replay.final_occupancy == guard._measure_occupancy(tr)


def test_effective_threshold_matches_the_guards_min_formula() -> None:
    """`min(pct% of window, abs)` — restated here only to be pinned."""
    assert report.effective_threshold(1_000_000, 40, 350_000) == 350_000
    assert report.effective_threshold(200_000, 40, 350_000) == 80_000
    assert report.effective_threshold(1_000_000, 40, 500_000) == 400_000


def test_window_resolution_defers_to_the_guards_model_map(tmp_path: Path) -> None:
    known = report.replay_transcript(
        _write(tmp_path / "a.jsonl", _assistant(10_000, model="claude-opus-5"))
    )
    unknown = report.replay_transcript(
        _write(tmp_path / "b.jsonl", _assistant(10_000, model="totally-unknown"))
    )
    assert known is not None and unknown is not None
    assert (known.window, known.window_matched) == (1_000_000, True)
    assert (unknown.window, unknown.window_matched) == (200_000, False)


# ---------------------------------------------------------------------------
# gate detection
# ---------------------------------------------------------------------------


def test_sidechain_turns_are_excluded_from_occupancy_and_gates(tmp_path: Path) -> None:
    tr = _write(
        tmp_path / "t.jsonl",
        _assistant(100_000, tool_uses=[_skill("build")]),
        _assistant(900_000, sidechain=True, tool_uses=[_agent("test-review")]),
    )
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert replay.peak_occupancy == 100_000
    assert len(replay.gates) == 1, "a subagent's own gated call is not a main-thread gate"


def test_recovery_skills_are_not_counted_as_gates(tmp_path: Path) -> None:
    """They are never gated at any occupancy, so counting them would inflate
    every block rate in the sweep."""
    tr = _write(
        tmp_path / "t.jsonl",
        _assistant(900_000, tool_uses=[_skill(s) for s in sorted(guard._RECOVERY_SKILLS)]),
    )
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert replay.gates == []


def test_plugin_qualified_recovery_skill_is_also_excluded(tmp_path: Path) -> None:
    tr = _write(tmp_path / "t.jsonl", _assistant(900_000, tool_uses=[_skill("dev-team:handoff")]))
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert replay.gates == []


@pytest.mark.parametrize("tool", ["Agent", "Task", "Skill"])
def test_every_gated_tool_the_guard_knows_is_detected(tmp_path: Path, tool: str) -> None:
    tu = {"name": tool, "input": {"skill": "build"} if tool == "Skill" else {"subagent_type": "x"}}
    replay = report.replay_transcript(
        _write(tmp_path / "t.jsonl", _assistant(500_000, tool_uses=[tu]))
    )
    assert replay is not None
    assert [g.tool for g in replay.gates] == [tool]


def test_ungated_tools_are_ignored(tmp_path: Path) -> None:
    tr = _write(
        tmp_path / "t.jsonl",
        _assistant(900_000, tool_uses=[{"name": "Bash", "input": {"command": "ls"}}]),
    )
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert replay.gates == []


def test_gate_sees_the_occupancy_of_its_own_turn(tmp_path: Path) -> None:
    """The assistant record carrying the tool_use also carries the usage the
    guard reads at PreToolUse time — not the previous turn's."""
    tr = _write(
        tmp_path / "t.jsonl",
        _assistant(100_000),
        _assistant(400_000, tool_uses=[_skill("build")]),
    )
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert [g.occupancy for g in replay.gates] == [400_000]


def test_parallel_dispatch_records_one_gate_per_call(tmp_path: Path) -> None:
    tr = _write(
        tmp_path / "t.jsonl",
        _assistant(400_000, tool_uses=[_agent("a"), _agent("b"), _agent("c")]),
    )
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert len(replay.gates) == 3
    assert {g.occupancy for g in replay.gates} == {400_000}


# ---------------------------------------------------------------------------
# the sweep
# ---------------------------------------------------------------------------


def _one_session(tmp_path: Path, *records: dict) -> list:
    replay = report.replay_transcript(_write(tmp_path / "t.jsonl", *records))
    assert replay is not None
    return [replay]


def test_a_ceiling_below_the_gate_blocks_and_one_above_does_not(tmp_path: Path) -> None:
    """The central counterfactual: the same session, two candidate ceilings."""
    replays = _one_session(tmp_path, _assistant(250_000, tool_uses=[_skill("build")]))
    low = report.evaluate_ceiling(replays, 150_000, 40, 5)
    high = report.evaluate_ceiling(replays, 350_000, 40, 5)
    assert low["sessions_blocked"] == 1
    assert low["median_occupancy_at_first_block"] == 250_000
    assert high["sessions_blocked"] == 0


def test_near_done_flags_a_session_blocked_at_the_finish_line(tmp_path: Path) -> None:
    """ADR 0037's revisit trigger in a metric: blocked with almost no work
    left is the signature of a ceiling set too low."""
    replays = _one_session(
        tmp_path,
        _assistant(400_000, tool_uses=[_skill("build")]),
        _assistant(410_000),
    )
    result = report.evaluate_ceiling(replays, 350_000, 40, near_done_turns=5)
    assert result["near_done_blocked"] == 1
    assert result["near_done_blocked_pct"] == 100.0


def test_a_session_with_a_long_tail_after_the_block_is_not_near_done(
    tmp_path: Path,
) -> None:
    records = [_assistant(400_000, tool_uses=[_skill("build")])]
    records += [_assistant(410_000) for _ in range(20)]
    replays = _one_session(tmp_path, *records)
    result = report.evaluate_ceiling(replays, 350_000, 40, near_done_turns=5)
    assert result["sessions_blocked"] == 1
    assert result["near_done_blocked"] == 0


def test_tokens_after_the_first_block_are_what_enforcement_reclaims(
    tmp_path: Path,
) -> None:
    replays = _one_session(
        tmp_path,
        _assistant(300_000, tool_uses=[_skill("build")]),
        _assistant(500_000),
        _assistant(600_000),
    )
    # Blocked at the first gate; everything spent afterwards is what a ceiling
    # here would have reclaimed.
    result = report.evaluate_ceiling(replays, 250_000, 40, 0)
    assert result["sessions_blocked"] == 1
    assert result["prompt_tokens_after_first_block"] == 1_100_000

    # Nothing is over a ceiling nothing reaches, so nothing is reclaimed.
    none_blocked = report.evaluate_ceiling(replays, 350_000, 40, 0)
    assert none_blocked["sessions_blocked"] == 0
    assert none_blocked["prompt_tokens_after_first_block"] == 0


def test_a_candidate_above_the_percentage_bound_is_reported_as_clamped(
    tmp_path: Path,
) -> None:
    """Raising the absolute cap past `ceiling_pct` of the window does nothing:
    `min()` picks the percentage. A sweep row that silently equals its
    neighbour reads as "the ceiling made no difference" when the truth is
    "this candidate was never applied" — so the clamp is reported."""
    replays = _one_session(
        tmp_path, _assistant(400_000, tool_uses=[_skill("build")])
    )
    # 40% of a 1M window is 400K, so a 900K candidate is clamped to 400K and
    # the gate at exactly 400K still blocks.
    clamped = report.evaluate_ceiling(replays, 900_000, 40, 0)
    assert clamped["clamped_sessions"] == 1
    assert clamped["clamped_pct"] == 100.0
    assert clamped["sessions_blocked"] == 1, (
        "the percentage bound still applies; the candidate never took effect"
    )

    # Lifting ceiling_pct too is what actually raises the ceiling here.
    unclamped = report.evaluate_ceiling(replays, 900_000, 90, 0)
    assert unclamped["clamped_sessions"] == 0
    assert unclamped["sessions_blocked"] == 0


def test_a_candidate_under_the_percentage_bound_is_not_clamped(
    tmp_path: Path,
) -> None:
    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("build")]))
    assert report.evaluate_ceiling(replays, 350_000, 40, 0)["clamped_sessions"] == 0


def test_a_200k_window_session_is_bound_by_the_percentage_not_the_cap(
    tmp_path: Path,
) -> None:
    """On a small window the absolute cap is a no-op — the sweep must reflect
    that, or it would report 200K-window sessions as never blocked."""
    replays = _one_session(
        tmp_path,
        _assistant(90_000, model="claude-haiku-4-5", tool_uses=[_skill("build")]),
    )
    for candidate in (150_000, 350_000, 600_000):
        result = report.evaluate_ceiling(replays, candidate, 40, 5)
        assert result["sessions_blocked"] == 1, (
            f"90K on a 200K window is over the 80K percentage bound "
            f"regardless of a {candidate} absolute cap"
        )


def test_occupancy_without_a_gated_call_never_blocks(tmp_path: Path) -> None:
    """The finding that motivates conditioning on gated calls: a session can
    sit far over any candidate ceiling and never trip it."""
    replays = _one_session(tmp_path, _assistant(900_000), _assistant(950_000))
    result = report.evaluate_ceiling(replays, 150_000, 40, 5)
    assert replays[0].peak_occupancy == 950_000
    assert result["sessions_blocked"] == 0
    assert result["sessions_blocked_pct"] is None


def test_percentages_are_none_not_zero_when_there_is_nothing_to_divide_by() -> None:
    """"No sessions to divide by" and "0% of sessions" are different findings;
    rendering the first as the second would read as evidence the ceiling is
    fine."""
    assert report._pct(0, 0) is None
    assert report._pct(0, 10) == 0.0


# ---------------------------------------------------------------------------
# robustness + CLI
# ---------------------------------------------------------------------------


def test_malformed_and_empty_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    tr = tmp_path / "t.jsonl"
    tr.write_text(
        "\n".join(
            [
                "",
                "not json at all",
                "[1, 2, 3]",
                json.dumps({"message": "not-a-dict"}),
                json.dumps(_assistant(120_000)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    replay = report.replay_transcript(tr)
    assert replay is not None
    assert replay.final_occupancy == 120_000


def test_a_transcript_with_no_usage_is_dropped(tmp_path: Path) -> None:
    tr = _write(tmp_path / "t.jsonl", {"message": {"model": "claude-opus-5"}})
    assert report.replay_transcript(tr) is None


def test_an_unreadable_transcript_is_dropped_not_raised(tmp_path: Path) -> None:
    assert report.replay_transcript(tmp_path / "absent.jsonl") is None


def test_discover_transcripts_accepts_files_and_directories(tmp_path: Path) -> None:
    nested = tmp_path / "proj" / "sub"
    nested.mkdir(parents=True)
    a = _write(nested / "a.jsonl", _assistant(1_000))
    b = _write(tmp_path / "b.jsonl", _assistant(1_000))
    (tmp_path / "ignored.txt").write_text("x", encoding="utf-8")
    assert set(report.discover_transcripts([tmp_path])) == {a, b}
    assert report.discover_transcripts([a]) == [a]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_cli_exits_2_when_no_transcripts_are_found(tmp_path: Path) -> None:
    result = _run_cli("--transcripts", str(tmp_path / "nope"))
    assert result.returncode == 2
    assert "no .jsonl transcripts found" in result.stderr


def test_cli_exits_2_on_a_malformed_ceiling_list(tmp_path: Path) -> None:
    _write(tmp_path / "t.jsonl", _assistant(120_000))
    result = _run_cli("--transcripts", str(tmp_path), "--ceilings", "abc")
    assert result.returncode == 2
    assert "comma-separated integers" in result.stderr


def test_cli_reports_and_writes_json(tmp_path: Path) -> None:
    _write(
        tmp_path / "t.jsonl",
        _assistant(250_000, tool_uses=[_skill("build")]),
        _assistant(260_000),
    )
    out = tmp_path / "report.json"
    result = _run_cli(
        "--transcripts", str(tmp_path), "--ceilings", "150000,350000", "--json", str(out)
    )
    assert result.returncode == 0, result.stderr
    assert "Context ceiling validation" in result.stdout

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "context-ceiling-report/v1"
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["peak_occupancy"] == 260_000
    by_ceiling = {row["abs_ceiling"]: row for row in payload["sweep"]}
    assert by_ceiling[150_000]["sessions_blocked"] == 1
    assert by_ceiling[350_000]["sessions_blocked"] == 0


def test_the_verdict_says_inconclusive_rather_than_endorsing_the_default(
    tmp_path: Path,
) -> None:
    """An empty corpus must never read as confirmation. A validator that
    reported "0 blocked, looks fine" on data containing no evidence would be
    exactly the gate-that-cannot-fail this repo warns about."""
    _write(tmp_path / "t.jsonl", _assistant(120_000))
    result = _run_cli("--transcripts", str(tmp_path))
    assert result.returncode == 0
    assert "inconclusive" in result.stdout


# ---------------------------------------------------------------------------
# ADR 0039 — the sweep counts blocks, and only Skill blocks
# ---------------------------------------------------------------------------


def test_an_agent_dispatch_over_the_ceiling_is_not_counted_as_a_block(
    tmp_path: Path,
) -> None:
    """The deliberate-failure case for the report side. Counting agent
    dispatches as blocks would overstate every candidate's block rate and
    argue for a higher ceiling than the evidence supports."""
    replays = _one_session(
        tmp_path, _assistant(400_000, tool_uses=[_agent("test-review")])
    )
    result = report.evaluate_ceiling(replays, 350_000, 40, 5)
    assert result["sessions_blocked"] == 0
    assert result["blocks_total"] == 0
    assert result["advisory_fires"] == 1, (
        "the dispatch still fired the guard — it warned, and the report must "
        "say so rather than dropping it silently"
    )


def test_a_skill_invocation_over_the_ceiling_is_counted_as_a_block(
    tmp_path: Path,
) -> None:
    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("build")]))
    result = report.evaluate_ceiling(replays, 350_000, 40, 5)
    assert result["sessions_blocked"] == 1
    assert result["blocks_total"] == 1
    assert result["advisory_fires"] == 0


def test_the_blocking_split_is_read_from_the_guard_not_restated(
    tmp_path: Path,
) -> None:
    """Anti-drift for the split itself: if the guard ever changes which
    tools block, the report must follow without being edited."""
    replays = _one_session(
        tmp_path,
        _assistant(400_000, tool_uses=[_skill("build"), _agent("x")]),
    )
    by_tool = {g.tool: g.blocks for g in replays[0].gates}
    assert by_tool == {
        tool: tool in guard._BLOCKING_TOOLS for tool in ("Skill", "Agent")
    }


def test_a_session_with_only_agent_dispatches_is_not_in_the_denominator(
    tmp_path: Path,
) -> None:
    """It can never be blocked at any ceiling, so including it would dilute
    every block rate toward zero and make a too-low ceiling look fine."""
    replays = _one_session(tmp_path, _assistant(900_000, tool_uses=[_agent("x")]))
    result = report.evaluate_ceiling(replays, 150_000, 40, 5)
    assert result["sessions_blocked"] == 0
    assert result["sessions_blocked_pct"] is None, (
        "no blockable session means there is nothing to take a percentage of"
    )


def test_tokens_after_first_block_ignores_a_preceding_agent_dispatch(
    tmp_path: Path,
) -> None:
    """"First block" means the first BLOCKING gate. An earlier agent
    dispatch over the ceiling is not where enforcement would have cut in."""
    replays = _one_session(
        tmp_path,
        _assistant(400_000, tool_uses=[_agent("x")]),  # warns, does not block
        _assistant(500_000, tool_uses=[_skill("build")]),  # this is the block
        _assistant(600_000),
    )
    result = report.evaluate_ceiling(replays, 350_000, 40, 0)
    assert result["median_occupancy_at_first_block"] == 500_000
    assert result["prompt_tokens_after_first_block"] == 600_000


def test_the_report_names_the_blockable_subset(tmp_path: Path) -> None:
    _write(
        tmp_path / "t.jsonl",
        _assistant(400_000, tool_uses=[_skill("build"), _agent("x")]),
    )
    result = _run_cli("--transcripts", str(tmp_path), "--ceilings", "350000")
    assert result.returncode == 0
    assert b"of which blockable" in result.stdout.encode()
    assert b"Agent/Task warns, never blocks" in result.stdout.encode()


# ---------------------------------------------------------------------------
# the trend stream — what makes "over time" possible
# ---------------------------------------------------------------------------


def _trend_args(**over):
    class _A:
        ceiling_pct = 40
        shipped = 350_000
        near_done_turns = 5

    a = _A()
    for k, v in over.items():
        setattr(a, k, v)
    return a


def test_the_trend_record_carries_metrics_only(tmp_path: Path) -> None:
    """The trend stream accumulates across rounds and outlives any single
    review, so it must carry no transcript paths, session ids, prompts or
    code — the same constraint `session_extract.py`'s `slim_record` accepts
    (#129). A leak here is permanent in a way a one-off report is not.
    """
    replays = _one_session(
        tmp_path, _assistant(400_000, tool_uses=[_skill("build")])
    )
    sweep = [report.evaluate_ceiling(replays, 350_000, 40, 5)]
    blob = json.dumps(report.trend_record(replays, sweep, _trend_args()))

    assert str(tmp_path) not in blob
    assert ".jsonl" not in blob
    for key in ("path", "session_id", "label"):
        assert f'"{key}"' not in blob


def test_the_trend_record_pins_the_settings_it_was_measured_under(
    tmp_path: Path,
) -> None:
    """A row that does not say which ceiling_pct and near-done window
    produced it cannot be compared against the next round — the whole point
    of persisting it."""
    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("x")]))
    sweep = [report.evaluate_ceiling(replays, 350_000, 40, 5)]
    rec = report.trend_record(replays, sweep, _trend_args())
    assert rec["schema"] == "context-ceiling-trend/v1"
    assert (rec["ceiling_pct"], rec["shipped_ceiling"], rec["near_done_turns"]) == (
        40,
        350_000,
        5,
    )


def test_recorded_at_is_the_only_wall_clock_field(tmp_path: Path) -> None:
    """Two runs over the same corpus must produce identical reports; the
    timestamp lives on the trend log, never in the deterministic output."""
    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("x")]))
    sweep = [report.evaluate_ceiling(replays, 350_000, 40, 5)]
    rec = report.trend_record(replays, sweep, _trend_args())
    assert "recorded_at" in rec
    assert "recorded_at" not in json.dumps(sweep)


def test_append_creates_the_stream_and_never_rewrites_it(tmp_path: Path) -> None:
    """Append-only: an earlier round is evidence, and a round that could
    overwrite its predecessors would destroy the comparison it exists for."""
    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("x")]))
    sweep = [report.evaluate_ceiling(replays, 350_000, 40, 5)]
    log = tmp_path / "nested" / "trend.jsonl"

    report.append_trend(log, report.trend_record(replays, sweep, _trend_args()))
    report.append_trend(log, report.trend_record(replays, sweep, _trend_args()))

    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    assert all(json.loads(ln)["schema"] == "context-ceiling-trend/v1" for ln in lines)


def test_cli_append_writes_one_record_per_run(tmp_path: Path) -> None:
    _write(tmp_path / "t.jsonl", _assistant(400_000, tool_uses=[_skill("build")]))
    log = tmp_path / "trend.jsonl"
    for _ in range(2):
        result = _run_cli(
            "--transcripts", str(tmp_path), "--ceilings", "350000",
            "--append", str(log),
        )
        assert result.returncode == 0, result.stderr
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_recorded_at_matches_the_repos_metrics_timestamp_format(
    tmp_path: Path,
) -> None:
    """`session_extract.py` and the other metrics writers all emit
    `%Y-%m-%dT%H:%M:%SZ`. The playbook reads both streams' timestamps side by
    side, so a second spelling of UTC would be a gratuitous difference at
    exactly the point of comparison."""
    import datetime as _dt

    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("x")]))
    sweep = [report.evaluate_ceiling(replays, 350_000, 40, 5)]
    stamp = report.trend_record(replays, sweep, _trend_args())["recorded_at"]

    assert stamp.endswith("Z") and "+00:00" not in stamp
    parsed = _dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=_dt.timezone.utc
    )
    assert parsed.tzinfo is _dt.timezone.utc


# ---------------------------------------------------------------------------
# what the first real corpus (306 sessions) exposed about the instrument
# ---------------------------------------------------------------------------


def test_turns_left_distinguishes_two_blocks_near_done_cannot(
    tmp_path: Path,
) -> None:
    """The gap the first real corpus exposed. `near_done_blocked_pct` sat at
    0-6% across every candidate from 150K to 600K, which reads as "nothing
    over-blocks anywhere" and would argue for lowering the ceiling without
    limit. It only ever saw one shape — blocked AT the finish line. These two
    sessions are identical to that metric and completely different in fact.
    """
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    early = _one_session(
        a,
        _assistant(400_000, tool_uses=[_skill("build")]),
        *[_assistant(410_000) for _ in range(40)],
    )
    late = _one_session(
        b,
        *[_assistant(100_000) for _ in range(40)],
        _assistant(400_000, tool_uses=[_skill("build")]),
        *[_assistant(410_000) for _ in range(8)],
    )
    early_r = report.evaluate_ceiling(early, 350_000, 40, 5)
    late_r = report.evaluate_ceiling(late, 350_000, 40, 5)

    # Both sit above the near-done threshold, so it reports them identically —
    # "0% over-blocking", the reading the real corpus produced at every
    # candidate.
    assert early_r["near_done_blocked_pct"] == late_r["near_done_blocked_pct"] == 0.0
    # They are not remotely the same block: one interrupts 40 turns of work,
    # the other 8.
    assert early_r["median_remaining_turns_at_first_block"] == 40
    assert late_r["median_remaining_turns_at_first_block"] == 8


def test_turns_left_is_none_when_nothing_was_blocked(tmp_path: Path) -> None:
    replays = _one_session(tmp_path, _assistant(100_000, tool_uses=[_skill("x")]))
    result = report.evaluate_ceiling(replays, 350_000, 40, 5)
    assert result["sessions_blocked"] == 0
    assert result["median_remaining_turns_at_first_block"] is None


def test_the_trend_record_carries_the_clamp(tmp_path: Path) -> None:
    """The first real corpus produced a 450K row and a 600K row with every
    persisted field equal, because both clamp to 40% of a 1M window. Without
    `clamped_sessions` the stream cannot say why, and a later reader compares
    two rows that were never two candidates."""
    replays = _one_session(tmp_path, _assistant(400_000, tool_uses=[_skill("x")]))
    sweep = [
        report.evaluate_ceiling(replays, c, 40, 5) for c in (350_000, 450_000, 600_000)
    ]
    rec = report.trend_record(replays, sweep, _trend_args())
    by_ceiling = {row["abs_ceiling"]: row for row in rec["sweep"]}

    assert by_ceiling[350_000]["clamped_sessions"] == 0
    assert by_ceiling[450_000]["clamped_sessions"] == 1
    assert by_ceiling[600_000]["clamped_sessions"] == 1
    # The two clamped rows are otherwise identical — which is exactly why the
    # clamp field has to be present to explain them.
    assert {k: v for k, v in by_ceiling[450_000].items() if k != "abs_ceiling"} == {
        k: v for k, v in by_ceiling[600_000].items() if k != "abs_ceiling"
    }


def test_the_trend_record_carries_turns_left(tmp_path: Path) -> None:
    replays = _one_session(
        tmp_path,
        _assistant(400_000, tool_uses=[_skill("build")]),
        _assistant(410_000),
        _assistant(420_000),
    )
    sweep = [report.evaluate_ceiling(replays, 350_000, 40, 5)]
    rec = report.trend_record(replays, sweep, _trend_args())
    assert rec["sweep"][0]["median_remaining_turns_at_first_block"] == 2
