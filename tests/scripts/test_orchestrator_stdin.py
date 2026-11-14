"""orchestrator.py reads its request from stdin only when stdin can end.

``orchestrator.py`` has no input flag, so an endless stdin falls back to the
default request and says so on stderr instead of failing. The matrix below
covers every stdin kind in-process; ``test_stdin_hang_guard.py`` proves the
wiring end to end in a subprocess. The ``claude -p`` children get no stdin.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

from _repo_root import REPO_ROOT
from tests._support.stdin_harness import (
    NO_PTY_ON_WINDOWS,
    NO_SOCKETS_ON_WINDOWS,
    SUBPROCESS_TIMEOUT_SECONDS,
    endless_socket,
    fallback_lines,
    terminal,
)
from tests._support.stdin_scripts import STDIN_SCRIPTS

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
DEFAULT_REQUEST = "default request"
PIPED_REQUEST = next(
    row.fixture for row in STDIN_SCRIPTS if row.script.endswith("orchestrator.py")
).strip()


@pytest.fixture(scope="module")
def orch():
    """The orchestrator module, imported with its directory on ``sys.path``
    only for the import."""
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(SCRIPTS_DIR))
        return importlib.import_module("orchestrator")


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
    slave = stack.enter_context(terminal())
    # Non-blocking, so a regression that reads the terminal fails instead of hanging.
    os.set_blocking(slave, False)
    return stack.enter_context(os.fdopen(slave, "r", closefd=False))


def _socket_peer_open(stack: contextlib.ExitStack):
    reader = stack.enter_context(endless_socket())
    # A regression that reads the open socket times out instead of hanging the run.
    reader.settimeout(SUBPROCESS_TIMEOUT_SECONDS)
    return stack.enter_context(reader.makefile("r"))


def _socket_request_then_eof(stack: contextlib.ExitStack):
    reader, peer = socket.socketpair()
    peer.sendall(PIPED_REQUEST.encode())
    peer.close()
    stack.callback(reader.close)
    return stack.enter_context(reader.makefile("r"))


def _closed_stream(stack: contextlib.ExitStack):
    with open(os.devnull, "r") as stream:
        pass
    return stream


def _missing_stdin(stack: contextlib.ExitStack):
    return None


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
        pytest.param(_missing_stdin, DEFAULT_REQUEST, 1, id="no-stdin-at-all"),
    ],
)
def test_orchestrator_picks_its_request_and_reports_a_fallback_only_when_it_fell_back(
    build_stdin, request_used, fallback_line_count, orch, monkeypatch, capsys
):
    with contextlib.ExitStack() as stack:
        monkeypatch.setattr(sys, "stdin", build_stdin(stack))
        resolved = orch._resolve_request_from_stdin()

    stderr = capsys.readouterr().err
    assert resolved == request_used
    assert len(fallback_lines(stderr)) == fallback_line_count
    if fallback_line_count == 0:
        assert stderr == ""


def _fake_completed_run(calls: list[dict]):
    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="trivial", stderr="")

    return fake_run


@pytest.mark.parametrize(
    "make_call",
    [
        pytest.param(lambda orch: orch.classify("add a login page"), id="classify"),
        pytest.param(
            lambda orch: orch.dispatch_persona("plan-review-design", {"goal": "x"}),
            id="dispatch-persona",
        ),
    ],
)
def test_claude_child_process_is_given_no_stdin(make_call, orch, monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(subprocess, "run", _fake_completed_run(calls))

    asyncio.run(make_call(orch))

    assert [call["stdin"] for call in calls] == [subprocess.DEVNULL]
