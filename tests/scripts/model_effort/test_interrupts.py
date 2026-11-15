"""Interrupts (model_effort.interrupts): Ctrl-C and termination signals end the run and keep the completed trials."""

from __future__ import annotations

import dataclasses
import io
import signal
from pathlib import Path

import pytest
from ab_constants import CLEAN_FORM_ARGS, NOW
from ab_signals import (
    INTERRUPT_SIGNALS,
    TERMINATION_SIGNALS,
    blocked_signals,
    note_signal,
    signal_own_thread,
)
from ab_world import (
    arm_block,
    assert_nothing_ran,
    cli,
    deps_signalling_after,
    gated_cli,
    interrupting_deps,
    outcomes_of,
    passing_stub,
    read_artifact,
)
from model_effort import interrupts, report
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL


class TestInterrupt:
    def test_ctrl_c_after_three_trials_keeps_them_and_marks_the_artifact_interrupted(
        self, world
    ):
        stub = passing_stub(world)

        code = cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=interrupting_deps(world, 3),
        )

        written = read_artifact(world)
        assert code == 1
        assert len(stub.calls) == 3
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert outcomes_of(written, BASELINE_LABEL) == ["pass", "pass"]
        assert outcomes_of(written, CANDIDATE_LABEL) == ["pass"]

    def test_interrupt_prints_no_traceback_and_names_the_artifact_and_the_dropped_trial(
        self, world, capsys
    ):
        cli(
            world,
            passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=interrupting_deps(world, 3),
        )

        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert (
            "error: run stopped early (interrupt): the trial in flight was dropped; "
            "3 completed trials were kept"
        ) in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_arm_with_no_completed_trial_lists_no_fixtures(self, world):
        cli(
            world,
            passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=interrupting_deps(world, 1),
        )

        written = read_artifact(world)
        assert arm_block(written, CANDIDATE_LABEL)["fixtures"] == []
        assert arm_block(written, CANDIDATE_LABEL)["totals"]["pass"] == 0
        assert outcomes_of(written, BASELINE_LABEL) == ["pass"]

    def test_ctrl_c_inside_the_first_trial_writes_an_interrupted_artifact_with_no_results(
        self, world, capsys
    ):
        stub = passing_stub(world)

        code = cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=interrupting_deps(world, 0),
        )

        written = read_artifact(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert [arm["fixtures"] for arm in written["arms"]] == [[], []]
        assert "Traceback" not in err
        assert "0 completed trials were kept" in err
        assert f"artifact written: {world.artifact_path}" in err


class TestIgnoredTerminationSignals:
    def test_a_signal_that_was_ignored_stays_ignored_while_the_others_raise_interrupt(
        self,
    ):
        originals = {
            signum: signal.signal(signum, note_signal)
            for signum in TERMINATION_SIGNALS
        }
        ignored, handled = TERMINATION_SIGNALS[0], TERMINATION_SIGNALS[1:]
        signal.signal(ignored, signal.SIG_IGN)
        try:
            with interrupts.termination_as_interrupt():
                assert signal.getsignal(ignored) is signal.SIG_IGN
                for signum in handled:
                    assert signal.getsignal(signum) is not note_signal
            assert signal.getsignal(ignored) is signal.SIG_IGN
            for signum in handled:
                assert signal.getsignal(signum) is note_signal
        finally:
            for signum, handler in originals.items():
                signal.signal(signum, handler)


@pytest.mark.usefixtures("harmless_termination_signals")
class TestTerminationSignals:
    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_termination_signal_ends_the_run_like_ctrl_c_and_keeps_the_completed_trials(
        self, world, capsys, signum
    ):
        code = cli(
            world,
            passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=deps_signalling_after(world, 3, signum),
        )

        written = read_artifact(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert outcomes_of(written, BASELINE_LABEL) == ["pass", "pass"]
        assert "Traceback" not in capsys.readouterr().err

    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_a_termination_signal_raises_keyboard_interrupt_while_the_context_is_active(
        self, signum
    ):
        with interrupts.termination_as_interrupt(), pytest.raises(KeyboardInterrupt):
            signal_own_thread(signum)

    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_previous_handlers_are_back_in_place_after_the_run(self, world, signum):
        cli(world, passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert signal.getsignal(signum) is note_signal

    def test_previous_handlers_are_back_in_place_after_a_declined_run(self, world):
        gated_cli(world, passing_stub(world), io.StringIO("n\n"))

        assert all(
            signal.getsignal(signum) is note_signal for signum in TERMINATION_SIGNALS
        )


@pytest.mark.usefixtures("harmless_termination_signals")
class TestRunGuard:
    def test_a_new_guard_has_neither_started_nor_seen_a_signal(self):
        guard = interrupts.RunGuard()

        assert (guard.started, guard.arrived) == (False, False)

    def test_signals_are_held_inside_and_free_after_and_the_guard_remembers_it_started(
        self,
    ):
        guard = interrupts.RunGuard()

        with guard.held():
            blocked_inside = blocked_signals()
            started_inside = guard.started

        assert set(INTERRUPT_SIGNALS) <= blocked_inside
        assert started_inside is True
        assert not set(INTERRUPT_SIGNALS) & blocked_signals()
        assert (guard.started, guard.arrived) == (True, False)

    def test_a_signal_that_arrives_inside_is_reported_and_consumed(self):
        guard = interrupts.RunGuard()

        with guard.held():
            signal_own_thread(signal.SIGTERM)

        assert guard.arrived is True
        with interrupts.held_signals():
            assert interrupts.pending() is False

    def test_a_keyboard_interrupt_from_the_body_is_absorbed_and_counted_as_arrived(
        self,
    ):
        guard = interrupts.RunGuard()

        with guard.held():
            raise KeyboardInterrupt

        assert guard.arrived is True
        assert not set(INTERRUPT_SIGNALS) & blocked_signals()

    def test_any_other_error_from_the_body_propagates_with_the_signals_free(self):
        guard = interrupts.RunGuard()

        with pytest.raises(RuntimeError, match="boom"), guard.held():
            raise RuntimeError("boom")

        assert not set(INTERRUPT_SIGNALS) & blocked_signals()


class TestInterruptNotices:
    def test_an_interrupt_before_the_run_says_nothing_was_run_or_spent(self):
        notice = report.render_unhandled_interrupt(run_started=False)

        assert notice == report.INTERRUPTED_BEFORE_RUN_MESSAGE
        assert "before any trial started" in notice
        assert "nothing was run or spent" in notice

    def test_an_interrupt_after_the_run_points_at_the_messages_above(self):
        notice = report.render_unhandled_interrupt(run_started=True)

        assert notice == report.INTERRUPTED_AFTER_RUN_MESSAGE
        assert "the messages above say what was saved" in notice

    def test_every_notice_for_an_interrupt_before_the_run_uses_the_same_phrase(self):
        assert (
            "interrupted before any trial started" in report.render_no_trials_notice()
        )
        assert report.INTERRUPTED_BEFORE_RUN_MESSAGE.startswith(
            "error: interrupted before any trial started"
        )

    def test_the_finishing_notice_names_the_written_artifact(self):
        notice = report.render_interrupted_while_finishing(Path("/runs/x.json"))

        assert notice == (
            "error: interrupted while finishing the run: the artifact was written "
            "to /runs/x.json"
        )


class TestInterruptBeforeTheRun:
    def test_ctrl_c_before_the_first_trial_says_nothing_was_run_or_spent(
        self, world, capsys
    ):
        def interrupted_clock():
            raise KeyboardInterrupt

        stub = passing_stub(world)

        code = cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            deps=dataclasses.replace(world.deps, clock=interrupted_clock),
        )

        err = capsys.readouterr().err
        assert code == 1
        assert err.splitlines()[-1] == report.INTERRUPTED_BEFORE_RUN_MESSAGE
        assert "nothing was run or spent" in err
        assert "artifact" not in err
        assert_nothing_ran(stub, world)

    @pytest.mark.usefixtures("harmless_termination_signals")
    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_a_termination_signal_before_the_run_says_nothing_was_run_or_spent(
        self, world, capsys, signum
    ):
        def clock_that_receives_the_signal():
            signal_own_thread(signum)
            return NOW

        stub = passing_stub(world)

        code = cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            deps=dataclasses.replace(world.deps, clock=clock_that_receives_the_signal),
        )

        err = capsys.readouterr().err
        assert code == 1
        assert err.splitlines()[-1] == report.INTERRUPTED_BEFORE_RUN_MESSAGE
        assert_nothing_ran(stub, world)
