"""The committed grader map and the fixtures it relies on stay consistent with the agents.

`evals/model-effort/graders.json` names how the A/B harness grades each agent that
the expected-findings default does not fit. These checks hold it to the agent
files, the eval corpus and the rubric files, so a renamed agent, a dropped
fixture or a judge pinned too low fails here before a paid run.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime

import pytest

from _repo_root import REPO_ROOT

for _path in (REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "lib"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from model_effort import (
    agent_file,
    external,
    fixtures,
    grader_config,
    paths,
    plan,
    tools,
)

GRADER_MAP = paths.GRADER_MAP_PATH
MIN_FIXTURES = 3
# The eval_grade registry grader each map kind's fixtures must declare.
REGISTRY_GRADERS = {
    grader_config.GraderKind.EXPECTED_FINDINGS: {"verdict", "finding_ids", None},
    grader_config.GraderKind.TESTS_PASS: {"tests_pass"},
    grader_config.GraderKind.DISPATCH_SET: {"dispatch_set"},
    grader_config.GraderKind.RUBRIC: {"rubric"},
}
MAPPED = sorted(grader_config.load_grader_map(GRADER_MAP))
AGENTS = agent_file.list_agent_names(paths.AGENTS_DIR)


def _frontmatter(agent: str) -> dict:
    return agent_file.load_agent_file(agent, paths.AGENTS_DIR).frontmatter


def _runnable_entries(agent: str) -> dict[str, dict]:
    entries = fixtures.expected_entries(agent, paths.EXPECTED_DIR)
    index = fixtures.fixture_index(paths.FIXTURES_DIR)
    return {stem: entry for stem, entry in entries.items() if stem in index}


def test_every_agent_has_at_least_one_runnable_fixture():
    fixtureless = [agent for agent in AGENTS if not _runnable_entries(agent)]

    assert fixtureless == []


def test_every_mapped_agent_is_a_real_agent():
    assert set(MAPPED) <= set(AGENTS)


@pytest.mark.parametrize("agent", MAPPED)
def test_mapped_agent_has_at_least_three_fixtures_graded_by_its_kind(agent):
    grading = grader_config.resolve_agent_grading(agent, GRADER_MAP)
    entries = _runnable_entries(agent)

    declared = {entry["agents"][agent].get("grader") for entry in entries.values()}
    assert len(entries) >= MIN_FIXTURES
    assert declared <= REGISTRY_GRADERS[grading.kind]


@pytest.mark.parametrize("agent", MAPPED)
def test_mapped_agent_runs_without_refusal_under_its_grading(agent):
    grading = grader_config.resolve_agent_grading(agent, GRADER_MAP)

    tools.resolve_tool_profile(
        agent,
        _frontmatter(agent),
        sandbox=grading.sandbox,
        dispatch=grading.kind is grader_config.GraderKind.DISPATCH_SET,
    )


@pytest.mark.parametrize("agent", MAPPED)
def test_sandbox_is_granted_only_to_agents_that_declare_write_tools(agent):
    grading = grader_config.resolve_agent_grading(agent, GRADER_MAP)
    declared = tools.classify_tools(_frontmatter(agent).get("tools"))

    assert grading.sandbox == bool(declared.refused_tools)


RUBRIC_AGENTS = [
    agent
    for agent in MAPPED
    if grader_config.resolve_agent_grading(agent, GRADER_MAP).kind
    is grader_config.GraderKind.RUBRIC
]


@pytest.mark.parametrize("agent", RUBRIC_AGENTS)
def test_rubric_judge_is_pinned_one_tier_above_the_agent(agent):
    judge = grader_config.resolve_agent_grading(agent, GRADER_MAP).judge
    agent_tier = grader_config.model_tier(_frontmatter(agent)["model"])

    expected = min(agent_tier + 1, len(grader_config.MODEL_TIERS) - 1)
    assert grader_config.model_tier(judge.model) == expected
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


@pytest.mark.parametrize(
    "agent",
    [
        agent
        for agent in MAPPED
        if grader_config.resolve_agent_grading(agent, GRADER_MAP).kind
        is grader_config.GraderKind.TESTS_PASS
    ],
)
def test_tests_pass_fixtures_declare_commands_and_protect_what_grades_them(agent):
    for stem, entry in _runnable_entries(agent).items():
        block = entry["agents"][agent]
        assert block.get("testCommands"), stem
        assert block.get("protectedPaths"), stem
        for relative in block["protectedPaths"]:
            assert (paths.FIXTURES_DIR / stem / relative).exists(), (stem, relative)


@pytest.mark.parametrize("agent", MAPPED)
def test_every_non_review_fixture_carries_its_own_task(agent):
    for stem, entry in _runnable_entries(agent).items():
        task = entry["agents"][agent].get("task", "")
        assert "{fixture}" in task, stem


def test_grader_map_lists_only_known_grader_kinds():
    data = json.loads(GRADER_MAP.read_text(encoding="utf-8"))
    kinds = {kind.value for kind in grader_config.GraderKind}

    assert {entry["grader"] for entry in data["agents"].values()} <= kinds


@pytest.mark.parametrize("agent", MAPPED)
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
    ) as planned:
        assert len(planned.fixtures) >= MIN_FIXTURES
        assert planned.grading == grader_config.resolve_agent_grading(agent, GRADER_MAP)
        assert all(fixture.task for fixture in planned.fixtures)
