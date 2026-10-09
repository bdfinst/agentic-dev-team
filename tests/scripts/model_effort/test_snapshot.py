"""Run inputs frozen at plan time (model_effort.snapshot)."""

from __future__ import annotations

import dataclasses
import os
import shutil
import signal
from pathlib import Path

import pytest
from _model_effort_support import (
    CLEAN_FORM_ARGS,
    MAX_COST_BELOW_ESTIMATE,
    WORLD_KNOWLEDGE_NOTE,
    World,
    _arm_block,
    _cli,
    _cli_canned,
    _deps_raising_after,
    _deps_with_canned_trials,
    _eval_paths,
    _make_directory_fixture,
    _make_file_fixture,
    _outcomes,
    _passing_stub,
    _run_estimate,
    _snapshot,
    _write_expected,
    _written,
)
from model_effort import (
    artifact_store,
    execution,
    paths,
    plan,
    process_record,
    run_types,
    snapshot,
    trial_count,
)
from model_effort import fixtures as fixture_resolution
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL
from model_effort.outcome import Outcome


class TestRunInputsAreFrozenAtPlanTime:
    def _edit_the_sources(self, world: World) -> None:
        paths_ = world.deps.eval_paths
        (paths_.fixtures_dir / "clean-form.html").write_text("EDITED", encoding="utf-8")
        (paths_.knowledge_dir / "note.md").write_text("EDITED", encoding="utf-8")
        _write_expected(paths_.expected_dir, "clean-form", "scout", "fail")

    def _deps_editing_sources_in_the_first_trial(self, world: World):
        canned, _ = _deps_with_canned_trials(world.deps)
        seen: list[tuple[str, str]] = []

        def run_trial(fixture, config, timeout):
            note = config.eval_paths.knowledge_dir / "note.md"
            seen.append((fixture.read_text(encoding="utf-8"), note.read_text("utf-8")))
            if len(seen) == 1:
                self._edit_the_sources(world)
            return canned.run_trial(fixture, config, timeout)

        return dataclasses.replace(world.deps, run_trial=run_trial), seen

    def test_editing_the_sources_mid_run_changes_neither_what_a_later_trial_sees_nor_its_grade(
        self, world
    ):
        deps, seen = self._deps_editing_sources_in_the_first_trial(world)

        code = _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "2")

        written = _written(world)
        assert code == 0
        assert seen == [("<form></form>", WORLD_KNOWLEDGE_NOTE)] * 4
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass", "pass"]

    def test_the_trial_reads_a_private_copy_and_cannot_reach_the_expected_answers(
        self, world
    ):
        canned, _ = _deps_with_canned_trials(world.deps)
        seen = []

        def run_trial(fixture, config, timeout):
            knowledge = config.eval_paths.knowledge_dir
            seen.append(
                (
                    fixture.parent,
                    knowledge,
                    sorted(path.name for path in knowledge.iterdir()),
                    config.eval_paths.expected_dir,
                )
            )
            return canned.run_trial(fixture, config, timeout)

        _cli_canned(
            world,
            dataclasses.replace(world.deps, run_trial=run_trial),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
        )

        source = world.deps.eval_paths
        fixtures_dir, knowledge, knowledge_files, expected_dir = seen[0]
        assert fixtures_dir != source.fixtures_dir
        assert knowledge != source.knowledge_dir
        assert knowledge_files == ["note.md"]
        assert expected_dir not in (knowledge, *knowledge.parents)
        assert knowledge not in expected_dir.parents

    def test_the_artifact_still_names_the_source_knowledge_dir(self, world):
        canned, _ = _deps_with_canned_trials(world.deps)

        _cli_canned(world, canned, *CLEAN_FORM_ARGS, "--trials", "1")

        assert _written(world)["knowledge_dir"] == str(
            world.deps.eval_paths.knowledge_dir
        )

    def test_trials_are_configured_and_graded_from_the_plans_snapshot(
        self, world, scout_plan
    ):
        canned, calls = _deps_with_canned_trials(world.deps)
        settings = run_types.TrialSettings(
            trials=trial_count.TrialCount(1, "test"),
            trial_timeout_seconds=1,
            claude_bin="unused",
        )
        # The live entry says a pass is right; only the snapshot's copy says fail.
        frozen_expected = scout_plan.snapshot.eval_paths.expected_dir
        _write_expected(frozen_expected, "clean-form", "scout", "fail")

        run = execution.run_trials(
            scout_plan, settings, _run_estimate(), run_trial=canned.run_trial
        )

        assert {config.eval_paths for _, config, _ in calls} == {
            scout_plan.snapshot.eval_paths
        }
        graded = [
            result.outcome
            for arm_run in run.arm_runs
            for fixture in arm_run.fixture_trials
            if fixture.stem == "clean-form"
            for result in fixture.results
        ]
        assert graded and set(graded) == {Outcome.GRADED_FAIL}


class TestSnapshotIsRemoved:
    @pytest.fixture(autouse=True)
    def _private_tmp(self, private_tmp) -> Path:
        self.private_tmp = private_tmp
        return private_tmp

    def _left_over(self) -> list[str]:
        return sorted(path.name for path in self.private_tmp.iterdir())

    def test_after_a_complete_run(self, world):
        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert code == 0
        assert self._left_over() == []

    def test_after_the_operator_declines(self, world):
        code = _cli(
            world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1", yes=False
        )

        assert code == 1
        assert self._left_over() == []

    def test_after_the_estimate_is_refused(self, world):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--max-cost",
            str(MAX_COST_BELOW_ESTIMATE),
        )

        assert code == 2
        assert self._left_over() == []

    def test_after_the_artifact_path_cannot_be_reserved(self, world):
        shutil.rmtree(world.runs_dir)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS)

        assert code == 2
        assert self._left_over() == []

    @pytest.mark.parametrize(
        "error", [KeyboardInterrupt(), RuntimeError("boom")], ids=["interrupt", "error"]
    )
    def test_after_a_trial_is_cut_short(self, world, error):
        deps = _deps_raising_after(world, 1, error)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, deps=deps)

        assert code == 1
        assert self._left_over() == []


@pytest.mark.usefixtures("harmless_termination_signals")
class TestRunResourcesSurviveSignals:
    """A signal while the plan's snapshot and placeholder are made or removed leaves nothing behind."""

    @pytest.fixture(autouse=True)
    def _private_tmp(self, private_tmp) -> Path:
        self.private_tmp = private_tmp
        return private_tmp

    def _left_over(self) -> list[str]:
        return sorted(path.name for path in self.private_tmp.iterdir())

    def test_interrupt_while_the_inputs_are_copied_leaves_nothing(
        self, world, monkeypatch
    ):
        def interrupted_copy(*_args, **_kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(snapshot.shutil, "copytree", interrupted_copy)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS)

        assert code == 1
        assert self._left_over() == []
        assert world.artifacts == []

    @pytest.mark.parametrize(
        ("owner", "name"),
        [
            pytest.param(plan, "take_snapshot", id="after-the-copy"),
            pytest.param(
                artifact_store, "reserve_artifact_path", id="after-the-reservation"
            ),
            pytest.param(plan, "RunPlan", id="after-the-plan-is-built"),
        ],
    )
    def test_signal_right_after_a_resource_is_made_leaves_nothing(
        self, world, monkeypatch, owner, name
    ):
        make = getattr(owner, name)

        def make_then_signal(*args, **kwargs):
            made = make(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return made

        # Wraps the step: a signal can be sent into the window after it only by hand.
        monkeypatch.setattr(owner, name, make_then_signal)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS)

        assert code == 1
        assert self._left_over() == []
        assert world.artifacts == []

    def test_signal_while_the_snapshot_is_removed_does_not_leave_a_partial_tree(
        self, world, monkeypatch
    ):
        remove = snapshot.remove_tree

        def signal_then_remove(directory):
            os.kill(os.getpid(), signal.SIGTERM)
            remove(directory)

        monkeypatch.setattr(snapshot, "remove_tree", signal_then_remove)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert code == 1
        assert self._left_over() == []
        assert _written(world)["status"] == "complete"


class TestSnapshotPathsAreScrubbed:
    def test_an_error_naming_the_snapshot_directory_is_recorded_with_a_placeholder(
        self, world
    ):
        def failing_trial(_fixture, config, _timeout):
            return process_record.TrialProcessRecord(
                exit_code=1,
                stdout="",
                stderr=f"cannot read {config.eval_paths.knowledge_dir}/missing.md",
                timed_out=False,
            )

        deps = dataclasses.replace(world.deps, run_trial=failing_trial)

        _cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "1")

        trial = _arm_block(_written(world), BASELINE_LABEL)["fixtures"][0]["trials"][0]
        assert trial["error"] == (
            "exit code 1: cannot read <snapshot>/plugin/knowledge/missing.md"
        )


class TestTakeSnapshot:
    def _source(self, tmp_path: Path) -> tuple[paths.EvalPaths, list]:
        fixtures_dir, expected_dir = tmp_path / "fx", tmp_path / "ex"
        knowledge = tmp_path / "kn"
        for directory in (fixtures_dir, expected_dir, knowledge / "sub"):
            directory.mkdir(parents=True)
        (knowledge / "sub" / "deep.md").write_text("deep", encoding="utf-8")
        _make_file_fixture(fixtures_dir, "a.html", "<a>")
        _make_directory_fixture(fixtures_dir)
        for stem in ("a", "service", "unused"):
            _write_expected(expected_dir, stem, "scout", "pass")
        fixtures = [
            fixture_resolution.ResolvedFixture(
                "a", fixtures_dir / "a.html", fixture_resolution.FixtureKind.FILE, True
            ),
            fixture_resolution.ResolvedFixture(
                "service",
                fixtures_dir / "service",
                fixture_resolution.FixtureKind.DIRECTORY,
                True,
            ),
        ]
        source = _eval_paths(
            agents_dir=tmp_path / "agents-elsewhere",
            expected_dir=expected_dir,
            fixtures_dir=fixtures_dir,
            plugin_root=tmp_path / "plugin-elsewhere",
            knowledge_dir=knowledge,
        )
        return source, fixtures

    def test_copies_the_fixtures_their_expected_entries_and_the_knowledge_dir(
        self, tmp_path, private_tmp
    ):
        source, fixtures = self._source(tmp_path)

        with snapshot.take_snapshot(source, fixtures) as taken:
            fixture_names = [fixture.path.name for fixture in taken.fixtures]
            copied_contents = [
                sorted(_snapshot(fixture.path).values()) for fixture in taken.fixtures
            ]
            expected_names = sorted(
                path.name for path in taken.eval_paths.expected_dir.iterdir()
            )
            knowledge_contents = list(
                _snapshot(taken.eval_paths.knowledge_dir).values()
            )

        assert fixture_names == ["a.html", "service"]
        assert copied_contents == [
            ["<a>"],
            ["print('app')", "print('util')", "readme"],
        ]
        assert expected_names == ["a.json", "service.json"]
        assert knowledge_contents == ["deep"]

    def test_the_snapshot_paths_point_inside_it_and_the_agents_dir_is_kept(
        self, tmp_path, private_tmp
    ):
        source, fixtures = self._source(tmp_path)

        with snapshot.take_snapshot(source, fixtures) as taken:
            root = taken.root
            inside = [
                taken.eval_paths.expected_dir,
                taken.eval_paths.fixtures_dir,
                taken.eval_paths.plugin_root,
                taken.eval_paths.knowledge_dir,
                *(fixture.path for fixture in taken.fixtures),
            ]
            assert all(root in directory.parents for directory in inside)
            assert taken.eval_paths.knowledge_dir.parent == taken.eval_paths.plugin_root
            assert taken.eval_paths.agents_dir == source.agents_dir
            assert [fixture.stem for fixture in taken.fixtures] == ["a", "service"]

        assert not root.exists()

    def test_a_failed_copy_leaves_no_directory_behind(
        self, tmp_path, private_tmp, monkeypatch
    ):
        source, fixtures = self._source(tmp_path)

        def failing_copy(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(snapshot.shutil, "copytree", failing_copy)

        with pytest.raises(OSError, match="disk full"):
            snapshot.take_snapshot(source, fixtures)

        assert list(private_tmp.iterdir()) == []
