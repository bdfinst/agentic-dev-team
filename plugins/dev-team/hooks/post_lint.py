#!/usr/bin/env python3
"""post_lint.py — opt-in PostToolUse hook: lint an edited JS/TS file with the
dev-team ESLint config and feed findings back to the agent.

Off unless ``DEVTEAM_POST_LINT=1``. Runs the project's own ESLint (9.x or
10.x) against the one edited file with the scaffolded
``eslint.devteam.config.js`` only, reads ``--format json`` and ignores the
exit code (the shipped rules are ``warn``, so a finding never changes it).
The hook only reports; it never passes ``--fix``.

Contract (docs/python-hook-contract.md, docs/post-edit-lint-hook.md):
    Input : PostToolUse JSON on stdin (tool_name, session_id, cwd,
            tool_input.file_path)
    Output: JSON on stdout — ``{"decision": "block", "reason": ...}`` for
            findings, ``{"systemMessage": ...}`` for a one-line notice, or
            nothing
    Exit  : 0 always. Every failure to lint fails open and says why once per
            session per reason.

Stdlib-only. See ADR 0014.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths  # type: ignore[import-not-found]
from atomic_state import (  # type: ignore[import-not-found]
    append_line_locked,
    atomic_write,
    locked_state,
)
from stdin_json import read_stdin_json  # type: ignore[import-not-found]

ENV_ENABLE = "DEVTEAM_POST_LINT"
ENV_TIMEOUT = "DEVTEAM_POST_LINT_TIMEOUT"
ENV_TYPED = "DEVTEAM_LINT_TYPED"
CONFIG_NAME = "eslint.devteam.config.js"
DEFAULT_TIMEOUT_SECONDS = 10.0
# One line per run: .claude/metrics/post-lint.jsonl
METRICS_FILE = "post-lint.jsonl"

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})
LINT_SUFFIXES = frozenset(
    {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
)

# Outcomes recorded per run.
SKIPPED = "skipped"
CLEAN = "clean"
BLOCKED = "blocked"
CAPPED = "capped"
FAILED_OPEN = "failed-open"

# What a block reason shows: the header, at most MAX_FINDINGS findings, then
# `+N more`, all within MAX_REASON_CHARS.
REASON_HEADER = "dev-team post-edit lint (set DEVTEAM_POST_LINT=0 to disable):"
MAX_FINDINGS = 10
MAX_REASON_CHARS = 4000
MAX_BLOCKS = 3
TRUNCATION_MARKER = "... [truncated]"

# ESLint reports a disable comment that names a rule it did not load (for
# example `functional/*` while typed rules are off) as an error carrying that
# rule's id. It says the comment is stale, not that the code breaks a rule.
UNLOADED_RULE_MESSAGE = re.compile(r"Definition for rule '.*' was not found\.")

# One line per fail-open reason; `{}` is filled by the one reason that varies.
NOTICES = {
    "no-config": f"{CONFIG_NAME} not found in project; lint skipped",
    "no-eslint": "ESLint not found in project; lint skipped",
    "no-node": "node not found on PATH; lint skipped",
    "timeout": "ESLint timed out after {}s; lint skipped",
    "no-json": "ESLint exited with code {} and no JSON; lint skipped",
    "invalid-json": "ESLint output was not valid JSON; lint skipped",
    "invalid-stdin": "hook input was not valid JSON; lint skipped",
    "parse-error": "edited file has a parse error; lint skipped",
    "no-state": "cannot save session state; lint skipped",
    "cap": f"cap {MAX_BLOCKS} reached; set DEVTEAM_POST_LINT=0 to disable",
}


class LintFailure(Exception):
    """ESLint could not produce findings; carries the fail-open reason key."""

    def __init__(self, key: str, detail: object = "") -> None:
        super().__init__(key)
        self.key = key
        self.detail = detail


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule_id: str
    message: str


@dataclass(frozen=True)
class Result:
    outcome: str
    output: dict | None = None
    ext: str = ""


# --- pure helpers -----------------------------------------------------------


def should_lint(payload: dict, root: Path) -> Path | None:
    """The resolved file to lint, or None for a normal (silent) skip.

    Skips non-edit tools, non-JS/TS suffixes, files that do not exist, files
    outside the project (symlinks are resolved first), and anything under
    ``node_modules``.
    """
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    declared = Path(raw) if Path(raw).is_absolute() else root / raw
    if declared.suffix.lower() not in LINT_SUFFIXES:
        return None
    try:
        resolved = declared.resolve()
        relative = resolved.relative_to(root.resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    if "node_modules" in relative.parts or "node_modules" in declared.parts:
        return None
    return resolved if resolved.is_file() else None


def build_command(node: str, eslint_js: Path, config: Path, target: Path) -> list[str]:
    """``node <eslint.js> --config <config> --format json <file>``; never the
    ``.bin`` shim, which is a ``.cmd`` wrapper on Windows."""
    return [
        node,
        str(eslint_js),
        "--config",
        str(config),
        "--format",
        "json",
        str(target),
    ]


def parse_findings(stdout: str, returncode: int, root: Path) -> list[Finding]:
    """Findings from ESLint's JSON, ignoring the exit code when JSON is valid.

    Raises LintFailure for empty output, invalid JSON, or a parse error in the
    edited file. Messages without a rule id (for example an unused
    ``eslint-disable`` report) and "Definition for rule 'X' was not found"
    messages (a disable comment for a rule that is not loaded) are not
    dev-team findings and are dropped.
    """
    if not stdout.strip():
        raise LintFailure("no-json", returncode)
    try:
        results = json.loads(stdout)
    except json.JSONDecodeError:
        raise LintFailure("invalid-json") from None
    if not isinstance(results, list):
        raise LintFailure("invalid-json")
    findings: list[Finding] = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("messages"), list):
            raise LintFailure("invalid-json")
        path = _display_path(result.get("filePath"), root)
        for message in result["messages"]:
            if not isinstance(message, dict):
                raise LintFailure("invalid-json")
            if message.get("fatal"):
                raise LintFailure("parse-error")
            rule_id = message.get("ruleId")
            if (
                isinstance(rule_id, str)
                and rule_id
                and not UNLOADED_RULE_MESSAGE.fullmatch(str(message.get("message", "")))
            ):
                findings.append(
                    Finding(
                        path,
                        message["line"] if isinstance(message.get("line"), int) else 0,
                        rule_id,
                        " ".join(str(message.get("message", "")).split()),
                    )
                )
    return findings


def _display_path(file_path: object, root: Path) -> str:
    if not isinstance(file_path, str) or not file_path:
        return "?"
    try:
        return Path(file_path).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return Path(file_path).as_posix()


def format_reason(findings: list[Finding]) -> str:
    """The block reason: one `path:line rule-id message` line per finding."""
    lines = [
        REASON_HEADER,
        *(
            f"{f.path}:{f.line} {f.rule_id} {f.message}"
            for f in findings[:MAX_FINDINGS]
        ),
    ]
    if len(findings) > MAX_FINDINGS:
        lines.append(f"+{len(findings) - MAX_FINDINGS} more")
    text = "\n".join(lines)
    if len(text) <= MAX_REASON_CHARS:
        return text
    return text[: MAX_REASON_CHARS - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


def timeout_seconds(env: Mapping[str, str]) -> float:
    try:
        value = float(env.get(ENV_TIMEOUT, ""))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


# --- per-session state (notice-once) ----------------------------------------


def default_state_dir(env: Mapping[str, str]) -> Path:
    return Path(env.get("TMPDIR") or tempfile.gettempdir()) / "dev-team-post-lint"


def state_path(session: str, state_dir: Path) -> Path:
    digest = sha256(session.encode("utf-8", errors="replace")).hexdigest()[:16]
    return state_dir / f"{digest}.json"


def _read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _update_state(session: str, state_dir: Path, mutate) -> object:
    """Run ``mutate(state)`` on the session's state under the lock and save it.
    Raises OSError when the state cannot be read-modify-written."""
    path = state_path(session, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_state(path):
        state = _read_state(path)
        result = mutate(state)
        atomic_write(path, json.dumps(state, separators=(",", ":")), fail_open=False)
    return result


def notice_once(session: str, key: str, text: str, state_dir: Path) -> dict | None:
    """``{"systemMessage": ...}`` the first time ``key`` fires in ``session``."""

    def mark(state: dict) -> bool:
        seen = state.get("notices")
        seen = seen if isinstance(seen, list) else []
        if key in seen:
            return False
        state["notices"] = [*seen, key]
        return True

    try:
        if not _update_state(session, state_dir, mark):
            return None
    except OSError:
        pass  # cannot persist: say it rather than stay silent
    return {"systemMessage": f"post_lint: {text}"}


def try_block(session: str, state_dir: Path) -> bool:
    """Count one more consecutive block; False once MAX_BLOCKS were used.
    Raises OSError when the count cannot be saved."""

    def count(state: dict) -> bool:
        blocks = state.get("blocks")
        blocks = blocks if isinstance(blocks, int) else 0
        if blocks >= MAX_BLOCKS:
            return False
        state["blocks"] = blocks + 1
        return True

    return bool(_update_state(session, state_dir, count))


def reset_blocks(session: str, state_dir: Path) -> None:
    """A clean lint ends the run of consecutive blocks."""
    if _read_state(state_path(session, state_dir)).get("blocks"):
        try:
            _update_state(session, state_dir, lambda state: state.pop("blocks", None))
        except OSError:
            pass


# --- running ESLint ---------------------------------------------------------


def run_eslint(
    cmd: list[str], cwd: Path, env: Mapping[str, str], timeout: float
) -> tuple[str, int]:
    """Run ``cmd`` and return (stdout, returncode). On timeout the whole
    process group is killed and LintFailure("timeout") is raised."""
    child_env = {**env, ENV_TYPED: "0"}
    posix = os.name == "posix"
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=posix,
        )
    except OSError:
        raise LintFailure("no-node") from None
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise LintFailure("timeout", f"{timeout:g}") from None
    return stdout, proc.returncode


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (OSError, ProcessLookupError):
        pass


# --- the hook ---------------------------------------------------------------


def _notice(
    session: str, key: str, state_dir: Path, detail: object = ""
) -> dict | None:
    return notice_once(session, key, NOTICES[key].format(detail), state_dir)


def _fail_open(session: str, failure: LintFailure, ext: str, state_dir: Path) -> Result:
    notice = _notice(session, failure.key, state_dir, failure.detail)
    return Result(FAILED_OPEN, notice, ext)


def evaluate(
    payload: dict | None, env: Mapping[str, str], state_dir: Path | None = None
) -> Result:
    """One hook run: decide, then append its metrics line."""
    started = time.monotonic()
    session = str((payload or {}).get("session_id") or "unknown")
    cwd = (payload or {}).get("cwd")
    start = cwd if isinstance(cwd, str) and Path(cwd).is_dir() else os.getcwd()
    root = artifact_paths.project_root(start)
    result = _decide(payload, env, state_dir or default_state_dir(env), session, root)
    wall_ms = round((time.monotonic() - started) * 1000)
    record_metrics(root, session, result, wall_ms)
    return result


def record_metrics(root: Path, session: str, result: Result, wall_ms: int) -> None:
    """Append `{ts, session, ext, wall_ms, outcome}` to the metrics stream."""
    row = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": session,
        "ext": result.ext,
        "wall_ms": wall_ms,
        "outcome": result.outcome,
    }
    try:
        path = artifact_paths.metrics_dir(root) / METRICS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        append_line_locked(path, json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        pass  # metrics are best-effort


def _decide(
    payload: dict | None,
    env: Mapping[str, str],
    state_dir: Path,
    session: str,
    root: Path,
) -> Result:
    if payload is None:
        return _fail_open(session, LintFailure("invalid-stdin"), "", state_dir)

    target = should_lint(payload, root)
    ext = Path(target).suffix.lower() if target else _declared_ext(payload)
    if target is None:
        return Result(SKIPPED, None, ext)

    config = root / CONFIG_NAME
    eslint_js = root / "node_modules" / "eslint" / "bin" / "eslint.js"
    node = shutil.which("node", path=env.get("PATH"))
    for key, present in (
        ("no-config", config.is_file()),
        ("no-eslint", eslint_js.is_file()),
        ("no-node", node is not None),
    ):
        if not present:
            return _fail_open(session, LintFailure(key), ext, state_dir)

    try:
        stdout, code = run_eslint(
            build_command(str(node), eslint_js, config, target),
            root,
            env,
            timeout_seconds(env),
        )
        findings = parse_findings(stdout, code, root)
    except LintFailure as failure:
        return _fail_open(session, failure, ext, state_dir)
    if not findings:
        reset_blocks(session, state_dir)
        return Result(CLEAN, None, ext)
    try:
        allowed = try_block(session, state_dir)
    except OSError:
        return _fail_open(session, LintFailure("no-state"), ext, state_dir)
    if not allowed:
        return Result(CAPPED, _notice(session, "cap", state_dir), ext)
    block = {"decision": "block", "reason": format_reason(findings)}
    return Result(BLOCKED, block, ext)


def _declared_ext(payload: dict) -> str:
    tool_input = payload.get("tool_input")
    raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    return Path(raw).suffix.lower() if isinstance(raw, str) else ""


def main() -> int:
    env = dict(os.environ)
    if env.get(ENV_ENABLE) != "1":
        return 0
    try:
        result = evaluate(read_stdin_json(), env)
    except Exception:  # noqa: BLE001 - a lint hook must never break an edit
        return 0
    if result.output:
        sys.stdout.write(json.dumps(result.output) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
