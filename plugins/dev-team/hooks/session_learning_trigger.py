#!/usr/bin/env python3
"""session_learning_trigger.py — SessionEnd hook (Python port of session-learning-trigger.sh).

Counts sessions and dispatches background session-analysis at threshold.

CONSENT : off by default. Set `DEV_TEAM_AUTO_REVIEW=on` to enable.
THRESHOLD: `DEV_TEAM_AUTO_REVIEW_THRESHOLD` (default 5) sessions before dispatch.
STATE    : counter persisted in `<cwd>/.claude/metrics/learning-loop-state.json`.

Posture: fail-open. Every I/O error exits 0 without crashing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import telemetry_consent

try:
    from atomic_state import locked_state, race_window_delay
except ImportError:  # pragma: no cover
    import contextlib as _contextlib

    @_contextlib.contextmanager
    def locked_state(_path: Path):  # type: ignore[misc]
        yield

    def race_window_delay(_env_var: str) -> None:  # type: ignore[misc]
        return None


def _load_counter(state_file: Path) -> int:
    """Return the persisted counter, recovering to 0 on any error."""
    if not state_file.is_file():
        return 0
    try:
        data = json.loads(state_file.read_text())
    except (OSError, ValueError):
        return 0
    counter = data.get("counter")
    if isinstance(counter, int) and counter >= 0:
        return counter
    if isinstance(counter, str) and counter.isdigit():
        return int(counter)
    return 0


def _write_state(state_file: Path, counter: int) -> None:
    """Atomically write `{"counter": N}` to `state_file`. Fail-open on any error."""
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".learning-loop-state-",
            suffix=".json",
            dir=str(state_file.parent),
        )
    except OSError:
        return
    try:
        with os.fdopen(fd, "w") as handle:
            # `jq -nc` in bash writes with a trailing newline — match it so the
            # parity harness's side-effect tree hash lines up.
            handle.write(json.dumps({"counter": counter}, separators=(",", ":")) + "\n")
        os.replace(tmp_path, state_file)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _resolve_session_extract(hook_dir: Path) -> Path:
    """The repo-root `scripts/session_extract.py` this monorepo's own dev
    checkout carries, resolved from a shipped hook's install location.

    `session_extract.py` is deliberately monorepo-only tooling, never shipped
    inside the plugin (see `tests/repo/test_shipped_script_refs.py`'s
    allowlist comment for `/session-review` — the sibling maintainer tool
    this same script backs) — so for every downstream plugin install this
    path resolves to a location that simply does not exist, and
    `_dispatch_background_analysis` must treat that as the normal case, not
    a failure to hide.

    `hook_dir` is `plugins/dev-team/hooks`; `scripts/` sits three levels up
    from there (`hooks` -> `dev-team` -> `plugins` -> repo root), not two
    (#1649 — the original `../..` landed on `plugins/scripts/`, which has
    never existed anywhere in this repo, so this call has been a silent
    no-op since it shipped).
    """
    return (hook_dir / ".." / ".." / ".." / "scripts" / "session_extract.py").resolve()


def _dispatch_background_analysis(
    cwd: Path, session_id: str | None, hook_dir: Path
) -> None:
    """Fire-and-forget background analysis run.

    Skips entirely, rather than composing a shell command guaranteed to fail,
    when `session_extract.py` isn't present (every downstream install, and
    any dev checkout missing the repo-root `scripts/` tree) — see
    `_resolve_session_extract`. When it IS present but the dispatch itself
    fails, the failure is logged to `metrics_dir/session-learning-errors.log`
    rather than swallowed by a bare `|| true`, so a future regression here
    is visible instead of permanently silent (#1649).
    """
    session_extract = _resolve_session_extract(hook_dir)
    if not session_extract.is_file():
        return
    pending = artifact_paths.resolve_file("metrics", "pending-review.jsonl", cwd)

    prompt = (
        "Run the session-analysis agent and output each finding as a JSONL "
        "entry to stdout with fields: queued_at (ISO-8601 UTC now), source "
        "(session-learning-trigger), session_id, findings (array of objects "
        "with lever, evidence, target_artifact, proposed_change, route)"
    )

    session_id_args = []
    if session_id:
        # --session-id shares the parent's prompt-cache prefix (~26% cost cut)
        session_id_args = ["--session-id", session_id]

    metrics_dir = artifact_paths.metrics_dir(cwd)
    try:
        metrics_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    # Compose a shell script that runs asynchronously — same fire-and-forget
    # semantics as bash's `( ... ) &`.
    #
    # session_extract.py's stderr is appended to a log file, not discarded
    # (#1649): the `|| true` still keeps this line from aborting the rest of
    # the chain on failure (though it never would — these are `;`-joined,
    # not `&&`), but a failure here previously left zero evidence anywhere.
    # `2>>` (append) rather than `2>` so repeated dispatches accumulate a
    # history instead of each one erasing the last.
    extract_log = metrics_dir / "session-learning-errors.log"
    shell_body = (
        f"python3 {shell_quote(str(session_extract))} --since last "
        f">/dev/null 2>>{shell_quote(str(extract_log))} || true; "
        f"tmp_out=$(mktemp {shell_quote(str(metrics_dir / '.pending-XXXXXX.jsonl'))} "
        "2>/dev/null) || exit 0; "
        f"if claude {' '.join(shell_quote(a) for a in session_id_args)} "
        f"--dangerously-skip-permissions --print {shell_quote(prompt)} "
        '>"$tmp_out" 2>/dev/null; then '
        f'cat "$tmp_out" >> {shell_quote(str(pending))} 2>/dev/null || true; fi; '
        'rm -f "$tmp_out"'
    )

    try:
        subprocess.Popen(
            ["sh", "-c", shell_body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, OSError):
        pass


def shell_quote(value: str) -> str:
    """Portable-ish single-quote quoting for POSIX sh."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> int:
    if os.environ.get("DEV_TEAM_AUTO_REVIEW", "") != "on":
        return 0
    if not telemetry_consent.is_enabled():
        return 0

    # bash requires jq; Python does not, but keep parity on the "no jq" exit
    # for hosts that intentionally strip it (fail-open discipline).
    if shutil.which("jq") is None:
        return 0

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return 0

    cwd_str = payload.get("cwd") if isinstance(payload, dict) else None
    cwd = Path(cwd_str) if isinstance(cwd_str, str) and cwd_str else Path.cwd()
    if not cwd.is_dir():
        cwd = Path.cwd()

    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(session_id, str) or not session_id:
        session_id = None

    threshold_env = os.environ.get("DEV_TEAM_AUTO_REVIEW_THRESHOLD", "5")
    try:
        threshold = int(threshold_env)
    except ValueError:
        threshold = 5

    state_file = artifact_paths.resolve_file("metrics", "learning-loop-state.json", cwd)
    hook_dir = Path(__file__).resolve().parent

    # Serialize the load-increment-write so two SessionEnd hooks ending in the
    # same cwd near-simultaneously each advance the counter exactly once
    # instead of racing and losing an increment (#1501). The write itself is
    # already atomic (tempfile + os.replace in _write_state); the lock closes
    # the remaining read-modify-write gap. Fail-open: unlockable → runs
    # unlocked. The dispatch stays outside the lock — it is fire-and-forget and
    # must not hold the lock across a subprocess spawn.
    dispatch = False
    with locked_state(state_file):
        counter = _load_counter(state_file) + 1
        race_window_delay("DEV_TEAM_SESSION_LEARNING_TEST_DELAY_MS")
        if counter >= threshold:
            _write_state(state_file, 0)
            dispatch = True
        else:
            _write_state(state_file, counter)

    if dispatch:
        _dispatch_background_analysis(cwd, session_id, hook_dir)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
