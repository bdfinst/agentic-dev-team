"""Stage a fixture and run one `claude -p` trial against it.

Each trial runs in a fresh temp copy of the fixture, outside the repo, so the
project `CLAUDE.md` and hooks are not loaded and the agent cannot alter the
source fixture. The run record is raw process output: parsing the stream and
grading it happen elsewhere.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import external, paths
from .arm import Arm

DEFAULT_CLAUDE_BIN = "claude"
DEFAULT_TRIAL_TIMEOUT_SECONDS = 600
# Shell convention for "command not found or not executable".
COMMAND_NOT_RUNNABLE_EXIT_CODE = 127
PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
TEMP_DIR_PREFIX = "model-effort-ab-"
OUTPUT_ENCODING = "utf-8"
KILL_COLLECT_TIMEOUT_SECONDS = 5
# Held back while the process starts, so an interrupt cannot land before `Popen`
# returns the pid the group kill needs.
INTERRUPT_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM, signal.SIGHUP})
# Python 3.12 renamed rmtree's `onerror` to `onexc` and changed what it receives.
RMTREE_HAS_ONEXC = sys.version_info >= (3, 12)


@dataclass(frozen=True)
class TrialConfig:
    """Everything that selects how the CLI runs, apart from the fixture."""

    arm: Arm
    system_prompt: str
    claude_bin: str = DEFAULT_CLAUDE_BIN
    plugin_root: Path = paths.PLUGIN_ROOT
    knowledge_dir: Path = paths.KNOWLEDGE_DIR


@dataclass(frozen=True)
class RunRecord:
    """Raw outcome of one CLI process. `exit_code` is None when it timed out.

    `cwd` is the directory the process ran in, so text it printed can be scrubbed of it.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    cwd: Path | None = None


def build_user_prompt(staged_name: str) -> str:
    return (
        f"Review `{staged_name}` in the current working directory. "
        "Respond with only the JSON object defined by your output contract, "
        "with no other text."
    )


def build_argv(config: TrialConfig, user_prompt: str) -> list[str]:
    """Return the full CLI argv.

    `--restricted` confines the file tools to the cwd and `--add-dir`, and
    excludes user-scope plugins, hooks and CLAUDE.md. Without it a `Read` of an
    absolute path outside those directories succeeds.
    """
    system_prompt = config.system_prompt.replace(
        PLUGIN_ROOT_PLACEHOLDER, str(config.plugin_root)
    )
    return [
        config.claude_bin,
        "-p",
        user_prompt,
        "--model",
        config.arm.model,
        "--effort",
        config.arm.effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--tools",
        ",".join(config.arm.profile.enabled_tools),
        "--add-dir",
        str(config.knowledge_dir),
        "--restricted",
        "--system-prompt",
        system_prompt,
    ]


def build_trial_env(parent_env: Mapping[str, str]) -> dict[str, str]:
    """Return `parent_env` without the parent Claude session's identity variables.

    The scrub rules come from the headless-run skill's `isolated_dispatch`. HOME
    is kept so authentication works; `--restricted` already excludes user-scope
    config, hooks and CLAUDE.md.
    """
    should_scrub = external.isolated_dispatch()._should_scrub
    return {name: value for name, value in parent_env.items() if not should_scrub(name)}


@contextmanager
def staged_fixture(fixture: Path) -> Iterator[Path]:
    """Copy a file or directory fixture into a fresh temp dir and yield that dir."""
    staging_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    try:
        target = staging_dir / fixture.name
        if fixture.is_dir():
            shutil.copytree(fixture, target, symlinks=True)
        else:
            shutil.copy2(fixture, target)
        yield staging_dir
    finally:
        _remove_staging_dir(staging_dir)


def _remove_staging_dir(staging_dir: Path) -> None:
    if RMTREE_HAS_ONEXC:
        shutil.rmtree(staging_dir, onexc=_report_cleanup_failure)
    else:
        shutil.rmtree(staging_dir, onerror=_report_cleanup_failure)


def _report_cleanup_failure(_function, path, error) -> None:
    # `onerror` passes an exc_info tuple; `onexc` passes the exception itself.
    exception = error[1] if isinstance(error, tuple) else error
    print(f"warning: could not remove {path}: {exception}", file=sys.stderr)


def run_cli_process(
    argv: Sequence[str],
    cwd: Path,
    trial_timeout: float,
    env: Mapping[str, str] | None = None,
) -> RunRecord:
    """Run `argv` in `cwd` in its own process group.

    On timeout or interrupt the whole group is killed, so grandchildren the CLI
    spawned do not outlive the trial; a timeout sets `timed_out` and keeps the
    partial output. A binary that cannot be started yields exit code 127 with
    the OS error as stderr.
    """
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPT_SIGNALS)
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
            # The child inherits the mask held during the start; undo it there.
            # The harness is single-threaded and the hook only sets a signal mask.
            preexec_fn=lambda: signal.pthread_sigmask(  # noqa: PLW1509
                signal.SIG_SETMASK, previous_mask
            ),
        )
    except Exception as error:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        if not isinstance(error, OSError):
            raise
        return RunRecord(
            exit_code=COMMAND_NOT_RUNNABLE_EXIT_CODE,
            stdout="",
            stderr=str(error),
            timed_out=False,
            cwd=cwd,
        )
    try:
        # Unblocking inside the try means a signal held back during the start
        # raises here, where the handler below kills the new group.
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        stdout, stderr = process.communicate(timeout=trial_timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
        stdout, stderr = _collect_after_kill(process)
        return RunRecord(
            exit_code=None, stdout=stdout, stderr=stderr, timed_out=True, cwd=cwd
        )
    except BaseException:
        # The new session detaches the child from the terminal, so Ctrl-C no
        # longer reaches it; kill it here before propagating. A second signal is
        # held back until the group is dead, so it cannot skip the kill.
        interrupted_mask = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPT_SIGNALS)
        try:
            _kill_process_group(process)
            process.wait()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, interrupted_mask)
        raise
    return RunRecord(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        cwd=cwd,
    )


def _collect_after_kill(process: subprocess.Popen) -> tuple[str, str]:
    """Return the output captured before the kill.

    A descendant that left the process group can still hold the pipes open;
    give up on the output after a bounded wait rather than hang the run.
    """
    try:
        return process.communicate(timeout=KILL_COLLECT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "", ""


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # The group already exited.


def run_trial(
    fixture: Path,
    config: TrialConfig,
    trial_timeout: float = DEFAULT_TRIAL_TIMEOUT_SECONDS,
) -> RunRecord:
    """Run one trial of `config` against a fresh copy of `fixture`."""
    argv = build_argv(config, build_user_prompt(fixture.name))
    env = build_trial_env(os.environ)
    with staged_fixture(fixture) as staging_dir:
        return run_cli_process(argv, staging_dir, trial_timeout, env)
