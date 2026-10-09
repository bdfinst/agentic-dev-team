"""Interrupts are held for the run, including while the run is finishing."""

from __future__ import annotations

import dataclasses
import os
import signal
import threading
import time

import model_effort_ab
import pytest
from _model_effort_support import (
    CLEAN_FORM_ARGS,
    INTERRUPT_SIGNALS,
    MAX_COST_MID_RUN,
    TIMEOUT_SECONDS,
    StubClaude,
    World,
    _blocked_signals,
    _cli,
    _config,
    _deps_signalling_after,
    _make_file_fixture,
    _outcomes,
    _passing_stub,
    _raise_keyboard_interrupt,
    _run_estimate,
    _written,
)
from model_effort import (
    artifact,
    artifact_store,
    execution,
    interrupts,
    report,
    run_types,
    runner,
    session,
    trial_count,
)
from model_effort.arm import BASELINE_LABEL, CANDIDATE_LABEL
from model_effort.run_status import AbortReason

ALL_INTERRUPT_SIGNALS = pytest.mark.parametrize(
    "signum", INTERRUPT_SIGNALS, ids=lambda n: n.name
)


def _deps_signalling_with_trial_run(
    world: World, completed_trials: int, signum: int
) -> model_effort_ab.Deps:
    """Send `signum` once the trial after `completed_trials` real ones has run.

    The process has exited by then, so the signal lands while its outcome is
    resolved and graded.
    """
    started = []

    def run_then_signal(*args, **kwargs):
        record = runner.run_trial(*args, **kwargs)
        if len(started) == completed_trials:
            os.kill(os.getpid(), signum)
        started.append(args)
        return record

    return dataclasses.replace(world.deps, run_trial=run_then_signal)


def _signal_during(monkeypatch, owner, step: str, signum: int) -> list[str]:
    """Send `signum` as `owner.step` starts; the returned list gets one entry per call.

    Call-through spy: the real step still runs. The public API cannot place a
    signal inside one step of the finish sequence, so the step is wrapped.
    """
    real_step = getattr(owner, step)
    calls = []

    def signal_then_run(*args, **kwargs):
        calls.append(step)
        os.kill(os.getpid(), signum)
        return real_step(*args, **kwargs)

    monkeypatch.setattr(owner, step, signal_then_run)
    return calls


def _spy_on_writes(monkeypatch) -> list[str]:
    """Record each artifact write and still perform it.

    Call-through spy: the public API shows only the final file, not how many
    writes produced it.
    """
    real_write = artifact_store.write_artifact
    writes = []

    def counting_write(path, text):
        writes.append(text)
        return real_write(path, text)

    monkeypatch.setattr(artifact_store, "write_artifact", counting_write)
    return writes


FINISH_STEPS = [
    pytest.param(artifact, "build_artifact", id="build"),
    pytest.param(artifact_store, "render_artifact", id="render"),
    pytest.param(artifact_store, "write_artifact", id="write"),
]


@pytest.mark.usefixtures("harmless_termination_signals")
class TestInterruptsAreHeldForTheRun:
    @ALL_INTERRUPT_SIGNALS
    def test_signal_after_the_process_exited_keeps_the_completed_trial(
        self, world, capsys, signum
    ):
        stub = _passing_stub(world)

        code = _cli(
            world,
            stub,
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_signalling_with_trial_run(world, 3, signum),
        )

        written = _written(world)
        assert code == 1
        assert len(stub.calls) == 4
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass", "pass"]
        assert (
            "run stopped early (interrupt): no trial was in flight; "
            "4 completed trials were kept"
        ) in capsys.readouterr().err

    @ALL_INTERRUPT_SIGNALS
    def test_signal_during_a_trial_kills_its_process_and_drops_only_that_trial(
        self, world, signum
    ):
        stub = _passing_stub(world)
        stub.queue({}, {}, {"sleep": 30})

        def signal_once_the_third_trial_runs() -> None:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if len(stub.calls) == 3:
                        break
                except ValueError:  # the stub was mid-write
                    pass
                time.sleep(0.02)
            signal.pthread_kill(threading.main_thread().ident, signum)

        threading.Thread(target=signal_once_the_third_trial_runs, daemon=True).start()
        code = _cli(world, stub, *CLEAN_FORM_ARGS, "--trials", "5")

        written = _written(world)
        assert code == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]
        with pytest.raises(ProcessLookupError):
            os.kill(stub.calls[2]["pid"], 0)

    def test_signal_while_the_timeout_is_handled_still_kills_the_group(
        self, stub_dir, fixture_root, monkeypatch
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        # Call-through spy on `_kill_process_group`: it sends a signal just before
        # the real kill. The public API cannot time a signal to that step of the
        # timeout handler.
        real_kill = runner._kill_process_group
        killed = []

        def signal_then_kill(process):
            os.kill(os.getpid(), signal.SIGTERM)
            killed.append(process.pid)
            real_kill(process)

        monkeypatch.setattr(runner, "_kill_process_group", signal_then_kill)
        held = interrupts.block()
        try:
            record = runner.run_trial(fixture, _config(stub), trial_timeout_seconds=1)
            still_pending = interrupts.take_pending()
        finally:
            interrupts.restore(held)

        assert record.timed_out is True
        assert still_pending, "the signal was dropped instead of left for the run"
        with pytest.raises(ProcessLookupError):
            os.kill(killed[0], 0)

    def test_interrupt_signals_are_blocked_from_the_first_trial_to_the_save_and_free_afterwards(
        self, world, monkeypatch
    ):
        blocked = {}
        real_trial, real_write = runner.run_trial, artifact_store.write_artifact

        def spy_trial(*args, **kwargs):
            blocked.setdefault("trial", _blocked_signals())
            return real_trial(*args, **kwargs)

        def spy_write(path, text):
            blocked["write"] = _blocked_signals()
            return real_write(path, text)

        monkeypatch.setattr(artifact_store, "write_artifact", spy_write)

        _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "1",
            deps=dataclasses.replace(world.deps, run_trial=spy_trial),
        )

        assert set(INTERRUPT_SIGNALS) <= blocked["trial"]
        assert set(INTERRUPT_SIGNALS) <= blocked["write"]
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_signal_pending_before_the_first_trial_starts_no_trial(
        self, world, scout_plan
    ):
        settings = run_types.TrialSettings(
            trials=trial_count.TrialCount(1, "test"),
            trial_timeout_seconds=TIMEOUT_SECONDS,
            claude_bin="unused",
        )

        def must_not_run(*_args):
            raise AssertionError("a trial started")

        held = interrupts.block()
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            run = execution.run_trials(
                scout_plan, settings, _run_estimate(), run_trial=must_not_run
            )
        finally:
            interrupts.restore(held)

        assert (run.abort_reason, run.started_trials) == (AbortReason.INTERRUPT, 0)

    def test_a_pending_signal_is_consumed_so_it_is_not_delivered_later(self):
        held = interrupts.block()
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            first, second = interrupts.take_pending(), interrupts.take_pending()
        finally:
            interrupts.restore(held)

        assert (first, second) == (True, False)

    def test_a_signal_landing_just_before_the_restore_is_reported_not_raised(
        self, monkeypatch
    ):
        held = interrupts.block()

        def consume_then_receive_one_more() -> bool:
            os.kill(os.getpid(), signal.SIGTERM)
            return False

        # Fault injected: `take_pending` is replaced so a SIGTERM lands after the
        # consume and before the restore. That window is a few bytecodes wide; the
        # public API gives a test no way to send a signal into it.
        monkeypatch.setattr(interrupts, "take_pending", consume_then_receive_one_more)
        previous_handler = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        try:
            arrived = interrupts.restore_reporting(held)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

        assert arrived is True
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_a_sighup_the_process_ignores_does_not_stop_the_run(self, world):
        stub = _passing_stub(world)
        original = signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            code = _cli(
                world,
                stub,
                *CLEAN_FORM_ARGS,
                "--trials",
                "3",
                deps=_deps_signalling_after(world, 2, signal.SIGHUP),
            )
        finally:
            signal.signal(signal.SIGHUP, original)

        written = _written(world)
        assert code == 0
        assert len(stub.calls) == 6
        assert (written["status"], written["abort_reason"]) == ("complete", None)


@pytest.mark.usefixtures("harmless_termination_signals")
class TestSignalWhileFinishing:
    @pytest.mark.parametrize(("owner", "step"), FINISH_STEPS)
    def test_a_complete_run_stays_complete_is_saved_once_and_exits_1_truthfully(
        self, world, capsys, monkeypatch, owner, step
    ):
        calls = _signal_during(monkeypatch, owner, step, signal.SIGTERM)
        writes = _spy_on_writes(monkeypatch)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert calls == [step]
        assert len(writes) == 1
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert f"the artifact was written to {world.artifact_path}" in err
        assert "Traceback" not in err

    @pytest.mark.parametrize(("owner", "step"), FINISH_STEPS)
    def test_a_stopped_run_keeps_its_recorded_stop_reason(
        self, world, monkeypatch, owner, step
    ):
        _signal_during(monkeypatch, owner, step, signal.SIGINT)
        writes = _spy_on_writes(monkeypatch)

        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            "--max-cost",
            str(MAX_COST_MID_RUN),
        )

        written = _written(world)
        assert code == 1
        assert len(writes) == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "max-cost",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]

    @pytest.mark.parametrize(("owner", "step"), FINISH_STEPS)
    def test_a_second_signal_while_finishing_an_interrupted_run_loses_nothing(
        self, world, capsys, monkeypatch, owner, step
    ):
        _signal_during(monkeypatch, owner, step, signal.SIGHUP)
        writes = _spy_on_writes(monkeypatch)

        code = _cli(
            world,
            _passing_stub(world),
            *CLEAN_FORM_ARGS,
            "--trials",
            "5",
            deps=_deps_signalling_after(world, 3, signal.SIGTERM),
        )

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert len(writes) == 1
        assert (written["status"], written["abort_reason"]) == (
            "incomplete",
            "interrupt",
        )
        assert _outcomes(written, BASELINE_LABEL) == ["pass", "pass"]
        assert _outcomes(written, CANDIDATE_LABEL) == ["pass"]
        assert f"artifact written: {world.artifact_path}" in err

    def test_a_signal_landing_as_the_signals_are_released_is_reported_as_finishing(
        self, world, capsys, monkeypatch
    ):
        # Fault injected: one more SIGTERM as `restore_reporting` hands the mask
        # back, still inside the session's guarded region. The public API cannot
        # reach that window: no step of the run runs there.
        real_restore = interrupts.restore_reporting

        def restore_then_receive_one_more(previous_mask):
            arrived = real_restore(previous_mask)
            os.kill(os.getpid(), signal.SIGTERM)
            return arrived

        monkeypatch.setattr(
            interrupts, "restore_reporting", restore_then_receive_one_more
        )

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert f"the artifact was written to {world.artifact_path}" in err
        assert "nothing was run or spent" not in err
        assert "Traceback" not in err

    def test_a_signal_landing_after_the_session_returns_is_not_reported_as_before_the_run(
        self, world, capsys, monkeypatch
    ):
        # Fault injected: a SIGTERM after `run_session` has returned, so it reaches
        # `main` with the signals free. The public API cannot reach that window:
        # the run is over and saved, and no step of it runs there.
        real_run_session = session.run_session

        def run_then_receive_one_more(*args, **kwargs):
            code = real_run_session(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return code

        monkeypatch.setattr(session, "run_session", run_then_receive_one_more)

        code = _cli(world, _passing_stub(world), *CLEAN_FORM_ARGS, "--trials", "1")

        written = _written(world)
        err = capsys.readouterr().err
        assert code == 1
        assert (written["status"], written["abort_reason"]) == ("complete", None)
        assert "nothing was run or spent" not in err
        assert report.INTERRUPTED_AFTER_RUN_MESSAGE in err
        assert "Traceback" not in err
