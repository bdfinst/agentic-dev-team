"""Run inputs frozen at plan time (model_effort.snapshot)."""

from __future__ import annotations

import dataclasses
import os
import shutil
import signal
from pathlib import Path

import pytest
from ab_constants import CLEAN_FORM_ARGS, MAX_COST_BELOW_ESTIMATE, WORLD_KNOWLEDGE_NOTE
from ab_inputs import (
    eval_paths_with,
    make_directory_fixture,
    make_file_fixture,
    read_tree,
    write_expected,
)
from ab_results import flat_run_estimate
from ab_signals import signal_own_thread
from ab_world import (
    World,
    arm_block,
    cli,
    cli_canned,
    deps_raising_after,
    deps_with_canned_trials,
    outcomes_of,
    passing_stub,
    read_artifact,
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
        write_expected(paths_.expected_dir, "clean-form", "scout", "fail")

    def _deps_editing_sources_in_the_first_trial(self, world: World):
        canned, _ = deps_with_canned_trials(world.deps)
        seen: list[tuple[str, str]] = []

        def run_trial(fixture, config, timeout):
            note = config.snapshot_paths.knowledge_dir / "note.md"
            seen.append((fixture.read_text(encoding="utf-8"), note.read_text("utf-8")))
            if len(seen) == 1:
                self._edit_the_sources(world)
            return canned.run_trial(fixture, config, timeout)

        return dataclasses.replace(world.deps, run_trial=run_trial), seen

    def test_editing_the_sources_mid_run_changes_neither_what_a_later_trial_sees_nor_its_grade(
        self, world
    ):
        deps, seen = self._deps_editing_sources_in_the_first_trial(world)

        code = cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "2")

        written = read_artifact(world)
        assert code == 0
        assert seen == [("<form></form>", WORLD_KNOWLEDGE_NOTE)] * 4
        assert outcomes_of(written, BASELINE_LABEL) == ["pass", "pass"]
        assert outcomes_of(written, CANDIDATE_LABEL) == ["pass", "pass"]

    def test_the_trial_reads_a_private_copy_and_cannot_reach_the_expected_answers(
        self, world
    ):
        canned, _ = deps_with_canned_trials(world.deps)
        seen = []

        def run_trial(fixture, config, timeout):
            knowledge = config.snapshot_paths.knowledge_dir
            seen.append(
                (
                    fixture.parent,
                    knowledge,
                    sorted(path.name for path in knowledge.iterdir()),
                    config.snapshot_paths.expected_dir,
                )
            )
            return canned.run_trial(fixture, config, timeout)

        cli_canned(
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
        canned, _ = deps_with_canned_trials(world.deps)

        cli_canned(world, canned, *CLEAN_FORM_ARGS, "--trials", "1")

        assert read_artifact(world)["knowledge_dir"] == str(
            world.deps.eval_paths.knowledge_dir
        )

    def test_trials_are_configured_and_graded_from_the_plans_snapshot(
        self, world, scout_plan
    ):
        canned, calls = deps_with_canned_trials(world.deps)
        settings = run_types.TrialSettings(
            trials=trial_count.TrialCount(1, "test"),
            trial_timeout_seconds=1,
            claude_bin="unused",
        )
        # The live entry says a pass is right; only the snapshot's copy says fail.
        frozen_expected = scout_plan.snapshot.paths.expected_dir
        write_expected(frozen_expected, "clean-form", "scout", "fail")

        run = execution.run_trials(
            scout_plan, settings, flat_run_estimate(), run_trial=canned.run_trial
        )

        assert {config.snapshot_paths for _, config, _ in calls} == {
            scout_plan.snapshot.paths
        }
        graded = [
            result.outcome
            for arm_run in run.arm_runs
            for fixture in arm_run.fixture_trials
            if fixture.stem == "clean-form"
            for result in fixture.results
        ]
        assert graded and set(graded) == {Outcome.GRADED_FAIL}

    def test_fixture_trials_carry_the_plans_skip_expectation(self, world, scout_plan):
        canned, _ = deps_with_canned_trials(world.deps)
        settings = run_types.TrialSettings(
            trials=trial_count.TrialCount(1, "test"),
            trial_timeout_seconds=1,
            claude_bin="unused",
        )
        skipped = tuple(
            dataclasses.replace(fixture, expected_clean=True, expected_skip=True)
            for fixture in scout_plan.fixtures
        )
        plan = dataclasses.replace(
            scout_plan,
            snapshot=dataclasses.replace(scout_plan.snapshot, fixtures=skipped),
        )

        run = execution.run_trials(
            plan, settings, flat_run_estimate(), run_trial=canned.run_trial
        )

        flags = [
            fixture.expected_skip
            for arm_run in run.arm_runs
            for fixture in arm_run.fixture_trials
        ]
        assert flags and all(flags)


class TestSnapshotIsRemoved:
    @pytest.fixture(autouse=True)
    def _private_tmp(self, private_tmp) -> Path:
        self.private_tmp = private_tmp
        return private_tmp

    def _left_over(self) -> list[str]:
        return sorted(path.name for path in self.private_tmp.iterdir())

    def test_after_a_complete_run(self, world):
        code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert code == 0
        assert self._left_over() == []

    def test_after_the_operator_declines(self, world):
        code = cli(
            world, passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1", yes=False
        )

        assert code == 1
        assert self._left_over() == []

    def test_after_the_estimate_is_refused(self, world):
        code = cli(
            world,
            passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--max-cost",
            str(MAX_COST_BELOW_ESTIMATE),
        )

        assert code == 2
        assert self._left_over() == []

    def test_after_the_artifact_path_cannot_be_reserved(self, world):
        shutil.rmtree(world.runs_dir)

        code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS)

        assert code == 2
        assert self._left_over() == []

    @pytest.mark.skipif(
        os.geteuid() == 0, reason="root can create files in a read-only directory"
    )
    def test_after_the_runs_directory_refuses_the_placeholder(self, world, capsys):
        world.runs_dir.chmod(0o500)
        try:
            code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS)
        finally:
            world.runs_dir.chmod(0o700)

        assert code == 2
        assert "cannot reserve artifact" in capsys.readouterr().err
        assert self._left_over() == []
        assert world.artifacts == []

    @pytest.mark.parametrize(
        "error", [KeyboardInterrupt(), RuntimeError("boom")], ids=["interrupt", "error"]
    )
    def test_after_a_trial_is_cut_short(self, world, error):
        deps = deps_raising_after(world, 1, error)

        code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS, deps=deps)

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

        code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS)

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
            signal_own_thread(signal.SIGTERM)
            return made

        # Wraps the step: a signal can be sent into the window after it only by hand.
        monkeypatch.setattr(owner, name, make_then_signal)

        code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS)

        assert code == 1
        assert self._left_over() == []
        assert world.artifacts == []

    def test_signal_while_the_snapshot_is_removed_does_not_leave_a_partial_tree(
        self, world, monkeypatch
    ):
        remove = snapshot.remove_tree

        def signal_then_remove(directory):
            signal_own_thread(signal.SIGTERM)
            remove(directory)

        monkeypatch.setattr(snapshot, "remove_tree", signal_then_remove)

        code = cli(world, passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert code == 1
        assert self._left_over() == []
        assert read_artifact(world)["status"] == "complete"


class TestSnapshotPathsAreScrubbed:
    def test_an_error_naming_the_snapshot_directory_is_recorded_with_a_placeholder(
        self, world
    ):
        def failing_trial(_fixture, config, _timeout):
            return process_record.TrialProcessRecord(
                exit_code=1,
                stdout="",
                stderr=f"cannot read {config.snapshot_paths.knowledge_dir}/missing.md",
                timed_out=False,
            )

        deps = dataclasses.replace(world.deps, run_trial=failing_trial)

        cli_canned(world, deps, *CLEAN_FORM_ARGS, "--trials", "1")

        trial = arm_block(read_artifact(world), BASELINE_LABEL)["fixtures"][0]["trials"][0]
        assert trial["error"] == (
            "exit code 1: cannot read <snapshot>/plugin/knowledge/missing.md"
        )


class TestTakeSnapshot:
    def _source(self, tmp_path: Path) -> tuple[paths.EvalPaths, list]:
        fixtures_dir, expected_dir = tmp_path / "fx", tmp_path / "ex"
        knowledge = tmp_path / "plugin" / "knowledge"
        for directory in (fixtures_dir, expected_dir, knowledge / "sub"):
            directory.mkdir(parents=True)
        (knowledge / "sub" / "deep.md").write_text("deep", encoding="utf-8")
        make_file_fixture(fixtures_dir, "a.html", "<a>")
        make_directory_fixture(fixtures_dir)
        for stem in ("a", "service", "unused"):
            write_expected(expected_dir, stem, "scout", "pass")
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
        source = eval_paths_with(
            agents_dir=tmp_path / "agents-elsewhere",
            expected_dir=expected_dir,
            fixtures_dir=fixtures_dir,
            plugin_root=knowledge.parent,
        )
        return source, fixtures

    def test_copies_the_fixtures_their_expected_entries_and_the_knowledge_dir(
        self, tmp_path, private_tmp
    ):
        source, fixtures = self._source(tmp_path)

        with snapshot.take_snapshot(source, fixtures) as taken:
            fixture_names = [fixture.path.name for fixture in taken.fixtures]
            copied_contents = [
                sorted(read_tree(fixture.path).values()) for fixture in taken.fixtures
            ]
            expected_names = sorted(
                path.name for path in taken.paths.expected_dir.iterdir()
            )
            knowledge_contents = list(
                read_tree(taken.paths.knowledge_dir).values()
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
            answer_root = taken.answer_root
            inside = [
                taken.paths.fixtures_dir,
                taken.paths.plugin_root,
                taken.paths.knowledge_dir,
                *(fixture.path for fixture in taken.fixtures),
            ]
            assert all(root in directory.parents for directory in inside)
            assert taken.paths.expected_dir.parent == answer_root
            assert root not in answer_root.parents and answer_root not in root.parents
            assert taken.paths.knowledge_dir.parent == taken.paths.plugin_root
            assert not hasattr(taken.paths, "agents_dir")
            assert [fixture.stem for fixture in taken.fixtures] == ["a", "service"]

        assert not root.exists()
        assert not answer_root.exists()

    def test_symlinks_in_the_knowledge_dir_and_a_directory_fixture_stay_links(
        self, tmp_path, private_tmp
    ):
        # Policy: a link is copied as a link, never as its target's content, so the
        # snapshot never pulls in a file from outside the tree it copies.
        source, fixtures = self._source(tmp_path)
        outside = tmp_path / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        (source.knowledge_dir / "link.md").symlink_to(outside)
        (fixtures[1].path / "link.py").symlink_to(outside)

        with snapshot.take_snapshot(source, fixtures) as taken:
            copied_links = [
                taken.paths.knowledge_dir / "link.md",
                taken.fixtures[1].path / "link.py",
            ]
            kept = [(link.is_symlink(), os.readlink(link)) for link in copied_links]

        assert kept == [(True, str(outside)), (True, str(outside))]

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
