#!/usr/bin/env python3
"""SessionStart hook (registered in .claude/settings.json): if CodeGraph,
Repowise, or Graphify are already installed but this checkout has never
been indexed (e.g. a freshly created worktree, or a fresh clone on a
machine that already has the CLIs globally installed), build the keyless
index automatically. This never installs a missing CLI — that stays an
explicit /project-init or /setup opt-in, per
knowledge/codegraph-vs-graphify.md ("None is guaranteed to be present").

Fail-open and time-boxed — never blocks session start. Stdlib-only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_CACHE_DIR = Path.home() / ".cache"


def _run(cmd: list[str], cwd: Path, log_path: Path, timeout: int) -> bool:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _ensure_codegraph(root: Path, notes: list[str]) -> None:
    if shutil.which("codegraph") is None or (root / ".codegraph").is_dir():
        return
    log_path = _CACHE_DIR / "codegraph-sessionstart.log"
    if _run(["codegraph", "init", "."], root, log_path, timeout=60):
        notes.append(
            "CodeGraph: initialized .codegraph/ (was missing in this checkout)."
        )
    else:
        notes.append(f"CodeGraph: init failed or timed out — see {log_path}.")


def _ensure_repowise(root: Path, notes: list[str]) -> None:
    if shutil.which("repowise") is None or (root / ".repowise").is_dir():
        return

    # `repowise init` also writes its own usage-instructions block straight
    # into the TRACKED .claude/CLAUDE.md (REPOWISE:START/END markers) —
    # snapshot and restore that file so the hook only leaves the gitignored
    # .repowise/ index behind, matching how it treats CodeGraph/Graphify
    # (index-only, no tracked file writes).
    claude_md = root / ".claude" / "CLAUDE.md"
    snapshot = claude_md.read_text(encoding="utf-8") if claude_md.is_file() else None

    log_path = _CACHE_DIR / "repowise-sessionstart.log"
    ok = _run(["repowise", "init", "--index-only"], root, log_path, timeout=120)

    if snapshot is not None:
        claude_md.write_text(snapshot, encoding="utf-8")

    if ok:
        notes.append(
            "Repowise: built the keyless index (was missing in this checkout)."
        )
    else:
        notes.append(f"Repowise: index failed or timed out — see {log_path}.")


def _ensure_graphify(root: Path, notes: list[str]) -> None:
    if (
        shutil.which("graphify") is None
        or (root / "graphify-out" / "graph.json").is_file()
    ):
        return
    log_path = _CACHE_DIR / "graphify-sessionstart.log"
    # `update` handles both a first build and an incremental refresh; keyless
    # (AST-only).
    if _run(["graphify", "update", "."], root, log_path, timeout=240):
        notes.append(
            "Graphify: built graphify-out/graph.json (was missing in this checkout)."
        )
    else:
        notes.append(f"Graphify: build failed or timed out — see {log_path}.")


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).parent.parent)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    _ensure_codegraph(root, notes)
    _ensure_repowise(root, notes)
    _ensure_graphify(root, notes)

    if notes:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": " ".join(notes),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
