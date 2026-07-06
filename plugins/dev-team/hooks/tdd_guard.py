#!/usr/bin/env python3
"""tdd_guard.py — PostToolUse advisory hook (Python port of tdd-guard.sh).

Tracks RED-GREEN-REFACTOR state and warns when implementation code is
written without a preceding test file edit in the same session. State is
tracked in a temp file per project (`$TMPDIR/tdd-guard/session-<hash>`),
purged after 4 hours.

Advisory-only: always exits 0. Message on stdout follows the bash format
byte-for-byte so consumers grepping the output keep working.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from boundary_events import emit_boundary_event as _emit_boundary_event  # noqa: E402


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001 - fail-open by design
        pass


_SOURCE_SUFFIXES = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".svelte",
    ".vue",
}

_TEST_SUFFIX_RE = re.compile(r"\.(test|spec)\.[^./]+$|_(test|spec)\.[^./]+$")
_TEST_DIR_FRAGMENTS = ("/test/", "/tests/", "/__tests__/", "/spec/")
_TEST_CONTENT_RE = re.compile(
    r"describe\(|it\(|test\(|expect\(|assert[A-Z]|def test_|func Test|"
    r"#\[test\]|#\[cfg\(test\)\]|\[Fact\]|\[Theory\]"
)

_STATE_TTL_SECONDS = 240 * 60  # 4 hours
_GREEN_PHASE_WINDOW_SECONDS = 300  # grace period after a test edit (RED->GREEN)


def _extract_file_path(raw: str) -> str:
    """Return `.tool_input.file_path // .tool_input.path // .file_path // .path`."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input") or {}
    for source in (
        tool_input.get("file_path"),
        tool_input.get("path"),
        payload.get("file_path"),
        payload.get("path"),
    ):
        if isinstance(source, str) and source:
            return source
    return ""


def _is_source_file(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in _SOURCE_SUFFIXES


def _is_excluded_dir(path: str) -> bool:
    lowered = path
    for frag in ("/node_modules/", "/dist/", "/build/", "/.next/", "/coverage/"):
        if frag in lowered:
            return True
    return False


def is_test_file(path: str) -> bool:
    """True when `path` looks like a test file by name, directory, or content."""
    lowered = path
    if _TEST_SUFFIX_RE.search(lowered):
        return True
    if any(frag in lowered for frag in _TEST_DIR_FRAGMENTS):
        return True
    if lowered.endswith(".feature"):
        return True
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for _ in range(30):
                line = handle.readline()
                if not line:
                    break
                if _TEST_CONTENT_RE.search(line):
                    return True
    except OSError:
        return False
    return False


def _state_dir() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "tdd-guard"


def _state_file(cwd: Optional[Path] = None) -> Path:
    base = str(cwd if cwd is not None else Path.cwd())
    # bash uses `echo "$PWD" | md5sum` which appends a trailing newline before
    # hashing; hash the same byte sequence so the state file lives at the same
    # path in both implementations.
    digest = hashlib.md5((base + "\n").encode("utf-8")).hexdigest()[:12]
    return _state_dir() / f"session-{digest}"


def _purge_stale(state_dir: Path) -> None:
    if not state_dir.is_dir():
        return
    now = time.time()
    for path in state_dir.glob("session-*"):
        try:
            if now - path.stat().st_mtime > _STATE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass


def _read_state(state_file: Path) -> Tuple[str, int]:
    if not state_file.is_file():
        return "", 0
    try:
        raw = state_file.read_text()
    except OSError:
        return "", 0
    lines = raw.splitlines()
    if not lines:
        return "", 0
    last_edit = lines[0]
    try:
        last_time = int(lines[-1])
    except (ValueError, IndexError):
        last_time = 0
    return last_edit, last_time


def _write_state(state_file: Path, file_path: str, now: int) -> None:
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    try:
        state_file.write_text(f"{file_path}\n{now}\n")
    except OSError:
        pass


def main() -> int:
    raw = sys.stdin.read()
    file_path = _extract_file_path(raw)
    if not file_path:
        return 0
    try:
        _payload = json.loads(raw)
    except (TypeError, ValueError):
        _payload = {}
    cwd = (_payload.get("cwd") if isinstance(_payload, dict) else None) or "."
    session_id = _payload.get("session_id") if isinstance(_payload, dict) else None
    if not Path(file_path).is_file():
        return 0
    if not _is_source_file(file_path):
        return 0
    if _is_excluded_dir(file_path):
        return 0

    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _purge_stale(state_dir)
    state_file = _state_file()

    last_edit, last_time = _read_state(state_file)
    now = int(time.time())

    if is_test_file(file_path):
        _write_state(state_file, file_path, now)
        return 0

    elapsed = now - last_time
    if elapsed < _GREEN_PHASE_WINDOW_SECONDS and last_edit:
        # Recent test edit — GREEN phase is fine.
        return 0

    basename = os.path.basename(file_path)
    print("")
    print("  TDD: Implementation file edited without a recent test edit.")
    print(f"  File: {basename}")
    print("  Write a failing test FIRST, then implement. RED before GREEN.")
    print("  If this is a refactor with passing tests, run the test suite to confirm.")
    emit_boundary_event(cwd, "tdd_guard", "Write", "warn", "tdd-red-before-green", session_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
