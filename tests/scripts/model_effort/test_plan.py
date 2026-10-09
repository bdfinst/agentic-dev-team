"""Run planning (model_effort.plan): candidate validation and the plan snapshot."""

from __future__ import annotations

import pytest
from _model_effort_support import NOW, FixedRng, World, _eval_paths
from model_effort import external, paths, plan, snapshot
from model_effort.errors import UsageError


class TestValidateCandidate:
    @pytest.mark.parametrize(
        ("model", "effort"),
        [
            (None, None),
            ("haiku", "low"),
            ("claude-opus-4-8", "max"),
            ("sonnet", None),
            (None, "xhigh"),
        ],
    )
    def test_values_in_the_agent_contract_are_accepted(self, model, effort):
        plan.validate_candidate(model, effort)

    @pytest.mark.parametrize("model", ["gpt-4", "../evil", "", "Haiku"])
    def test_model_outside_the_contract_is_refused_listing_valid_values(self, model):
        with pytest.raises(UsageError) as excinfo:
            plan.validate_candidate(model, None)

        message = str(excinfo.value)
        assert "--model" in message
        assert "haiku" in message and "sonnet" in message

    def test_unreadable_agent_contract_is_refused_naming_the_file(self, monkeypatch):
        monkeypatch.setattr(
            external.agent_contract_validator(), "load_contract", lambda: None
        )

        with pytest.raises(UsageError) as excinfo:
            plan.validate_candidate("haiku", None)

        assert "cannot read the agent contract" in str(excinfo.value)
        assert "agent-contract.json" in str(excinfo.value)

    @pytest.mark.parametrize("effort", ["hgih", "ultracode", ""])
    def test_effort_outside_the_contract_is_refused_listing_valid_values(self, effort):
        with pytest.raises(UsageError) as excinfo:
            plan.validate_candidate(None, effort)

        message = str(excinfo.value)
        assert "--effort" in message
        assert "low" in message and "high" in message


class TestPlanSnapshot:
    def _plan(self, world: World, eval_paths: paths.EvalPaths) -> plan.RunPlan:
        return plan.plan_run(
            "scout",
            candidate_model="haiku",
            candidate_effort=None,
            fixture_stems=["clean-form"],
            runs_dir=world.runs_dir,
            now=NOW,
            rng=FixedRng(),
            git_sha=None,
            eval_paths=eval_paths,
        )

    def test_the_shipped_knowledge_dir_is_recorded_relative_to_the_repo(
        self, world, private_tmp
    ):
        shipped_knowledge = _eval_paths(
            agents_dir=world.deps.eval_paths.agents_dir,
            expected_dir=world.deps.eval_paths.expected_dir,
            fixtures_dir=world.deps.eval_paths.fixtures_dir,
        )

        planned = self._plan(world, shipped_knowledge)

        with planned.snapshot:
            assert planned.metadata.knowledge_dir == "plugins/dev-team/knowledge"

    def test_inputs_that_cannot_be_copied_are_refused_and_leave_nothing_behind(
        self, world, private_tmp, monkeypatch
    ):
        def failing_copy(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(snapshot.shutil, "copytree", failing_copy)

        with pytest.raises(UsageError, match="cannot copy the run's inputs.*disk full"):
            self._plan(world, world.deps.eval_paths)

        assert list(private_tmp.iterdir()) == []
        assert world.artifacts == []


class TestPlanLoadsTheScriptsTrialsUse:
    """The grader and the env scrub load at plan time, before the operator approves."""

    @pytest.fixture(autouse=True)
    def _reload_scripts(self, private_tmp):
        external._load_module.cache_clear()

    def _plan(self, world: World) -> plan.RunPlan:
        return plan.plan_run(
            "scout",
            candidate_model="haiku",
            candidate_effort=None,
            fixture_stems=["clean-form"],
            runs_dir=world.runs_dir,
            now=NOW,
            rng=FixedRng(),
            git_sha=None,
            eval_paths=world.deps.eval_paths,
        )

    def test_a_script_edited_after_planning_changes_nothing(
        self, world, tmp_path, monkeypatch
    ):
        grader, dispatch = tmp_path / "grader.py", tmp_path / "dispatch.py"
        grader.write_text(
            "def run_grading(expected_dir, actuals, baseline, only=None):\n"
            "    return [('planned', True, [])], None\n",
            encoding="utf-8",
        )
        dispatch.write_text(
            "def _should_scrub(name):\n    return name == 'PLANNED'\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(paths, "EVAL_GRADE", grader)
        monkeypatch.setattr(paths, "ISOLATED_DISPATCH", dispatch)
        planned = self._plan(world)
        grader.write_text(
            "raise RuntimeError('edited after approval')", encoding="utf-8"
        )
        dispatch.write_text(
            "raise RuntimeError('edited after approval')", encoding="utf-8"
        )

        with planned.snapshot:
            rows = external.grade_against_expected(tmp_path, "stem", "agent", {})
            assert rows == [("planned", True, [])]
            assert external.should_scrub_env_var("PLANNED") is True

    def test_a_script_that_cannot_be_loaded_is_refused_before_anything_is_copied(
        self, world, tmp_path, monkeypatch, private_tmp
    ):
        monkeypatch.setattr(paths, "EVAL_GRADE", tmp_path / "missing.py")

        with pytest.raises(UsageError, match="cannot load a script the trials rely on"):
            self._plan(world)

        assert list(private_tmp.iterdir()) == []
        assert world.artifacts == []

    def test_a_grader_that_no_longer_fits_the_call_is_refused_before_anything_is_copied(
        self, world, monkeypatch, private_tmp
    ):
        def renamed(expected_directory, actuals, baseline, only=None):
            raise AssertionError("never called")

        monkeypatch.setattr(external.eval_grade(), "run_grading", renamed)

        with pytest.raises(UsageError, match="run_grading no longer accepts"):
            self._plan(world)

        assert list(private_tmp.iterdir()) == []
        assert world.artifacts == []
