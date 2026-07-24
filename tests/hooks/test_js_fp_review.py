"""Pytest tests for hooks/js_fp_review.py.

Drives main() via subprocess with representative PostToolUse JSON
payloads (Write/Edit on a JS/TS file). The hook is advisory-only — it
never blocks (always exits 0) — so "should be blocked" here means the
warning text is emitted on stdout for a mutation-pattern file, and
"should pass through" means stdout is empty for a clean file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "js_fp_review.py"


def _run(payload: dict) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
    }
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=json.dumps(payload).encode(),
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )


def test_array_mutation_warns(tmp_path: Path) -> None:
    """A file with an in-place array mutation must produce an advisory
    warning on stdout, but the hook always exits 0 (advisory, non-blocking)."""
    js_file = tmp_path / "widget.js"
    js_file.write_text("function addItem(list, item) {\n  list.push(item);\n}\n")

    r = _run({"tool_input": {"file_path": str(js_file)}})

    assert r.returncode == 0
    assert b"FP: Array mutation detected" in r.stdout
    assert b"list.push" in r.stdout


def test_clean_file_passes_through(tmp_path: Path) -> None:
    """A file with no mutation patterns must produce no output."""
    js_file = tmp_path / "widget.js"
    js_file.write_text("function addItem(list, item) {\n  return [...list, item];\n}\n")

    r = _run({"tool_input": {"file_path": str(js_file)}})

    assert r.returncode == 0
    assert r.stdout == b""


def test_non_js_file_skipped(tmp_path: Path) -> None:
    """Non JS/TS files are ignored entirely, even with mutation patterns."""
    py_file = tmp_path / "widget.py"
    py_file.write_text("list.push(item)\n")

    r = _run({"tool_input": {"file_path": str(py_file)}})

    assert r.returncode == 0
    assert r.stdout == b""


def test_missing_file_path_silent() -> None:
    r = _run({"tool_input": {}})
    assert r.returncode == 0
    assert r.stdout == b""


def test_nonexistent_file_silent(tmp_path: Path) -> None:
    missing = tmp_path / "ghost.ts"
    r = _run({"tool_input": {"file_path": str(missing)}})
    assert r.returncode == 0
    assert r.stdout == b""


def test_malformed_stdin_silent() -> None:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    r = subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=b"{broken",
        env=env,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout == b""
