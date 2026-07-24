#!/usr/bin/env python3
"""knowledge_index — Claude Code PostToolUse hook (Python port).

Python port of hooks/knowledge-index.sh (#580 / #572 Cluster A dependent).

When an Edit or Write touches a file in the indexed corpus
(knowledge/*.md or skills/*/SKILL.md, excluding knowledge/schemas/),
regenerate plugins/dev-team/knowledge/index.json by shelling out to the
builder (default: hooks/lib/build-knowledge-index.sh, itself a thin
wrapper over build_knowledge_index.py).

Contract (docs/python-hook-contract.md):
    Input : PostToolUse JSON on stdin
    Output: stderr feedback when the corpus is touched; otherwise silent
    Exit  : always 0 (fail-open — never blocks an Edit)

Env seams (TEST-ONLY):
    KNOWLEDGE_INDEX_BUILDER  override the builder path

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

# Import the shared corpus predicate from the ported Cluster A lib (#575).
sys.path.insert(0, str(_LIB_DIR))
try:
    from knowledge_index_paths import is_corpus_path  # type: ignore[import-not-found]
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    # Fail-open: if the shared lib is missing (should never happen in a
    # correctly installed plugin), treat every path as non-corpus and
    # exit silently.
    def is_corpus_path(_: str) -> bool:  # type: ignore[misc]
        return False

    def read_stdin_json():  # type: ignore[misc]
        return None


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        # Malformed/empty input — fail-open.
        return 0

    tool_name = str(payload.get("tool_name") or "")
    if tool_name not in ("Edit", "Write"):
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    file_path = str(tool_input.get("file_path") or "")
    if not file_path:
        return 0
    if not is_corpus_path(file_path):
        return 0

    builder = os.environ.get(
        "KNOWLEDGE_INDEX_BUILDER",
        str(_LIB_DIR / "build_knowledge_index.py"),
    )

    # Dispatch on filename extension so tests can inject a bash fake via
    # KNOWLEDGE_INDEX_BUILDER=/path/to/fake-builder.sh, while production uses
    # the Python builder directly.
    argv = [sys.executable, builder] if builder.endswith(".py") else ["bash", builder]

    # Rebuild. Capture stderr so we can summarize on failure.
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        print(f"[knowledge-index] rebuild failed: {exc}", file=sys.stderr)
        return 0

    if completed.returncode == 0:
        print("[knowledge-index] rebuilt", file=sys.stderr)
    else:
        stderr_text = (completed.stderr or b"").decode("utf-8", errors="replace")
        first_line = stderr_text.splitlines()[0] if stderr_text.strip() else "unknown"
        print(f"[knowledge-index] rebuild failed: {first_line}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open by design; absolute
        # fail-open guarantee — this hook must never block on an
        # unexpected error.
        sys.exit(0)
