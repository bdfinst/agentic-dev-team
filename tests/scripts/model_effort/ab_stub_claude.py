"""A stand-in `claude` binary for the A/B harness tests, and builders for the stream-json it prints."""

from __future__ import annotations

import json
from pathlib import Path

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)
from ab_constants import HAIKU_MODEL_ID, TRANSCRIPT_FIXTURES, TRIAL_COST


def flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


STUB_TEMPLATE = """#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
from pathlib import Path

RECORD = Path(__RECORD__)
QUEUE = Path(__QUEUE__)
BEHAVIOR = json.loads(__BEHAVIOR__)
if QUEUE.exists():
    queued = json.loads(QUEUE.read_text())
    if queued:
        BEHAVIOR = {**BEHAVIOR, **queued.pop(0)}
        QUEUE.write_text(json.dumps(queued))
cwd = Path(os.getcwd())
files_before = {
    str(p.relative_to(cwd)): p.read_text()
    for p in sorted(cwd.rglob("*"))
    if p.is_file() and ".git" not in p.parts
}
symlinks = [str(p.relative_to(cwd)) for p in sorted(cwd.rglob("*")) if p.is_symlink()]
observed = None
if BEHAVIOR.get("observe"):
    target = Path(BEHAVIOR["observe"])
    observed = {
        "exists": target.exists(),
        "size": target.stat().st_size if target.exists() else None,
    }
calls = json.loads(RECORD.read_text()) if RECORD.exists() else []
calls.append({
    "pid": os.getpid(),
    # Wall-clock seconds, comparable with the test's own clock: a timing bound
    # counts from here, not from before a slow interpreter start.
    "started_at": time.time(),
    "argv": sys.argv[1:],
    "cwd": str(cwd),
    "files_before": files_before,
    "symlinks": symlinks,
    "env_names": sorted(os.environ),
    "blocked_signals": sorted(
        s.name for s in signal.pthread_sigmask(signal.SIG_BLOCK, [])
    ),
    "observed": observed,
    "git_dirs": sorted(str(p.relative_to(cwd)) for p in cwd.rglob(".git")),
    "tmpdir": os.environ.get("TMPDIR"),
    "home": os.environ.get("HOME"),
    "stdin": "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read(),
})
RECORD.write_text(json.dumps(calls))
if BEHAVIOR.get("tamper"):
    for p in cwd.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            p.write_text(p.read_text() + "TAMPERED")
if BEHAVIOR.get("touch"):
    Path(BEHAVIOR["touch"]).write_text("created during the run")
if BEHAVIOR.get("lock_subdir"):
    locked = cwd / "locked"
    locked.mkdir()
    (locked / "inner.txt").write_text("x")
    locked.chmod(0o500)
if BEHAVIOR.get("grandchild_marker"):
    # The grandchild touches the spawned file itself as it starts sleeping, so its
    # mtime marks when the delay began, however slowly the interpreter started.
    code = (
        "import pathlib, time; pathlib.Path(%r).write_text('spawned'); "
        "time.sleep(%s); pathlib.Path(%r).write_text('late')"
    ) % (
        BEHAVIOR["grandchild_spawned"],
        BEHAVIOR["grandchild_delay"],
        BEHAVIOR["grandchild_marker"],
    )
    subprocess.Popen([sys.executable, "-c", code])
if BEHAVIOR.get("detached_sleep"):
    # Stays in the CLI's process group but lets go of its pipes, so the CLI's exit
    # ends the wait at once and only an explicit group kill stops it.
    detached = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%s)" % BEHAVIOR["detached_sleep"]],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    Path(BEHAVIOR["detached_pid_file"]).write_text(str(detached.pid))
if BEHAVIOR.get("holder_sleep"):
    # Inherits stdout and stderr, so it keeps both pipes open after this process exits.
    holder = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%s)" % BEHAVIOR["holder_sleep"]],
        start_new_session=bool(BEHAVIOR.get("holder_new_session")),
    )
    if BEHAVIOR.get("holder_pid_file"):
        Path(BEHAVIOR["holder_pid_file"]).write_text(str(holder.pid))
if BEHAVIOR.get("stdout_hex"):
    sys.stdout.buffer.write(bytes.fromhex(BEHAVIOR["stdout_hex"]))
    sys.stdout.flush()
if BEHAVIOR.get("early_stdout") or BEHAVIOR.get("early_stderr"):
    # Written and flushed before any sleep, so a killed process has left it behind.
    sys.stdout.write(BEHAVIOR.get("early_stdout", ""))
    sys.stderr.write(BEHAVIOR.get("early_stderr", ""))
    sys.stdout.flush()
    sys.stderr.flush()
time.sleep(BEHAVIOR.get("sleep", 0))
sys.stdout.write(BEHAVIOR.get("stdout", ""))
sys.stderr.write(BEHAVIOR.get("stderr", ""))
if BEHAVIOR.get("stderr_cwd"):
    sys.stderr.write("cannot read " + str(cwd) + "/form.html")
sys.exit(BEHAVIOR.get("exit_code", 0))
"""


class StubClaude:
    """A stand-in `claude` executable that records every invocation."""

    def __init__(self, directory: Path, **behavior):
        self.path = directory / "claude-stub"
        self._record = directory / "calls.json"
        self._queue = directory / "queue.json"
        self.path.write_text(
            STUB_TEMPLATE.replace("__RECORD__", repr(str(self._record)))
            .replace("__QUEUE__", repr(str(self._queue)))
            .replace("__BEHAVIOR__", repr(json.dumps(behavior))),
            encoding="utf-8",
        )
        self.path.chmod(0o755)

    def queue(self, *per_call_behaviors: dict) -> None:
        """Make call N use the Nth behavior (merged over the defaults); later calls use the defaults."""
        self._queue.write_text(json.dumps(list(per_call_behaviors)), encoding="utf-8")

    @property
    def calls(self) -> list[dict]:
        if not self._record.exists():
            return []
        return json.loads(self._record.read_text(encoding="utf-8"))


def fixture_text(filename: str) -> str:
    return (TRANSCRIPT_FIXTURES / filename).read_text(encoding="utf-8")


def stream_of(*events: dict | str) -> str:
    return "\n".join(e if isinstance(e, str) else json.dumps(e) for e in events)


def result_event(text="ok", model_usage=None, **fields) -> dict:
    usage = {HAIKU_MODEL_ID: {}} if model_usage is None else model_usage
    return {
        "type": "result",
        "result": text,
        "is_error": False,
        "total_cost_usd": TRIAL_COST,
        "modelUsage": usage,
        **fields,
    }


def tool_use_event(*names: str) -> dict:
    blocks = [{"type": "tool_use", "name": n, "input": {}} for n in names]
    return {"type": "assistant", "message": {"content": blocks}}


def init_event(model_id: str = HAIKU_MODEL_ID, **fields) -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "cwd": "/private/var/folders/XX/T/model-effort-ab-abc123",
        "session_id": "11111111-1111-1111-1111-111111111111",
        "model": model_id,
        "permissionMode": "default",
        "tools": ["Read", "Grep"],
        "mcp_servers": [],
        "plugins": [{"name": "builtin-a", "path": "/home/someone/.claude/plugins/a"}],
        **fields,
    }


def expected_session_config(model_id: str) -> dict:
    return {
        "model": model_id,
        "permissionMode": "default",
        "tools": ["Read", "Grep"],
        "mcp_servers": [],
        "plugins": ["builtin-a"],
        "cwd": "<staged>",
    }


def verdict_call(
    verdict: dict, model_id: str, *tool_names: str, cost: float = TRIAL_COST
) -> dict:
    events = [tool_use_event(*tool_names)] if tool_names else []
    result = result_event(
        json.dumps(verdict), model_usage={model_id: {}}, total_cost_usd=cost
    )
    return {"stdout": stream_of(init_event(model_id), *events, result)}
