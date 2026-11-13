"""Scripts fail fast, not hang, when stdin never reaches EOF (#2303).

Each row runs a real script as a subprocess with the stdin kind under test:
a socket whose peer stays open, a pseudo-terminal, a pipe, ``/dev/null``, a
regular file. A regression that blocks on stdin fails the row with a timeout
instead of hanging the run. Goldens for the pipe and ``/dev/null`` rows were
captured from the scripts before the guard was wired in (see
``tests/_support/stdin_scripts.py``).
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT
from tests._support.stdin_scripts import (
    INPUT_FLAGS,
    ORCHESTRATOR_RUNS_STDERR,
    STDIN_SCRIPTS,
    Golden,
    StdinScript,
)

PLUGIN_DIR = REPO_ROOT / "plugins" / "dev-team"
LIMIT_SECONDS = 30
REFUSAL_EXIT_STATUS = 2
NEVER_ENDS_MARKER = "stdin never reaches EOF"

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
GOLDEN_ROWS = [row for row in STDIN_SCRIPTS if row.piped and row.devnull]
EVERY_SCRIPT = [pytest.param(row, id=_name(row)) for row in GOLDEN_ROWS]
NEEDS_FLAG = [pytest.param(row, id=_name(row)) for row in FLAG_ROWS]
ROW_BY_NAME = {_name(row): row for row in STDIN_SCRIPTS}
#: One case per (script, argv) that reads stdin through a flag other than the
#: row's primary one.
SECOND_FLAG_CASES = [
    pytest.param(
        ROW_BY_NAME[rule.script],
        rule.flag,
        argv,
        id=f"{Path(rule.script).stem}-{'-'.join(argv)}",
    )
    for rule in INPUT_FLAGS
    for argv in rule.stdin_argvs
]


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
    """The slave end of a pseudo-terminal; skips where none can be opened."""
    import pty

    try:
        master, slave = pty.openpty()
    except OSError as exc:
        pytest.skip(f"no pseudo-terminal available: {exc}")
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
        pytest.fail(f"{row.script}: no result in {LIMIT_SECONDS} s (hang or slow host)")


def _assert_refused(result: subprocess.CompletedProcess, flag: str) -> None:
    assert result.returncode == REFUSAL_EXIT_STATUS, result.stderr
    assert result.stdout == ""
    assert NEVER_ENDS_MARKER in result.stderr
    assert flag in result.stderr


def _assert_matches(result: subprocess.CompletedProcess, golden: Golden) -> None:
    assert result.returncode == golden.exit_status, result.stderr
    if golden.json_keys is None:
        assert result.stdout == golden.stdout
    else:
        actual = json.loads(result.stdout)
        assert {key: actual.get(key) for key in golden.json_keys} == json.loads(
            golden.stdout
        )
    if golden.stderr_fragment is None:
        assert NEVER_ENDS_MARKER not in result.stderr
    else:
        assert golden.stderr_fragment in result.stderr


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_script_refuses_an_endless_socket_stdin_and_names_its_flag(row, tmp_path):
    with _endless_socket() as sock:
        result = _run(row, tmp_path, stdin=sock)

    _assert_refused(result, row.flag)


@NO_PTY_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_script_refuses_a_terminal_stdin_and_names_its_flag(row, tmp_path):
    with _terminal() as slave:
        result = _run(row, tmp_path, stdin=slave)

    _assert_refused(result, row.flag)


@pytest.mark.parametrize("row", EVERY_SCRIPT)
def test_piped_fixture_gives_the_pre_guard_exit_stdout_and_stderr(row, tmp_path):
    result = _run(row, tmp_path, text_in=row.fixture)

    _assert_matches(result, row.piped)


@pytest.mark.parametrize("row", EVERY_SCRIPT)
def test_regular_file_stdin_gives_the_piped_exit_stdout_and_stderr(row, tmp_path):
    fixture_file = tmp_path / "stdin.txt"
    fixture_file.write_text(row.fixture, encoding="utf-8")

    with open(fixture_file, encoding="utf-8") as stream:
        result = _run(row, tmp_path, stdin=stream)

    _assert_matches(result, row.piped)


@pytest.mark.parametrize("row", EVERY_SCRIPT)
def test_null_device_gives_the_pre_guard_exit_stdout_and_stderr(row, tmp_path):
    result = _run(row, tmp_path, stdin=subprocess.DEVNULL)

    _assert_matches(result, row.devnull)


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_input_flag_wins_over_an_endless_socket_stdin(row, tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text(row.fixture, encoding="utf-8")

    with _endless_socket() as sock:
        result = _run(
            row, tmp_path, stdin=sock, leading_argv=(row.flag, str(input_file))
        )

    _assert_matches(result, row.piped)


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize(("row", "flag", "argv"), SECOND_FLAG_CASES)
def test_a_second_stdin_flag_on_one_script_is_named_when_it_is_the_one_used(
    row, flag, argv, tmp_path
):
    with _endless_socket() as sock:
        result = _run(row, tmp_path, stdin=sock, leading_argv=argv)

    _assert_refused(result, flag)


# ---------------------------------------------------------------------------
# orchestrator.py has no input flag: an endless stdin falls back to the default
# request and says so on stderr, instead of failing. The matrix below covers
# every stdin kind in-process; one subprocess test proves the wiring end to end.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(PLUGIN_DIR / "scripts"))
import orchestrator as orch

DEFAULT_REQUEST = "default request"
ORCHESTRATOR = ROW_BY_NAME["orchestrator.py"]
PIPED_REQUEST = ORCHESTRATOR.fixture.strip()


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
    assert ORCHESTRATOR_RUNS_STDERR in result.stderr


def _pipe_holding_a_request(stack: contextlib.ExitStack):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, f"{PIPED_REQUEST}\n".encode())
    os.close(write_fd)
    return stack.enter_context(os.fdopen(read_fd, "r"))


def _null_device(stack: contextlib.ExitStack):
    return stack.enter_context(open(os.devnull, "r"))


def _regular_file_holding_a_request(stack: contextlib.ExitStack):
    fd, name = tempfile.mkstemp()
    stack.callback(os.unlink, name)
    with os.fdopen(fd, "w") as writer:
        writer.write(f"{PIPED_REQUEST}\n")
    return stack.enter_context(open(name, "r"))


def _terminal_stream(stack: contextlib.ExitStack):
    slave = stack.enter_context(_terminal())
    # Non-blocking, so a regression that reads the terminal fails instead of hanging.
    os.set_blocking(slave, False)
    return stack.enter_context(os.fdopen(slave, "r", closefd=False))


def _socket_peer_open(stack: contextlib.ExitStack):
    theirs = stack.enter_context(_endless_socket())
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
        pytest.param(
            _regular_file_holding_a_request,
            PIPED_REQUEST,
            0,
            id="regular-file-with-request",
        ),
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
            id="socket-request-then-eof-falls-back",
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
