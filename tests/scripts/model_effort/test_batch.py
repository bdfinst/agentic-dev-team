"""A stress batch: every agent at one model tier, one combined estimate, one approval."""

from __future__ import annotations

import dataclasses
import io
import json
import re

import pytest
from ab_inputs import make_file_fixture, write_agent_file, write_expected
from ab_results import CLI_FAILURE_RECORD
from ab_world import cli_canned, deps_with_canned_trials, stderr_lines
from model_effort import external
from model_effort.approval import DECLINED_MESSAGE, NO_TTY_MESSAGE
from model_effort.arm import BASELINE_LABEL
from model_effort.stress_arms import STEP_DOWN_LABEL, STEP_UP_LABEL
from model_effort.verdict import DECISION_KEEP
from test_stress_run import OPUS_PRICING

ESTIMATE_TOTAL_RE = re.compile(r"total \$(\d+\.\d{4})$")


def _batch_deps(world, **overrides):
    deps = dataclasses.replace(world.deps, pricing_table=OPUS_PRICING, **overrides)
    return deps_with_canned_trials(deps)


def _batch(world, *args, yes=True, **overrides):
    deps, calls = _batch_deps(world, **overrides)
    code = cli_canned(
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


def test_batch_skips_agents_on_other_tiers(world, capsys):
    # quick could run (it has a fixture), so only its tier keeps it out.
    paths = world.deps.eval_paths
    write_agent_file(paths.agents_dir, "quick", "Read", model="haiku", effort="low")
    write_expected(paths.expected_dir, "quick-only", "quick", "pass")
    make_file_fixture(paths.fixtures_dir, "quick-only.txt", "quick")

    code, _ = _batch(world)

    assert code == 0
    assert set(_artifacts(world)) == {"scout", "other"}
    assert not any(line.startswith("  quick:") for line in stderr_lines(capsys))


def test_batch_lists_each_skipped_agent_with_its_reason(world, capsys):
    _batch(world)

    lines = stderr_lines(capsys)
    assert any(line.startswith("  lonely: ") for line in lines), lines
    assert any(line.startswith("  write-capable: ") for line in lines), lines


def test_batch_prints_one_combined_estimate_summing_every_agent(world, capsys):
    _batch(world)

    lines = stderr_lines(capsys)
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
        line for line in stderr_lines(capsys) if line.startswith("Batch estimate")
    )
    assert "rubric judge $2.0000" in batch_line


def test_batch_asks_once_and_runs_nothing_when_declined(world, capsys):
    code, calls = _batch(
        world, yes=False, stdin=io.StringIO("n\n"), stdin_is_tty=lambda: True
    )

    err = capsys.readouterr().err
    assert (code, calls, world.artifacts) == (1, [], [])
    assert err.count("Proceed? [y/N]") == 1
    assert err.endswith(f"Proceed? [y/N] error: {DECLINED_MESSAGE}\n")


def test_batch_without_yes_and_no_tty_refuses_and_runs_nothing(world, capsys):
    code, calls = _batch(world, yes=False, stdin_is_tty=lambda: False)

    lines = stderr_lines(capsys)
    assert (code, calls, world.artifacts) == (1, [], [])
    assert f"error: {NO_TTY_MESSAGE}" in lines
    assert not any("Proceed?" in line for line in lines)


def test_batch_refuses_a_combined_estimate_above_max_cost(world, capsys):
    code, calls = _batch(world, "--max-cost", "0.0000001")

    lines = stderr_lines(capsys)
    assert (code, calls) == (2, [])
    assert any(
        line.startswith("error: batch estimate $")
        and line.endswith(
            "is above --max-cost $0.0000: raise --max-cost, or lower --trials"
        )
        for line in lines
    ), lines


def test_batch_with_no_runnable_agent_is_a_usage_error(world, capsys):
    deps, calls = _batch_deps(world)

    code = cli_canned(world, deps, "--batch", "haiku", "--trials", "1")

    assert (code, calls) == (2, [])
    assert (
        "error: no agent at the haiku tier can run a stress batch (none found)"
        in stderr_lines(capsys)
    )


def test_batch_and_an_agent_name_together_are_a_usage_error(world, capsys):
    deps, calls = _batch_deps(world)

    code = cli_canned(world, deps, "scout", "--batch", "sonnet")

    assert (code, calls) == (2, [])
    assert (
        "error: --batch runs every agent at its tier: drop the agent name"
        in stderr_lines(capsys)
    )


@pytest.mark.parametrize(
    "flag", [("--model", "haiku"), ("--effort", "low"), ("--fixtures", "clean-form")]
)
def test_batch_with_a_per_agent_flag_is_a_usage_error(world, capsys, flag):
    deps, calls = _batch_deps(world)

    code = cli_canned(world, deps, "--batch", "sonnet", *flag)

    assert (code, calls, world.artifacts) == (2, [], [])
    assert (
        "error: --batch picks each agent's arms and fixtures: drop --model, "
        "--effort and --fixtures"
    ) in stderr_lines(capsys)


def test_neither_an_agent_nor_a_batch_is_a_usage_error(world, capsys):
    deps, calls = _batch_deps(world)

    code = cli_canned(world, deps, "--trials", "1")

    assert (code, calls) == (2, [])
    assert "error: name an agent, or pass --batch haiku|sonnet|opus" in (
        stderr_lines(capsys)
    )


def test_batch_lists_an_agent_with_unreadable_frontmatter_as_skipped(world, capsys):
    (world.deps.eval_paths.agents_dir / "broken.md").write_text(
        "no frontmatter here\n", encoding="utf-8"
    )

    code, _ = _batch(world)

    lines = stderr_lines(capsys)
    assert code == 0
    assert "broken" not in _artifacts(world)
    assert any(
        line.startswith("  broken: cannot read frontmatter of agent 'broken'")
        for line in lines
    ), lines


def test_batch_lists_an_agent_whose_model_validator_drifted_as_skipped(
    world, capsys, monkeypatch
):
    def drifted(_value, _enum):
        raise external.ExternalContractError("_model_is_valid drifted")

    monkeypatch.setattr(external, "model_is_valid", drifted)

    code, calls = _batch(world)

    lines = stderr_lines(capsys)
    assert code == 2
    assert calls == []
    assert any(
        "scout: " in line and "_model_is_valid drifted" in line for line in lines
    ), lines


def test_batch_on_the_effort_axis_steps_effort_for_every_agent(world):
    code, _ = _batch(world, "--axis", "effort")

    assert code == 0
    for data in _artifacts(world).values():
        assert {arm["label"]: (arm["model"], arm["effort"]) for arm in data["arms"]} == {
            BASELINE_LABEL: ("sonnet", "high"),
            STEP_DOWN_LABEL: ("sonnet", "medium"),
            STEP_UP_LABEL: ("sonnet", "xhigh"),
        }


def test_batch_skips_the_recall_gap_agent(world, capsys):
    write_agent_file(
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
        for line in stderr_lines(capsys)
    )


def test_batch_stops_after_an_agent_run_that_does_not_complete(world, capsys):
    deps = dataclasses.replace(world.deps, pricing_table=OPUS_PRICING)
    deps, calls = deps_with_canned_trials(deps, overrides={0: CLI_FAILURE_RECORD})

    code = cli_canned(world, deps, "--batch", "sonnet", "--trials", "1")

    artifacts = _artifacts(world)
    assert (code, len(calls)) == (1, 1)
    assert list(artifacts) == ["other"]
    assert artifacts["other"]["status"] == "incomplete"
    assert artifacts["other"]["verdict"]["decision"] == DECISION_KEEP
    assert "error: batch stopped after other; not run: scout" in stderr_lines(capsys)


# --- the spend limit across the batch -------------------------------------------

# A trial cost so large that the tiny fixtures' estimate stays far below the limit.
BIG_TRIAL_COST = 1.0
# `other` runs first (3 arms, 1 fixture, 1 trial): three trials charge exactly this.
LIMIT_USED_BY_OTHER = "3"


def _batch_with_trial_cost(world, cost, *args):
    deps = dataclasses.replace(world.deps, pricing_table=OPUS_PRICING)
    deps, calls = deps_with_canned_trials(deps, cost=cost)
    code = cli_canned(world, deps, "--batch", "sonnet", "--trials", "1", *args)
    return code, calls


def test_batch_does_not_start_an_agent_once_the_spend_limit_is_used_up(world, capsys):
    code, calls = _batch_with_trial_cost(
        world, BIG_TRIAL_COST, "--max-cost", LIMIT_USED_BY_OTHER
    )

    artifacts = _artifacts(world)
    assert (code, len(calls)) == (1, 3)
    assert list(artifacts) == ["other"]
    assert artifacts["other"]["status"] == "complete"
    assert "error: spend limit reached; not run: scout" in stderr_lines(capsys)


def test_batch_gives_the_next_agent_only_what_is_left_of_the_limit(world, capsys):
    # other charges 2.25 of 3; scout gets 0.75: its second trial goes above it.
    code, calls = _batch_with_trial_cost(world, 0.75, "--max-cost", LIMIT_USED_BY_OTHER)

    artifacts = _artifacts(world)
    assert (code, len(calls)) == (1, 5)
    assert artifacts["scout"]["status"] == "incomplete"
    assert artifacts["scout"]["abort_reason"] == "max-cost"
    assert "error: batch stopped after scout; not run: none" in stderr_lines(capsys)


def _pinned_arm_estimates(monkeypatch, usd_per_arm):
    from model_effort import estimate

    real = estimate.estimate_run

    def pinned(*args, **kwargs):
        run_estimate = real(*args, **kwargs)
        return dataclasses.replace(
            run_estimate,
            by_arm=tuple((label, usd_per_arm) for label, _ in run_estimate.by_arm),
        )

    monkeypatch.setattr(estimate, "estimate_run", pinned)


def test_batch_estimate_equal_to_max_cost_runs(world, monkeypatch):
    # 2 agents x 3 arms x 0.5 = 3.0, exactly the limit.
    _pinned_arm_estimates(monkeypatch, 0.5)

    code, calls = _batch(world, "--max-cost", "3")

    assert (code, len(calls)) == (0, 9)


def test_batch_estimate_just_above_max_cost_is_refused(world, monkeypatch, capsys):
    _pinned_arm_estimates(monkeypatch, 0.5)

    code, calls = _batch(world, "--max-cost", "2.99")

    assert (code, calls) == (2, [])
    assert (
        "error: batch estimate $3.0000 is above --max-cost $2.9900: raise --max-cost, "
        "or lower --trials"
    ) in stderr_lines(capsys)
