"""stdin_guard: refuse stdin streams that never reach EOF, read the rest.

Refusal rows that need a real fd 0 run the helper in a subprocess with a
timeout, so a regression fails the row instead of hanging the run. Streams
passed with ``stream=`` never touch the test process's own fd 0.
"""

from __future__ import annotations

import io
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT
from tests._support.stdin_harness import (
    NO_PTY_ON_WINDOWS,
    NO_SOCKETS_ON_WINDOWS,
    REFUSAL,
    SUBPROCESS_TIMEOUT_SECONDS,
    assert_refused,
    endless_socket,
    terminal,
)
from tests._support.stdin_scripts import INPUT_FLAGS, STDIN_SCRIPTS

LIB_DIR = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import stdin_guard

PIPE_BUFFER_EXCEEDING_BYTES = 200_000
NEVER_OPEN_FD = 2**30

NO_DIRECTORY_FDS_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows cannot open a directory as a descriptor"
)


def _write_then_close(write_fd: int, payload: bytes) -> None:
    with os.fdopen(write_fd, "wb") as writer:
        writer.write(payload)


def _read_through_pipe(payload: bytes) -> str:
    """Read ``payload`` through a pipe, with the write on its own thread.

    An exception raised by the writer thread is re-raised after the join.
    """
    read_fd, write_fd = os.pipe()
    writer_errors: list[OSError] = []

    def write() -> None:
        try:
            _write_then_close(write_fd, payload)
        except OSError as error:  # re-raised on the test thread below
            writer_errors.append(error)

    writer = threading.Thread(target=write)
    writer.start()
    try:
        with os.fdopen(read_fd, "r") as stream:
            text = stdin_guard.read_stdin_or_exit("--findings", stream=stream)
    finally:
        writer.join()
    if writer_errors:
        raise writer_errors[0]
    return text


def test_piped_input_is_read():
    assert _read_through_pipe(b"abc") == "abc"


def test_empty_pipe_returns_an_empty_string():
    assert _read_through_pipe(b"") == ""


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


SCRIPT_PATH_BY_NAME = {Path(row.script).name: row.script for row in STDIN_SCRIPTS}


def test_table_lists_distinct_scripts():
    scripts = [row.script for row in STDIN_SCRIPTS]
    assert len(scripts) == len(set(scripts))


def test_every_input_flag_belongs_to_a_script_in_the_table():
    assert {rule.script for rule in INPUT_FLAGS} <= set(SCRIPT_PATH_BY_NAME)


def _add_argument_call(source: str, option: str) -> str | None:
    """Source text of the ``add_argument(`` call whose option is exactly
    ``option``, up to the next call: ``"--findings-file"`` or a flag only
    mentioned in a comment does not match."""
    opener = re.compile(
        r"add_argument\(\s*(?:[\"'][^\"']*[\"']\s*,\s*)*"
        + r"[\"']"
        + re.escape(option)
        + r"[\"']"
    )
    match = opener.search(source)
    if match is None:
        return None
    following = source.find("add_argument(", match.end())
    return source[match.start() : following if following != -1 else len(source)]


#: Every option the table names: each input flag, each rule's mode option, and
#: each value that mode option has to accept.
REGISTRATION_CASES = [
    pytest.param(rule.script, rule.flag, None, id=f"{rule.script}-{rule.flag}")
    for rule in INPUT_FLAGS
] + [
    pytest.param(
        rule.script,
        rule.mode_option,
        mode,
        id=f"{rule.script}-{rule.mode_option}-{mode or 'option'}",
    )
    for rule in INPUT_FLAGS
    if rule.mode_option
    for mode in (None, *rule.modes)
]


@pytest.mark.parametrize(("script", "option", "value"), REGISTRATION_CASES)
def test_table_option_is_registered_as_an_argparse_option(script, option, value):
    source = (REPO_ROOT / "plugins" / "dev-team" / SCRIPT_PATH_BY_NAME[script]).read_text(
        "utf-8"
    )
    call = _add_argument_call(source, option)
    assert call is not None, f"{option} is not an add_argument option of {script}"
    if value is not None:
        assert re.search(rf"[\"']{re.escape(value)}[\"']", call), (
            f"{option} of {script} does not accept {value}"
        )


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
    try:
        return subprocess.run(
            [sys.executable, str(script), flag],
            stdin=stdin,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"no result in {SUBPROCESS_TIMEOUT_SECONDS} s (hang or slow host)")


@NO_SOCKETS_ON_WINDOWS
def test_socket_that_never_ends_is_refused(probe_script):
    with endless_socket() as reader:
        result = _run_probe(probe_script, "--diff-from", reader)
    assert_refused(result, "--diff-from")


@NO_SOCKETS_ON_WINDOWS
def test_socket_carrying_finished_input_is_refused(probe_script):
    reader, peer = socket.socketpair()
    try:
        peer.sendall(b"abc")
        peer.close()
        result = _run_probe(probe_script, "--findings", reader)
    finally:
        reader.close()
    assert_refused(result, "--findings")


@NO_PTY_ON_WINDOWS
def test_terminal_is_refused(probe_script):
    with terminal() as slave:
        result = _run_probe(probe_script, "--findings", slave)
    assert_refused(result, "--findings")


NO_CHARACTER_DEVICES_ON_WINDOWS = pytest.mark.skipif(
    sys.platform == "win32", reason="/dev/zero does not exist on Windows"
)


@NO_CHARACTER_DEVICES_ON_WINDOWS
def test_null_device_is_read_as_empty_input(probe_script):
    with open(os.devnull, "rb") as null_device:
        read = _run_probe(probe_script, "--findings", null_device)
    assert (read.returncode, read.stdout, read.stderr) == (0, "", "")


@NO_CHARACTER_DEVICES_ON_WINDOWS
@pytest.mark.parametrize("device", ["/dev/zero", "/dev/urandom"])
def test_endless_character_device_cannot_reach_eof(device):
    with open(device, "rb") as stream:
        assert stdin_guard.stream_can_reach_eof(stream) is False


def _refusal_of(stream, capsys) -> tuple[int, str]:
    with pytest.raises(SystemExit) as raised:
        stdin_guard.read_stdin_or_exit("--findings", stream=stream)
    return raised.value.code, capsys.readouterr().out


def test_closed_stream_object_is_refused(capsys):
    with open(os.devnull) as stream:
        pass
    assert _refusal_of(stream, capsys) == (2, "")


def _stream_with_fileno(fileno) -> SimpleNamespace:
    return SimpleNamespace(closed=False, fileno=fileno)


def _fileno_raising(error: Exception):
    def fileno():
        raise error

    return fileno


def test_stream_whose_descriptor_is_not_open_is_refused(capsys):
    stream = _stream_with_fileno(lambda: NEVER_OPEN_FD)
    assert _refusal_of(stream, capsys) == (2, "")


def test_missing_stdin_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", None)
    assert _refusal_of(None, capsys) == (2, "")


@NO_SOCKETS_ON_WINDOWS
def test_socket_cannot_reach_eof_and_does_not_exit():
    with endless_socket() as reader, os.fdopen(os.dup(reader.fileno()), "r") as stream:
        assert stdin_guard.stream_can_reach_eof(stream) is False


@NO_PTY_ON_WINDOWS
def test_terminal_cannot_reach_eof():
    with terminal() as slave, os.fdopen(slave, "r", closefd=False) as stream:
        assert stdin_guard.stream_can_reach_eof(stream) is False


@NO_DIRECTORY_FDS_ON_WINDOWS
def test_directory_cannot_reach_eof(tmp_path: Path):
    directory_fd = os.open(tmp_path, os.O_RDONLY)
    try:
        stream = _stream_with_fileno(lambda: directory_fd)
        assert stdin_guard.stream_can_reach_eof(stream) is False
    finally:
        os.close(directory_fd)


@pytest.mark.parametrize(
    ("error", "can_reach_eof"),
    [(OSError, False), (ValueError, True)],
    ids=["fileno-oserror-fails-safe", "fileno-valueerror-on-open-stream"],
)
def test_stream_whose_fileno_raises(error, can_reach_eof):
    stream = _stream_with_fileno(_fileno_raising(error("no descriptor")))
    assert stdin_guard.stream_can_reach_eof(stream) is can_reach_eof


@NO_SOCKETS_ON_WINDOWS
def test_refusal_message_is_exact_and_goes_to_stderr_only(probe_script):
    with endless_socket() as reader:
        result = _run_probe(probe_script, "--findings", reader)
    assert result.stdout == ""
    assert result.stderr == (
        f"{probe_script.name}: no input; stdin never reaches EOF here (terminal, "
        "open socket or closed stream). Pass --findings <file> or pipe the input "
        "in.\n"
    )
    assert REFUSAL in result.stderr
