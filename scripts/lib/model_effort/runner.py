"""Stage a fixture and run one `claude -p` trial against it.

Each trial runs in a fresh temp copy of the fixture, outside the repo, so the
project `CLAUDE.md` and hooks are not loaded and the agent cannot alter the
source fixture. The run record is raw process output: parsing the stream and
grading it happen elsewhere.
"""

from __future__ import annotations

import dataclasses
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from . import interrupts, invocation
from .check_jail import CheckJail
from .fixtures import copy_fixture
from .process_record import TrialProcessRecord
from .temp_tree import remove_tree

DEFAULT_TRIAL_TIMEOUT_SECONDS = 600
# Shell convention for "command not found or not executable".
COMMAND_NOT_RUNNABLE_EXIT_CODE = 127
TEMP_DIR_PREFIX = "model-effort-ab-"
PRIVATE_DIR_PREFIX = "model-effort-trial-private-"
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
    the process's own exit code is kept either way. A signal that arrives during
    that wait ends it early and stays pending: the finished trial is kept.
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

    A signal that arrives while the process runs is consumed and raises
    `KeyboardInterrupt`. Without `stop_at_exit` the process has already exited
    and its result is complete, so a pending signal only ends the wait (None) and
    stays pending for the run to act on, instead of dropping the finished trial.
    """
    while True:
        if stop_at_exit:
            if interrupts.take_pending():
                raise KeyboardInterrupt
        elif interrupts.pending():
            return None
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
    """Run one trial of `config` against a fresh copy of `fixture`.

    A sandboxed trial's copy is first made a git repo with one commit, and the
    trial reads its own copy of the knowledge directory, so a write to it cannot
    reach a later trial. When the config has test commands they run in the copy
    after the agent finishes, jailed when the config has a jail, with no
    credential in their environment; their results ride on the returned record.
    """
    with staged_fixture(fixture) as staging_dir, _private_dirs() as private:
        if config.sandbox:
            config = _with_own_knowledge(config, private / "plugin")
        argv = invocation.build_argv(
            config, invocation.build_user_prompt(fixture.name, config.task)
        )
        env = invocation.build_trial_env(os.environ, _fresh_dir(private / "home"))
        work_dir = staging_dir / fixture.name if fixture.is_dir() else staging_dir
        if config.sandbox:
            init_sandbox_repo(work_dir)
        record = run_cli_process(argv, staging_dir, trial_timeout_seconds, env)
        if not config.test_commands or record.timed_out:
            return record
        restore_protected_paths(fixture, work_dir, config.protected_paths)
        check_env = invocation.build_check_env(
            os.environ, _fresh_dir(private / "check-home")
        )
        check_temp = _fresh_dir(private / "check-tmp")
        results = tuple(
            run_check_command(
                command,
                work_dir,
                trial_timeout_seconds,
                {**check_env, "TMPDIR": str(check_temp)},
                jail=config.check_jail,
                jail_temp_dir=check_temp,
            )
            for command in config.test_commands
        )
        return dataclasses.replace(record, check_results=results)


@contextmanager
def _private_dirs() -> Iterator[Path]:
    """A temp dir outside the staging dir for the trial's HOME, knowledge copy and check temp."""
    root = Path(tempfile.mkdtemp(prefix=PRIVATE_DIR_PREFIX))
    try:
        yield root
    finally:
        remove_tree(root)


def _fresh_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _with_own_knowledge(
    config: invocation.TrialConfig, plugin_root: Path
) -> invocation.TrialConfig:
    knowledge_dir = plugin_root / config.eval_paths.knowledge_dir.name
    shutil.copytree(config.eval_paths.knowledge_dir, knowledge_dir, symlinks=True)
    return dataclasses.replace(
        config,
        eval_paths=dataclasses.replace(
            config.eval_paths, plugin_root=plugin_root, knowledge_dir=knowledge_dir
        ),
    )


SANDBOX_GIT_IDENTITY = ("-c", "user.name=model-effort-ab", "-c", "user.email=ab@example.com")
PYTHON_PLACEHOLDER = "{python}"


def init_sandbox_repo(work_dir: Path) -> None:
    """Make `work_dir` a git repo whose one commit holds the fixture as staged.

    Raises:
        OSError, subprocess.CalledProcessError: git is missing or a step failed;
            the run records that as a harness error.
    """
    for args in (
        ("init", "-q"),
        ("add", "-A"),
        ("commit", "-q", "--no-verify", "--no-gpg-sign", "-m", "fixture"),
    ):
        subprocess.run(
            ["git", *SANDBOX_GIT_IDENTITY, *args],
            cwd=work_dir,
            check=True,
            capture_output=True,
        )


class UnsafeProtectedPathError(RuntimeError):
    """A protected path would resolve outside the trial's working copy."""


def restore_protected_paths(
    pristine_fixture: Path, work_dir: Path, protected_paths: tuple[str, ...]
) -> None:
    """Put each protected path back as the pristine fixture has it, so the agent cannot change its own grader.

    The agent may have replaced any part of a path with a symlink. Every ancestor
    is walked from `work_dir` down: a symlink or file in an ancestor's place is
    removed and a real directory made, and each step is checked to resolve inside
    `work_dir` before anything is removed or copied. A symlink is removed, never
    followed, so nothing outside `work_dir` is touched.

    Raises:
        UnsafeProtectedPathError: a path is absolute or climbs out with `..`
            (fixture loading refuses those first), or a step resolves outside
            `work_dir`.
    """
    root = work_dir.resolve()
    for relative in protected_paths:
        parts = PurePosixPath(relative).parts
        if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
            raise UnsafeProtectedPathError(f"protected path {relative!r} is not inside the fixture")
        parent = root
        for part in parts[:-1]:
            parent = _real_dir(parent, part, root)
        target = parent / parts[-1]
        _assert_inside(target.parent, root)
        _remove_entry(target)
        source = pristine_fixture / relative
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, target, symlinks=True)
        elif source.is_file() or source.is_symlink():
            shutil.copy2(source, target, follow_symlinks=False)


def _real_dir(parent: Path, name: str, root: Path) -> Path:
    """`parent / name` as a real directory inside `root`, replacing a symlink or file there."""
    _assert_inside(parent, root)
    entry = parent / name
    if entry.is_symlink() or (entry.exists() and not entry.is_dir()):
        entry.unlink()
    if not entry.exists():
        entry.mkdir()
    _assert_inside(entry, root)
    return entry


def _remove_entry(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def _assert_inside(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root):
        raise UnsafeProtectedPathError(f"{path} resolves outside the working copy {root}")


def run_check_command(
    command: str,
    work_dir: Path,
    timeout_seconds: float,
    env: dict[str, str] | None,
    *,
    jail: CheckJail | None = None,
    jail_temp_dir: Path | None = None,
) -> dict:
    """Run one test command in `work_dir`; `{python}` is this interpreter.

    With `jail` the command may write only to `work_dir` and `jail_temp_dir`
    (default: `work_dir`) and has no network.
    """
    argv = shlex.split(command.replace(PYTHON_PLACEHOLDER, shlex.quote(sys.executable)))
    if jail is not None:
        argv = jail.wrap(argv, work_dir, jail_temp_dir or work_dir)
    record = run_cli_process(argv, work_dir, timeout_seconds, env)
    return {
        "command": command,
        "exit_code": record.exit_code,
        "stderr_first_line": _failure_line(record),
    }


def _failure_line(record: TrialProcessRecord) -> str:
    """A line saying why a command failed: stderr's first, else stdout's last."""
    if record.exit_code == 0:
        return ""
    if record.timed_out:
        return "timed out"
    for text, pick in ((record.stderr, 0), (record.stdout, -1)):
        lines = [line for line in text.splitlines() if line.strip()]
        if lines:
            return lines[pick].strip()[:200]
    return ""
