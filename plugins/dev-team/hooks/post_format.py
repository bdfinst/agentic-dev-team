#!/usr/bin/env python3
"""post_format.py — Claude Code PostToolUse hook (Python port of post-format.sh).

Runs after Write and Edit tool calls. Auto-formats the changed file using the
appropriate formatter for the detected language. All formatter invocations are
best-effort — any failure is swallowed and the hook exits 0.

Input : JSON on stdin with `tool_input.file_path`.
Output: silent on success (all formatters redirect stdout/stderr to devnull);
        exits 0 even when a formatter is missing or fails.

Ported per docs/python-hook-contract.md — stdlib-only,.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _run(argv: list[str]) -> None:
    """Best-effort formatter invocation — swallow all errors, discard output."""
    try:
        subprocess.run(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except (FileNotFoundError, OSError):
        # command not on PATH — bash `command -v` guards it, we just skip
        pass


def _extract_file_path(raw: str) -> str | None:
    """Return `tool_input.file_path` from the JSON stdin, or None."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path or not isinstance(file_path, str):
        return None
    return file_path


_JS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def format_file(file_path: str) -> None:
    """Dispatch to the formatter that matches `file_path`'s extension."""
    suffix = Path(file_path).suffix.lower()

    if suffix in _JS_SUFFIXES:
        if shutil.which("npx"):
            _run(["npx", "prettier", "--write", file_path])
            _run(["npx", "eslint", "--fix", file_path])
        return

    if suffix == ".py":
        if shutil.which("ruff"):
            _run(["ruff", "format", file_path])
            _run(["ruff", "check", "--fix", file_path])
        elif shutil.which("black"):
            _run(["black", file_path])
        return

    if suffix == ".go":
        if shutil.which("gofmt"):
            _run(["gofmt", "-w", file_path])
        return

    if suffix == ".rs":
        if shutil.which("rustfmt"):
            _run(["rustfmt", file_path])
        return

    if suffix == ".rb":
        if shutil.which("bundle"):
            _run(["bundle", "exec", "rubocop", "-A", file_path])
        return

    if suffix == ".java":
        if shutil.which("google-java-format"):
            _run(["google-java-format", "-i", file_path])
        return

    if suffix == ".kt":
        if shutil.which("ktlint"):
            _run(["ktlint", "-F", file_path])
        return

    if suffix == ".cs":
        if shutil.which("dotnet"):
            _run(["dotnet", "format", "--include", file_path])
        return


def main() -> int:
    raw = sys.stdin.read()
    file_path = _extract_file_path(raw)
    if not file_path:
        return 0
    if not Path(file_path).is_file():
        return 0
    format_file(file_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
