"""The committed grader map and the fixtures it relies on stay consistent with the agents.

`evals/model-effort/graders.json` names how the A/B harness grades each agent that
the expected-findings default does not fit. These checks hold it to the agent
files, the eval corpus and the rubric files, so a renamed agent, a dropped
fixture or a judge pinned too low fails here before a paid run.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from datetime import UTC, datetime

import pytest

from _repo_root import REPO_ROOT

for _path in (REPO_ROOT / "scripts" / "lib", REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from eval_graders import DEFAULT_GRADERS
from model_effort import (
    agent_file,
    external,
    fixtures,
    grader_config,
    judge_tier,
    paths,
    plan,
    runner,
    tools,
)
from model_effort.grader_config import GraderKind

GRADER_MAP = paths.GRADER_MAP_PATH
MIN_FIXTURES = 3
CHECK_TIMEOUT_SECONDS = 120


def _mapped() -> list[str]:
    return sorted(grader_config.load_grader_map(GRADER_MAP))


def _agents() -> list[str]:
    return agent_file.list_agent_names(paths.AGENTS_DIR)


def _kind(agent: str) -> GraderKind:
    return grader_config.resolve_agent_grading(agent, GRADER_MAP).kind


def _mapped_of_kind(kind: GraderKind) -> list[str]:
    return [agent for agent in _mapped() if _kind(agent) is kind]


def _frontmatter(agent: str) -> dict:
    return agent_file.load_agent_file(agent, paths.AGENTS_DIR).frontmatter


def _runnable_entries(agent: str) -> dict[str, dict]:
    entries = fixtures.expected_entries(agent, paths.EXPECTED_DIR)
    index = fixtures.fixture_index(paths.FIXTURES_DIR)
    return {stem: entry for stem, entry in entries.items() if stem in index}


def test_every_agent_has_at_least_one_runnable_fixture():
    fixtureless = [agent for agent in _agents() if not _runnable_entries(agent)]

    assert fixtureless == []


def test_every_mapped_agent_is_a_real_agent():
    assert set(_mapped()) <= set(_agents())


def test_the_harness_default_grader_is_the_registrys_agents_default():
    assert grader_config.AGENT_BLOCK_DEFAULT_GRADER == DEFAULT_GRADERS["agents"]


@pytest.mark.parametrize("agent", _mapped())
def test_mapped_agent_has_at_least_three_fixtures_graded_by_its_kind(agent):
    entries = _runnable_entries(agent)

    declared = {
        grader_config.entry_grader(entry["agents"][agent]) for entry in entries.values()
    }
    assert len(entries) >= MIN_FIXTURES
    assert declared <= grader_config.REGISTRY_GRADERS[_kind(agent)]


def test_every_non_default_expected_grader_belongs_to_an_agent_of_that_kind():
    mismatched = []
    for path in sorted(paths.EXPECTED_DIR.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        for agent, block in entry.get("agents", {}).items():
            grader = grader_config.entry_grader(block)
            if grader == grader_config.AGENT_BLOCK_DEFAULT_GRADER:
                continue
            if grader not in grader_config.REGISTRY_GRADERS[_kind(agent)]:
                mismatched.append((path.stem, agent, grader, _kind(agent).value))

    assert mismatched == []


@pytest.mark.parametrize("agent", _mapped())
def test_mapped_agent_runs_without_refusal_under_its_grading(agent):
    grading = grader_config.resolve_agent_grading(agent, GRADER_MAP)

    tools.resolve_tool_profile(
        agent,
        _frontmatter(agent),
        sandbox=grading.sandbox,
        dispatch=grading.kind is GraderKind.DISPATCH_SET,
    )


@pytest.mark.parametrize("agent", _mapped())
def test_sandbox_is_granted_only_to_agents_that_declare_write_tools(agent):
    grading = grader_config.resolve_agent_grading(agent, GRADER_MAP)
    declared = tools.classify_tools(_frontmatter(agent).get("tools"))

    assert grading.sandbox == bool(declared.refused_tools)


RUBRIC_AGENTS = _mapped_of_kind(GraderKind.RUBRIC)


def test_the_map_has_rubric_agents_so_the_rubric_checks_run():
    assert RUBRIC_AGENTS


@pytest.mark.parametrize("agent", RUBRIC_AGENTS)
def test_rubric_judge_is_pinned_one_tier_above_the_agent(agent):
    judge = grader_config.resolve_agent_grading(agent, GRADER_MAP).judge
    agent_tier = judge_tier.model_tier(_frontmatter(agent)["model"])

    expected = min(agent_tier + 1, len(judge_tier.MODEL_TIERS) - 1)
    assert judge_tier.model_tier(judge.model) == expected
    assert judge.model.startswith("claude-"), "pin a full model ID, not an alias"
    enums = external.contract_enums()
    assert judge.effort in enums[1]


@pytest.mark.parametrize("agent", RUBRIC_AGENTS)
def test_rubric_points_have_ids_distinct_from_the_rubric_criteria(agent):
    judge = grader_config.resolve_agent_grading(agent, GRADER_MAP).judge
    for stem, entry in _runnable_entries(agent).items():
        points = [p["id"] for p in entry["agents"][agent].get("rubricPoints", [])]
        assert points, f"{stem} has no rubricPoints"
        assert len(points) == len(set(points)), stem
        assert not set(points) & set(judge.criterion_ids), stem


TESTS_PASS_AGENTS = _mapped_of_kind(GraderKind.TESTS_PASS)


def test_the_map_has_tests_pass_agents_so_the_fixture_checks_run():
    assert TESTS_PASS_AGENTS


def _tests_pass_fixtures() -> list[tuple[str, str]]:
    return [
        (agent, stem)
        for agent in TESTS_PASS_AGENTS
        for stem in sorted(_runnable_entries(agent))
    ]


@pytest.mark.parametrize(("agent", "stem"), _tests_pass_fixtures())
def test_each_tests_pass_fixture_fails_its_commands_before_the_agent_works(
    agent, stem, tmp_path
):
    block = _runnable_entries(agent)[stem]["agents"][agent]
    work_dir = tmp_path / stem
    shutil.copytree(paths.FIXTURES_DIR / stem, work_dir)

    results = [
        runner.run_check_command(command, work_dir, CHECK_TIMEOUT_SECONDS, None)
        for command in block["testCommands"]
    ]

    assert any(result["exit_code"] != 0 for result in results), results


@pytest.mark.parametrize("agent", TESTS_PASS_AGENTS)
def test_tests_pass_fixtures_declare_commands_and_protect_what_grades_them(agent):
    for stem, entry in _runnable_entries(agent).items():
        block = entry["agents"][agent]
        assert block.get("testCommands"), stem
        assert block.get("protectedPaths"), stem
        for relative in block["protectedPaths"]:
            assert (paths.FIXTURES_DIR / stem / relative).exists(), (stem, relative)


@pytest.mark.parametrize("agent", _mapped())
def test_every_non_review_fixture_carries_its_own_task(agent):
    for stem, entry in _runnable_entries(agent).items():
        task = entry["agents"][agent].get("task", "")
        assert "{fixture}" in task, stem


def test_grader_map_lists_only_known_grader_kinds():
    data = json.loads(GRADER_MAP.read_text(encoding="utf-8"))
    kinds = {kind.value for kind in GraderKind}

    assert {entry["grader"] for entry in data["agents"].values()} <= kinds


@pytest.mark.parametrize("agent", _mapped())
def test_mapped_agent_plans_a_run_against_the_shipped_corpus(agent, tmp_path):
    effort = _frontmatter(agent)["effort"]
    with plan.plan_run(
        agent,
        candidate_model=None,
        candidate_effort="low" if effort != "low" else "medium",
        fixture_stems=None,
        runs_dir=tmp_path,
        now=datetime(2026, 1, 1, tzinfo=UTC),
        rng=random.Random(0),
        git_sha=None,
        eval_paths=paths.EvalPaths.default(),
        find_check_jail=lambda: None,
        allow_unjailed_checks=True,
    ) as planned:
        assert len(planned.fixtures) >= MIN_FIXTURES
        assert planned.grading == grader_config.resolve_agent_grading(agent, GRADER_MAP)
        assert all(fixture.task for fixture in planned.fixtures)
