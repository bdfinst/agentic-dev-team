"""Unit + end-to-end tests for hooks/lib/boundary_events.py (#859).

Covers:
  - the emit helper itself: append, dir creation, compact single-line JSON,
    fail-open on OSError / arbitrary exceptions.
  - one block, one warn, one bypass, and one intervention emission, driven
    end-to-end through the real hooks (destructive_guard.py, verify_guard.py,
    pre_commit_review.py, telemetry.py).
  - fail-open: with the emit helper monkeypatched to raise, each hook's
    exit code / stdout / stderr are unaffected.
  - append-only valid JSONL across two consecutive emissions.
  - the "never free text" privacy boundary: sentinel strings fed through
    commands/prompts never appear anywhere in boundary-events.jsonl, and
    every emitted event has exactly the documented schema keys with
    `decision` inside the enum.
  - knowledge/telemetry-schema.md documents every `metrics/*.jsonl`/`.json`
    path referenced in shipped code (coverage cross-check).
  - concurrent writers (#1874): N processes appending simultaneously must
    never interleave into a corrupted JSONL line.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

# One test in this file toggles the REAL, fixed-path
# plugins/dev-team/hooks/careful-state.json (destructive_guard.py's actual
# state file, not a tmp_path-scoped copy) to exercise careful-mode blocking.
# Every other test that invokes destructive_guard.py as a subprocess asserts
# it is NOT blocked — under `-n auto`, if that toggling test lands on a
# different worker and runs concurrently, the other tests can see the
# temporarily-active careful-state.json and fail with a spurious block.
# Force the whole file onto one worker so the toggle is never concurrent
# with a read (issue #1495) — a single per-function marker on only the
# toggling test does not prevent this, since the *readers* also need to be
# excluded from running in parallel with it.
pytestmark = pytest.mark.xdist_group(name="careful-state-shared-file")

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_HOOKS_DIR = _PLUGIN_DIR / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_TESTS_LIB = _PLUGIN_DIR / "tests" / "lib"

for _p in (_HOOKS_DIR, _LIB_DIR, _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import boundary_events  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]
from jsonl import read_jsonl as _read_jsonl  # type: ignore[import-not-found]

_DECISION_ENUM = {
    "block",
    "warn",
    "bypass",
    "intervention",
    "revert",
    "record",
    "dispatch-failure",
}
_SCHEMA_FIELDS = {"ts", "hook", "tool", "decision", "matched_rule", "plugin_version"}
_OPTIONAL_FIELDS = {"session_id"}


# ---------------------------------------------------------------------------
# emit_boundary_event() — the helper itself
# ---------------------------------------------------------------------------


def test_emit_appends_one_compact_jsonl_line(tmp_path: Path) -> None:
    boundary_events.emit_boundary_event(
        tmp_path, "destructive_guard", "Bash", "warn", "file_destruction:rm-rf"
    )
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    assert log.is_file()
    raw = log.read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) == 1
    assert raw.endswith("\n")
    # Compact separators: no space after ',' or ':'.
    assert ", " not in lines[0]
    assert '": ' not in lines[0]
    event = json.loads(lines[0])
    assert event["hook"] == "destructive_guard"
    assert event["tool"] == "Bash"
    assert event["decision"] == "warn"
    assert event["matched_rule"] == "file_destruction:rm-rf"
    assert "ts" in event and "plugin_version" in event


def test_emit_creates_metrics_dir_when_absent(tmp_path: Path) -> None:
    assert not (tmp_path / ".claude" / "metrics").exists()
    boundary_events.emit_boundary_event(tmp_path, "verify_guard", "Bash", "block", "x")
    assert (tmp_path / ".claude" / "metrics").is_dir()


def test_emit_appends_not_overwrites_across_two_calls(tmp_path: Path) -> None:
    boundary_events.emit_boundary_event(tmp_path, "h1", "Bash", "warn", "r1")
    boundary_events.emit_boundary_event(tmp_path, "h2", "Bash", "block", "r2")
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 2
    assert events[0]["hook"] == "h1"
    assert events[1]["hook"] == "h2"


def test_emit_includes_session_id_when_given(tmp_path: Path) -> None:
    boundary_events.emit_boundary_event(
        tmp_path, "verify_guard", "Bash", "block", "verify-repeat-threshold", "sess-1"
    )
    event = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")[0]
    assert event["session_id"] == "sess-1"


def test_emit_omits_session_id_when_absent(tmp_path: Path) -> None:
    boundary_events.emit_boundary_event(tmp_path, "verify_guard", "Bash", "block", "r")
    event = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")[0]
    assert "session_id" not in event


def test_emit_fails_open_on_unwritable_metrics_dir(tmp_path: Path) -> None:
    """A metrics/ that can't be created (e.g. a file occupying its path)
    must not raise — the caller's exit code must never be affected."""
    (tmp_path / ".claude").write_text("not a directory")
    # Must not raise.
    boundary_events.emit_boundary_event(tmp_path, "h", "Bash", "warn", "r")


def test_emit_fails_open_on_arbitrary_exception(tmp_path: Path, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("disk is on fire")

    monkeypatch.setattr(boundary_events, "_isoformat_utc", _boom)
    # Must not raise.
    boundary_events.emit_boundary_event(tmp_path, "h", "Bash", "warn", "r")
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_emit_swallows_bad_cwd_type(tmp_path: Path, monkeypatch) -> None:
    """An unusable `cwd` (e.g. None with no real cwd fallback failing) must
    still not raise — fail-open covers the whole call, not just I/O."""
    monkeypatch.setattr(boundary_events.Path, "cwd", lambda: tmp_path)
    boundary_events.emit_boundary_event(None, "h", "Bash", "warn", "r")


def test_append_line_locked_swallows_oserror_inside_the_critical_section(
    tmp_path: Path,
) -> None:
    """#1874 (correctness re-review): calls `_append_line_locked` directly,
    bypassing `emit_boundary_event`'s outer `except Exception` — which
    would mask the inner handler's removal and make an
    `emit_boundary_event`-level test unable to fail for the reason it
    claims to guard. Making `log`'s own path a directory means
    `open(log, "a")` raises OSError *inside* the lock, the one spot
    `atomic_state.locked_state`'s documented contract says the caller must
    handle itself. Must not raise."""
    log = tmp_path / "metrics" / "boundary-events.jsonl"
    log.mkdir(parents=True)
    boundary_events._append_line_locked(log, '{"hook":"h"}\n')
    assert list(log.iterdir()) == []


class _SpyHandle:
    """Records write()/flush() calls without touching a real file, so a
    test can assert *how many* writes `_write_jsonl_line` issues — the
    thing that actually distinguishes its plain-write branch from its
    split-write branch, since both branches reassemble to the same final
    bytes (content-only assertions can't tell them apart)."""

    def __init__(self) -> None:
        self.writes: list[str] = []
        self.flushes = 0

    def write(self, chunk: str) -> None:
        self.writes.append(chunk)

    def flush(self) -> None:
        self.flushes += 1


@pytest.mark.parametrize(
    ("raw", "expect_split"),
    [
        (None, False),  # unset
        ("", False),  # empty string
        ("0", False),  # non-positive: disabled, per this repo's DEV_TEAM_* convention
        ("-5", False),  # negative: also disabled
        ("abc", False),  # unparseable: falls back to disabled
        ("1", True),  # positive: split-write branch
    ],
)
def test_write_jsonl_line_delay_gate_selects_the_documented_branch(
    monkeypatch, raw: str | None, expect_split: bool
) -> None:
    """#1874 (correctness re-review): discriminates `_write_jsonl_line`'s
    two branches by write COUNT, not final content — a bare truthiness
    check on the environment string (the bug this gate guards against)
    would take the split-write branch for `"0"` too, since it's a
    non-empty string, but would still reassemble to identical bytes,
    which is why a content-only assertion can't catch it."""
    if raw is None:
        monkeypatch.delenv(boundary_events._TEST_DELAY_ENV, raising=False)
    else:
        monkeypatch.setenv(boundary_events._TEST_DELAY_ENV, raw)
    line = '{"hook":"h"}\n'
    spy = _SpyHandle()
    boundary_events._write_jsonl_line(spy, line)
    assert len(spy.writes) == (2 if expect_split else 1)
    assert spy.flushes == (1 if expect_split else 0)
    assert "".join(spy.writes) == line


# ---------------------------------------------------------------------------
# Concurrent writers (#1874): N processes appending simultaneously must
# never interleave into a corrupted JSONL line.
# ---------------------------------------------------------------------------

_CONCURRENCY_WORKERS = 8
_CONCURRENCY_DELAY_MS = 60


def _write_concurrent_emit_worker(tmp_path: Path) -> Path:
    """A tiny standalone script that calls the real `emit_boundary_event`
    once against `tmp_path`. Run as N separate OS processes (not threads) so
    each gets its own `open()` file descriptor on the shared log — the same
    shape as sliced-mode code-review (#1874), where 2-3 concurrent slice
    dispatches can each independently emit a "dispatch-failure" event."""
    worker = tmp_path / "_emit_worker.py"
    worker.write_text(
        textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(_LIB_DIR)!r})
            import boundary_events
            boundary_events.emit_boundary_event(
                {str(tmp_path)!r}, "concurrency-test", "Bash", "warn", "worker-emit"
            )
            """
        )
    )
    return worker


def test_concurrent_emits_never_interleave_into_a_corrupted_line(
    tmp_path: Path,
) -> None:
    """#1874: N processes appending concurrently, each holding the append
    open across an injected delay (`boundary_events._write_jsonl_line`'s
    test-only split-write, gated by DEV_TEAM_BOUNDARY_EVENTS_TEST_DELAY_MS),
    must still produce exactly N well-formed JSONL lines.

    Without the `atomic_state.locked_state` lock `emit_boundary_event` now
    holds for the full open+write+close, this test reliably goes red: the
    injected delay widens the window enough that another worker's full line
    lands between this worker's own two write() halves, corrupting both
    lines into invalid JSON / merging two events into one line."""
    worker = _write_concurrent_emit_worker(tmp_path)
    # Hermetic env (matches this file's own `_run_hook`/`hermetic_git_env`
    # convention): the worker's `emit_boundary_event` resolves its target
    # via `artifact_paths.project_root`, which shells out to `git
    # rev-parse --show-toplevel`. Passing the raw host environment would
    # let an inherited GIT_DIR/GIT_WORK_TREE (as git itself sets for a
    # hook-invoked process, e.g. this very suite running under the
    # `pre-push` hook) redirect that resolution outside `tmp_path` — and
    # this test's exact `len(events) == _CONCURRENCY_WORKERS` assertion is
    # the most sensitive test in this file to that misresolution.
    env = {
        **hermetic_git_env(home=tmp_path),
        boundary_events._TEST_DELAY_ENV: str(_CONCURRENCY_DELAY_MS),
    }
    procs = [
        subprocess.Popen(
            [sys.executable, str(worker)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(_CONCURRENCY_WORKERS)
    ]
    for proc in procs:
        # 30s, not 10s: 8 sequential subprocess.communicate() calls each pay
        # interpreter startup + a `git rev-parse` (via project_root) + the
        # deliberate 60ms injected delay, and a slow/contended CI runner
        # (test-review, #1874) could otherwise trip the timeout for
        # unrelated infra reasons rather than the race condition under test.
        _out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, f"worker failed: {err!r}"

    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    raw = log.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    # json.loads raises on any interleaved/torn line — a corrupted append
    # surfaces here as a JSONDecodeError, not a silent pass.
    events = [json.loads(ln) for ln in lines]
    assert len(events) == _CONCURRENCY_WORKERS, (
        f"expected {_CONCURRENCY_WORKERS} distinct JSONL lines, got "
        f"{len(events)} — a merged/lost line indicates interleaved "
        f"concurrent appends: {lines!r}"
    )
    assert all(event["matched_rule"] == "worker-emit" for event in events), events


# ---------------------------------------------------------------------------
# End-to-end: one block, one warn, one bypass, one intervention through the
# real hooks.
# ---------------------------------------------------------------------------


def _run_hook(hook_name: str, payload: dict, env_extra: dict | None = None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(_HOOKS_DIR / hook_name)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_destructive_guard_warn_emits_boundary_event(tmp_path: Path) -> None:
    result = _run_hook(
        "destructive_guard.py",
        {"tool_input": {"command": "kill -9 1234"}, "cwd": str(tmp_path)},
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    event = events[0]
    assert event["hook"] == "destructive_guard"
    assert event["tool"] == "Bash"
    assert event["decision"] == "warn"
    assert "Process destruction" in event["matched_rule"]


def test_destructive_guard_block_emits_boundary_event(tmp_path: Path) -> None:
    # careful-state.json is destructive_guard.py's real, fixed-path state
    # file, shared with tests/hooks/test_destructive_guard.py and
    # plugins/dev-team/tests/hooks/test_code_intelligence_nudge.py (same
    # xdist_group name there, applied module-wide in both — see this file's
    # own module-level pytestmark above). --dist loadgroup (scripts/ci-local.sh)
    # forces everything in this group onto one worker so they never race on
    # the shared file across pytest-xdist worker processes.
    careful_state = _HOOKS_DIR / "careful-state.json"
    original = careful_state.read_text() if careful_state.is_file() else None
    try:
        careful_state.write_text(json.dumps({"active": True}), encoding="utf-8")
        result = _run_hook(
            "destructive_guard.py",
            {"tool_input": {"command": "rm -rf /"}, "cwd": str(tmp_path)},
        )
        assert result.returncode == 2
        events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
        assert len(events) == 1
        assert events[0]["decision"] == "block"
        assert events[0]["hook"] == "destructive_guard"
    finally:
        if original is None:
            careful_state.unlink(missing_ok=True)
        else:
            careful_state.write_text(original, encoding="utf-8")


def test_verify_guard_block_emits_boundary_event(tmp_path: Path) -> None:
    env = {"TMPDIR": str(tmp_path)}
    payload = {
        "session_id": "boundary-verify-1",
        "cwd": str(tmp_path),
        "tool_input": {"command": "npm test"},
    }
    for _ in range(3):
        result = _run_hook("verify_guard.py", payload, env)
    assert result.returncode == 2
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    block_events = [e for e in events if e["decision"] == "block"]
    assert len(block_events) == 1
    assert block_events[0]["hook"] == "verify_guard"
    assert block_events[0]["matched_rule"] == "verify-repeat-threshold"
    assert block_events[0]["session_id"] == "boundary-verify-1"


def _init_git_repo(root: Path) -> dict:
    env = hermetic_git_env(home=root)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
    )
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=root, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, env=env, check=True)
    (root / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"], cwd=root, env=env, check=True
    )
    (root / "file.txt").write_text("hello again\n")
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    return env


def test_pre_commit_review_block_emits_boundary_event(tmp_path: Path) -> None:
    env = _init_git_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "pre_commit_review.py")],
        input=json.dumps(
            {
                "tool_input": {"command": 'git commit -m "wip"'},
                "cwd": str(tmp_path),
            }
        ).encode(),
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["hook"] == "pre_commit_review"
    assert events[0]["decision"] == "block"
    assert events[0]["matched_rule"] == "pre-commit-review"


def test_pre_commit_review_bypass_emits_boundary_event(tmp_path: Path) -> None:
    env = _init_git_repo(tmp_path)
    env["GATE_BYPASS_REASON"] = "hotfix, review to follow"
    result = subprocess.run(
        [sys.executable, str(_HOOKS_DIR / "pre_commit_review.py")],
        input=json.dumps(
            {
                "tool_input": {"command": 'git commit --no-verify -m "wip"'},
                "cwd": str(tmp_path),
            }
        ).encode(),
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["hook"] == "pre_commit_review"
    assert events[0]["decision"] == "bypass"
    assert events[0]["matched_rule"] == "--no-verify"
    # The existing gate-bypass-audit.jsonl accountability record is untouched
    # (now under .claude/metrics/ per the artifact_paths migration, Slice 4).
    audit = _read_jsonl(tmp_path / ".claude" / "metrics" / "gate-bypass-audit.jsonl")
    assert len(audit) == 1
    assert audit[0]["reason"] == "hotfix, review to follow"


def test_intervention_keyword_emits_event(tmp_path: Path) -> None:
    for prompt, keyword in (("override", "override"), ("pause", "pause"), ("stop", "stop")):
        result = _run_hook(
            "telemetry.py",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": prompt,
                "cwd": str(tmp_path),
                "session_id": "s-intervention",
            },
        )
        assert result.returncode == 0
        events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
        assert events[-1]["decision"] == "intervention"
        assert events[-1]["matched_rule"] == keyword
        assert events[-1]["hook"] == "telemetry"
        assert events[-1]["tool"] == "UserPromptSubmit"


def test_intervention_with_payload_records_only_keyword(tmp_path: Path) -> None:
    """`override: some secret reason` must record only `override`, never
    the payload after the colon."""
    result = _run_hook(
        "telemetry.py",
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "override: SENTINEL-PAYLOAD-TEXT",
            "cwd": str(tmp_path),
        },
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["matched_rule"] == "override"
    raw = (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").read_text()
    assert "SENTINEL-PAYLOAD-TEXT" not in raw


def test_non_intervention_prompt_emits_nothing(tmp_path: Path) -> None:
    """The word 'stop' mid-sentence (not anchored at the start) must not
    fire an intervention event — grammar-anchored, not substring match."""
    result = _run_hook(
        "telemetry.py",
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "please don't stop working on this",
            "cwd": str(tmp_path),
        },
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


def test_ordinary_prompt_emits_nothing(tmp_path: Path) -> None:
    result = _run_hook(
        "telemetry.py",
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "please implement feature X",
            "cwd": str(tmp_path),
        },
    )
    assert result.returncode == 0
    assert not (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").exists()


# ---------------------------------------------------------------------------
# Fail-open: telemetry failure must never change the hooked tool call's
# exit code / stdout / stderr.
# ---------------------------------------------------------------------------


def test_destructive_guard_behavior_unaffected_when_metrics_unwritable(
    tmp_path: Path,
) -> None:
    (tmp_path / ".claude").write_text("occupied by a file, not a directory")
    result = _run_hook(
        "destructive_guard.py",
        {"tool_input": {"command": "kill -9 1234"}, "cwd": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"CAUTION: Destructive command detected (Process destruction: kill -9)." in (
        result.stdout
    )


def test_emit_helper_monkeypatched_to_raise_does_not_change_hook_behavior(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Each hook wraps the shared helper in a local safety net (#859): even
    if the underlying `boundary_events.emit_boundary_event` itself is
    broken/monkeypatched to raise, the hook's own `emit_boundary_event`
    (the module-level wrapper every call site uses) swallows it — main()'s
    exit code and stdout are unaffected."""
    if str(_HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(_HOOKS_DIR))
    import io

    import destructive_guard  # type: ignore[import-not-found]

    def _boom(*_a, **_k):
        raise RuntimeError("telemetry exploded")

    # Patch the underlying (imported-as-_emit_boundary_event) implementation
    # that destructive_guard's local emit_boundary_event() wrapper delegates
    # to — this simulates the shared helper itself misbehaving.
    monkeypatch.setattr(destructive_guard, "_emit_boundary_event", _boom)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps({"tool_input": {"command": "kill -9 1"}, "cwd": str(tmp_path)})
        ),
    )
    result = destructive_guard.main()
    out = capsys.readouterr().out
    assert result == 0
    assert "CAUTION: Destructive command detected (Process destruction: kill -9)." in out


# ---------------------------------------------------------------------------
# Privacy: no free text anywhere in the stream.
# ---------------------------------------------------------------------------


def test_no_free_text_leaks_into_boundary_events(tmp_path: Path) -> None:
    sentinel = "SENTINEL-DO-NOT-LOG-THIS-COMMAND-TEXT"
    # destructive_guard: pattern match still fires on the destructive
    # substring even embedded in a sentinel-laden command.
    _run_hook(
        "destructive_guard.py",
        {
            "tool_input": {"command": f"kill -9 1234 # {sentinel}"},
            "cwd": str(tmp_path),
        },
    )
    _run_hook(
        "telemetry.py",
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": f"override: {sentinel}",
            "cwd": str(tmp_path),
        },
    )
    raw = (tmp_path / ".claude" / "metrics" / "boundary-events.jsonl").read_text(encoding="utf-8")
    assert sentinel not in raw
    for event in _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"):
        keys = set(event.keys())
        assert keys <= (_SCHEMA_FIELDS | _OPTIONAL_FIELDS)
        assert _SCHEMA_FIELDS <= keys
        assert event["decision"] in _DECISION_ENUM


# ---------------------------------------------------------------------------
# CLI entry point (#1461) — lets skill markdown emit an event directly.
# ---------------------------------------------------------------------------


def test_cli_emits_one_event(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "doc-only",
            "--subject-hash",
            "deadbeef",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["hook"] == "code-review"
    assert events[0]["tool"] == "Skill"
    assert events[0]["decision"] == "bypass"
    assert events[0]["matched_rule"] == "doc-only-review-exempt"
    assert events[0]["subject_hash"] == "deadbeef"


def test_cli_includes_session_id_when_given(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "doc-only",
            "--subject-hash",
            "deadbeef",
            "--session-id",
            "sess-cli",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert events[0]["session_id"] == "sess-cli"


def test_cli_single_agent_event_emits_the_other_fixed_tuple(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "single-agent",
            "--subject-hash",
            "cafef00d",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert events[0]["matched_rule"] == "single-agent-review-exempt"


def test_cli_dispatch_failure_emits_event_with_agent_as_matched_rule(
    tmp_path: Path,
) -> None:
    """#1763: `--event dispatch-failure` writes a well-formed event with the
    given (registered) agent name as `matched_rule` and the given hash as
    `subject_hash`."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--agent",
            "security-review",
            "--subject-hash",
            "feedface",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    event = events[0]
    assert event["hook"] == "code-review"
    assert event["tool"] == "Skill"
    assert event["matched_rule"] == "security-review"
    assert event["subject_hash"] == "feedface"
    # The decision value is never "record" and is distinct from every other
    # existing verdict value.
    assert event["decision"] == "dispatch-failure"
    assert event["decision"] != "record"
    assert event["decision"] not in {"block", "warn", "bypass", "intervention", "revert"}


def test_cli_dispatch_failure_unregistered_agent_is_dropped(tmp_path: Path) -> None:
    """An agent name absent from the registered review-agent set must be
    silently NOT recorded — no boundary event is appended for that
    invocation."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--agent",
            "totally-fabricated-not-a-real-review-agent",
            "--subject-hash",
            "deadbeef",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    assert not log.exists()


def test_cli_dispatch_failure_stamps_subject_hash_normalized_when_given(
    tmp_path: Path,
) -> None:
    """Mirrors agent_dispatch_ledger.py's "record" events, which stamp both
    hashes — without this, review_gate_corroboration's cosmetic-delta
    carry-forward lens (which reads only the normalized hash) could never
    see a genuine dispatch failure."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--agent",
            "security-review",
            "--subject-hash",
            "feedface",
            "--subject-hash-normalized",
            "normface",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["subject_hash_normalized"] == "normface"


def test_cli_dispatch_failure_omits_subject_hash_normalized_when_absent(
    tmp_path: Path,
) -> None:
    """--subject-hash-normalized is optional — an event written without it
    carries no such key, matching every other optional field's convention
    in this module."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--agent",
            "security-review",
            "--subject-hash",
            "feedface",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert "subject_hash_normalized" not in events[0]


def test_cli_dispatch_failure_normalizes_plugin_qualified_agent_name(
    tmp_path: Path,
) -> None:
    """The plugin's normal, installed invocation form ("dev-team:<agent>")
    must be recognized identically to the bare stem and recorded under the
    bare (closed-vocabulary) name — matching agent_dispatch_ledger.py's own
    strip_plugin_prefix normalization exactly (see that hook's
    test_a_qualified_name_is_normalized_to_the_bare_stem)."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--agent",
            "dev-team:security-review",
            "--subject-hash",
            "feedface",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    events = _read_jsonl(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert len(events) == 1
    assert events[0]["matched_rule"] == "security-review"


def test_cli_dispatch_failure_other_plugin_qualified_name_is_dropped(
    tmp_path: Path,
) -> None:
    """A DIFFERENT plugin's qualified name must never be recorded — only
    this plugin's own "dev-team:" prefix is stripped, matching
    agent_dispatch_ledger.py's own posture."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--agent",
            "other-plugin:security-review",
            "--subject-hash",
            "feedface",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    assert not log.exists()


def test_cli_dispatch_failure_missing_agent_is_a_silent_noop(tmp_path: Path) -> None:
    """Fail-open, matching _main()'s own "always exits 0" emit-path contract
    (module docstring) — a caller that forgot --agent gets a no-op, not a
    nonzero exit from a telemetry emitter."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "dispatch-failure",
            "--subject-hash",
            "deadbeef",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    assert not log.exists()


def test_cli_rejects_arbitrary_hook_decision_matched_rule(tmp_path: Path) -> None:
    """#1461 security review: the CLI must NOT accept free-form
    --hook/--tool/--decision/--matched-rule — that would let anyone forge an
    arbitrary boundary event, including a fake "record" row for an
    unregistered agent name, defeating the whole dispatch-ledger gate. Only
    a fixed, named --event may be selected; the old free-form flags must no
    longer be recognized at all."""
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--hook",
            "agent_dispatch_ledger",
            "--tool",
            "Agent",
            "--decision",
            "record",
            "--matched-rule",
            "security-review",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    assert not log.exists()


def test_cli_rejects_unknown_event_name(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_LIB_DIR / "boundary_events.py"),
            "--cwd",
            str(tmp_path),
            "--event",
            "agent-dispatch-ledger-record",
            "--subject-hash",
            "deadbeef",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    log = tmp_path / ".claude" / "metrics" / "boundary-events.jsonl"
    assert not log.exists()


def test_cli_missing_required_arg_exits_nonzero() -> None:
    result = subprocess.run(
        [sys.executable, str(_LIB_DIR / "boundary_events.py"), "--hook", "x"],
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Schema doc completeness (#859 acceptance criterion).
# ---------------------------------------------------------------------------


def test_schema_doc_covers_all_metrics_paths() -> None:
    """Every `metrics/*.jsonl` / `metrics/*.json` path string referenced in
    shipped plugin code (hooks/skills/agents/knowledge) must have a
    corresponding section in knowledge/telemetry-schema.md."""
    schema_doc = _PLUGIN_DIR / "knowledge" / "telemetry-schema.md"
    schema_text = schema_doc.read_text(encoding="utf-8")

    pattern = re.compile(r"metrics/([A-Za-z0-9_.{}-]+\.(?:jsonl|json))")
    found: set[str] = set()
    search_dirs = ["hooks", "skills", "agents", "knowledge"]
    for sub in search_dirs:
        root = _PLUGIN_DIR / sub
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            if path.suffix not in (".py", ".md", ".json"):
                continue
            if path == schema_doc:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in pattern.finditer(text):
                found.add(match.group(1))

    # Dated task-log files (metrics/2026-02-20-task-log.jsonl, etc.) are one
    # family — normalize any concrete date-stamped name to the documented
    # placeholder form.
    normalized = set()
    date_stamped = re.compile(r"^\d{4}-\d{2}-\d{2}-task-log\.jsonl$")
    for name in found:
        if date_stamped.match(name):
            normalized.add("{date}-task-log.jsonl")
        else:
            normalized.add(name)

    missing = [name for name in sorted(normalized) if name not in schema_text]
    assert not missing, (
        "knowledge/telemetry-schema.md is missing coverage for: "
        f"{missing} — add a section documenting each stream's schema."
    )


def test_schema_doc_documents_boundary_events_fields() -> None:
    schema_doc = _PLUGIN_DIR / "knowledge" / "telemetry-schema.md"
    text = schema_doc.read_text(encoding="utf-8")
    assert "boundary-events.jsonl" in text
    for field in _SCHEMA_FIELDS | _OPTIONAL_FIELDS:
        assert field in text, f"telemetry-schema.md missing field `{field}`"
    for decision in _DECISION_ENUM:
        assert decision in text
