"""stdin_guard: refuse stdin streams that never reach EOF, read the rest.

Refusal rows that need a real fd 0 run the helper in a subprocess with a
timeout, so a regression fails the row instead of hanging the run. Streams
passed with ``stream=`` never touch the test process's own fd 0.
"""

from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT
from tests._support.stdin_scripts import STDIN_SCRIPTS

LIB_DIR = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import stdin_guard

REFUSAL_TIMEOUT_SECONDS = 5
PIPE_BUFFER_EXCEEDING_BYTES = 200_000
REFUSAL_EXIT_STATUS = 2
NEVER_ENDS_MARKER = "stdin never reaches EOF"

NO_SOCKETS_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="fstat cannot tell a socket from a pipe on Windows",
)
NO_PTY_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="the pty module does not exist on Windows"
)


def _write_then_close(write_fd: int, payload: bytes) -> None:
    with os.fdopen(write_fd, "wb") as writer:
        writer.write(payload)


def _read_through_pipe(payload: bytes) -> str:
    """Read ``payload`` through a pipe, with the write on its own thread."""
    read_fd, write_fd = os.pipe()
    writer = threading.Thread(target=_write_then_close, args=(write_fd, payload))
    writer.start()
    try:
        with os.fdopen(read_fd, "r") as stream:
            return stdin_guard.read_stdin_or_exit("--findings", stream=stream)
    finally:
        writer.join()


def test_piped_input_is_read():
    assert _read_through_pipe(b"abc") == "abc"


def test_empty_pipe_returns_an_empty_string():
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    with os.fdopen(read_fd, "r") as stream:
        assert stdin_guard.read_stdin_or_exit("--findings", stream=stream) == ""


def test_pipe_larger_than_the_pipe_buffer_is_read_completely():
    text = _read_through_pipe(b"a" * PIPE_BUFFER_EXCEEDING_BYTES)
    assert len(text) == PIPE_BUFFER_EXCEEDING_BYTES


def test_regular_file_is_read(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_text("abc")
    with source.open() as stream:
        assert stdin_guard.read_stdin_or_exit("--findings", stream=stream) == "abc"


def test_null_device_reads_as_empty():
    with open(os.devnull) as stream:
        assert stdin_guard.read_stdin_or_exit("--findings", stream=stream) == ""


def test_stream_without_a_file_descriptor_is_read_instead_of_the_process_stdin(
    monkeypatch,
):
    # sys.stdin is made unreadable so a guard that inspected it would refuse.
    monkeypatch.setattr(sys, "stdin", None)
    stream = io.StringIO("abc")
    assert stdin_guard.read_stdin_or_exit("--findings", stream=stream) == "abc"


def test_default_stream_is_the_current_sys_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("abc"))
    assert stdin_guard.read_stdin_or_exit("--findings") == "abc"


def test_table_lists_the_eight_scripts_with_real_flags():
    scripts = {row.script for row in STDIN_SCRIPTS}
    assert len(STDIN_SCRIPTS) == len(scripts) == 8
    for row in STDIN_SCRIPTS:
        source = (REPO_ROOT / "plugins" / "dev-team" / row.script).read_text("utf-8")
        assert row.needs_flag == (row.flag is not None)
        if row.flag is not None:
            assert f'"{row.flag}"' in source, row.script


@pytest.fixture
def probe_script(tmp_path: Path) -> Path:
    """A tiny script that reads stdin through the guard and echoes it."""
    script = tmp_path / "probe_tool.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(LIB_DIR)!r})\n"
        "import stdin_guard\n"
        "sys.stdout.write(stdin_guard.read_stdin_or_exit(sys.argv[1]))\n"
    )
    return script


def _run_probe(script: Path, flag: str, stdin) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), flag],
        stdin=stdin,
        capture_output=True,
        text=True,
        timeout=REFUSAL_TIMEOUT_SECONDS,
        check=False,
    )


def _assert_refused(result: subprocess.CompletedProcess, flag: str) -> None:
    assert result.returncode == REFUSAL_EXIT_STATUS
    assert result.stdout == ""
    assert NEVER_ENDS_MARKER in result.stderr
    assert flag in result.stderr


@pytest.fixture
def open_socket_stdin():
    """The read end of a socket pair whose peer stays open: it never reaches EOF."""
    reader, peer = socket.socketpair()
    try:
        yield reader
    finally:
        reader.close()
        peer.close()


@NO_SOCKETS_ON_WINDOWS
def test_socket_that_never_ends_is_refused(probe_script, open_socket_stdin):
    result = _run_probe(probe_script, "--diff-from", open_socket_stdin)
    _assert_refused(result, "--diff-from")
    assert "pipe" in result.stderr


@NO_SOCKETS_ON_WINDOWS
def test_socket_carrying_finished_input_is_refused(probe_script):
    reader, peer = socket.socketpair()
    try:
        peer.sendall(b"abc")
        peer.close()
        result = _run_probe(probe_script, "--findings", reader)
    finally:
        reader.close()
    _assert_refused(result, "--findings")


@NO_PTY_ON_WINDOWS
def test_terminal_is_refused(probe_script):
    import pty

    master_fd, slave_fd = pty.openpty()
    try:
        result = _run_probe(probe_script, "--findings", slave_fd)
    finally:
        os.close(slave_fd)
        os.close(master_fd)
    _assert_refused(result, "--findings")


def _refusal_of(stream, capsys) -> tuple[int, str]:
    with pytest.raises(SystemExit) as raised:
        stdin_guard.read_stdin_or_exit("--findings", stream=stream)
    return raised.value.code, capsys.readouterr().out


def test_closed_stream_object_is_refused(capsys):
    with open(os.devnull) as stream:
        pass
    assert _refusal_of(stream, capsys) == (REFUSAL_EXIT_STATUS, "")


def test_stream_whose_descriptor_was_closed_is_refused(capsys):
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    stream = os.fdopen(read_fd, "r", closefd=False)
    os.close(read_fd)
    assert _refusal_of(stream, capsys) == (REFUSAL_EXIT_STATUS, "")


def test_missing_stdin_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", None)
    with pytest.raises(SystemExit) as raised:
        stdin_guard.read_stdin_or_exit("--findings")
    assert (raised.value.code, capsys.readouterr().out) == (REFUSAL_EXIT_STATUS, "")


@NO_SOCKETS_ON_WINDOWS
def test_predicate_reports_a_socket_unreadable_without_exiting(open_socket_stdin):
    with os.fdopen(os.dup(open_socket_stdin.fileno()), "r") as stream:
        assert stdin_guard.stdin_is_readable(stream) is False


def test_directory_is_unreadable(tmp_path: Path):
    directory_fd = os.open(tmp_path, os.O_RDONLY)
    try:
        stream = SimpleNamespace(closed=False, fileno=lambda: directory_fd)
        assert stdin_guard.stdin_is_readable(stream) is False
    finally:
        os.close(directory_fd)


def test_refusal_message_names_the_script_and_goes_to_stderr_only(
    probe_script, open_socket_stdin
):
    result = _run_probe(probe_script, "--findings", open_socket_stdin)
    assert result.stdout == ""
    assert result.stderr == (
        "probe_tool.py: no input; stdin never reaches EOF here (terminal or open "
        "socket). Pass --findings <file> or pipe the input in.\n"
    )
