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

import errno
import json
import os
import shutil
import sys
import textwrap
import threading
import time

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_TESTS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"

for _p in (_LIB_DIR, _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import atomic_state
from atomic_state import atomic_write, locked_state
from concurrency import DEFAULT_DELAY_MS as _DELAY_MS
from concurrency import DEFAULT_WORKERS as _WORKERS
from concurrency import run_concurrently as _run_concurrently

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


# ---------------------------------------------------------------------------
# locked_state gives up after a bounded budget rather than blocking forever
# on a stalled holder (#1888 — security review of #1874).
# ---------------------------------------------------------------------------


def test_locked_state_gives_up_after_stalled_holder(tmp_path, monkeypatch):
    state_file = tmp_path / "counter.json"
    state_file.write_text("{}")

    # `fcntl.flock` locks are scoped to the open file description, not the
    # process (POSIX) — two separate `open()` calls from two threads in this
    # one process genuinely contend, the same as two separate processes
    # would. That is what makes an in-process holder thread a valid stand-in
    # for a stalled cross-process holder here.
    hold_seconds = 0.4
    budget_ms = 50
    acquired = threading.Event()

    def _hold_lock():
        with locked_state(state_file):
            acquired.set()
            time.sleep(hold_seconds)

    holder = threading.Thread(target=_hold_lock)
    holder.start()
    try:
        assert acquired.wait(timeout=2), "holder thread never acquired the lock"

        # Small budget so the test runs fast; production uses the 2s default.
        monkeypatch.setenv("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS", str(budget_ms))
        start = time.monotonic()
        with locked_state(state_file):
            elapsed = time.monotonic() - start
            # The give-up path must still do real work unlocked, not just
            # return early — prove it via the same primitive callers use.
            atomic_write(state_file, json.dumps({"gave_up": True}))
    finally:
        holder.join(timeout=2)
    assert not holder.is_alive(), "holder thread never released the lock"

    budget_s = budget_ms / 1000
    # Lower bound proves genuine contention was hit (the give-up path actually
    # ran), not just that the second acquire happened to be fast on its own —
    # `_acquire_bounded` only returns False after `monotonic() >= deadline`.
    assert elapsed >= budget_s, (
        f"locked_state returned after only {elapsed:.3f}s against a "
        f"{budget_ms}ms budget — the second acquire may never have contended "
        "with the holder, so this test wouldn't catch a regression"
    )
    # Generous multiple of the configured budget (not of hold_seconds, which
    # only exists to guarantee overlap) — bounds the give-up latency against
    # what was actually configured, with margin for scheduler/CI jitter.
    max_elapsed = budget_s * 4
    assert elapsed < max_elapsed, (
        f"locked_state blocked for {elapsed:.3f}s despite a {budget_ms}ms "
        "acquire budget — a stalled holder must not block a caller "
        "indefinitely"
    )
    assert json.loads(state_file.read_text()) == {"gave_up": True}


def test_lock_acquire_budget_exceeds_worst_case_contention():
    # Mechanical link (not prose) between the production default and the
    # regression tests' worst-case legitimate queueing above, so widening
    # _WORKERS/_DELAY_MS fails loudly here instead of leaving a stale comment.
    worst_case_contention_seconds = _WORKERS * _DELAY_MS / 1000
    assert (
        worst_case_contention_seconds
        < atomic_state._DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS
    )


def test_lock_acquire_budget_invalid_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS", "not-a-number")
    assert (
        atomic_state._lock_acquire_budget_seconds()
        == atomic_state._DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS
    )


def test_lock_acquire_budget_negative_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS", "-5")
    assert (
        atomic_state._lock_acquire_budget_seconds()
        == atomic_state._DEFAULT_LOCK_ACQUIRE_BUDGET_SECONDS
    )


def test_lock_acquire_budget_clamped_to_ceiling(monkeypatch):
    monkeypatch.setenv("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS", "999999999")
    assert (
        atomic_state._lock_acquire_budget_seconds()
        == atomic_state._MAX_LOCK_ACQUIRE_BUDGET_SECONDS
    )


def test_try_acquire_returns_false_with_no_lock_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(atomic_state, "fcntl", None)
    monkeypatch.setattr(atomic_state, "msvcrt", None)
    lock_path = tmp_path / "state.lock"
    with open(lock_path, "a+") as handle:
        assert atomic_state._try_acquire(handle) is False


def test_acquire_bounded_gives_up_immediately_on_non_contention_error(
    tmp_path, monkeypatch
):
    # A non-contention OSError (e.g. ENOLCK/EOPNOTSUPP on a filesystem that
    # doesn't support flock) must give up right away, not burn the full
    # budget retrying an operation that can never succeed.
    def _raise_enolck(_handle):
        raise OSError(errno.ENOLCK, "no locks available")

    monkeypatch.setattr(atomic_state, "_try_acquire", _raise_enolck)
    monkeypatch.setenv("DEV_TEAM_LOCK_ACQUIRE_BUDGET_TEST_MS", "2000")
    lock_path = tmp_path / "state.lock"
    with open(lock_path, "a+") as handle:
        start = time.monotonic()
        assert atomic_state._acquire_bounded(handle) is False
        elapsed = time.monotonic() - start
    assert elapsed < 0.1, (
        f"gave up after {elapsed:.3f}s — a non-contention OSError should "
        "return immediately, not retry for the full budget"
    )
