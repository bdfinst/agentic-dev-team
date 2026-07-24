"""Pytest tests for hooks/token_efficiency_review.py (#607 / #572 Phase 3).

Behavioral: given a Write/Edit PostToolUse payload naming a real file,
the hook emits advisory warnings on stdout when any of these hold:
  - The file is CLAUDE.md and > 5000 chars
  - The file is a recognized source type (.js/.ts/.jsx/.tsx/.py/.rb/.go/
    .rs/.java/.cs) and > 500 lines
  - A function inside a recognized source file exceeds 50 lines

Never blocks (exit 0 always). Missing file → silent. Missing path → silent.
Malformed JSON → silent.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "token_efficiency_review.py"


def _run(stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HOOK_PY)],
        input=stdin,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
        capture_output=True,
        timeout=10,
        check=False,
    )


def _payload(path: Path) -> bytes:
    return json.dumps({"tool_input": {"file_path": str(path)}}).encode()


def test_missing_stdin_is_silent() -> None:
    r = _run(b"")
    assert r.returncode == 0
    assert r.stdout == b""


def test_malformed_json_is_silent() -> None:
    r = _run(b"{broken")
    assert r.returncode == 0
    assert r.stdout == b""


def test_missing_path_is_silent() -> None:
    r = _run(b'{"tool_input":{}}')
    assert r.returncode == 0
    assert r.stdout == b""


def test_nonexistent_path_is_silent(tmp_path: Path) -> None:
    r = _run(_payload(tmp_path / "nope.js"))
    assert r.returncode == 0
    assert r.stdout == b""


def test_claude_md_over_limit_warns(tmp_path: Path) -> None:
    big = tmp_path / "CLAUDE.md"
    big.write_text("x" * 6000)
    r = _run(_payload(big))
    assert r.returncode == 0
    assert b"CLAUDE.md is 6000 chars" in r.stdout
    assert b"limit: 5000" in r.stdout


def test_claude_md_under_limit_silent(tmp_path: Path) -> None:
    small = tmp_path / "CLAUDE.md"
    small.write_text("x" * 100)
    r = _run(_payload(small))
    assert r.returncode == 0
    assert r.stdout == b""


def test_long_source_file_warns(tmp_path: Path) -> None:
    long_js = tmp_path / "long.js"
    long_js.write_text("\n".join(f"// line {i}" for i in range(600)))
    r = _run(_payload(long_js))
    assert r.returncode == 0
    assert b"File is 600 lines" in r.stdout


def test_short_source_file_silent(tmp_path: Path) -> None:
    small = tmp_path / "small.js"
    small.write_text("const x = 1;\n")
    r = _run(_payload(small))
    assert r.returncode == 0
    assert r.stdout == b""


def test_long_function_warns(tmp_path: Path) -> None:
    src = tmp_path / "longfn.js"
    body = "\n".join(f"  console.log({i});" for i in range(60))
    src.write_text(f"function bigOne() {{\n{body}\n}}\n")
    r = _run(_payload(src))
    assert r.returncode == 0
    assert b"Long functions detected" in r.stdout
    assert b"bigOne" in r.stdout


def test_non_source_extension_ignored_for_length(tmp_path: Path) -> None:
    """A .md file (that isn't CLAUDE.md) doesn't get length-checked."""
    md = tmp_path / "notes.md"
    md.write_text("\n".join(f"line {i}" for i in range(600)))
    r = _run(_payload(md))
    assert r.returncode == 0
    assert r.stdout == b""


def test_alt_path_field_names(tmp_path: Path) -> None:
    """The hook accepts .tool_input.path, .file_path, or .path as fallback."""
    big = tmp_path / "CLAUDE.md"
    big.write_text("x" * 6000)
    for shape in (
        {"tool_input": {"path": str(big)}},
        {"file_path": str(big)},
        {"path": str(big)},
    ):
        r = _run(json.dumps(shape).encode())
        assert r.returncode == 0
        assert b"CLAUDE.md is 6000 chars" in r.stdout, f"failed for {shape}"
