"""Trial runner: a fixture is staged into a fresh temp dir per trial and the CLI is invoked with an isolating argv.
A stub executable stands in for `claude` and records its argv, cwd and the files it saw.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest
from _model_effort_support import (
    INTERRUPT_SIGNALS,
    TIMEOUT_SECONDS,
    StubClaude,
    _blocked_signals,
    _config,
    _make_directory_fixture,
    _make_file_fixture,
    _raise_keyboard_interrupt,
    _snapshot,
)
from model_effort import invocation, runner


class TestStagingFixtures:
    def test_file_fixture_is_staged_under_its_own_name(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root)

        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["files_before"] == {"form.html": "<form></form>"}

    def test_directory_fixture_is_staged_with_nested_files(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir)
        fixture = _make_directory_fixture(fixture_root)

        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["files_before"] == {
            "service/README.md": "readme",
            "service/src/app.py": "print('app')",
            "service/src/deep/util.py": "print('util')",
        }

    @pytest.mark.parametrize(
        "make_fixture",
        [_make_file_fixture, _make_directory_fixture],
        ids=["file", "directory"],
    )
    def test_two_trials_each_see_a_pristine_copy_and_source_is_unchanged(
        self, make_fixture, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, tamper=True)
        fixture = make_fixture(fixture_root)
        source_before = _snapshot(fixture)

        runner.run_trial(fixture, _config(stub))
        runner.run_trial(fixture, _config(stub))

        first, second = stub.calls
        assert first["files_before"] == second["files_before"]
        assert not any("TAMPERED" in text for text in second["files_before"].values())
        assert _snapshot(fixture) == source_before

    def test_trials_run_in_distinct_temp_dirs(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))
        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["cwd"] != stub.calls[1]["cwd"]

    def test_temp_dir_is_removed_after_the_trial(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))

        assert not Path(stub.calls[0]["cwd"]).exists()

    def test_temp_dir_is_removed_after_a_timeout(self, stub_dir, fixture_root):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS)

        assert stub.calls, "the stub never started, so the timeout proved nothing"
        assert not Path(stub.calls[0]["cwd"]).exists()

    def test_symlinks_in_a_directory_fixture_are_copied_as_links(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir)
        fixture = _make_directory_fixture(fixture_root)
        outside = _make_file_fixture(fixture_root, "outside.txt", "outside")
        (fixture / "link.txt").symlink_to(outside)

        runner.run_trial(fixture, _config(stub))

        assert stub.calls[0]["symlinks"] == ["service/link.txt"]

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
    def test_temp_dir_that_cannot_be_removed_is_reported_on_stderr(
        self, stub_dir, fixture_root, capsys
    ):
        stub = StubClaude(stub_dir, lock_subdir=True)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))

        leftover = Path(stub.calls[0]["cwd"])
        try:
            assert "could not remove" in capsys.readouterr().err
        finally:
            (leftover / "locked").chmod(0o700)
            shutil.rmtree(leftover)


class TestSignalsAroundSpawn:
    def test_interrupt_signals_are_blocked_while_the_process_starts_and_free_afterwards(
        self, stub_dir, fixture_root, monkeypatch
    ):
        blocked_during_spawn = []
        real_popen = subprocess.Popen

        def record_mask_then_spawn(*args, **kwargs):
            blocked_during_spawn.append(_blocked_signals())
            return real_popen(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", record_mask_then_spawn)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(StubClaude(stub_dir)))

        assert set(INTERRUPT_SIGNALS) <= blocked_during_spawn[0]
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_the_cli_process_gets_no_stdin_and_its_own_session(
        self, stub_dir, fixture_root, monkeypatch
    ):
        spawn_options = []
        real_popen = subprocess.Popen

        def record_options_then_spawn(*args, **kwargs):
            spawn_options.append(kwargs)
            return real_popen(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", record_options_then_spawn)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(StubClaude(stub_dir)))

        assert spawn_options[0]["stdin"] == subprocess.DEVNULL
        assert spawn_options[0]["start_new_session"] is True

    def test_signals_are_free_again_when_the_binary_cannot_start(self, fixture_root):
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(claude_bin="/no/such/claude"))

        assert record.exit_code == runner.COMMAND_NOT_RUNNABLE_EXIT_CODE
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()

    def test_the_cli_process_starts_with_the_interrupt_signals_unblocked(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        runner.run_trial(fixture, _config(stub))

        blocked_in_child = set(stub.calls[0]["blocked_signals"])
        assert not {signum.name for signum in INTERRUPT_SIGNALS} & blocked_in_child

    def test_signal_arriving_during_the_spawn_still_kills_the_new_process_group(
        self, stub_dir, fixture_root, monkeypatch
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        children = []
        real_popen = subprocess.Popen

        def spawn_then_terminate(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        monkeypatch.setattr(subprocess, "Popen", spawn_then_terminate)
        previous = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        try:
            with pytest.raises(KeyboardInterrupt):
                runner.run_trial(fixture, _config(stub))
            assert children[0].poll() is not None, "the child outlived the interrupt"
        finally:
            signal.signal(signal.SIGTERM, previous)
            for child in children:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_interrupt_signals_are_blocked_while_the_group_is_killed_and_free_afterwards(
        self, stub_dir, fixture_root, monkeypatch
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        blocked_during_kill = []
        # Call-through spy on `_kill_process_group`: it records the signal mask at
        # the kill. The mask is not visible from outside the process.
        real_kill = runner._kill_process_group
        real_popen = subprocess.Popen

        def record_mask_then_kill(process):
            blocked_during_kill.append(_blocked_signals())
            real_kill(process)

        def spawn_then_terminate(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        monkeypatch.setattr(runner, "_kill_process_group", record_mask_then_kill)
        monkeypatch.setattr(subprocess, "Popen", spawn_then_terminate)
        previous = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
        try:
            with pytest.raises(KeyboardInterrupt):
                runner.run_trial(fixture, _config(stub))
        finally:
            signal.signal(signal.SIGTERM, previous)

        assert blocked_during_kill, "the process group was never killed"
        assert set(INTERRUPT_SIGNALS) <= blocked_during_kill[0]
        assert not set(INTERRUPT_SIGNALS) & _blocked_signals()


class TestTrialEnvironment:
    def test_parent_session_identity_variables_are_removed_and_the_rest_kept(self):
        parent = {
            "CLAUDE_CODE_SESSION_ID": "parent-session",
            "CLAUDE_CODE_ENTRYPOINT": "cli",
            "HOME": "/home/me",
            "ANTHROPIC_API_KEY": "key",
        }

        env = invocation.build_trial_env(parent)

        assert env == {"HOME": "/home/me", "ANTHROPIC_API_KEY": "key"}

    def test_the_cli_process_receives_the_scrubbed_environment(
        self, stub_dir, fixture_root, monkeypatch
    ):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
        monkeypatch.setenv("KEEP_ME", "1")
        stub = StubClaude(stub_dir)

        runner.run_trial(_make_file_fixture(fixture_root), _config(stub))

        env_names = stub.calls[0]["env_names"]
        assert "CLAUDE_CODE_SESSION_ID" not in env_names
        assert "KEEP_ME" in env_names and "HOME" in env_names


GRANDCHILD_DELAY_SECONDS = 4
# Short grace for the output of an exited child, so the tests do not wait the real 5 s.
HOLDER_GRACE_SECONDS = 1


def _wait_until_after(started: float, delay: float) -> None:
    """Sleep until a grandchild started after `started` would have written its marker."""
    margin = 1.5
    remaining = started + delay + margin - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def _process_gone_within(pid: int, seconds: float) -> bool:
    """True once `pid` no longer exists; a killed orphan is reaped a moment after the kill."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)


@pytest.fixture
def short_output_grace(monkeypatch) -> None:
    monkeypatch.setattr(runner, "KILL_COLLECT_TIMEOUT_SECONDS", HOLDER_GRACE_SECONDS)


class TestExecution:
    def test_exit_code_stdout_and_stderr_are_captured_for_a_failing_run(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(
            stub_dir, exit_code=3, stdout="out-line", stderr="boom: bad model"
        )
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout, record.stderr, record.timed_out) == (
            3,
            "out-line",
            "boom: bad model",
            False,
        )

    def test_successful_run_reports_zero_exit_and_not_timed_out(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, stdout="ok")
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout, record.timed_out) == (0, "ok", False)

    def test_output_that_is_not_utf8_is_decoded_with_replacement_characters(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, stdout_hex="6f6bff")
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(fixture, _config(stub))

        assert (record.exit_code, record.stdout) == (0, "ok�")

    def test_run_exceeding_the_time_limit_is_marked_timed_out(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS
        )

        assert stub.calls, "the stub never started, so the timeout proved nothing"
        assert record.timed_out is True
        assert record.exit_code is None

    def test_clean_exit_is_not_a_timeout_when_a_descendant_holds_the_pipes_open(
        self, stub_dir, fixture_root, short_output_grace
    ):
        stub = StubClaude(stub_dir, stdout="result", exit_code=0, holder_sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        started = time.monotonic()

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS * 10
        )

        assert time.monotonic() - started < TIMEOUT_SECONDS
        assert (record.exit_code, record.stdout, record.timed_out) == (
            0,
            "result",
            False,
        )

    def test_a_descendant_in_the_trials_group_is_killed_when_the_output_wait_ends(
        self, stub_dir, fixture_root, short_output_grace
    ):
        pid_file = stub_dir / "holder.pid"
        stub = StubClaude(
            stub_dir,
            stdout="result",
            holder_sleep=30,
            holder_pid_file=str(pid_file),
        )
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS * 10
        )

        holder_pid = int(pid_file.read_text(encoding="utf-8"))
        assert (record.exit_code, record.timed_out) == (0, False)
        assert _process_gone_within(holder_pid, TIMEOUT_SECONDS)

    def test_a_timed_out_trial_keeps_the_output_written_before_the_kill(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(
            stub_dir,
            sleep=30,
            early_stdout="partial stdout",
            early_stderr="partial stderr",
        )
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS
        )

        assert record.timed_out is True
        assert (record.stdout, record.stderr) == ("partial stdout", "partial stderr")

    def test_failing_exit_code_is_kept_when_a_descendant_holds_the_pipes_open(
        self, stub_dir, fixture_root, short_output_grace
    ):
        stub = StubClaude(stub_dir, stderr="boom", exit_code=3, holder_sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS * 10
        )

        assert (record.exit_code, record.stderr, record.timed_out) == (3, "boom", False)

    def test_output_is_kept_when_a_descendant_in_another_session_holds_the_pipes(
        self, stub_dir, fixture_root, short_output_grace
    ):
        stub = StubClaude(
            stub_dir,
            stdout="result",
            holder_sleep=HOLDER_GRACE_SECONDS * 6,
            holder_new_session=True,
        )
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        started = time.monotonic()

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS * 10
        )

        assert time.monotonic() - started < HOLDER_GRACE_SECONDS * 4
        assert (record.exit_code, record.stdout, record.timed_out) == (
            0,
            "result",
            False,
        )

    def test_child_that_outlives_the_deadline_is_still_a_timeout_with_a_descendant_holding_the_pipes(
        self, stub_dir, fixture_root
    ):
        stub = StubClaude(stub_dir, sleep=30, holder_sleep=30)
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")

        record = runner.run_trial(
            fixture, _config(stub), trial_timeout_seconds=TIMEOUT_SECONDS
        )

        assert (record.exit_code, record.timed_out) == (None, True)

    def test_process_that_survives_the_kill_is_left_unreaped_after_a_bounded_wait(
        self, monkeypatch
    ):
        waits = []

        class UnkillableProcess:
            pid = 0

            def communicate(self, timeout):
                raise subprocess.TimeoutExpired("claude", timeout)

            def wait(self, timeout):
                waits.append(timeout)
                raise subprocess.TimeoutExpired("claude", timeout)

        monkeypatch.setattr(runner, "_kill_process_group", lambda _process: None)

        output = runner._kill_group_and_collect(UnkillableProcess())

        assert output == ("", "")
        assert waits == [runner.KILL_COLLECT_TIMEOUT_SECONDS]

    def test_timeout_kills_the_whole_process_group_not_just_the_child(
        self, stub_dir, fixture_root
    ):
        marker, spawned = stub_dir / "late.txt", stub_dir / "spawned.txt"
        stub = StubClaude(
            stub_dir,
            sleep=30,
            grandchild_marker=str(marker),
            grandchild_delay=GRANDCHILD_DELAY_SECONDS,
            grandchild_spawned=str(spawned),
        )
        started = time.monotonic()

        runner.run_trial(
            _make_file_fixture(fixture_root, "a.txt", "a"),
            _config(stub),
            trial_timeout_seconds=TIMEOUT_SECONDS,
        )
        _wait_until_after(started, GRANDCHILD_DELAY_SECONDS)

        assert spawned.exists(), (
            "the grandchild never started, so the kill proved nothing"
        )
        assert not marker.exists()

    def test_interrupt_kills_the_whole_process_group_before_propagating(
        self, stub_dir, fixture_root
    ):
        marker, spawned = stub_dir / "late.txt", stub_dir / "spawned.txt"
        delay = GRANDCHILD_DELAY_SECONDS - 2
        stub = StubClaude(
            stub_dir,
            sleep=30,
            grandchild_marker=str(marker),
            grandchild_delay=delay,
            grandchild_spawned=str(spawned),
        )
        started = time.monotonic()
        cancelled = threading.Event()

        def interrupt_once_spawned() -> None:
            deadline = time.monotonic() + 10
            while not spawned.exists() and time.monotonic() < deadline:
                if cancelled.wait(0.05):
                    return
            if spawned.exists() and not cancelled.is_set():
                signal.pthread_kill(threading.main_thread().ident, signal.SIGINT)

        interrupter = threading.Thread(target=interrupt_once_spawned, daemon=True)
        interrupter.start()
        try:
            with pytest.raises(KeyboardInterrupt):
                runner.run_trial(
                    _make_file_fixture(fixture_root, "a.txt", "a"),
                    _config(stub),
                    trial_timeout_seconds=60,
                )
        finally:
            cancelled.set()
            interrupter.join()
        _wait_until_after(started, delay)

        assert spawned.exists()
        assert not marker.exists()

    def test_missing_claude_binary_yields_exit_127_with_the_os_error_as_stderr(
        self, tmp_path, fixture_root
    ):
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        missing = tmp_path / "no-such-claude"

        record = runner.run_trial(fixture, _config(claude_bin=str(missing)))

        assert (record.exit_code, record.timed_out) == (127, False)
        assert "no-such-claude" in record.stderr

    def test_non_executable_claude_binary_yields_exit_127(self, tmp_path, fixture_root):
        fixture = _make_file_fixture(fixture_root, "a.txt", "a")
        not_executable = tmp_path / "claude-plain-file"
        not_executable.write_text("not a program", encoding="utf-8")
        not_executable.chmod(0o644)

        record = runner.run_trial(fixture, _config(claude_bin=str(not_executable)))

        assert record.exit_code == 127
        assert record.stderr != ""
