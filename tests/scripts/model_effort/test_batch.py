"""A stress batch: every agent at one model tier, one combined estimate, one approval."""

from __future__ import annotations

import dataclasses
import io
import json
import re

from _model_effort_support import (
    CLI_FAILURE_RECORD,
    _cli_canned,
    _deps_with_canned_trials,
    _stderr_lines,
    _write_agent,
)
from model_effort.verdict import DECISION_KEEP
from test_stress_run import OPUS_PRICING

ESTIMATE_TOTAL_RE = re.compile(r"total \$(\d+\.\d{4})$")


def _batch_deps(world, **overrides):
    deps = dataclasses.replace(world.deps, pricing_table=OPUS_PRICING, **overrides)
    return _deps_with_canned_trials(deps)


def _batch(world, *args, yes=True, **overrides):
    deps, calls = _batch_deps(world, **overrides)
    code = _cli_canned(
        world, deps, "--batch", "sonnet", "--trials", "1", *args, yes=yes
    )
    return code, calls


def _artifacts(world) -> dict[str, dict]:
    written = [json.loads(p.read_text(encoding="utf-8")) for p in world.artifacts]
    return {data["agent"]: data for data in written}


def test_batch_runs_a_stress_run_for_every_runnable_agent_at_the_tier(world):
    code, calls = _batch(world)

    artifacts = _artifacts(world)
    assert code == 0
    assert sorted(artifacts) == ["other", "scout"]
    # scout: 2 fixtures, other: 1 fixture; 3 arms, 1 trial each
    assert len(calls) == 9
    assert all(data["mode"] == "stress" for data in artifacts.values())


def test_batch_skips_agents_on_other_tiers(world):
    _write_agent(
        world.deps.eval_paths.agents_dir, "quick", "Read", model="haiku", effort="low"
    )

    _batch(world)

    assert "quick" not in _artifacts(world)


def test_batch_lists_each_skipped_agent_with_its_reason(world, capsys):
    _batch(world)

    lines = _stderr_lines(capsys)
    assert any(line.startswith("  lonely: ") for line in lines), lines
    assert any(line.startswith("  write-capable: ") for line in lines), lines


def test_batch_prints_one_combined_estimate_summing_every_agent(world, capsys):
    _batch(world)

    lines = _stderr_lines(capsys)
    per_agent = [
        float(match[1])
        for line in lines
        if line.startswith("Estimate ") and (match := ESTIMATE_TOTAL_RE.search(line))
    ]
    batch_line = next(line for line in lines if line.startswith("Batch estimate"))
    batch_total = float(ESTIMATE_TOTAL_RE.search(batch_line)[1])
    assert len(per_agent) == 2
    # each printed figure is rounded to 4 decimals
    assert abs(batch_total - sum(per_agent)) <= 0.0001 * len(per_agent)
    assert "2 agents" in batch_line


def test_batch_estimate_includes_the_rubric_judge(world, capsys, monkeypatch):
    from model_effort import estimate

    real = estimate.estimate_run

    def with_judge(*args, **kwargs):
        return dataclasses.replace(real(*args, **kwargs), judge_usd=1.0)

    monkeypatch.setattr(estimate, "estimate_run", with_judge)

    _batch(world)

    batch_line = next(
        line for line in _stderr_lines(capsys) if line.startswith("Batch estimate")
    )
    assert "rubric judge $2.0000" in batch_line


def test_batch_asks_once_and_runs_nothing_when_declined(world, capsys):
    code, calls = _batch(
        world, yes=False, stdin=io.StringIO("n\n"), stdin_is_tty=lambda: True
    )

    assert (code, calls, world.artifacts) == (1, [], [])
    assert capsys.readouterr().err.count("Proceed? [y/N]") == 1


def test_batch_refuses_a_combined_estimate_above_max_cost(world):
    code, calls = _batch(world, "--max-cost", "0.0000001")

    assert (code, calls) == (2, [])


def test_batch_with_no_runnable_agent_is_a_usage_error(world, capsys):
    deps, calls = _batch_deps(world)

    code = _cli_canned(world, deps, "--batch", "haiku", "--trials", "1")

    assert (code, calls) == (2, [])
    assert "no agent" in capsys.readouterr().err


def test_batch_and_an_agent_name_together_are_a_usage_error(world):
    deps, calls = _batch_deps(world)

    code = _cli_canned(world, deps, "scout", "--batch", "sonnet")

    assert (code, calls) == (2, [])


def test_neither_an_agent_nor_a_batch_is_a_usage_error(world):
    deps, calls = _batch_deps(world)

    code = _cli_canned(world, deps, "--trials", "1")

    assert (code, calls) == (2, [])


def test_batch_skips_the_recall_gap_agent(world, capsys):
    _write_agent(
        world.deps.eval_paths.agents_dir,
        "correctness-review",
        "Read",
        model="sonnet",
        effort="high",
    )

    _batch(world)

    assert "correctness-review" not in _artifacts(world)
    assert any(
        line.startswith("  correctness-review: ") and "recall gap" in line
        for line in _stderr_lines(capsys)
    )


def test_batch_stops_after_an_agent_run_that_does_not_complete(world):
    deps = dataclasses.replace(world.deps, pricing_table=OPUS_PRICING)
    deps, calls = _deps_with_canned_trials(deps, overrides={0: CLI_FAILURE_RECORD})

    code = _cli_canned(world, deps, "--batch", "sonnet", "--trials", "1")

    artifacts = _artifacts(world)
    assert (code, len(calls)) == (1, 1)
    assert list(artifacts) == ["other"]
    assert artifacts["other"]["status"] == "incomplete"
    assert artifacts["other"]["verdict"]["decision"] == DECISION_KEEP
