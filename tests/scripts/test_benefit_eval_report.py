"""Benefit report: the metric modules and the ``report`` command.

Covers scripts/lib/benefit_eval/formatting.py, metrics_ledger.py, metrics_hooks.py
and metrics_cost.py through scripts/benefit_eval_cli.py, which this file loads by
file path as the audit tests do.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

# Both import roots are added here so no import relies on a side effect of another.
sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "benefit_eval_cli_report", REPO_ROOT / "scripts" / "benefit_eval_cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

REAL_PREREG = REPO_ROOT / "docs" / "benefit-eval" / "preregistration.md"
LONG_ID = str(uuid.UUID("0123abcd-4567-89ab-cdef-0123456789ab"))

IN_WINDOW = "2026-03-01T12:00:00Z"
BEFORE_WINDOW = "2026-01-01T12:00:00Z"
WINDOW_START = "2026-02-01T00:00:00Z"


def real_entries() -> dict[str, dict]:
    text = REAL_PREREG.read_text()
    start = text.index("```json prereg\n") + len("```json prereg\n")
    return {entry["id"]: entry for entry in json.loads(text[start : text.index("\n```", start)])["metrics"]}


class World:
    """A project root, a home metrics dir and a transcript tree under tmp_path."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.project = tmp_path / "project"
        self.home = tmp_path / "home-metrics"
        self.projects = tmp_path / "projects"
        for directory in (self.project / ".claude" / "metrics", self.home, self.projects / "proj-a"):
            directory.mkdir(parents=True)

    def stream(self, name: str, rows: list[dict]) -> Path:
        path = self.project / ".claude" / "metrics" / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def session(self, session_id: str, content: str = '{"type":"user"}\n') -> None:
        """A real session: a main transcript that parses."""
        (self.projects / "proj-a" / f"{session_id}.jsonl").write_text(content)

    def subagent(self, session_id: str, agent_id: str, records: list[dict]) -> Path:
        directory = self.projects / "proj-a" / session_id / "subagents"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"agent-{agent_id}.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
        return path

    def snapshot(self) -> dict[str, bytes | None]:
        return {
            str(p.relative_to(self.root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(self.root.rglob("*"))
        }


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


def run_report(world: World, tmp_path: Path, capsys, ids: list[str], *extra: str, minimum_n: int = 1, **overrides):
    prereg_path = write_prereg(tmp_path, ids, minimum_n, **overrides)
    code = cli.main(
        [
            "report",
            "--prereg", str(prereg_path),
            "--project-root", str(world.project),
            "--home-metrics", str(world.home),
            "--projects-root", str(world.projects),
            *extra,
        ]
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
    assert "20.69" in out
    assert code == 0


def test_skip_rate_splits_first_runs_from_repeat_runs(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream(
        "ledger-skips",
        [consult("sess-a", 10, 0, "2026-03-01T10:00:00Z"), consult("sess-a", 10, 5, "2026-03-01T11:00:00Z")],
    )
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert "first runs: 0.00% (0/10)" in out
    assert "repeat runs: 50.00% (5/10)" in out


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


def guard_world(world: World, count: int = 30) -> None:
    """``count`` flagged stops, each in its own session with its own subagent transcript."""
    rows = []
    for i in range(count):
        session_id = f"{i:08d}-aaaa-bbbb-cccc-dddddddddddd"
        world.session(session_id)
        ts = f"2026-03-01T12:{i:02d}:00Z"
        world.subagent(session_id, f"a{i:02d}", [{"type": "assistant", "timestamp": ts, "message": {"content": []}}])
        rows.append(stop(session_id, "empty-final-turn" if i % 2 else "truncated-final-turn", ts))
    world.stream("subagent-stops", rows)


def sample_lines(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if line.strip().startswith("session=")]


def test_the_same_seed_gives_the_same_twenty_line_sample_and_another_seed_a_different_one(world, tmp_path, capsys):
    guard_world(world)
    first = sample_lines(run_report(world, tmp_path, capsys, ["guard-divergence"], "--seed", "1")[1])
    again = sample_lines(run_report(world, tmp_path, capsys, ["guard-divergence"], "--seed", "1")[1])
    other = sample_lines(run_report(world, tmp_path, capsys, ["guard-divergence"], "--seed", "2")[1])
    assert len(first) == 20
    assert first == again
    assert first != other


def test_sample_lines_carry_session_classification_agent_and_transcript_from_discovery(world, tmp_path, capsys):
    guard_world(world, count=3)
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    lines = sample_lines(out)
    assert len(lines) == 3
    for line in lines:
        session, classification, agent, transcript = (part.split("=", 1)[1] for part in line.split())
        index = int(session)
        assert classification in ("empty-final-turn", "truncated-final-turn")
        assert agent == f"a{index:02d}"
        assert transcript == f"proj-a/{session}*/subagents/agent-a{index:02d}.jsonl"
    assert f"{0:08d}-aaaa-bbbb-cccc-dddddddddddd" not in out


def test_a_flagged_stop_with_no_subagent_transcript_prints_unmatched(world, tmp_path, capsys):
    world.session("sess-a")
    world.stream("subagent-stops", [stop("sess-a", "empty-final-turn")])
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert "agent=unmatched transcript=none" in out


def test_a_sample_smaller_than_twenty_lists_every_flagged_stop(world, tmp_path, capsys):
    guard_world(world, count=5)
    _, out, _ = run_report(world, tmp_path, capsys, ["guard-divergence"])
    assert len(sample_lines(out)) == 5


# --- missing scope marker ----------------------------------------------------


def test_missing_scope_marker_count_is_split_by_whether_the_session_ran_a_consult(world, tmp_path, capsys):
    sessions = [f"sess-{i}" for i in range(5)]
    for session in sessions:
        world.session(session)
    world.stream("ledger-skips", [consult(s, 4, 1) for s in sessions[3:]])
    events = [
        {"ts": IN_WINDOW, "session_id": s, "hook": "review_verdict_recorder", "decision": "record", "matched_rule": "missing-scope-marker"}
        for s in sessions
    ]
    events.append({**events[0], "matched_rule": "unparseable-result"})
    (world.project / ".claude" / "metrics" / "boundary-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    _, out, _ = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert "missing-scope-marker: direct=3 consult=2" in out


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


def test_a_window_bound_that_is_not_utc_with_z_exits_2(world, tmp_path, capsys):
    with pytest.raises(SystemExit) as raised:
        run_report(world, tmp_path, capsys, ["skip-rate"], "--window-start", "2026-02-01T00:00:00+00:00")
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


# --- unreadable input --------------------------------------------------------


def test_a_malformed_instrument_line_exits_2_with_file_line_problem_and_next(world, tmp_path, capsys):
    path = world.stream("ledger-skips", [consult("sess-a", 1, 0)])
    path.write_text(path.read_text() + "not json\n")
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert code == 2
    assert re.match(r".+ledger-skips\.jsonl:2: line is not valid JSON\. Next: .+", err)


def test_a_row_with_a_bad_timestamp_exits_2_naming_its_line(world, tmp_path, capsys):
    world.stream("ledger-skips", [{**consult("sess-a", 1, 0), "ts": "yesterday"}])
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"])
    assert code == 2
    assert "ledger-skips.jsonl:1:" in err


def test_a_missing_pre_registration_exits_2(world, tmp_path, capsys):
    code = cli.main(["report", "--prereg", str(tmp_path / "nope.md"), "--project-root", str(world.project)])
    assert code == 2
    assert "pre-registration file not found" in capsys.readouterr().err


def test_a_metric_the_report_cannot_compute_exits_2_naming_it(world, tmp_path, capsys):
    code, _, err = run_report(world, tmp_path, capsys, ["skip-rate"], **{"skip-rate": {"id": "mystery-metric"}})
    assert code == 2
    assert "mystery-metric" in err


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


def test_report_leaves_every_input_and_the_listing_unchanged(world, tmp_path, capsys):
    guard_world(world, count=3)
    world.stream("ledger-skips", [consult("00000001-aaaa-bbbb-cccc-dddddddddddd", 4, 1)])
    prereg_path = write_prereg(tmp_path, ["skip-rate", "guard-divergence"])
    before = world.snapshot()
    code = cli.main(
        ["report", "--prereg", str(prereg_path), "--project-root", str(world.project), "--home-metrics", str(world.home), "--projects-root", str(world.projects)]
    )
    capsys.readouterr()
    assert code in (0, 1, 3)
    assert world.snapshot() == before
