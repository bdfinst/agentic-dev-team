"""Benefit report: the metric modules and the ``report`` command.

Covers scripts/lib/benefit_eval/formatting.py, metrics_ledger.py, metrics_hooks.py
and metrics_cost.py through scripts/benefit_eval_cli.py, which this file loads by
file path as the audit tests do.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pytest
from _benefit_eval_support import (
    LONG_ID,
    REAL_PREREG,
    World,
    cli_argv,
    load_cli,
    real_entries,
)
from benefit_eval import prereg as prereg_module

cli = load_cli("benefit_eval_cli_report")

IN_WINDOW = "2026-03-01T12:00:00Z"
BEFORE_WINDOW = "2026-01-01T12:00:00Z"
WINDOW_START = "2026-02-01T00:00:00Z"
POSTED = "2026-02-15T09:30:00Z"


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def write_prereg(tmp_path: Path, ids: list[str], minimum_n: int = 1, **overrides) -> Path:
    """A pre-registration of the named real entries; each ``overrides`` key is a metric id mapping to its changed cells."""
    entries = []
    for metric_id in ids:
        entry = {**real_entries()[metric_id], "minimum_n": minimum_n}
        entries.append({**entry, **overrides.get(metric_id, {})})
    path = tmp_path / "preregistration.md"
    path.write_text(f"# Pre-registration\n\n```json prereg\n{json.dumps({'metrics': entries}, indent=2)}\n```\n")
    return path


def run_report(
    world: World,
    tmp_path: Path,
    capsys,
    ids: list[str],
    *extra: str,
    minimum_n: int = 1,
    posted: str | None = POSTED,
    boundary: str | None = None,
    **overrides,
):
    prereg_path = write_prereg(tmp_path, ids, minimum_n, **overrides)
    code = cli.main(
        cli_argv(
            "report",
            world,
            prereg_path,
            *(["--prereg-posted", posted] if posted else []),
            *(["--boundary", boundary] if boundary else []),
            *extra,
        )
    )
    out = capsys.readouterr()
    return code, out.out, out.err


def consult(session_id: str, candidates: int, skipped: int, ts: str = IN_WINDOW, source: str = "consult") -> dict:
    return {
        "ts": ts,
        "session_id": session_id,
        "source": source,
        "candidate_pairs": candidates,
        "skipped_pairs": skipped,
        "fully_skipped_lenses": [],
    }


def line_of(out: str, prefix: str) -> str:
    return next(line for line in out.splitlines() if line.startswith(prefix))


def block_of(out: str, prefix: str) -> str:
    """The metric line and the indented detail lines that follow it."""
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(prefix))
    end = start + 1
    while end < len(lines) and lines[end].startswith("  "):
        end += 1
    return "\n".join(lines[start:end])


def assert_input_error(err: str, file: Path | str, line: int, problem: str) -> None:
    """The whole ``<file>:<line>: <problem>. Next: <action>`` shape, on one stderr line."""
    pattern = rf"{re.escape(str(file))}:{line}: .*{re.escape(problem)}.*\. Next: \S.*"
    assert re.fullmatch(pattern, err.strip()), err


# --- delta-scoping skip rate -------------------------------------------------


def test_skip_rate_counts_consult_rows_only(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream(
        "ledger-skips",
        [consult("sess-a", 12, 3), consult("sess-a", 20, 20, source="dispatch-hook")],
    )
    code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    line = line_of(out, "skip-rate:")
    assert "25.00% (3/12)" in line
    assert "N=12 candidate pairs" in line
    assert code == 0


def test_skip_rate_prints_the_ceiling_and_floor_the_pre_registration_carries(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 12, 3)])
    cells = {"ceiling": 33.33, "keep": ">= 12.5"}
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], **{"skip-rate": cells})
    block = block_of(out, "skip-rate:")
    assert "| floor 12.50 |" in block
    assert "theoretical ceiling 33.33%" in block
    assert "20.69" not in out


@pytest.mark.parametrize(("skipped", "flagged"), [(3, True), (2, False)])
def test_a_skip_rate_above_the_ceiling_is_flagged_as_a_counting_defect(world, tmp_path, capsys, skipped, flagged):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 10, skipped)])
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], **{"skip-rate": {"ceiling": 25.0}})
    assert ("counting defect" in block_of(out, "skip-rate:")) is flagged


def test_a_skip_rate_with_no_ceiling_is_never_flagged_as_a_counting_defect(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 10, 10)])
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], **{"skip-rate": {"ceiling": None}})
    assert "100.00% (10/10)" in line_of(out, "skip-rate:")
    assert "counting defect" not in out
    assert "theoretical ceiling" not in out


def test_first_and_repeat_runs_order_by_parsed_time_when_timestamps_differ_in_precision(world, tmp_path, capsys):
    world.session("sess-a")
    # By text "...:00.500Z" sorts before "...:00Z"; by time it is half a second later.
    world.stream(
        "ledger-skips",
        [consult("sess-a", 10, 0, "2026-03-01T11:00:00.500Z"), consult("sess-a", 10, 5, "2026-03-01T11:00:00Z")],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert "first runs: 50.00% (5/10)" in out
    assert "repeat runs: 0.00% (0/10)" in out


def test_skip_rate_splits_first_runs_from_repeat_runs_by_time_not_file_order(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream(
        "ledger-skips",
        [consult("sess-a", 10, 5, "2026-03-01T11:00:00Z"), consult("sess-a", 10, 0, "2026-03-01T10:00:00Z")],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert "first runs: 0.00% (0/10)" in out
    assert "repeat runs: 50.00% (5/10)" in out


def test_a_session_whose_first_consult_predates_the_window_counts_its_first_in_window_consult_as_a_first_run(
    world, tmp_path, capsys
):
    world.session("sess-a")
    world.stream(
        "ledger-skips",
        [consult("sess-a", 10, 0, BEFORE_WINDOW), consult("sess-a", 10, 5, IN_WINDOW)],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], "--window-start", WINDOW_START)
    assert "first runs: 50.00% (5/10)" in out
    assert "repeat runs: no candidate pairs" in out


def test_zero_candidate_pairs_print_no_rows_in_window_and_exit_3(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 0, 0)])
    code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], minimum_n=10)
    assert line_of(out, "skip-rate:") == "skip-rate: no rows in window"
    assert "0.00%" not in out
    assert code == 3
    as_json = json.loads(run_report(world, tmp_path, capsys, ["skip-rate"], "--json", minimum_n=10)[1])
    assert as_json["metrics"][0]["value"] is None


# --- checkpoint aborts -------------------------------------------------------


def abort_row(session_id: str, aborted: bool, lenses: list[str], source: str = "checkpoint", ts: str = IN_WINDOW) -> dict:
    return {
        "ts": ts,
        "session_id": session_id,
        "source": source,
        "mode": "abort",
        "aborted": aborted,
        "triggering_agent": "correctness-review" if aborted else None,
        "deferred_lenses": lenses,
    }


def test_abort_yield_counts_only_lenses_deferred_by_an_aborted_checkpoint(world, tmp_path, capsys):
    world.session("sess-a")
    world.session("sess-b")
    deferred = ["security-review", "domain-review", "arch-review", "structure-review"]
    found_new = {
        **abort_row("sess-a", True, [], source="stop-hook", ts="2026-03-01T12:30:00Z"),
        "triggering_agent": "dev-team:security-review",
    }
    world.stream(
        "checkpoint-aborts",
        [
            abort_row("sess-a", True, deferred),
            found_new,
            abort_row("sess-b", False, ["lens-one", "lens-two"]),
        ],
    )
    code, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    assert "25.00% (1/4)" in line_of(out, "abort-yield:")
    assert code == 0


def test_a_lens_result_before_the_abort_is_not_deferred_yield(world, tmp_path, capsys):
    world.session("sess-a")
    earlier = {**abort_row("sess-a", True, [], source="stop-hook", ts="2026-03-01T11:00:00Z"), "triggering_agent": "security-review"}
    world.stream("checkpoint-aborts", [earlier, abort_row("sess-a", True, ["security-review"])])
    _, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    assert "0.00% (0/1)" in line_of(out, "abort-yield:")


def outcome_row(session_id: str) -> dict:
    return {"ts": IN_WINDOW, "session_id": session_id, "source": "checkpoint", "mode": "outcome", "aborted": True}


def test_abort_frequency_is_aborted_over_abort_mode_rows_for_each_source_on_its_own(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream(
        "checkpoint-aborts",
        [
            abort_row("sess-a", True, ["lens-one"]),
            abort_row("sess-a", False, []),
            abort_row("sess-a", False, []),
            abort_row("sess-a", True, [], source="stop-hook"),
            abort_row("sess-a", True, [], source="stop-hook"),
            outcome_row("sess-a"),
        ],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    block = block_of(out, "abort frequency")
    assert "  checkpoint: 33.33% (1/3)" in block
    assert "  stop-hook: 100.00% (2/2)" in block
    note = json.loads(run_report(world, tmp_path, capsys, ["abort-yield"], "--json")[1])["notes"]["abort-frequency"]
    assert note["checkpoint"] == {"aborted": 1, "total": 3}
    assert note["stop-hook"] == {"aborted": 2, "total": 2}


def test_abort_frequency_counts_unverified_rows_and_leaves_them_out_of_the_rate(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream(
        "checkpoint-aborts",
        [abort_row("sess-a", False, []), abort_row("no-transcript", True, ["lens-one"])],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    block = block_of(out, "abort frequency")
    assert "  checkpoint: 0.00% (0/1)" in block
    assert "  unverified: 1" in block


def test_abort_frequency_names_a_source_with_no_abort_mode_rows(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("checkpoint-aborts", [outcome_row("sess-a")])
    _, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    block = block_of(out, "abort frequency")
    assert "  checkpoint: no abort-mode rows" in block
    assert "  stop-hook: no abort-mode rows" in block


def test_a_lens_result_half_a_second_before_the_abort_is_not_deferred_yield_whatever_the_timestamp_precision(
    world, tmp_path, capsys
):
    world.session("sess-a")
    # By text "...:00Z" sorts after "...:00.500Z"; by time it is half a second earlier.
    earlier = {**abort_row("sess-a", True, [], source="stop-hook", ts="2026-03-01T12:00:00Z"), "triggering_agent": "security-review"}
    aborted = abort_row("sess-a", True, ["security-review"], ts="2026-03-01T12:00:00.500Z")
    world.stream("checkpoint-aborts", [earlier, aborted])
    _, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    assert "0.00% (0/1)" in line_of(out, "abort-yield:")


def test_a_lens_result_from_another_session_is_not_deferred_yield(world, tmp_path, capsys):
    world.session("sess-a")
    world.session("sess-b")
    elsewhere = {**abort_row("sess-b", True, [], source="stop-hook", ts="2026-03-01T13:00:00Z"), "triggering_agent": "security-review"}
    world.stream("checkpoint-aborts", [abort_row("sess-a", True, ["security-review"]), elsewhere])
    _, out, _ = run_report(world, tmp_path, capsys, ["abort-yield"])
    assert "0.00% (0/1)" in line_of(out, "abort-yield:")


# --- skill-context injection -------------------------------------------------


def injection(session_id: str, added_chars: int, skills=("api-design",), agent_type="dev-team:correctness-review") -> dict:
    return {
        "ts": IN_WINDOW,
        "session_id": session_id,
        "agent_type": agent_type,
        "skills": list(skills),
        "added_chars": added_chars,
    }


def test_injection_overhead_prints_the_mean_against_the_ceiling(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("skill-injection", [injection("sess-a", 300), injection("sess-a", 500)])
    code, out, _ = run_report(world, tmp_path, capsys, ["injection-overhead"], **{"injection-overhead": {"keep": "<= 450"}})
    line = line_of(out, "injection-overhead:")
    assert "mean 400 characters" in line
    assert "ceiling 450" in line
    assert "N=2 injections" in line
    assert code == 0


def skill_call(skill: str) -> dict:
    return {
        "type": "assistant",
        "timestamp": IN_WINDOW,
        "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": skill}}]},
    }


def attributed(agent_type: str, *records: dict) -> list[dict]:
    return [{**record, "isSidechain": True, "attributionAgent": agent_type} for record in records]


def test_uptake_counts_only_the_injected_skill(world, tmp_path, capsys):
    world.session("sess-a")
    world.subagent(
        "sess-a",
        "a1",
        attributed("dev-team:correctness-review", skill_call("dev-team:api-design"), skill_call("dev-team:legacy-code")),
    )
    world.stream("skill-injection", [injection("sess-a", 100)])
    _, out, _ = run_report(world, tmp_path, capsys, ["injection-uptake"])
    assert "100.00% (1/1)" in line_of(out, "injection-uptake:")


def test_a_skill_call_by_another_skill_alone_is_not_uptake(world, tmp_path, capsys):
    world.session("sess-a")
    world.subagent("sess-a", "a1", attributed("dev-team:correctness-review", skill_call("dev-team:legacy-code")))
    world.stream("skill-injection", [injection("sess-a", 100)])
    _, out, _ = run_report(world, tmp_path, capsys, ["injection-uptake"])
    assert "0.00% (0/1)" in line_of(out, "injection-uptake:")


def test_a_skill_call_by_a_different_agent_type_is_not_uptake(world, tmp_path, capsys):
    world.session("sess-a")
    world.subagent("sess-a", "a1", attributed("dev-team:other-review", skill_call("dev-team:api-design")))
    world.stream("skill-injection", [injection("sess-a", 100)])
    _, out, _ = run_report(world, tmp_path, capsys, ["injection-uptake"])
    assert "0.00% (0/1)" in line_of(out, "injection-uptake:")


def test_agent_type_comes_from_the_dispatch_join_when_the_transcript_has_no_attribution(world, tmp_path, capsys):
    dispatch = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "tu1", "name": "Agent", "input": {"subagent_type": "dev-team:correctness-review"}}]},
    }
    result = {
        "type": "user",
        "toolUseResult": {"agentId": "a1"},
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "done"}]},
    }
    world.session("sess-a", "".join(json.dumps(r) + "\n" for r in (dispatch, result)))
    world.subagent("sess-a", "a1", [skill_call("dev-team:api-design")])
    world.stream("skill-injection", [injection("sess-a", 100)])
    _, out, _ = run_report(world, tmp_path, capsys, ["injection-uptake"])
    assert "100.00% (1/1)" in line_of(out, "injection-uptake:")


# --- completion guard --------------------------------------------------------


def stop(session_id: str, classification: str, ts: str = IN_WINDOW) -> dict:
    return {"ts": ts, "session_id": session_id, "classification": classification}


def test_divergence_rate_is_flagged_over_clean_plus_flagged_and_leaves_unreadable_out(world, tmp_path, capsys):
    world.session("sess-a")
    rows = [stop("sess-a", c) for c in ("clean", "clean", "clean", "empty-final-turn", "unreadable")]
    world.stream("subagent-stops", rows)
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert "25.00% (1/4)" in line_of(out, "guard-divergence:")


def guard_world(world: World, count: int = 30, decoys: bool = False) -> None:
    """``count`` flagged stops, each in its own session with its own subagent transcript.

    With ``decoys`` each stop row also carries an agent id and a transcript path that name nothing real."""
    rows = []
    for i in range(count):
        session_id = f"{i:08d}-aaaa-bbbb-cccc-dddddddddddd"
        world.session(session_id)
        ts = f"2026-03-01T12:{i:02d}:00Z"
        world.subagent(session_id, f"a{i:02d}", [{"type": "assistant", "timestamp": ts, "message": {"content": []}}])
        row = stop(session_id, "empty-final-turn" if i % 2 else "truncated-final-turn", ts)
        if decoys:
            row.update(agent_id="decoy-agent", transcript_path="/decoy/transcript.jsonl")
        rows.append(row)
    world.stream("subagent-stops", rows)


def sample_lines(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if line.strip().startswith("session=")]


def test_the_same_seed_gives_the_same_twenty_line_sample_and_another_seed_a_different_one(world, tmp_path, capsys):
    guard_world(world)
    first = sample_lines(run_report(world, tmp_path, capsys, ["guard-divergence"], "--seed", "1")[1])
    again = sample_lines(run_report(world, tmp_path, capsys, ["guard-divergence"], "--seed", "1")[1])
    other = sample_lines(run_report(world, tmp_path, capsys, ["guard-divergence"], "--seed", "2")[1])
    assert len(set(first)) == 20
    assert first == again
    assert set(first) != set(other)


def test_sample_lines_carry_session_classification_agent_and_transcript_from_discovery(world, tmp_path, capsys):
    guard_world(world, count=3, decoys=True)
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert "decoy" not in out
    lines = sample_lines(out)
    assert len(lines) == 3
    for line in lines:
        session, classification, agent, transcript = (part.split("=", 1)[1] for part in line.split())
        index = int(session)
        assert classification in ("empty-final-turn", "truncated-final-turn")
        assert agent == f"a{index:02d}"
        assert transcript == f"*/{session}*/subagents/agent-a{index:02d}.jsonl"
        assert f"{index:08d}-aaaa-bbbb-cccc-dddddddddddd" not in out


@pytest.mark.parametrize("json_mode", [False, True])
def test_the_sample_transcript_path_leaves_out_the_encoded_project_directory(world, tmp_path, capsys, json_mode):
    encoded = "-Users-alice-private-checkout"
    session_dir = world.projects / encoded
    session_dir.mkdir()
    (session_dir / f"{LONG_ID}.jsonl").write_text('{"type":"user"}\n')
    subagents = session_dir / LONG_ID / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-a1.jsonl").write_text(json.dumps({"type": "assistant", "timestamp": IN_WINDOW}) + "\n")
    world.stream("subagent-stops", [stop(LONG_ID, "empty-final-turn")])
    _, out, err = run_report(world, tmp_path, capsys, ["guard-divergence"], *(["--json"] if json_mode else []))
    assert f"*/{LONG_ID[:8]}*/subagents/agent-a1.jsonl" in out
    assert "alice" not in out + err
    assert encoded not in out + err


def test_a_flagged_stop_with_no_subagent_transcript_prints_unmatched(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("subagent-stops", [stop("sess-a", "empty-final-turn")])
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert "agent=unmatched transcript=none" in out


def sample_agents(out: str) -> dict[str, str]:
    """Sample lines keyed by classification, valued by the agent they matched."""
    pairs = (dict(part.split("=", 1) for part in line.split()) for line in sample_lines(out))
    return {pair["classification"]: pair["agent"] for pair in pairs}


def test_each_flagged_stop_matches_the_transcript_nearest_its_time_whatever_the_discovery_order(
    world, tmp_path, capsys
):
    world.session("sess-a")
    # Discovery lists agent-a before agent-b, but the first stop is nearest agent-b.
    world.subagent("sess-a", "a", [{"type": "assistant", "timestamp": "2026-03-01T12:09:50Z"}])
    world.subagent("sess-a", "b", [{"type": "assistant", "timestamp": "2026-03-01T12:00:10Z"}])
    world.stream(
        "subagent-stops",
        [
            stop("sess-a", "empty-final-turn", "2026-03-01T12:00:00Z"),
            stop("sess-a", "truncated-final-turn", "2026-03-01T12:10:00Z"),
        ],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert sample_agents(out) == {"empty-final-turn": "b", "truncated-final-turn": "a"}


def test_stops_are_matched_in_time_order_when_their_timestamps_differ_in_precision(world, tmp_path, capsys):
    world.session("sess-a")
    # By text "...:00.500Z" sorts before "...:00Z"; by time the whole-second stop comes first and takes
    # the transcript both stops are nearest to.
    world.subagent("sess-a", "near", [{"type": "assistant", "timestamp": "2026-03-01T12:00:00.200Z"}])
    world.subagent("sess-a", "far", [{"type": "assistant", "timestamp": "2026-03-01T12:00:09Z"}])
    world.stream(
        "subagent-stops",
        [
            stop("sess-a", "truncated-final-turn", "2026-03-01T12:00:00.500Z"),
            stop("sess-a", "empty-final-turn", "2026-03-01T12:00:00Z"),
        ],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert sample_agents(out) == {"empty-final-turn": "near", "truncated-final-turn": "far"}


def test_a_subagent_transcript_matches_one_flagged_stop_only(world, tmp_path, capsys):
    world.session("sess-a")
    # Both stops are nearest agent-a; the second must take agent-b.
    world.subagent("sess-a", "a", [{"type": "assistant", "timestamp": "2026-03-01T12:00:02Z"}])
    world.subagent("sess-a", "b", [{"type": "assistant", "timestamp": "2026-03-01T12:30:00Z"}])
    world.stream(
        "subagent-stops",
        [
            stop("sess-a", "empty-final-turn", "2026-03-01T12:00:00Z"),
            stop("sess-a", "truncated-final-turn", "2026-03-01T12:00:05Z"),
        ],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert sample_agents(out) == {"empty-final-turn": "a", "truncated-final-turn": "b"}


def test_a_flagged_stop_whose_only_transcript_has_no_parseable_timestamp_prints_unmatched(world, tmp_path, capsys):
    world.session("sess-a")
    world.subagent("sess-a", "a", [{"type": "assistant", "timestamp": "not a time"}])
    world.stream("subagent-stops", [stop("sess-a", "empty-final-turn")])
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert "agent=unmatched transcript=none" in out


def test_a_sample_smaller_than_twenty_lists_every_flagged_stop(world, tmp_path, capsys):
    guard_world(world, count=5)
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert len(sample_lines(out)) == 5


# --- missing scope marker ----------------------------------------------------


def boundary_event(session_id: str, rule: str = "missing-scope-marker") -> dict:
    return {"ts": IN_WINDOW, "session_id": session_id, "hook": "review_verdict_recorder", "decision": "record", "matched_rule": rule}


def write_boundary_events(world: World, events: list[dict]) -> Path:
    path = world.project / ".claude" / "metrics" / "boundary-events.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path


def test_missing_scope_marker_count_is_split_by_whether_the_session_ran_a_consult(world, tmp_path, capsys):
    sessions = [f"sess-{i}" for i in range(5)]
    for session in sessions:
        world.session(session)
    world.stream("ledger-skips", [consult(s, 4, 1) for s in sessions[3:]])
    events = [boundary_event(s) for s in sessions] + [boundary_event(sessions[0], "unparseable-result")]
    write_boundary_events(world, events)
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert "missing-scope-marker: direct=3 consult=2" in out


def test_known_limitation_every_missing_scope_marker_of_a_session_that_ran_a_consult_counts_as_consult(
    world, tmp_path, capsys
):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 1)])
    # One event may come from a direct dispatch, but the event carries no source to say so.
    write_boundary_events(world, [boundary_event("sess-a"), boundary_event("sess-a")])
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert "missing-scope-marker: direct=0 consult=2" in out


# --- unverified rows and the window ------------------------------------------


def test_rows_whose_session_has_no_transcript_are_excluded_and_counted(world, tmp_path, capsys):
    world.session("sess-a")
    rows = [consult("sess-a", 1, 0)] * 5 + [consult("no-transcript", 1, 1)] * 3
    world.stream("ledger-skips", rows)
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    line = line_of(out, "skip-rate:")
    assert "N=5 candidate pairs" in line
    assert "0.00% (0/5)" in line
    assert "unverified: 3" in out


def test_rows_before_the_window_start_add_nothing(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 1, 0)] * 5 + [consult("sess-a", 1, 0, BEFORE_WINDOW)] * 5)
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], "--window-start", WINDOW_START)
    assert "N=5 candidate pairs" in line_of(out, "skip-rate:")


def test_the_window_start_is_inclusive_and_the_window_end_exclusive(world, tmp_path, capsys):
    world.session("sess-a")
    window_end = "2026-04-01T00:00:00Z"
    world.stream(
        "ledger-skips",
        [
            consult("sess-a", 1, 0, "2026-01-31T23:59:59Z"),
            consult("sess-a", 2, 0, WINDOW_START),
            consult("sess-a", 4, 0, "2026-03-31T23:59:59Z"),
            consult("sess-a", 8, 0, window_end),
        ],
    )
    _, out, _ = run_report(
        world, tmp_path, capsys, ["skip-rate"], "--window-start", WINDOW_START, "--window-end", window_end
    )
    assert "N=6 candidate pairs" in line_of(out, "skip-rate:")


@pytest.mark.parametrize("flag", ["--window-start", "--window-end"])
def test_a_window_bound_that_is_not_utc_with_z_exits_2(world, tmp_path, capsys, flag):
    with pytest.raises(SystemExit) as raised:
        run_report(world, tmp_path, capsys, ["skip-rate"], flag, "2026-02-01T00:00:00+00:00")
    assert raised.value.code == 2


# --- threshold boundary ------------------------------------------------------


@pytest.mark.parametrize(("direction", "status", "code"), [("<=", "within", 0), ("<", "breach", 1)])
def test_a_value_on_the_limit_follows_the_pre_registered_inclusivity(world, tmp_path, capsys, direction, status, code):
    world.session("sess-a")
    world.stream("skill-injection", [injection("sess-a", 450)])
    inclusivity = "inclusive" if direction == "<=" else "exclusive"
    cells = {"keep": f"{direction} 450", "direction": direction, "inclusivity": inclusivity}
    got_code, out, _ = run_report(world, tmp_path, capsys, ["injection-overhead"], **{"injection-overhead": cells})
    assert line_of(out, "injection-overhead:").endswith(f"| {status}")
    assert got_code == code


@pytest.mark.parametrize(
    ("direction", "candidates", "skipped", "status", "code"),
    [
        (">=", 8, 2, "within", 0),  # exactly 25.00
        (">", 8, 2, "breach", 1),
        (">=", 9, 2, "breach", 1),  # 22.22, just under
        (">", 9, 2, "breach", 1),
        (">=", 11, 3, "within", 0),  # 27.27, just over
        (">", 11, 3, "within", 0),
    ],
)
def test_a_floor_follows_the_pre_registered_inclusivity_on_and_either_side_of_the_limit(
    world, tmp_path, capsys, direction, candidates, skipped, status, code
):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", candidates, skipped)])
    inclusivity = "inclusive" if direction == ">=" else "exclusive"
    cells = {"keep": f"{direction} 25", "direction": direction, "inclusivity": inclusivity}
    got_code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], **{"skip-rate": cells})
    assert line_of(out, "skip-rate:").endswith(f"| {status}")
    assert got_code == code


# --- unreadable input --------------------------------------------------------


def test_a_malformed_instrument_line_exits_2_with_file_line_problem_and_next(world, tmp_path, capsys):
    path = world.stream("ledger-skips", [consult("sess-a", 1, 0)])
    path.write_text(path.read_text() + "not json\n")
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert code == 2
    assert_input_error(err, path, 2, "line is not valid JSON")


def test_an_absent_instrument_stream_is_no_rows_and_exits_3(world, tmp_path, capsys):
    assert not (world.project / ".claude" / "metrics" / "ledger-skips.jsonl").exists()
    code, out, err = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert line_of(out, "skip-rate:") == "skip-rate: no rows in window"
    assert (code, err) == (3, "")


def test_an_instrument_stream_that_is_not_utf8_exits_2_naming_the_file(world, tmp_path, capsys):
    path = world.stream("ledger-skips", [])
    path.write_bytes(b"\xff\xfe not utf-8\n")
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert code == 2
    assert_input_error(err, path, 0, "cannot read file")


def test_a_row_with_a_bad_timestamp_exits_2_naming_its_line(world, tmp_path, capsys):
    path = world.stream("ledger-skips", [{**consult("sess-a", 1, 0), "ts": "yesterday"}])
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert code == 2
    assert_input_error(err, path, 1, "row has no valid 'ts' timestamp")


def test_a_missing_pre_registration_exits_2(world, tmp_path, capsys):
    missing = tmp_path / "nope.md"
    code = cli.main(cli_argv("report", world, missing, "--prereg-posted", POSTED))
    assert code == 2
    assert_input_error(capsys.readouterr().err, missing, 0, "pre-registration file not found")


def test_a_metric_the_report_cannot_compute_exits_2_naming_it(world, tmp_path, capsys):
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"], **{"skip-rate": {"id": "mystery-metric"}})
    assert code == 2
    assert_input_error(err, tmp_path / "preregistration.md", 0, "no computation for metric 'mystery-metric'")


# --- output ------------------------------------------------------------------


def test_report_prints_the_run_time_in_utc_and_no_ansi(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 1)])
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert re.search(r"run at \(UTC\): \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", out)
    assert "\x1b[" not in out


@pytest.mark.parametrize("json_mode", [False, True])
def test_report_never_prints_a_full_session_id(world, tmp_path, capsys, json_mode):
    world.session(LONG_ID)
    world.stream("ledger-skips", [consult(LONG_ID, 4, 1)])
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], *(["--json"] if json_mode else []))
    assert LONG_ID not in out
    assert LONG_ID[:8] in out


def test_report_json_carries_each_metric_with_its_status_and_exit_code(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 12, 3)])
    code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], "--json")
    payload = json.loads(out)
    (metric,) = payload["metrics"]
    assert (metric["metric_id"], metric["n"], metric["value"], metric["status"]) == ("skip-rate", 12, 25.0, "within")
    assert payload["exit_code"] == code == 0
    assert payload["notes"]["missing-scope-marker"] == {"direct": 0, "consult": 0, "unverified": 0}


def test_a_breach_outranks_insufficient_data_in_the_exit_code(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("skill-injection", [injection("sess-a", 900)])
    code, _, _ = run_report(
        world, tmp_path, capsys, ["injection-overhead", "skip-rate"], **{"injection-overhead": {"keep": "<= 450"}}
    )
    assert code == 1


def populate_every_input_kind(world: World) -> list[Path]:
    """One file of each kind the report reads, so a write to any of them shows in a snapshot."""
    guard_world(world, count=3)
    session = "00000001-aaaa-bbbb-cccc-dddddddddddd"
    dispatch(world, IN_WINDOW, 500, session=session)
    return [
        world.stream("ledger-skips", [consult(session, 4, 1)]),
        world.stream("skill-injection", [injection(session, 300)]),
        world.stream("checkpoint-aborts", [abort_row(session, True, ["security-review"])]),
        world.stream("cost-metering", [{"timestamp": IN_WINDOW, "by_agent_type": {}}]),
        write_boundary_events(world, [boundary_event(session)]),
        usage_file(world, {"source-verification": {"use_count": 10}}),
        write_manual(world, {"pbt-mutants-killed": {"value": 2, "n": 10}}),
        world.projects / "proj-a" / f"{session}.jsonl",
        next((world.projects / "proj-a").glob("*/subagents/agent-*.jsonl")),
    ]


READ_ONLY_METRICS = [
    "skip-rate", "abort-yield", "injection-overhead", "injection-uptake", "guard-divergence",
    "test-review-token-delta", "contradicted-rate", "pbt-mutants-killed",
]  # fmt: skip


# The real pre-registration holds metrics at their real minimum N, so every verdict line is NULL (exit 3);
# the small pre-registration's injection-uptake falls under its floor (exit 1).
@pytest.mark.parametrize(("real_prereg", "expected_code"), [(False, 1), (True, 3)])
def test_report_leaves_every_input_kind_byte_identical(world, tmp_path, capsys, real_prereg, expected_code):
    inputs = populate_every_input_kind(world)
    prereg_path = REAL_PREREG if real_prereg else write_prereg(tmp_path, READ_ONLY_METRICS)
    before = world.snapshot()
    assert {str(path.relative_to(world.root)) for path in inputs} <= before.keys()
    code = cli.main(cli_argv("report", world, prereg_path, "--prereg-posted", POSTED, "--boundary", BOUNDARY))
    out = capsys.readouterr().out
    registered = list(real_entries()) if real_prereg else READ_ONLY_METRICS
    assert code == expected_code
    assert all(f"\n{metric_id}: " in f"\n{out}" for metric_id in registered)
    assert world.snapshot() == before


# --- required arguments ------------------------------------------------------


def test_a_report_without_the_pre_registration_post_time_exits_2(world, tmp_path, capsys):
    with pytest.raises(SystemExit) as raised:
        run_report(world, tmp_path, capsys, ["skip-rate"], posted=None)
    assert raised.value.code == 2
    assert "--prereg-posted" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["2026-02-15", "2026-02-15T09:30:00+00:00", "yesterday"])
def test_a_post_time_that_is_not_utc_with_z_exits_2(world, tmp_path, capsys, bad):
    with pytest.raises(SystemExit) as raised:
        run_report(world, tmp_path, capsys, ["skip-rate"], posted=bad)
    assert raised.value.code == 2


def test_the_post_time_is_echoed_beside_the_run_time(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 1)])
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert f"prereg posted (UTC): {POSTED}" in out
    assert re.search(r"run at \(UTC\): \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", out)
    payload = json.loads(run_report(world, tmp_path, capsys, ["skip-rate"], "--json")[1])
    assert payload["prereg_posted"] == POSTED


# --- before and after at the boundary ----------------------------------------

DELTA = ["test-review-token-delta"]
BOUNDARY = "2026-03-01T00:00:00Z"
BEFORE_BOUNDARY = "2026-02-01T00:00:00Z"
_agent_ids = itertools.count()


def dispatch(
    world: World,
    ts: str | None,
    tokens: int,
    agent: str = "dev-team:test-review",
    session: str = "sess-a",
    usage: dict | None = None,
) -> None:
    """One dispatch of ``agent``: a subagent transcript of ``session`` whose last record sits at ``ts``."""
    world.session(session)
    record = {"type": "assistant", "message": {"role": "assistant", "usage": usage or {"input_tokens": tokens}}}
    if ts is not None:
        record["timestamp"] = ts
    world.subagent(session, f"d{next(_agent_ids)}", attributed(agent, record))


def dispatches(world: World, before: int, after: int, tokens: tuple[int, int] = (1000, 500)) -> None:
    for _ in range(before):
        dispatch(world, BEFORE_BOUNDARY, tokens[0])
    for _ in range(after):
        dispatch(world, IN_WINDOW, tokens[1])


def test_a_missing_boundary_exits_2_when_a_before_and_after_metric_is_registered(world, tmp_path, capsys):
    dispatch(world, IN_WINDOW, 100)
    code, out, err = run_report(world, tmp_path, capsys, DELTA)
    assert (code, out) == (2, "")
    assert_input_error(err, "--boundary", 0, "test-review-token-delta splits before and after a boundary")
    assert "--boundary" in err.split("Next:")[1]


@pytest.mark.parametrize("bad", ["2026-02-15", "2026-02-15T09:30:00+02:00"])
def test_a_boundary_that_is_not_utc_with_z_exits_2(world, tmp_path, capsys, bad):
    with pytest.raises(SystemExit) as raised:
        run_report(world, tmp_path, capsys, DELTA, boundary=bad)
    assert raised.value.code == 2


@pytest.mark.parametrize("as_json", [False, True])
def test_the_boundary_is_echoed_as_the_operator_typed_it_fractional_seconds_included(world, tmp_path, capsys, as_json):
    typed = "2026-03-01T00:00:00.500Z"
    dispatch(world, IN_WINDOW, 100)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, *(["--json"] if as_json else []), boundary=typed)
    if as_json:
        assert json.loads(out)["boundary"] == typed
    else:
        assert f"boundary (UTC): {typed}\n" in out


def test_a_boundary_is_not_required_when_no_before_and_after_metric_is_registered(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 1)])
    assert run_report(world, tmp_path, capsys, ["skip-rate"])[0] == 0


def test_a_dispatch_ending_exactly_at_the_boundary_is_on_the_after_side_only(world, tmp_path, capsys):
    for ts in ("2026-02-28T23:59:59Z", BOUNDARY, "2026-03-01T00:00:01Z"):
        dispatch(world, ts, 100)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "before: N=1" in out
    assert "after: N=2" in out


def test_the_directional_line_reads_directional_with_the_pre_registered_confounds(world, tmp_path, capsys):
    dispatches(world, 1, 1)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    confounds = "; ".join(real_entries()["test-review-token-delta"]["confounds"])
    assert f"DIRECTIONAL (confounds: {confounds})" in line_of(out, "test-review-token-delta:")


def test_the_delta_is_the_percent_change_in_mean_test_review_tokens_and_ignores_other_agents(world, tmp_path, capsys):
    dispatch(world, BEFORE_BOUNDARY, 1000)
    dispatch(world, "2026-02-02T00:00:00Z", 3000)
    dispatch(world, IN_WINDOW, 1600)
    dispatch(world, IN_WINDOW, 99999, agent="dev-team:other-review")
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    line = line_of(out, "test-review-token-delta:")
    assert "delta -20.00%" in line
    assert "before: N=2 dispatches, mean 2000 tokens" in out
    assert "after: N=1 dispatches, mean 1600 tokens" in out


def test_every_token_field_of_a_dispatch_counts_toward_it(world, tmp_path, capsys):
    every_field = {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40}
    dispatch(world, BEFORE_BOUNDARY, 0, usage=every_field)
    dispatch(world, IN_WINDOW, 100)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "before: N=1 dispatches, mean 100 tokens" in out


def test_the_records_of_one_transcript_are_one_dispatch_whose_tokens_add_up(world, tmp_path, capsys):
    world.session("sess-a")
    records = [
        {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "usage": {"input_tokens": 40}}}
        for ts in ("2026-02-01T00:00:00Z", "2026-02-01T00:00:05Z", "2026-02-01T00:00:09Z")
    ]
    world.subagent("sess-a", "one", attributed("dev-team:test-review", *records))
    dispatch(world, IN_WINDOW, 60)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "before: N=1 dispatches, mean 120 tokens" in out
    assert "delta -50.00%" in out


def test_cumulative_cost_snapshots_are_not_dispatches(world, tmp_path, capsys):
    snapshots = [
        {"timestamp": ts, "by_agent_type": {"dev-team:test-review": {"cost_usd": 1.0, "input_tokens": tokens}}}
        for ts, tokens in ((BEFORE_BOUNDARY, 100), ("2026-02-01T00:05:00Z", 200), (IN_WINDOW, 300), ("2026-03-01T12:05:00Z", 400))
    ]
    world.stream("cost-metering", snapshots)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "no rows in window" in line_of(out, "test-review-token-delta:")


def test_a_non_numeric_usage_value_in_a_transcript_adds_no_tokens_and_does_not_crash(world, tmp_path, capsys):
    dispatch(world, BEFORE_BOUNDARY, 0, usage={"input_tokens": "many", "output_tokens": True, "cache_read_input_tokens": 25})
    dispatch(world, IN_WINDOW, 25)
    code, out, err = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "before: N=1 dispatches, mean 25 tokens" in out
    assert (code, err) == (0, "")


def test_an_empty_after_side_prints_insufficient_and_computes_no_delta(world, tmp_path, capsys):
    dispatches(world, 3, 0)
    code, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    line = line_of(out, "test-review-token-delta:")
    assert "insufficient" in line
    assert "DIRECTIONAL (confounds:" in line
    assert "before: N=3 dispatches, mean 1000 tokens" in out
    assert "after: N=0 insufficient" in out
    assert "delta: not computed" in out
    assert not re.search(r"delta [+-]\d", out)
    assert code == 0


def test_a_before_mean_of_zero_prints_insufficient_and_computes_no_delta(world, tmp_path, capsys):
    dispatches(world, 3, 1, tokens=(0, 500))
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "insufficient" in line_of(out, "test-review-token-delta:")
    assert "delta: not computed" in out
    assert not re.search(r"delta [+-]\d", out)


def test_a_metric_with_data_on_one_side_only_is_insufficient_not_no_rows(world, tmp_path, capsys):
    dispatches(world, 0, 1)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "no rows in window" not in out
    assert "insufficient" in line_of(out, "test-review-token-delta:")


def test_no_test_review_dispatch_on_either_side_prints_no_rows_in_window(world, tmp_path, capsys):
    dispatch(world, IN_WINDOW, 1000, agent="dev-team:other-review")
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "no rows in window" in line_of(out, "test-review-token-delta:")


def test_a_side_below_the_minimum_n_is_null_and_hides_the_delta(world, tmp_path, capsys):
    dispatches(world, 4, 12)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY, minimum_n=10)
    assert "NULL (N=4)" in line_of(out, "test-review-token-delta:")
    assert "mean" not in out
    assert not re.search(r"delta [+-]\d", out)
    (metric,) = json.loads(run_report(world, tmp_path, capsys, DELTA, "--json", boundary=BOUNDARY, minimum_n=10)[1])["metrics"]
    assert metric["value"] is None


@pytest.mark.parametrize(("before", "after"), [(0, 4), (4, 0)])
def test_one_empty_side_with_the_other_below_the_minimum_n_is_null_not_insufficient(world, tmp_path, capsys, before, after):
    dispatches(world, before, after)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY, minimum_n=10)
    line = line_of(out, "test-review-token-delta:")
    assert "NULL (N=4)" in line
    assert "insufficient" not in line


def test_the_window_bounds_the_after_side_only(world, tmp_path, capsys):
    for ts in ("2026-01-01T00:00:00Z", "2026-03-02T00:00:00Z", "2026-04-02T00:00:00Z"):
        dispatch(world, ts, 100)
    window = ("--window-start", "2026-03-02T00:00:00Z", "--window-end", "2026-04-01T00:00:00Z")
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, *window, boundary=BOUNDARY)
    assert "before: N=1" in out
    assert "after: N=1" in out


def test_the_directional_line_is_a_real_session_line_that_is_no_verdict_input(world, tmp_path, capsys):
    dispatches(world, 1, 1)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    line = line_of(out, "test-review-token-delta:")
    assert "DIRECTIONAL" in line
    assert "excluded from verdict inputs" in line
    assert "UNVERIFIED" not in line
    (metric,) = json.loads(run_report(world, tmp_path, capsys, DELTA, "--json", boundary=BOUNDARY)[1])["metrics"]
    assert metric["verdict_input"] is False
    assert metric["sessions"] == ["sess-a"]


def test_dispatches_of_a_session_with_no_real_transcript_are_left_out_and_counted(world, tmp_path, capsys):
    dispatches(world, 1, 1)
    world.subagent("ghost", "g1", attributed("dev-team:test-review", {"type": "assistant", "timestamp": IN_WINDOW, "message": {"usage": {"input_tokens": 9999}}}))
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "after: N=1 dispatches, mean 500 tokens" in out
    assert "left out: 1 dispatches of sessions with no real transcript" in out


def test_a_transcript_of_another_agent_in_a_session_with_no_real_transcript_is_not_counted_as_left_out(world, tmp_path, capsys):
    dispatches(world, 1, 1)
    world.subagent("ghost", "g1", attributed("dev-team:other-review", {"type": "assistant", "timestamp": IN_WINDOW, "message": {"usage": {"input_tokens": 9999}}}))
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "left out" not in out


def test_a_dispatch_with_no_timestamp_is_left_out_and_counted(world, tmp_path, capsys):
    dispatches(world, 1, 1)
    dispatch(world, None, 700)
    _, out, _ = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY)
    assert "before: N=1" in out and "after: N=1" in out
    assert "left out: 1 dispatches with no timestamp" in out


def test_a_directional_line_prints_its_status_but_leaves_the_exit_code_alone(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 1)])
    dispatches(world, 3, 0)
    code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate", *DELTA], boundary=BOUNDARY)
    assert "insufficient" in line_of(out, "test-review-token-delta:")
    assert code == 0
    payload = json.loads(run_report(world, tmp_path, capsys, ["skip-rate", *DELTA], "--json", boundary=BOUNDARY)[1])
    assert [m["exit_code"] for m in payload["metrics"]] == [0, 3]


def test_a_directional_metric_pre_registered_on_an_id_less_instrument_prints_unverified_and_directional_and_feeds_no_verdict(
    world, tmp_path, capsys
):
    dispatches(world, 1, 1, tokens=(1000, 2000))
    overrides = {"test-review-token-delta": {"instrument": "cost-metering", "identity_class": "id-less", "id_less_handling": "UNVERIFIED"}}
    code, out, err = run_report(world, tmp_path, capsys, DELTA, boundary=BOUNDARY, **overrides)
    line = line_of(out, "test-review-token-delta:")
    assert "UNVERIFIED (no session ids)" in line
    assert "DIRECTIONAL (confounds:" in line
    assert "breach" in line
    assert (code, err) == (0, "")
    (metric,) = json.loads(run_report(world, tmp_path, capsys, DELTA, "--json", boundary=BOUNDARY, **overrides)[1])["metrics"]
    assert (metric["status"], metric["exit_code"], metric["verdict_input"]) == ("breach", 1, False)


def test_an_id_less_line_prints_its_status_but_leaves_the_exit_code_alone(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 1)])
    write_usage(world, {"source-verification": {"use_count": 10}})
    code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate", "contradicted-rate"])
    assert "not entered" in line_of(out, "contradicted-rate:")
    assert code == 0


def test_a_breach_on_a_verdict_line_still_sets_the_exit_code_beside_a_directional_line(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("skill-injection", [injection("sess-a", 900)])
    dispatches(world, 1, 1)
    code, _, _ = run_report(
        world, tmp_path, capsys, ["injection-overhead", *DELTA], boundary=BOUNDARY, **{"injection-overhead": {"keep": "<= 450"}}
    )
    assert code == 1


# --- below minimum N ---------------------------------------------------------


def test_a_metric_below_the_minimum_n_prints_null_without_its_value_and_exits_3(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("ledger-skips", [consult("sess-a", 4, 2)])
    code, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"], minimum_n=10)
    assert line_of(out, "skip-rate:") == "skip-rate: NULL (N=4)"
    assert "50.00%" not in out
    assert code == 3
    (metric,) = json.loads(run_report(world, tmp_path, capsys, ["skip-rate"], "--json", minimum_n=10)[1])["metrics"]
    assert metric["value"] is None
    assert "50.00%" not in json.dumps(metric)


# --- skill verdicts and adoption ---------------------------------------------


def write_manual(world: World, document) -> Path:
    path = world.project / ".claude" / "metrics" / "benefit-manual-input.json"
    path.write_text(document if isinstance(document, str) else json.dumps(document))
    return path


def write_usage(world: World, usage: dict) -> None:
    (world.home / "artifact-usage.json").write_text(json.dumps(usage))


VERDICT = ["contradicted-rate"]


def test_the_contradicted_rate_divides_by_invocations_not_by_verdicts(world, tmp_path, capsys):
    write_usage(world, {"dev-team:source-verification": {"use_count": 10, "last_used_at": IN_WINDOW, "lifecycle": "active"}})
    write_manual(world, {"contradicted-rate": {"value": 6, "n": 30, "sessions": [], "note": "tallied from the verification reports"}})
    _, out, _ = run_report(world, tmp_path, capsys, VERDICT)
    line = line_of(out, "contradicted-rate:")
    assert "0.60 per invocation" in line
    assert "UNVERIFIED (no session ids)" in line
    assert "excluded from verdict inputs" in line
    assert "N=10 invocations" in line
    assert "DIRECTIONAL" not in line


def test_a_contradicted_rate_with_no_tally_entered_prints_not_entered_not_insufficient(world, tmp_path, capsys):
    write_usage(world, {"source-verification": {"use_count": 10}})
    _, out, _ = run_report(world, tmp_path, capsys, VERDICT)
    line = line_of(out, "contradicted-rate:")
    assert "not entered" in line
    assert "insufficient" not in line
    assert "contradicted tally: not entered in the manual-input file" in out
    (metric,) = json.loads(run_report(world, tmp_path, capsys, VERDICT, "--json")[1])["metrics"]
    assert (metric["status"], metric["exit_code"], metric["value"]) == ("not entered", 3, None)


def test_a_contradicted_tally_over_zero_invocations_is_no_rows_in_window_not_a_division(world, tmp_path, capsys):
    write_usage(world, {"source-verification": {"use_count": 0}})
    write_manual(world, {"contradicted-rate": {"value": 3, "n": 5}})
    code, out, err = run_report(world, tmp_path, capsys, VERDICT)
    assert line_of(out, "contradicted-rate:").split("UNVERIFIED (no session ids)")[1].strip().startswith("no rows in window")
    assert "contradicted verdicts entered: 3 of 5 verdicts" in out
    assert (code, err) == (0, "")


def test_the_adoption_block_needs_no_other_metric_in_the_pre_registration(world, tmp_path, capsys):
    write_usage(world, {"source-verification": {"use_count": 5}})
    code, out, err = run_report(world, tmp_path, capsys, VERDICT)
    assert "source-verification: direct invocations 5, consumer dispatches 0 ORPHAN: wire-or-archive" in out
    assert "property-based-testing: direct invocations 0, consumer dispatches 0 ORPHAN: wire-or-archive" in out
    assert (code, err) == (0, "")


def test_a_stream_metric_with_unmeasurable_handling_prints_unmeasurable_and_no_adoption_block(world, tmp_path, capsys):
    write_usage(world, {"source-verification": {"use_count": 10}})
    code, out, _ = run_report(world, tmp_path, capsys, VERDICT, **{"contradicted-rate": {"id_less_handling": "unmeasurable"}})
    assert line_of(out, "contradicted-rate:").startswith("contradicted-rate: unmeasurable")
    assert "UNVERIFIED" not in out
    assert "skill adoption" not in out
    assert code == 0


def test_artifact_usage_is_read_once_per_run_though_two_blocks_use_it(world, tmp_path, capsys, monkeypatch):
    write_usage(world, {"source-verification": {"use_count": 10}})
    usage_file = world.home / "artifact-usage.json"
    opened = []
    real_open = Path.open

    def counting_open(self, *args, **kwargs):
        opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    _, out, _ = run_report(world, tmp_path, capsys, VERDICT)
    assert "skill adoption" in out
    assert opened.count(usage_file) == 1


@pytest.mark.parametrize("use_count", [0, 500])
def test_a_skill_dispatched_to_by_no_consumer_is_an_orphan_however_often_invoked_directly(
    world, tmp_path, capsys, use_count
):
    write_usage(world, {"source-verification": {"use_count": use_count}})
    _, out, _ = run_report(world, tmp_path, capsys, VERDICT)
    assert f"source-verification: direct invocations {use_count}, consumer dispatches 0 ORPHAN: wire-or-archive" in out


def test_a_skill_with_a_consumer_dispatch_is_not_an_orphan(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("skill-injection", [injection("sess-a", 100, skills=("dev-team:source-verification",))])
    write_usage(world, {"source-verification": {"use_count": 5}})
    _, out, _ = run_report(world, tmp_path, capsys, VERDICT)
    assert "source-verification: direct invocations 5, consumer dispatches 1" in out
    assert "source-verification: direct invocations 5, consumer dispatches 1 ORPHAN" not in out


def test_an_injection_row_without_a_real_session_is_not_a_consumer_dispatch(world, tmp_path, capsys):
    world.stream("skill-injection", [injection("no-transcript", 100, skills=("source-verification",))])
    write_usage(world, {"source-verification": {"use_count": 5}})
    _, out, _ = run_report(world, tmp_path, capsys, VERDICT)
    assert "source-verification: direct invocations 5, consumer dispatches 0 ORPHAN: wire-or-archive" in out


# --- hand-entered numbers ----------------------------------------------------


def test_a_hand_entered_value_is_judged_against_its_threshold(world, tmp_path, capsys):
    world.session(LONG_ID)
    write_manual(world, {"pbt-mutants-killed": {"value": 2, "n": 10, "sessions": [LONG_ID], "note": "ten targets"}})
    code, out, _ = run_report(world, tmp_path, capsys, ["pbt-mutants-killed"])
    line = line_of(out, "pbt-mutants-killed:")
    assert "2 mutants per target" in line
    assert line.endswith("| within")
    assert LONG_ID[:8] in out
    assert LONG_ID not in out
    assert code == 0


def test_a_listed_session_with_no_real_transcript_is_counted_as_unverified_and_left_off_the_list(world, tmp_path, capsys):
    world.session(LONG_ID)
    write_manual(world, {"pbt-mutants-killed": {"value": 2, "n": 10, "sessions": [LONG_ID, "ghost-session"]}})
    _, out, _ = run_report(world, tmp_path, capsys, ["pbt-mutants-killed"])
    block = block_of(out, "pbt-mutants-killed:")
    assert f"sessions: {LONG_ID[:8]}" in block
    assert "ghost" not in out
    assert "unverified: 1" in block
    (metric,) = json.loads(run_report(world, tmp_path, capsys, ["pbt-mutants-killed"], "--json")[1])["metrics"]
    assert (metric["sessions"], metric["unverified_rows"]) == ([LONG_ID[:8]], 1)


def test_the_manual_input_option_overrides_the_default_file(world, tmp_path, capsys):
    write_manual(world, {"pbt-mutants-killed": {"value": 2, "n": 10}})
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"pbt-mutants-killed": {"value": 7, "n": 10}}))
    _, out, _ = run_report(world, tmp_path, capsys, ["pbt-mutants-killed"], "--manual-input", str(elsewhere))
    assert "7 mutants per target" in line_of(out, "pbt-mutants-killed:")
    assert "2 mutants per target" not in out


def test_a_hand_entered_value_below_its_minimum_n_is_null(world, tmp_path, capsys):
    write_manual(world, {"pbt-mutants-killed": {"value": 2, "n": 4}})
    code, out, _ = run_report(world, tmp_path, capsys, ["pbt-mutants-killed"], minimum_n=10)
    assert line_of(out, "pbt-mutants-killed:") == "pbt-mutants-killed: NULL (N=4)"
    assert code == 3


def test_a_hand_entered_metric_with_nothing_entered_prints_no_rows_in_window(world, tmp_path, capsys):
    code, out, _ = run_report(world, tmp_path, capsys, ["pbt-mutants-killed"])
    assert "no rows in window" in line_of(out, "pbt-mutants-killed:")
    assert code == 3


@pytest.mark.parametrize(
    ("document", "line", "problem"),
    [
        ('{\n  "pbt-mutants-killed": {"value": "many", "n": 10}\n}', 2, "value is not a number"),
        ('{"pbt-mutants-killed": {"value": true, "n": 10}}', 1, "value is not a number"),
        ('{"pbt-mutants-killed": {"value": 1, "n": -2}}', 1, "n is not a non-negative integer"),
        ('{"pbt-mutants-killed": {"value": 1, "n": 2, "sessions": "abc"}}', 1, "sessions is not a list"),
        ('{"pbt-mutants-killed": 3}', 1, "is not an object"),
        ('{"not-a-metric": {"value": 1, "n": 2}}', 1, "has no pre-registered metric"),
        ('{"pbt-mutants-killed": ', 1, "file is not valid JSON"),
        ("[1]", 0, "file is not a JSON object"),
    ],
)
def test_a_malformed_manual_input_file_exits_2_with_file_line_problem_and_next(world, tmp_path, capsys, document, line, problem):
    path = write_manual(world, document)
    code, _, err = run_report(world, tmp_path, capsys, ["pbt-mutants-killed"])
    assert code == 2
    assert err.startswith(f"{path}:{line}: ")
    assert problem in err
    assert ". Next: " in err


# --- row fields of the wrong type --------------------------------------------


def usage_file(world: World, usage: dict) -> Path:
    write_usage(world, usage)
    return world.home / "artifact-usage.json"


def stream_file(name: str):
    return lambda world, rows: world.stream(name, rows)


def usage_writer(world, rows):
    return usage_file(world, rows[0])


# Each case: id, metrics to run, writer, the bad rows, and the problem the error names.
_ROW_SCHEMA = [
    ("candidate-pairs-negative", ["skip-rate"], stream_file("ledger-skips"), [{**consult("sess-a", 1, 0), "candidate_pairs": -1}], "'candidate_pairs' is not a non-negative integer"),
    ("candidate-pairs-bool", ["skip-rate"], stream_file("ledger-skips"), [{**consult("sess-a", 1, 0), "candidate_pairs": True}], "'candidate_pairs' is not a non-negative integer"),
    ("skipped-pairs-text", ["skip-rate"], stream_file("ledger-skips"), [{**consult("sess-a", 1, 0), "skipped_pairs": "2"}], "'skipped_pairs' is not a non-negative integer"),
    ("skipped-pairs-float", ["skip-rate"], stream_file("ledger-skips"), [{**consult("sess-a", 1, 0), "skipped_pairs": 1.5}], "'skipped_pairs' is not a non-negative integer"),
    ("lenses-text", ["abort-yield"], stream_file("checkpoint-aborts"), [abort_row("sess-a", True, "security-review")], "'deferred_lenses' is not a list of names"),
    ("lenses-number-item", ["abort-yield"], stream_file("checkpoint-aborts"), [abort_row("sess-a", True, [3])], "'deferred_lenses' is not a list of names"),
    ("added-chars-text", ["injection-overhead"], stream_file("skill-injection"), [{**injection("sess-a", 1), "added_chars": "100"}], "'added_chars' is not an int"),
    ("added-chars-bool", ["injection-overhead"], stream_file("skill-injection"), [{**injection("sess-a", 1), "added_chars": True}], "'added_chars' is not an int"),
    ("agent-type-number", ["injection-uptake"], stream_file("skill-injection"), [{**injection("sess-a", 1), "agent_type": 5}], "'agent_type' is not a str"),
    ("uptake-skills-text", ["injection-uptake"], stream_file("skill-injection"), [{**injection("sess-a", 1), "skills": "api-design"}], "'skills' is not a list of skill names"),
    ("uptake-skills-number-item", ["injection-uptake"], stream_file("skill-injection"), [{**injection("sess-a", 1), "skills": ["api-design", 3]}], "'skills' is not a list of skill names"),
    ("adoption-skills-number", VERDICT, stream_file("skill-injection"), [{**injection("sess-a", 1), "skills": 5}], "'skills' is not a list of skill names"),
    ("adoption-skills-number-item", VERDICT, stream_file("skill-injection"), [{**injection("sess-a", 1), "skills": [3]}], "'skills' is not a list of skill names"),
    ("classification-list", ["guard-divergence"], stream_file("subagent-stops"), [{**stop("sess-a", "clean"), "classification": ["clean"]}], "'classification' is not a str"),
    ("classification-missing", ["guard-divergence"], stream_file("subagent-stops"), [{"ts": IN_WINDOW, "session_id": "sess-a"}], "'classification' is not a str"),
    ("use-count-negative", VERDICT, usage_writer, [{"source-verification": {"use_count": -1}}], "use_count is not a non-negative integer"),
    ("use-count-bool", VERDICT, usage_writer, [{"source-verification": {"use_count": True}}], "use_count is not a non-negative integer"),
    ("use-count-text", VERDICT, usage_writer, [{"source-verification": {"use_count": "3"}}], "use_count is not a non-negative integer"),
]
ROW_SCHEMA_CASES = [pytest.param(*case[1:], id=case[0]) for case in _ROW_SCHEMA]


@pytest.mark.parametrize(("ids", "write", "rows", "problem"), ROW_SCHEMA_CASES)
def test_a_row_field_of_the_wrong_type_exits_2_with_file_line_problem_and_next(world, tmp_path, capsys, ids, write, rows, problem):
    world.session("sess-a")
    path = write(world, rows)
    code, _, err = run_report(world, tmp_path, capsys, ids, boundary=BOUNDARY)
    assert code == 2
    assert_input_error(err, path, 1, problem)


# --- tiered-findings expand rate ---------------------------------------------


def render(session_id: str, report: str, expand: str = "none", ts: str = IN_WINDOW) -> dict:
    return {"ts": ts, "session_id": session_id, "report": report, "findings": 3, "expand": expand}


def test_expand_rate_counts_each_report_once_and_expanded_when_any_render_expanded(world, tmp_path, capsys):
    world.session("sess-a")
    world.session("sess-b")
    world.stream(
        "tiered-renders",
        [
            render("sess-a", "r1"),
            render("sess-a", "r1", "one"),
            render("sess-a", "r1", "all"),
            render("sess-a", "r2"),
            render("sess-b", "r1"),
            render("sess-b", "r3"),
        ],
    )
    code, out, _ = run_report(world, tmp_path, capsys, ["expand-rate"])
    line = line_of(out, "expand-rate:")
    assert "25.00% (1/4)" in line
    assert "N=4 rendered reports" in line
    assert "breach" in line
    assert code == 1


def test_expand_rate_exactly_on_its_ceiling_is_within(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("tiered-renders", [render("sess-a", f"r{i}") for i in range(5)] + [render("sess-a", "r0", "one")])
    code, out, _ = run_report(world, tmp_path, capsys, ["expand-rate"])
    line = line_of(out, "expand-rate:")
    assert "20.00% (1/5)" in line
    assert line.endswith("within")
    assert code == 0


def test_expand_rate_leaves_rows_without_a_real_session_out_of_the_rate(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("tiered-renders", [render("sess-a", "r1"), render("ghost", "r2", "all"), {**render("", "r3", "one")}])
    _, out, _ = run_report(world, tmp_path, capsys, ["expand-rate"])
    block = block_of(out, "expand-rate:")
    assert "0.00% (0/1)" in block
    assert "unverified: 2" in block


def test_expand_rate_rejects_an_unknown_expand_value(world, tmp_path, capsys):
    world.session("sess-a")
    path = world.stream("tiered-renders", [render("sess-a", "r1", "some")])
    code, _, err = run_report(world, tmp_path, capsys, ["expand-rate"])
    assert code == 2
    assert_input_error(err, path, 1, "row field 'expand'")


# --- unmeasurable ------------------------------------------------------------


NO_INSTRUMENT_CELLS = {"instrument": "none", "identity_class": "id-less", "id_less_handling": "unmeasurable"}


def test_a_metric_with_no_instrument_prints_unmeasurable_and_does_not_change_the_exit_code(world, tmp_path, capsys):
    code, out, _ = run_report(
        world, tmp_path, capsys, ["expand-rate", "report-size-cut"], **{"expand-rate": NO_INSTRUMENT_CELLS}
    )
    assert "expand-rate: unmeasurable" in out
    assert "report-size-cut: unmeasurable" in out
    assert code == 0


# --- the real pre-registration -----------------------------------------------


def test_the_real_pre_registration_reports_every_metric_with_no_data(world, tmp_path, capsys):
    code = cli.main(cli_argv("report", world, REAL_PREREG, "--prereg-posted", POSTED, "--boundary", BOUNDARY))
    out = capsys.readouterr().out
    for metric_id in real_entries():
        assert f"\n{metric_id}: " in out
    assert "expand-rate: no rows in window" in out
    assert "UNVERIFIED (no session ids)" in out
    assert code == 3


def _own(metric_id: str) -> tuple[int, float]:
    """A real entry's own minimum N and keep limit."""
    entry = real_entries()[metric_id]
    return entry["minimum_n"], prereg_module.parse_threshold(entry["keep"]).limit


def _whole(limit: float) -> int:
    """A limit as the integer a row field needs; fails rather than truncates a fractional one."""
    assert float(limit).is_integer(), limit
    return int(limit)


def test_the_real_pre_registration_with_data_reports_each_metrics_own_status(world, tmp_path, capsys):
    # Inputs derive from each metric's own entry, so editing a threshold or a minimum N cannot silently change the expected status.
    skip_n, skip_limit = _own("skip-rate")
    overhead_n, overhead_limit = _own("injection-overhead")
    pbt_n, pbt_limit = _own("pbt-mutants-killed")
    verdict_n, _ = _own("contradicted-rate")
    for i in range(3):
        world.session(f"sess-{i}")
    # A skip rate exactly on its floor, over enough candidate pairs to clear the minimum N.
    world.stream("ledger-skips", [consult("sess-0", 100 * skip_n, _whole(skip_limit * skip_n))])
    world.stream("skill-injection", [injection("sess-1", _whole(overhead_limit) + 100)] * overhead_n)
    world.stream("subagent-stops", [stop("sess-2", "clean")])
    dispatches(world, 1, 1)
    write_usage(world, {"source-verification": {"use_count": verdict_n}})
    write_manual(world, {"pbt-mutants-killed": {"value": pbt_limit, "n": pbt_n}})
    code = cli.main(cli_argv("report", world, REAL_PREREG, "--prereg-posted", POSTED, "--boundary", BOUNDARY, "--json"))
    payload = json.loads(capsys.readouterr().out)
    statuses = {m["metric_id"]: m["status"] for m in payload["metrics"]}
    assert statuses["skip-rate"] == "within"
    assert statuses["injection-overhead"] == "breach"
    assert statuses["pbt-mutants-killed"] == "within"
    assert statuses["findings-parity"] == "no rows in window"
    assert statuses["guard-divergence"] == "NULL (N=1)"
    assert statuses["test-review-token-delta"] == "NULL (N=1)"
    assert statuses["contradicted-rate"] == "not entered"
    assert statuses["expand-rate"] == "no rows in window"
    assert code == payload["exit_code"] == 1
