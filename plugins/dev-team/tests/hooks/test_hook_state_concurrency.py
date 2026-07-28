"""Concurrency regression tests for the hook state read-modify-write race (#1501).

`bash_retry_guard.py` and `session_learning_trigger.py` each maintain an
on-disk counter with a read-increment-write cycle. Before #1501 two concurrent
invocations against the same state file could both read the same value,
increment, and clobber each other — silently losing an update. These tests
drive each hook (and the shared `atomic_state.locked_state` primitive) with N
genuinely concurrent OS processes and assert the counter lands at exactly N.

A per-invocation race-window delay (`*_TEST_DELAY_MS`), injected INSIDE the
locked critical section, widens the overlap so that if the lock were ever
removed the workers would reliably lose updates — making these strong
regression guards, not timing-luck tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"

# N concurrent workers and the delay (ms) each holds the critical section.
# The delay guarantees overlap: total serialized wall-clock ~= N * DELAY.
_WORKERS = 8
_DELAY_MS = 60


def _run_concurrently(cmds):
    """Launch every (argv, stdin, env) concurrently; wait for all to exit 0-ish."""
    procs = []
    for argv, stdin_text, env in cmds:
        procs.append(
            (
                subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                ),
                stdin_text,
            )
        )
    # Feed stdin to all first (non-blocking-ish for tiny payloads), then wait.
    outputs = []
    for proc, stdin_text in procs:
        out, err = proc.communicate(stdin_text)
        outputs.append((proc.returncode, out, err))
    return outputs


# ---------------------------------------------------------------------------
# Shared primitive: atomic_state.locked_state serializes a RMW across processes
# ---------------------------------------------------------------------------


def test_locked_state_serializes_concurrent_increments(tmp_path):
    counter_file = tmp_path / "counter.json"
    counter_file.write_text(json.dumps({"n": 0}))

    worker = tmp_path / "worker.py"
    worker.write_text(
        textwrap.dedent(
            f"""
            import json, sys
            from pathlib import Path
            sys.path.insert(0, {str(_LIB_DIR)!r})
            from atomic_state import locked_state, atomic_write, race_window_delay
            p = Path({str(counter_file)!r})
            with locked_state(p):
                n = json.loads(p.read_text())["n"]
                race_window_delay("LOCK_TEST_DELAY_MS")
                atomic_write(p, json.dumps({{"n": n + 1}}))
            """
        )
    )

    env = {**os.environ, "LOCK_TEST_DELAY_MS": str(_DELAY_MS)}
    cmds = [([sys.executable, str(worker)], "", env) for _ in range(_WORKERS)]
    results = _run_concurrently(cmds)

    for rc, _out, err in results:
        assert rc == 0, f"worker failed (rc={rc}): {err}"

    final = json.loads(counter_file.read_text())["n"]
    assert final == _WORKERS, (
        f"lost-update race: expected {_WORKERS} increments, got {final}"
    )


# ---------------------------------------------------------------------------
# bash_retry_guard.py: N identical concurrent commands -> count == N
# ---------------------------------------------------------------------------


def test_bash_retry_guard_no_lost_increments(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    tmpdir = tmp_path / "state"
    tmpdir.mkdir()

    payload = json.dumps({"tool_input": {"command": "git status"}, "cwd": str(work)})
    env = {
        **os.environ,
        "TMPDIR": str(tmpdir),
        "DEV_TEAM_BASH_RETRY_THRESHOLD": "1000",  # never trip the nudge
        "DEV_TEAM_BASH_RETRY_TEST_DELAY_MS": str(_DELAY_MS),
    }
    cmds = [
        ([sys.executable, str(_HOOKS_DIR / "bash_retry_guard.py")], payload, env)
        for _ in range(_WORKERS)
    ]
    results = _run_concurrently(cmds)
    for rc, _out, err in results:
        assert rc == 0, f"hook failed (rc={rc}): {err}"

    state_files = list((tmpdir / "dev-team-bash-retry").glob("*.json"))
    assert len(state_files) == 1, f"expected one shared state file, got {state_files}"
    count = json.loads(state_files[0].read_text())["count"]
    assert count == _WORKERS, (
        f"lost-update race: expected count {_WORKERS}, got {count}"
    )


# ---------------------------------------------------------------------------
# session_learning_trigger.py: N concurrent SessionEnd hooks -> counter == N
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("jq") is None, reason="hook requires jq on PATH")
def test_session_learning_trigger_no_lost_increments(tmp_path):
    project = tmp_path / "project"
    (project / ".claude" / "metrics").mkdir(parents=True)

    # telemetry_consent reads ~/.claude/telemetry.json — point HOME at a temp
    # home with consent enabled so the hook proceeds past its consent gate.
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / "telemetry.json").write_text('{"enabled": true}')

    payload = json.dumps({"cwd": str(project), "session_id": "s"})
    env = {
        **os.environ,
        "HOME": str(fake_home),
        "DEV_TEAM_AUTO_REVIEW": "on",
        "DEV_TEAM_AUTO_REVIEW_THRESHOLD": "100000",  # never dispatch/reset
        "DEV_TEAM_SESSION_LEARNING_TEST_DELAY_MS": str(_DELAY_MS),
    }
    cmds = [
        ([sys.executable, str(_HOOKS_DIR / "session_learning_trigger.py")], payload, env)
        for _ in range(_WORKERS)
    ]
    results = _run_concurrently(cmds)
    for rc, _out, err in results:
        assert rc == 0, f"hook failed (rc={rc}): {err}"

    state = project / ".claude" / "metrics" / "learning-loop-state.json"
    assert state.is_file(), "hook never wrote state — consent/jq gate not satisfied?"
    counter = json.loads(state.read_text())["counter"]
    assert counter == _WORKERS, (
        f"lost-update race: expected counter {_WORKERS}, got {counter}"
    )
