"""Interrupts (model_effort.interrupts): Ctrl-C and termination signals end the run and keep the completed trials."""

from __future__ import annotations

import dataclasses
import io
import os
import signal
from pathlib import Path

import pytest
from _model_effort_support import (
    CLEAN_FORM_ARGS,
    INTERRUPT_SIGNALS,
    NOW,
    TERMINATION_SIGNALS,
    _arm_block,
    _blocked_signals,
    _cli,
    _deps_signalling_after,
    _gated_cli,
    _interrupting_deps,
    _note_signal,
    _outcomes,
    _passing_stub,
    _written,
    assert_nothing_ran,
)
from model_effort import interrupts, report
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL


class TestInterrupt:
    def test_ctrl_c_after_three_trials_keeps_them_and_marks_the_artifact_interrupted(
        self, world
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 3),
        )

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == 3
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]

    def test_interrupt_prints_no_traceback_and_names_the_artifact_and_the_dropped_trial(
        self, world, capsys
    ):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 3),
        )

        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert (
            "error: run stopped early (interrupt): the trial in flight was dropped; "
            "3 completed trials were kept"
        ) in err
        assert f"artifact written: {world.artifact_path}" in err

    def test_arm_with_no_completed_trial_lists_no_fixtures(self, world):
        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 1),
        )

        written = _written(world)
        assert _arm_block(written, CANDIDATE_LABEL)["fixtures"] == []
        assert _arm_block(written, CANDIDATE_LABEL)["totals"]["pass"] == 0
        assert _outcomes(written, BASELINE_LABEL) == ["pass"]

    def test_ctrl_c_inside_the_first_trial_writes_an_interrupted_artifact_with_no_results(
        self, world, capsys
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_interrupting_deps(world, 0),
        )

        written = _written(world)
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
            signum: signal.signal(signum, _note_signal)
            for signum in TERMINATION_SIGNALS
        }
        ignored, handled = TERMINATION_SIGNALS[0], TERMINATION_SIGNALS[1:]
        signal.signal(ignored, signal.SIG_IGN)
        try:
            with interrupts.termination_as_interrupt():
                assert signal.getsignal(ignored) is signal.SIG_IGN
                for signum in handled:
                    assert signal.getsignal(signum) is not _note_signal
            assert signal.getsignal(ignored) is signal.SIG_IGN
            for signum in handled:
                assert signal.getsignal(signum) is _note_signal
        finally:
            for signum, handler in originals.items():
                signal.signal(signum, handler)


@pytest.mark.usefixtures("harmless_termination_signals")
class TestTerminationSignals:
    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_termination_signal_ends_the_run_like_ctrl_c_and_keeps_the_completed_trials(
        self, world, capsys, signum
    ):
        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_signalling_after(world, 3, signum),
        )

        written = _written(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert "Traceback" not in capsys.readouterr().err

    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_a_termination_signal_raises_keyboard_interrupt_while_the_context_is_active(
        self, signum
    ):
        with interrupts.termination_as_interrupt(), pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signum)

    @pytest.mark.parametrize("signum", TERMINATION_SIGNALS, ids=lambda n: n.name)
    def test_previous_handlers_are_back_in_place_after_the_run(self, world, signum):
        _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        assert signal.getsignal(signum) is _note_signal

    def test_previous_handlers_are_back_in_place_after_a_declined_run(self, world):
        _gated_cli(world, _passing_stub(world), io.StringIO("n\n"))

        assert all(
            signal.getsignal(signum) is _note_signal for signum in TERMINATION_SIGNALS
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
            blocked_inside = _blocked_signals()
            started_inside = guard.started

        assert set(INTERRUPT_SIGNALS) <= blocked_inside
        assert started_inside is True
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()
        assert (guard.started, guard.arrived) == (True, False)

    def test_a_signal_that_arrives_inside_is_reported_and_consumed(self):
        guard = interrupts.RunGuard()

        with guard.held():
            os.kill(os.getpid(), signal.SIGTERM)

        assert guard.arrived is True
        held = interrupts.block()
        try:
            assert interrupts.take_pending() is False
        finally:
            interrupts.restore(held)

    def test_a_keyboard_interrupt_from_the_body_is_absorbed_and_counted_as_arrived(
        self,
    ):
        guard = interrupts.RunGuard()

        with guard.held():
            raise KeyboardInterrupt

        assert guard.arrived is True
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_any_other_error_from_the_body_propagates_with_the_signals_free(self):
        guard = interrupts.RunGuard()

        with pytest.raises(RuntimeError, match="boom"), guard.held():
            raise RuntimeError("boom")

        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()


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

        stub = _passing_stub(world)

        code = _cli(
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
            os.kill(os.getpid(), signum)
            return NOW

        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            deps=dataclasses.replace(world.deps, clock=clock_that_receives_the_signal),
        )

        err = capsys.readouterr().err
        assert code == 1
        assert err.splitlines()[-1] == report.INTERRUPTED_BEFORE_RUN_MESSAGE
        assert_nothing_ran(stub, world)
