"""Stage a fixture and run one `claude -p` trial against it.

Each trial runs in a fresh temp copy of the fixture, outside the repo, so the
project `CLAUDE.md` and hooks are not loaded and the agent cannot alter the
source fixture. The run record is raw process output: parsing the stream and
grading it happen elsewhere.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from . import interrupts, invocation
from .fixtures import copy_fixture
from .process_record import TrialProcessRecord
from .temp_tree import remove_tree

DEFAULT_TRIAL_TIMEOUT_SECONDS = 600
# Shell convention for "command not found or not executable".
COMMAND_NOT_RUNNABLE_EXIT_CODE = 127
TEMP_DIR_PREFIX = "model-effort-ab-"
OUTPUT_ENCODING = "utf-8"
KILL_COLLECT_TIMEOUT_SECONDS = 5
# How often the wait on a process looks for an interrupt: the longest an operator
# waits for Ctrl-C to be noticed.
INTERRUPT_POLL_SECONDS = 0.1


@contextmanager
def staged_fixture(fixture: Path) -> Iterator[Path]:
    """Copy a file or directory fixture into a fresh temp dir and yield that dir."""
    staging_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    try:
        copy_fixture(fixture, staging_dir / fixture.name)
        yield staging_dir
    finally:
        remove_tree(staging_dir)


def run_cli_process(
    argv: Sequence[str],
    cwd: Path,
    trial_timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> TrialProcessRecord:
    """Run `argv` in `cwd` in its own process group.

    The interrupt signals are held back for the whole call (the run already holds
    them; a caller that does not gets them held here), so no signal handler runs
    while a process is started, waited on or killed. The wait comes up for air
    every `INTERRUPT_POLL_SECONDS` to look for one.

    On timeout or interrupt the whole group is killed, so grandchildren the CLI
    spawned do not outlive the trial; a timeout sets `timed_out` and keeps the
    partial output, an interrupt consumes the signal and raises `KeyboardInterrupt`.
    A binary that cannot be started yields exit code 127 with the OS error as stderr.
    """
    previous_mask = interrupts.block()
    try:
        # The child must start with the interrupt signals free, whatever the parent holds.
        child_mask = previous_mask - interrupts.INTERRUPT_SIGNALS
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=OUTPUT_ENCODING,
                errors="replace",
                start_new_session=True,
                # The harness is single-threaded and the hook only sets a signal mask.
                preexec_fn=lambda: signal.pthread_sigmask(  # noqa: PLW1509
                    signal.SIG_SETMASK, child_mask
                ),
            )
        except OSError as error:
            return TrialProcessRecord(
                exit_code=COMMAND_NOT_RUNNABLE_EXIT_CODE,
                stdout="",
                stderr=str(error),
                timed_out=False,
                cwd=cwd,
            )
        try:
            return _wait_for_exit(process, cwd, trial_timeout_seconds)
        except BaseException:
            # The new session detaches the child from the terminal, so Ctrl-C no
            # longer reaches it; kill it here before propagating.
            _kill_group_and_collect(process)
            raise
    finally:
        interrupts.restore(previous_mask)


def _wait_for_exit(
    process: subprocess.Popen, cwd: Path, trial_timeout_seconds: float
) -> TrialProcessRecord:
    """Wait for the process to exit and its output to end, noticing an interrupt.

    A trial times out only when the process itself is still running at the
    deadline. If the process exited but a descendant keeps its pipes open, the
    output gets `KILL_COLLECT_TIMEOUT_SECONDS` to end, then the group is killed;
    the process's own exit code is kept either way.
    """
    deadline = time.monotonic() + trial_timeout_seconds
    output = _read_output(process, deadline, stop_at_exit=True)
    if output is None and process.poll() is None:
        stdout, stderr = _kill_group_and_collect(process)
        return TrialProcessRecord(
            exit_code=None, stdout=stdout, stderr=stderr, timed_out=True, cwd=cwd
        )
    if output is None:
        grace_deadline = time.monotonic() + KILL_COLLECT_TIMEOUT_SECONDS
        output = _read_output(process, grace_deadline, stop_at_exit=False)
    if output is None:
        output = _kill_group_and_collect(process)
    stdout, stderr = output
    return TrialProcessRecord(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        cwd=cwd,
    )


def _read_output(
    process: subprocess.Popen, deadline: float, *, stop_at_exit: bool
) -> tuple[str, str] | None:
    """Read the output to its end, in slices short enough to notice an interrupt.

    Returns None at the deadline, or, with `stop_at_exit`, as soon as the process
    has exited with its pipes still open. Reading continues while the process
    runs, so a child blocked on a full pipe is not deadlocked.
    """
    while True:
        if interrupts.take_pending():
            raise KeyboardInterrupt
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            return process.communicate(timeout=min(INTERRUPT_POLL_SECONDS, remaining))
        except subprocess.TimeoutExpired:
            if stop_at_exit and process.poll() is not None:
                return None


def _kill_group_and_collect(process: subprocess.Popen) -> tuple[str, str]:
    """Kill the whole group, reap the process and return the output captured so far.

    A descendant that left the process group can still hold the pipes open;
    give up on the rest of the output after a bounded wait rather than hang the
    run. If the process itself does not die within a bounded wait either, it is
    left unreaped.
    """
    _kill_process_group(process)
    try:
        return process.communicate(timeout=KILL_COLLECT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as expired:
        captured = _decode_partial(expired.stdout), _decode_partial(expired.stderr)
    try:
        process.wait(timeout=KILL_COLLECT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pass  # Not reaped; the run goes on without the process's exit status.
    return captured


def _decode_partial(data: bytes | str | None) -> str:
    """Output a timed-out `communicate` had read: bytes, even in text mode."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode(OUTPUT_ENCODING, errors="replace")
    return data


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # The group already exited.


def run_trial(
    fixture: Path,
    config: invocation.TrialConfig,
    trial_timeout_seconds: float = DEFAULT_TRIAL_TIMEOUT_SECONDS,
) -> TrialProcessRecord:
    """Run one trial of `config` against a fresh copy of `fixture`."""
    argv = invocation.build_argv(config, invocation.build_user_prompt(fixture.name))
    env = invocation.build_trial_env(os.environ)
    with staged_fixture(fixture) as staging_dir:
        return run_cli_process(argv, staging_dir, trial_timeout_seconds, env)
