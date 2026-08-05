"""Shared concurrent-subprocess-worker helper for plugins/dev-team/tests/ (#1889).

`run_concurrently` launches N OS processes at once and waits for all of them
— the same shape `tests/hooks/test_hook_state_concurrency.py` (#1501) used
inline before this extraction. Genuinely concurrent OS processes (not
threads) are the point: they let a `*_TEST_DELAY_MS` env var injected inside
a hook's own locked critical section force real overlap, turning a
lock-serialization regression test into a deterministic guard rather than a
timing-luck one.

`assert_concurrent_appends_produce_one_line_per_marker` is the shared
assertion for the #1874/#1889 append-lock regression tests: `json.loads()`
succeeding on every line is necessary but not sufficient to prove no
corruption happened, since a torn/interleaved merge can coincidentally
collapse into something that still parses (e.g. a duplicate key, last value
wins). Giving each worker a distinct marker and asserting each appears in
exactly one output line closes that gap — a merge splicing two workers'
bytes together would contain zero, or more than one, of the expected
markers, either of which fails the assertion.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

DEFAULT_WORKERS = 8
DEFAULT_DELAY_MS = 60

# tests/repo/test_hermetic_adoption.py (#715/#546) AST-scans for a
# subprocess call whose literal argv starts `git <mutating-verb>` and flags
# it unless an `env=` kwarg is present, closing the "mutating git env leaks
# into a pre-push hook and corrupts the parent worktree's refs" hole. That
# scan matches the call site's function name and a literal argv — neither
# holds when a caller hands a *variable* git argv to this module's own
# `run_concurrently`, so this guard closes the same hole for that caller
# shape instead of relying on the AST scan noticing it. Kept in lockstep
# with that file's own `_PY_MUTATING_VERBS` — no current caller in this repo
# hits this (all pass `sys.executable`/hook argv), so this is a latent-gap
# closer, not a live-bug fix.
_GIT_MUTATING_VERBS = {
    "init",
    "commit",
    "push",
    "update-ref",
    "checkout",
    "branch",
    "tag",
    "add",
    "clone",
    "fetch",
    "pull",
    "merge",
    "rebase",
    "reset",
    "apply",
    "cherry-pick",
    "revert",
    "worktree",
    "stash",
}


def run_concurrently(cmds, timeout=30):
    """Launch every (argv, stdin, env) concurrently; wait for all to exit.

    All processes are started (non-blocking `Popen`) before any is waited
    on, so they run genuinely concurrently regardless of how long draining
    each one's pipes takes afterward. `timeout` (seconds, per process) turns
    a hung worker — e.g. a deadlocked lock — into a clear
    `subprocess.TimeoutExpired`-derived failure instead of an indefinite
    hang.

    Rejects a `cmds` entry whose `argv` is a mutating `git` command run with
    `env=None` — that would inherit this process's real git env vars into a
    subprocess a test spawned, the exact hazard `hermetic_git_env()` exists
    to close (see module docstring). Pass a hermetic `env` explicitly if a
    future caller genuinely needs to run one concurrently.

    Recognizes `argv[0]` as `git` by basename (so `/usr/bin/git` and
    `git.exe` match too), then requires the *immediately following* token to
    be a mutating verb — disclosed limitation, not fixed here since no
    current caller is affected: a global option before the verb (`git -C
    <dir> commit`, `git -c user.name=x push`) is NOT recognized, so this
    guard only catches the plain `git <verb> ...` shape.

    Returns a list of (returncode, stdout, stderr) tuples, one per command,
    in the same order as `cmds`. A timed-out process reports `returncode`
    `None` and an `stderr` prefixed with `"TIMEOUT"`.
    """
    for argv, _stdin_text, env in cmds:
        if (
            env is None
            and len(argv) >= 2
            and Path(argv[0]).name.removesuffix(".exe") == "git"
            and argv[1] in _GIT_MUTATING_VERBS
        ):
            raise ValueError(
                f"run_concurrently: mutating git argv {argv!r} passed with env=None — "
                "pass a hermetic env (see tests/lib/hermetic.py::hermetic_git_env)"
            )
    procs = [
        subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        for argv, _stdin_text, env in cmds
    ]
    outputs = []
    for proc, (_argv, stdin_text, _env) in zip(procs, cmds):
        try:
            out, err = proc.communicate(stdin_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            outputs.append((None, out, f"TIMEOUT after {timeout}s: {err}"))
            continue
        outputs.append((proc.returncode, out, err))
    return outputs


def assert_concurrent_appends_produce_one_line_per_marker(argv_env_pairs, log_path, markers):
    """Run `argv_env_pairs` concurrently, then assert the resulting JSONL
    file has exactly one valid, unambiguous line per marker.

    `argv_env_pairs` is a list of (argv, env) pairs — note the different
    shape from `run_concurrently`'s (argv, stdin, env) triples; this
    function always passes empty stdin — one per marker (same order as
    `markers`); each `argv` must be built so its emitted line contains its
    corresponding marker verbatim (e.g. baked into a `--session`,
    `--subject-hash`, or JSON payload field the CLI under test already
    accepts). Markers must be mutually non-substrings of each other (e.g.
    `f"marker-{i}-end"`, not bare `str(i)`) so a substring search can't
    false-positive across two different workers' markers.
    """
    assert len(markers) == len(set(markers)), "markers must be unique"
    results = run_concurrently([(argv, "", env) for argv, env in argv_env_pairs])
    for rc, _out, err in results:
        assert rc == 0, f"cli failed (rc={rc}): {err}"

    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln]
    assert len(lines) == len(markers), f"expected {len(markers)} lines, got {len(lines)}"
    for line in lines:
        json.loads(line)  # raises if a line is torn/interleaved

    for marker in markers:
        hits = [line for line in lines if marker in line]
        assert len(hits) == 1, (
            f"marker {marker!r} expected in exactly one line, found in {len(hits)}: {hits}"
        )
