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
import stat
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
from .work_diff import working_copy_diff

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
    *,
    stdin_text: str | None = None,
) -> TrialProcessRecord:
    """Run `argv` in `cwd` in its own process group.

    `stdin_text` is written to the process's stdin, which is then closed; without
    it stdin is `/dev/null`. Input too large for one argv string goes here.

    The interrupt signals are held back for the whole call (the run already holds
    them; a caller that does not gets them held here), so no signal handler runs
    while a process is started, waited on or killed. The wait comes up for air
    every `INTERRUPT_POLL_SECONDS` to look for one.

    The whole group is killed once the process ends, however it ends, so a
    grandchild the CLI spawned in its group does not outlive the call: nothing
    it started can still be writing when the caller restores or grades the copy.
    A process that left the group (a new session) is not reached. A timeout sets
    `timed_out` and keeps the partial output, an interrupt consumes the signal
    and raises `KeyboardInterrupt`.
    A binary that cannot be started yields exit code 127 with the OS error as stderr.
    """
    with interrupts.held_signals() as previous_mask:
        # The child must start with the interrupt signals free, whatever the parent holds.
        child_mask = previous_mask - interrupts.INTERRUPT_SIGNALS
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
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
            record = _wait_for_exit(process, cwd, trial_timeout_seconds, stdin_text)
        except BaseException:
            # The new session detaches the child from the terminal, so Ctrl-C no
            # longer reaches it; kill it here before propagating.
            _kill_group_and_collect(process)
            raise
        # A group ID is not reused while the group has a member. Once it is empty,
        # a new session leader could take the ID between the reap and this call;
        # that window is the residual.
        _kill_process_group(process)
        return record


def _wait_for_exit(
    process: subprocess.Popen,
    cwd: Path,
    trial_timeout_seconds: float,
    stdin_text: str | None = None,
) -> TrialProcessRecord:
    """Wait for the process to exit and its output to end, noticing an interrupt.

    A trial times out only when the process itself is still running at the
    deadline. If the process exited but a descendant keeps its pipes open, the
    output gets `KILL_COLLECT_TIMEOUT_SECONDS` to end, then the group is killed;
    the process's own exit code is kept either way. A signal that arrives during
    that wait ends it early and stays pending: the finished trial is kept.
    """
    deadline = time.monotonic() + trial_timeout_seconds
    output = _read_output(process, deadline, stop_at_exit=True, stdin_text=stdin_text)
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
    process: subprocess.Popen,
    deadline: float,
    *,
    stop_at_exit: bool,
    stdin_text: str | None = None,
) -> tuple[str, str] | None:
    """Read the output to its end, in slices short enough to notice an interrupt.

    Returns None at the deadline, or, with `stop_at_exit`, as soon as the process
    has exited with its pipes still open. Reading continues while the process
    runs, so a child blocked on a full pipe is not deadlocked.

    A signal that arrives while the process runs is consumed and raises
    `KeyboardInterrupt`. Without `stop_at_exit` the process has already exited
    and its result is complete, so a pending signal only ends the wait (None) and
    stays pending for the run to act on, instead of dropping the finished trial.

    `stdin_text` goes to the first `communicate` only: a retry carries on writing
    it, and passing it again would be refused.
    """
    pending_input = stdin_text
    while True:
        if stop_at_exit:
            interrupts.raise_if_pending()
        elif interrupts.pending():
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        stdin_input, pending_input = pending_input, None
        try:
            return process.communicate(
                input=stdin_input, timeout=min(INTERRUPT_POLL_SECONDS, remaining)
            )
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
    except (ProcessLookupError, PermissionError):
        pass  # The group already exited; its ID is gone or no longer ours.


def run_trial(
    fixture: Path,
    config: invocation.TrialConfig,
    trial_timeout_seconds: float = DEFAULT_TRIAL_TIMEOUT_SECONDS,
) -> TrialProcessRecord:
    """Run one trial of `config` against a fresh copy of `fixture`.

    The CLI gets its own empty HOME (with a credential variable) and TMPDIR in a
    private temp dir, removed with the trial. A sandboxed trial's copy is first
    made a git repo with one commit, the trial reads its own copy of the
    knowledge directory, so a write to it cannot reach a later trial, and its
    changes to the copy ride on the record as `work_diff`. When the config has
    test commands they run in the copy after the agent finishes, jailed when the
    config has a jail, with no credential in their environment; their results
    ride on the returned record.

    The staging dir and the working copy are identified (device and inode, not
    following symlinks) before the CLI runs and checked again once it exits. If
    either was moved, replaced or turned into a symlink, nothing is diffed,
    restored or tested, and the record carries a `workspace_error`, as it does
    when the protected paths cannot be restored: the trial fails, the run goes on.
    The test commands' HOME and TMPDIR are made only after the CLI is dead, in
    a new random temp dir, and the working copy and that TMPDIR are checked
    again before every test command.
    """
    with staged_fixture(fixture) as staging_dir, _private_dirs() as private:
        if config.sandbox:
            config = _with_own_knowledge(config, private / "plugin")
        argv = invocation.build_argv(
            config, invocation.build_user_prompt(fixture.name, config.task)
        )
        env = {
            **invocation.build_trial_env(os.environ, _fresh_dir(private / "home")),
            "TMPDIR": str(_fresh_dir(private / "tmp")),
        }
        work_dir = staging_dir / fixture.name if fixture.is_dir() else staging_dir
        # Resolved now, while only the harness has touched these paths; the jail
        # is later given these real paths and never resolves one itself.
        real_work_dir = Path(os.path.realpath(work_dir))
        identities = _dir_identities((staging_dir, work_dir, real_work_dir))
        if config.sandbox:
            init_sandbox_repo(work_dir)
        # Returns only once the CLI's whole process group is dead.
        record = run_cli_process(argv, staging_dir, trial_timeout_seconds, env)
        if not _same_dirs(identities):
            return dataclasses.replace(record, workspace_error=SWAPPED_WORK_DIR_ERROR)
        if config.sandbox:
            record = dataclasses.replace(
                record, work_diff=working_copy_diff(fixture, work_dir)
            )
        if not config.test_commands or record.timed_out:
            return record
        try:
            restore_protected_paths(fixture, work_dir, config.protected_paths)
        except (OSError, UnsafeProtectedPathError, RecursionError) as error:
            return dataclasses.replace(
                record, workspace_error=f"{RESTORE_FAILED_ERROR}: {error}"
            )
        with _check_dirs() as (check_home, check_temp):
            return _run_checks(
                record,
                config,
                real_work_dir,
                check_home,
                check_temp,
                {**identities, **_dir_identities((check_temp,))},
                trial_timeout_seconds,
            )


def _run_checks(
    record: TrialProcessRecord,
    config: invocation.TrialConfig,
    work_dir: Path,
    check_home: Path,
    check_temp: Path,
    identities: Mapping[Path, _DirIdentity],
    timeout_seconds: float,
) -> TrialProcessRecord:
    """Run the test commands in order, each only while every dir is still the one it was.

    A jailed command may write to the working copy and its temp dir, so it can
    rename either and leave a symlink in its place; a later command would then
    run in, and be jailed to, wherever the link points. The identities are
    checked before every command and the trial stops at the first change.
    """
    env = {
        **invocation.build_check_env(os.environ, check_home),
        "TMPDIR": str(check_temp),
    }
    results = []
    for command in config.test_commands:
        if not _same_dirs(identities):
            return dataclasses.replace(
                record,
                check_results=tuple(results),
                workspace_error=SWAPPED_DURING_CHECKS_ERROR,
            )
        results.append(
            run_check_command(
                command,
                work_dir,
                timeout_seconds,
                env,
                jail=config.check_jail,
                jail_temp_dir=check_temp,
            )
        )
    return dataclasses.replace(record, check_results=tuple(results))


SWAPPED_WORK_DIR_ERROR = (
    "the working copy or its staging dir was moved, replaced or made a symlink "
    "during the trial; it was not diffed, restored or tested"
)
RESTORE_FAILED_ERROR = "the protected paths could not be restored"
SWAPPED_DURING_CHECKS_ERROR = (
    "a test command moved, replaced or made a symlink of the working copy or its "
    "temp dir; the remaining test commands were not run"
)
CHECK_DIR_PREFIX = "model-effort-check-"

# A directory's identity: its device and inode, read without following a symlink.
_DirIdentity = tuple[int, int]


def _dir_identities(directories: Sequence[Path]) -> dict[Path, _DirIdentity]:
    identities = {}
    for directory in directories:
        entry = os.lstat(directory)
        identities[directory] = (entry.st_dev, entry.st_ino)
    return identities


def _same_dirs(identities: Mapping[Path, _DirIdentity]) -> bool:
    """True when each path is still the real directory it was, not a symlink or a replacement."""
    for directory, identity in identities.items():
        try:
            entry = os.stat(directory, follow_symlinks=False)
        except OSError:
            return False
        if not stat.S_ISDIR(entry.st_mode) or (entry.st_dev, entry.st_ino) != identity:
            return False
    return True


@contextmanager
def _private_dirs() -> Iterator[Path]:
    """A temp dir outside the staging dir for the trial's HOME, TMPDIR, knowledge copy and check temp."""
    root = Path(tempfile.mkdtemp(prefix=PRIVATE_DIR_PREFIX))
    try:
        yield root
    finally:
        remove_tree(root)


def _fresh_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _check_dirs() -> Iterator[tuple[Path, Path]]:
    """A new HOME and TMPDIR for the test commands, made only after the CLI is dead.

    They live in a new random temp dir, not in the trial's private dir, whose
    paths the agent knows and could have filled with symlinks. Each is made
    with a plain `mkdir` (which fails on anything already there) and checked
    with `lstat`; the root's path is resolved right after it is made.
    """
    root = Path(os.path.realpath(tempfile.mkdtemp(prefix=CHECK_DIR_PREFIX)))
    try:
        yield _new_real_dir(root / "home"), _new_real_dir(root / "tmp")
    finally:
        remove_tree(root)


def _new_real_dir(path: Path) -> Path:
    os.mkdir(path, 0o700)
    if not stat.S_ISDIR(os.lstat(path).st_mode):
        raise OSError(f"{path} is not a real directory")
    return path


def _with_own_knowledge(
    config: invocation.TrialConfig, plugin_root: Path
) -> invocation.TrialConfig:
    own = dataclasses.replace(config.snapshot_paths, plugin_root=plugin_root)
    shutil.copytree(
        config.snapshot_paths.knowledge_dir, own.knowledge_dir, symlinks=True
    )
    return dataclasses.replace(config, snapshot_paths=own)


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


# Opens a directory entry only if it is a real directory, never through a symlink.
_DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_OWNER_RWX = stat.S_IRWXU
# Where `chmod` cannot refuse to follow a symlink (Linux before Python 3.13), the
# entry is checked with lstat first; the CLI's process group is dead by then.
_CHMOD_NOFOLLOW = os.chmod in os.supports_follow_symlinks
_NEW_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
_NEW_DIR_MODE = 0o755


def restore_protected_paths(
    pristine_fixture: Path, work_dir: Path, protected_paths: tuple[str, ...]
) -> None:
    """Put each protected path back as the pristine fixture has it, so the agent cannot change its own grader.

    The walk holds an open directory descriptor at every step and names each
    entry relative to it (`dir_fd`), opening directories with `O_NOFOLLOW`. A
    symlink or file in a parent's place is removed and a real directory made;
    the target is removed (a directory recursively, through descriptors) and
    copied in with `O_EXCL | O_NOFOLLOW`. Each directory on the way, `work_dir`
    included, first gets owner read, write and search back (chmod, never through
    a symlink), so an agent that locked the copy cannot stop the restore.
    `work_dir` itself must be a real directory, not a symlink. A symlink swapped in mid-walk makes
    the open fail instead of redirecting it, so nothing outside `work_dir` is
    removed or written. A process still running can change the copy after the
    restore; `run_cli_process` kills the CLI's process group first.

    Raises:
        UnsafeProtectedPathError: a path is absolute or climbs out with `..`
            (fixture loading refuses those first), or a parent could not be
            opened as a real directory.
        OSError: an entry could still not be removed or written (for example
            a file the agent made immutable).
    """
    root = work_dir
    for relative in protected_paths:
        parts = PurePosixPath(relative).parts
        if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
            raise UnsafeProtectedPathError(f"protected path {relative!r} is not inside the fixture")
        parent_fd = _open_real_dirs(root, parts[:-1])
        try:
            _remove_at(parent_fd, parts[-1])
            _copy_in(pristine_fixture / relative, parent_fd, parts[-1])
        finally:
            os.close(parent_fd)


def _open_dir_at(name: str | Path, dir_fd: int | None, shown: str) -> int:
    try:
        return os.open(name, _DIR_OPEN_FLAGS, dir_fd=dir_fd)
    except OSError as error:
        raise UnsafeProtectedPathError(
            f"{shown} is not a real directory inside the working copy: {error}"
        ) from error


def _open_real_dirs(root: Path, names: tuple[str, ...]) -> int:
    """A descriptor for `root / names...`, each step made a real, owner-accessible directory first."""
    _unlock_at(None, root)
    fd = _open_dir_at(root, None, str(root))
    try:
        for name in names:
            entry = _lstat_at(fd, name)
            if entry is not None and not stat.S_ISDIR(entry.st_mode):
                os.unlink(name, dir_fd=fd)
                entry = None
            if entry is None:
                os.mkdir(name, _NEW_DIR_MODE, dir_fd=fd)
            _unlock_at(fd, name)
            child = _open_dir_at(name, fd, name)
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)
        raise
    return fd


def _lstat_at(dir_fd: int | None, name: str | Path) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _remove_at(dir_fd: int, name: str) -> None:
    """Remove `name` under `dir_fd`; a directory's contents first, never through a symlink.

    The walk is a loop over an explicit stack, not recursion, so no nesting
    depth can exhaust the call stack, and it holds one directory descriptor at
    a time: it steps down by name and back up through `..`, checking that `..`
    is the directory it came from (device and inode).
    """
    entry = _lstat_at(dir_fd, name)
    if entry is None:
        return
    if not stat.S_ISDIR(entry.st_mode):
        os.unlink(name, dir_fd=dir_fd)
        return
    _unlock_at(dir_fd, name)
    fd = _open_dir_at(name, dir_fd, name)
    # One frame per open level: its name in its parent, the parent's identity,
    # and the entries still to remove.
    frames = [(name, _fd_identity(dir_fd), _entry_names(fd))]
    try:
        while frames:
            level_name, parent_identity, pending = frames[-1]
            if pending:
                child = pending.pop()
                child_entry = _lstat_at(fd, child)
                if child_entry is None:
                    continue
                if not stat.S_ISDIR(child_entry.st_mode):
                    os.unlink(child, dir_fd=fd)
                    continue
                _unlock_at(fd, child)
                identity = _fd_identity(fd)
                child_fd = _open_dir_at(child, fd, child)
                os.close(fd)
                fd = child_fd
                frames.append((child, identity, _entry_names(fd)))
                continue
            frames.pop()
            if not frames:
                break
            parent_fd = _open_parent(fd, parent_identity)
            os.close(fd)
            fd = parent_fd
            os.rmdir(level_name, dir_fd=fd)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=dir_fd)


def _entry_names(fd: int) -> list[str]:
    with os.scandir(fd) as entries:
        return [entry.name for entry in entries]


def _fd_identity(fd: int) -> _DirIdentity:
    entry = os.fstat(fd)
    return entry.st_dev, entry.st_ino


def _open_parent(fd: int, expected: _DirIdentity) -> int:
    """A descriptor for the directory above `fd`, which must still be `expected`."""
    parent_fd = _open_dir_at("..", fd, "..")
    if _fd_identity(parent_fd) != expected:
        os.close(parent_fd)
        raise UnsafeProtectedPathError("a directory was moved during the restore")
    return parent_fd


def _unlock_at(dir_fd: int | None, name: str | Path) -> None:
    """Give a real directory `name` owner read, write and search; a symlink or file is left alone."""
    entry = _lstat_at(dir_fd, name)
    if entry is None or not stat.S_ISDIR(entry.st_mode):
        return
    mode = stat.S_IMODE(entry.st_mode)
    if mode & _OWNER_RWX == _OWNER_RWX:
        return
    if _CHMOD_NOFOLLOW:
        os.chmod(name, mode | _OWNER_RWX, dir_fd=dir_fd, follow_symlinks=False)
    else:
        os.chmod(name, mode | _OWNER_RWX, dir_fd=dir_fd)


def _copy_in(source: Path, dir_fd: int, name: str) -> None:
    """Copy the pristine `source` to `name` under `dir_fd`, which must not exist; links stay links.

    A directory tree is walked with an explicit stack, holding one directory
    descriptor at a time, as `_remove_at` does.
    """
    if source.is_symlink() or not source.is_dir():
        _copy_leaf(source, dir_fd, name)
        return
    os.mkdir(name, _NEW_DIR_MODE, dir_fd=dir_fd)
    fd = _open_dir_at(name, dir_fd, name)
    # One frame per open level: its source, the parent's identity, and the
    # children still to copy (popped from the end, so stored in reverse).
    frames = [(source, _fd_identity(dir_fd), sorted(source.iterdir(), reverse=True))]
    try:
        while frames:
            level_source, parent_identity, pending = frames[-1]
            if pending:
                child = pending.pop()
                if child.is_symlink() or not child.is_dir():
                    _copy_leaf(child, fd, child.name)
                    continue
                os.mkdir(child.name, _NEW_DIR_MODE, dir_fd=fd)
                identity = _fd_identity(fd)
                child_fd = _open_dir_at(child.name, fd, child.name)
                os.close(fd)
                fd = child_fd
                frames.append((child, identity, sorted(child.iterdir(), reverse=True)))
                continue
            frames.pop()
            # `..` is opened before the mode is set, which may drop search.
            parent_fd = _open_parent(fd, parent_identity) if frames else None
            os.fchmod(fd, stat.S_IMODE(level_source.stat().st_mode))
            if parent_fd is not None:
                os.close(fd)
                fd = parent_fd
    finally:
        os.close(fd)


def _copy_leaf(source: Path, dir_fd: int, name: str) -> None:
    """Copy a symlink as a symlink, or a regular file with its mode; anything else is skipped."""
    if source.is_symlink():
        os.symlink(os.readlink(source), name, dir_fd=dir_fd)
    elif source.is_file():
        mode = stat.S_IMODE(source.stat().st_mode)
        fd = os.open(name, _NEW_FILE_FLAGS, mode, dir_fd=dir_fd)
        with os.fdopen(fd, "wb") as target:
            target.write(source.read_bytes())
            os.fchmod(target.fileno(), mode)


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
