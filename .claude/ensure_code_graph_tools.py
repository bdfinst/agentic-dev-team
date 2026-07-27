#!/usr/bin/env python3
"""SessionStart hook (registered in .claude/settings.json): if CodeGraph,
Repowise, or Graphify are already installed but this checkout has never
been indexed (e.g. a freshly created worktree, or a fresh clone on a
machine that already has the CLIs globally installed), build the keyless
index automatically. This never installs a missing CLI — that stays an
explicit /project-init or /setup opt-in, per
knowledge/codegraph-vs-graphify.md ("None is guaranteed to be present").

Known side effect guarded against: `repowise init` is known to write its
own usage-instructions block directly into the tracked .claude/CLAUDE.md
(REPOWISE:START/END markers), not just into the gitignored .repowise/
index it's supposed to produce. This hook snapshots .claude/CLAUDE.md
before invoking `repowise init` and restores it afterward, so the tracked
file is left untouched and only the gitignored index directory is added.

Fail-open and time-boxed — never blocks session start. Stdlib-only.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
try:
    from session_start_common import resolve_project_root, run_logged
except ImportError:
    # The shared module must be present for this hook to do anything useful;
    # if it's missing (e.g. a partial checkout), fail open rather than raise.
    sys.exit(0)

_CACHE_DIR = Path.home() / ".cache"


def _ensure_codegraph(root: Path, notes: list) -> None:
    if shutil.which("codegraph") is None or (root / ".codegraph").is_dir():
        return
    log_path = _CACHE_DIR / "codegraph-sessionstart.log"
    if run_logged(["codegraph", "init", "."], root, log_path, timeout_seconds=60):
        notes.append(
            "CodeGraph: initialized .codegraph/ (was missing in this checkout)."
        )
    else:
        notes.append(f"CodeGraph: init failed or timed out — see {log_path}.")


def _ensure_repowise(root: Path, notes: list) -> None:
    if shutil.which("repowise") is None or (root / ".repowise").is_dir():
        return

    # `repowise init` writes into the TRACKED .claude/CLAUDE.md — snapshot
    # and restore it (unconditionally, even on failure) so the hook only
    # leaves the gitignored .repowise/ index behind, matching how it treats
    # CodeGraph/Graphify (index-only, no tracked file writes). If CLAUDE.md
    # didn't exist before this run, remove whatever repowise created rather
    # than leaving a file behind that was never tracked.
    claude_md = root / ".claude" / "CLAUDE.md"
    had_claude_md = claude_md.is_file()
    snapshot = claude_md.read_text(encoding="utf-8") if had_claude_md else None

    log_path = _CACHE_DIR / "repowise-sessionstart.log"
    try:
        ok = run_logged(
            ["repowise", "init", "--index-only"], root, log_path, timeout_seconds=120
        )
    finally:
        try:
            if had_claude_md:
                claude_md.write_text(snapshot, encoding="utf-8")
            elif claude_md.exists():
                claude_md.unlink()
        except OSError:
            notes.append(
                "Repowise: WARNING — could not restore .claude/CLAUDE.md after "
                "`repowise init`; inspect `git diff .claude/CLAUDE.md` before "
                "trusting agent instructions this session."
            )

    if ok:
        notes.append(
            "Repowise: built the keyless index (was missing in this checkout)."
        )
    else:
        notes.append(f"Repowise: index failed or timed out — see {log_path}.")


def _ensure_graphify(root: Path, notes: list) -> None:
    if (
        shutil.which("graphify") is None
        or (root / "graphify-out" / "graph.json").is_file()
    ):
        return
    log_path = _CACHE_DIR / "graphify-sessionstart.log"
    # `update` handles both a first build and an incremental refresh; keyless
    # (AST-only).
    if run_logged(["graphify", "update", "."], root, log_path, timeout_seconds=240):
        notes.append(
            "Graphify: built graphify-out/graph.json (was missing in this checkout)."
        )
    else:
        notes.append(f"Graphify: build failed or timed out — see {log_path}.")


def main() -> int:
    try:
        root = resolve_project_root()
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

        notes: list = []
        for ensure_fn in (_ensure_codegraph, _ensure_repowise, _ensure_graphify):
            try:
                ensure_fn(root, notes)
            except Exception:
                # Fail-open per tool: one tool's unexpected failure must
                # never block the others.
                continue

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
    except Exception:
        # Never let this hook block or fail session start.
        return 0


if __name__ == "__main__":
    sys.exit(main())
