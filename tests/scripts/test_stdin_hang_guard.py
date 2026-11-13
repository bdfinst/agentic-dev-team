"""Scripts fail fast, not hang, when stdin never reaches EOF (#2303).

Each row runs a real script as a subprocess with the stdin kind under test:
a socket whose peer stays open, a pseudo-terminal, a pipe, ``/dev/null``. A
regression that blocks on stdin fails the row with a timeout instead of
hanging the run. Goldens for the pipe and ``/dev/null`` rows were captured
from the scripts before the guard was wired in (see
``tests/_support/stdin_scripts.py``).
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT
from tests._support.stdin_scripts import (
    CWD_PLACEHOLDER,
    LARGE_FIXTURE_SCRIPT,
    STDIN_SCRIPTS,
    Golden,
    StdinScript,
)

PLUGIN_DIR = REPO_ROOT / "plugins" / "dev-team"
LIMIT_SECONDS = 5
REFUSAL_EXIT_STATUS = 2
NEVER_ENDS_MARKER = "stdin never reaches EOF"
SIXTY_FOUR_KIB = 64 * 1024

NO_SOCKETS_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="fstat cannot tell a socket from a pipe on Windows",
)
NO_PTY_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="pseudo-terminals do not exist on Windows"
)


def _name(row: StdinScript) -> str:
    return Path(row.script).name


FLAG_ROWS = [row for row in STDIN_SCRIPTS if row.needs_flag]
EVERY_SCRIPT = [pytest.param(row, id=_name(row)) for row in STDIN_SCRIPTS]
NEEDS_FLAG = [pytest.param(row, id=_name(row)) for row in FLAG_ROWS]


@contextlib.contextmanager
def _endless_socket():
    """A socket whose peer stays open and silent, so a read never ends."""
    ours, theirs = socket.socketpair()
    try:
        yield theirs
    finally:
        ours.close()
        theirs.close()


@contextlib.contextmanager
def _terminal():
    import pty

    master, slave = pty.openpty()
    try:
        yield slave
    finally:
        os.close(master)
        os.close(slave)


def _run(
    row: StdinScript,
    cwd: Path,
    *,
    stdin=None,
    text_in: str | None = None,
    leading_argv: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(PLUGIN_DIR / row.script), *leading_argv, *row.argv]
    try:
        return subprocess.run(
            argv,
            stdin=stdin,
            input=text_in,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=LIMIT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{row.script} still blocked on stdin after {LIMIT_SECONDS}s")


def _assert_refused(row: StdinScript, result: subprocess.CompletedProcess) -> None:
    assert result.returncode == REFUSAL_EXIT_STATUS, result.stderr
    assert result.stdout == ""
    assert NEVER_ENDS_MARKER in result.stderr
    assert row.flag in result.stderr


def _assert_matches(
    result: subprocess.CompletedProcess, golden: Golden, cwd: Path
) -> None:
    assert result.returncode == golden.exit_status, result.stderr
    assert result.stdout.replace(str(cwd.resolve()), CWD_PLACEHOLDER) == golden.stdout
    if golden.stderr_fragment is None:
        assert NEVER_ENDS_MARKER not in result.stderr
    else:
        assert golden.stderr_fragment in result.stderr


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_script_refuses_an_endless_socket_stdin_and_names_its_flag(row, tmp_path):
    with _endless_socket() as sock:
        result = _run(row, tmp_path, stdin=sock)

    _assert_refused(row, result)


@NO_PTY_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_script_refuses_a_terminal_stdin_and_names_its_flag(row, tmp_path):
    with _terminal() as slave:
        result = _run(row, tmp_path, stdin=slave)

    _assert_refused(row, result)


@pytest.mark.parametrize("row", EVERY_SCRIPT)
def test_piped_fixture_gives_the_pre_guard_exit_stdout_and_stderr(row, tmp_path):
    result = _run(row, tmp_path, text_in=row.fixture)

    _assert_matches(result, row.piped, tmp_path)


@pytest.mark.parametrize("row", EVERY_SCRIPT)
def test_null_device_gives_the_pre_guard_exit_stdout_and_stderr(row, tmp_path):
    result = _run(row, tmp_path, stdin=subprocess.DEVNULL)

    _assert_matches(result, row.devnull, tmp_path)


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_input_flag_wins_over_an_endless_socket_stdin(row, tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text(row.fixture, encoding="utf-8")

    with _endless_socket() as sock:
        result = _run(
            row, tmp_path, stdin=sock, leading_argv=(row.flag, str(input_file))
        )

    _assert_matches(result, row.piped, tmp_path)


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize(
    ("script", "argv", "flag"),
    [
        pytest.param(
            "scripts/checkpoint_abort.py",
            ("--mode", "outcome"),
            "--from",
            id="checkpoint_abort-outcome-mode",
        ),
        pytest.param(
            "scripts/checkpoint_abort.py",
            ("--mode", "merge"),
            "--from",
            id="checkpoint_abort-merge-mode",
        ),
        pytest.param(
            "skills/code-review/scripts/review_context_pack.py",
            ("--name-status-from", "-"),
            "--name-status-from",
            id="review_context_pack-name-status",
        ),
    ],
)
def test_a_second_stdin_flag_on_one_script_is_named_when_it_is_the_one_used(
    script, argv, flag, tmp_path
):
    with _endless_socket() as sock:
        result = subprocess.run(
            [sys.executable, str(PLUGIN_DIR / script), *argv],
            stdin=sock,
            capture_output=True,
            text=True,
            cwd=tmp_path,
            timeout=LIMIT_SECONDS,
            check=False,
        )

    assert result.returncode == REFUSAL_EXIT_STATUS, result.stderr
    assert result.stdout == ""
    assert flag in result.stderr


def test_exactly_one_fixture_exceeds_64_kib_and_it_is_the_named_script():
    large = [
        r.script for r in STDIN_SCRIPTS if len(r.fixture.encode()) > SIXTY_FOUR_KIB
    ]

    assert large == [LARGE_FIXTURE_SCRIPT]


# ---------------------------------------------------------------------------
# orchestrator.py has no input flag: an endless stdin falls back to the default
# request and says so on stderr, instead of failing.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(PLUGIN_DIR / "scripts"))
import orchestrator as orch

DEFAULT_REQUEST = "default request"
PIPED_REQUEST = "add a login page"
ORCHESTRATOR = next(r for r in STDIN_SCRIPTS if r.script == "scripts/orchestrator.py")


def _fallback_lines(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if NEVER_ENDS_MARKER in line]


@NO_SOCKETS_ON_WINDOWS
def test_orchestrator_falls_back_and_says_so_on_an_endless_socket_stdin(tmp_path):
    with _endless_socket() as sock:
        result = _run(ORCHESTRATOR, tmp_path, stdin=sock)

    fallback = _fallback_lines(result.stderr)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert len(fallback) == 1
    assert DEFAULT_REQUEST in fallback[0]
    assert ORCHESTRATOR.devnull.stderr_fragment in result.stderr


@NO_SOCKETS_ON_WINDOWS
def test_orchestrator_refuses_a_socket_that_delivered_a_request_then_eof(tmp_path):
    ours, theirs = socket.socketpair()
    try:
        ours.sendall(PIPED_REQUEST.encode())
        ours.close()
        result = _run(ORCHESTRATOR, tmp_path, stdin=theirs)
    finally:
        theirs.close()

    assert result.returncode == 0, result.stderr
    assert len(_fallback_lines(result.stderr)) == 1


@NO_PTY_ON_WINDOWS
def test_orchestrator_stays_silent_about_stdin_on_a_terminal(tmp_path):
    with _terminal() as slave:
        result = _run(ORCHESTRATOR, tmp_path, stdin=slave)

    assert result.returncode == 0, result.stderr
    assert _fallback_lines(result.stderr) == []
    assert ORCHESTRATOR.devnull.stderr_fragment in result.stderr


def _pipe_holding_a_request(stack: contextlib.ExitStack):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, f"{PIPED_REQUEST}\n".encode())
    os.close(write_fd)
    return stack.enter_context(os.fdopen(read_fd, "r"))


def _null_device(stack: contextlib.ExitStack):
    return stack.enter_context(open(os.devnull, "r"))


def _terminal_stream(stack: contextlib.ExitStack):
    import pty

    master, slave = pty.openpty()
    stack.callback(os.close, master)
    # Non-blocking, so a regression that reads the terminal fails instead of hanging.
    os.set_blocking(slave, False)
    return stack.enter_context(os.fdopen(slave, "r"))


def _socket_peer_open(stack: contextlib.ExitStack):
    ours, theirs = socket.socketpair()
    stack.callback(ours.close)
    stack.callback(theirs.close)
    # A regression that reads the open socket times out instead of hanging the run.
    theirs.settimeout(LIMIT_SECONDS)
    return stack.enter_context(theirs.makefile("r"))


def _socket_request_then_eof(stack: contextlib.ExitStack):
    ours, theirs = socket.socketpair()
    ours.sendall(PIPED_REQUEST.encode())
    ours.close()
    stack.callback(theirs.close)
    return stack.enter_context(theirs.makefile("r"))


def _closed_stream(stack: contextlib.ExitStack):
    with open(os.devnull, "r") as stream:
        pass
    return stream


@pytest.mark.parametrize(
    ("build_stdin", "request_used", "fallback_line_count"),
    [
        pytest.param(_pipe_holding_a_request, PIPED_REQUEST, 0, id="pipe-with-request"),
        pytest.param(_null_device, DEFAULT_REQUEST, 0, id="null-device"),
        pytest.param(
            _terminal_stream,
            DEFAULT_REQUEST,
            0,
            id="terminal",
            marks=NO_PTY_ON_WINDOWS,
        ),
        pytest.param(
            _socket_peer_open,
            DEFAULT_REQUEST,
            1,
            id="socket-peer-open",
            marks=NO_SOCKETS_ON_WINDOWS,
        ),
        pytest.param(
            _socket_request_then_eof,
            DEFAULT_REQUEST,
            1,
            id="socket-request-then-eof",
            marks=NO_SOCKETS_ON_WINDOWS,
        ),
        pytest.param(_closed_stream, DEFAULT_REQUEST, 1, id="closed-stream"),
    ],
)
def test_orchestrator_picks_its_request_and_reports_a_fallback_only_when_it_fell_back(
    build_stdin, request_used, fallback_line_count, monkeypatch, capsys
):
    with contextlib.ExitStack() as stack:
        monkeypatch.setattr(orch.sys, "stdin", build_stdin(stack))
        resolved = orch._resolve_request_from_stdin()

    assert resolved == request_used
    assert len(_fallback_lines(capsys.readouterr().err)) == fallback_line_count
