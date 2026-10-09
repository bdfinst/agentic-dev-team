"""Cost estimation (model_effort.estimate)."""

from __future__ import annotations

from pathlib import Path

import pytest
from _model_effort_support import (
    BASELINE_TWO_ARM_ESTIMATE,
    CANDIDATE_TWO_ARM_ESTIMATE,
    PINNED_OUTPUT_TOKENS,
    PINNED_TURN_MULTIPLIER,
    SCOUT_HAIKU_ARGS,
    SCOUT_TRIALS,
    TEST_PRICING,
    _arm_block,
    _cli,
    _make_directory_fixture,
    _make_file_fixture,
    _passing_stub,
    _run_estimate,
    _trial_result,
    _written,
)
from model_effort import estimate, invocation
from model_effort import fixtures as fixture_resolution
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL, Arm
from model_effort.errors import UsageError
from model_effort.outcome import Outcome


def _file_fixture_of_size(
    root: Path, name: str, size: int
) -> fixture_resolution.ResolvedFixture:
    path = root / name
    path.write_bytes(b"x" * size)
    return fixture_resolution.ResolvedFixture(
        stem=path.stem,
        path=path,
        kind=fixture_resolution.FixtureKind.FILE,
        expected_clean=False,
    )


def _priced_arm(label: str, model: str) -> Arm:
    return Arm(label=label, model=model, effort="high")


class TestFixtureSize:
    def test_file_size_is_its_byte_count(self, tmp_path):
        fixture = _make_file_fixture(tmp_path, "form.html", "<form></form>")

        assert estimate.fixture_size_bytes(fixture) == 13

    def test_directory_size_sums_every_file_in_nested_directories(self, tmp_path):
        fixture = _make_directory_fixture(tmp_path)

        assert estimate.fixture_size_bytes(fixture) == 6 + 12 + 13


class TestEstimateRun:
    @pytest.fixture(autouse=True)
    def pinned_constants(self, monkeypatch):
        monkeypatch.setattr(estimate, "TOOL_TURN_MULTIPLIER", PINNED_TURN_MULTIPLIER)
        monkeypatch.setattr(estimate, "OUTPUT_TOKENS_PER_TRIAL", PINNED_OUTPUT_TOKENS)

    def _estimate(
        self, tmp_path, fixtures, arms=None, trials=3, pricing_table=TEST_PRICING
    ):
        # Each trial sends 4000 chars (system prompt padded to fill what the 3000-char
        # fixture and the user prompt leave) = 1000 tokens, doubled by the pinned
        # turn multiplier.
        arms = arms or [
            _priced_arm("baseline", "sonnet"),
            _priced_arm("candidate", "haiku"),
        ]
        prompt_chars = len(invocation.build_user_prompt(fixtures[0].path.name))
        system_prompt = "s" * (4000 - 3000 - prompt_chars)
        return estimate.estimate_run(
            arms, system_prompt, fixtures, trials, pricing_table
        )

    def test_each_arm_costs_input_plus_output_priced_times_fixtures_times_trials(
        self, tmp_path
    ):
        fixtures = [
            _file_fixture_of_size(tmp_path, "a.txt", 3000),
            _file_fixture_of_size(tmp_path, "b.txt", 3000),
        ]

        result = self._estimate(tmp_path, fixtures)

        # Per trial across both fixtures: 4000 input tokens, 200 output tokens.
        # pricey: (4000*4 + 200*20) / 1e6 = 0.02, x3 trials. cheap: (4000*1 + 200*5) / 1e6 = 0.005, x3.
        assert result.cost_usd_for_arm("baseline") == pytest.approx(0.06)
        assert result.cost_usd_for_arm("candidate") == pytest.approx(0.015)
        assert result.estimated_total_usd == pytest.approx(0.075)

    def test_directory_fixture_counts_the_summed_size_of_its_files(self, tmp_path):
        directory = tmp_path / "d" / "service"
        (directory / "src").mkdir(parents=True)
        (directory / "a.txt").write_bytes(b"x" * 1000)
        (directory / "src" / "b.txt").write_bytes(b"x" * 2000)
        as_directory = fixture_resolution.ResolvedFixture(
            "service", directory, fixture_resolution.FixtureKind.DIRECTORY, False
        )
        (tmp_path / "f").mkdir()
        as_file = _file_fixture_of_size(tmp_path / "f", "service", 3000)

        assert self._estimate(
            tmp_path, [as_directory]
        ).estimated_total_usd == pytest.approx(
            self._estimate(tmp_path, [as_file]).estimated_total_usd
        )

    def test_per_trial_estimate_is_the_arm_estimate_over_its_planned_trials(
        self, tmp_path
    ):
        fixtures = [
            _file_fixture_of_size(tmp_path, "a.txt", 3000),
            _file_fixture_of_size(tmp_path, "b.txt", 3000),
        ]

        result = self._estimate(tmp_path, fixtures, trials=3)

        assert result.total_trials_per_arm == 2 * 3
        assert result.per_trial_usd("baseline") == pytest.approx(0.06 / (2 * 3))

    def test_unpriced_model_is_refused_naming_the_model_and_its_arm(self, tmp_path):
        fixtures = [_file_fixture_of_size(tmp_path, "a.txt", 3000)]
        arms = [_priced_arm("baseline", "sonnet"), _priced_arm("candidate", "opus")]

        with pytest.raises(UsageError) as excinfo:
            self._estimate(tmp_path, fixtures, arms)

        message = str(excinfo.value)
        assert "'opus' (candidate arm)" in message
        assert "sonnet" not in message
        assert "model-pricing.json" in message

    def test_empty_pricing_table_refuses_every_model(self, tmp_path):
        fixtures = [_file_fixture_of_size(tmp_path, "a.txt", 3000)]

        with pytest.raises(UsageError) as excinfo:
            self._estimate(tmp_path, fixtures, pricing_table={})

        assert "'sonnet' (baseline arm), 'haiku' (candidate arm)" in str(excinfo.value)


class TestChargedCost:
    def test_trial_with_a_reported_cost_is_charged_that_cost(self):
        result = _trial_result(Outcome.PASS, cost=0.0123)

        assert _run_estimate().charged_usd(BASELINE_LABEL, result) == 0.0123

    def test_trial_with_no_reported_cost_is_charged_its_arms_per_trial_estimate(self):
        result = _trial_result(Outcome.CLI_ERROR, cost=0.0, cost_reported=False)
        run_estimate = estimate.RunEstimate(
            by_arm=((BASELINE_LABEL, 0.06), (CANDIDATE_LABEL, 0.015)),
            total_trials_per_arm=3,
        )

        assert run_estimate.charged_usd(CANDIDATE_LABEL, result) == pytest.approx(0.005)


class TestArtifactEstimate:
    def test_artifact_records_each_arms_estimated_cost(self, world):
        stub = _passing_stub(world)

        _cli(world, stub, *SCOUT_HAIKU_ARGS, "--trials", str(SCOUT_TRIALS))

        written = _written(world)
        assert _arm_block(written, BASELINE_LABEL)[
            "estimated_cost_usd"
        ] == pytest.approx(BASELINE_TWO_ARM_ESTIMATE)
        assert _arm_block(written, CANDIDATE_LABEL)[
            "estimated_cost_usd"
        ] == pytest.approx(CANDIDATE_TWO_ARM_ESTIMATE)
