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
`repowise init` also writes a project-root .mcp.json registering its MCP
server (plugins/dev-team/skills/project-init/SKILL.md's Repowise
sub-section); unlike CLAUDE.md this hook does not snapshot/restore it —
.mcp.json is gitignored (see that skill's `.mcp.json` hygiene standing
check), so an overwrite here never leaks into git, only into the working
tree of whichever machine ran this hook.

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
        # 420s budget: project-init/SKILL.md documents ~5.5 minutes for this
        # exact `--no-prose -y` invocation on a ~1600-file repo; a shorter box
        # would routinely kill the run mid-index on a repo this size.
        ok = run_logged(
            ["repowise", "init", ".", "--no-prose", "-y"],
            root,
            log_path,
            timeout_seconds=420,
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
        # A killed/failed run can still leave a partial .repowise/ behind;
        # the guard at the top of this function treats that directory's mere
        # presence as "already indexed" and would never retry. Clear it so
        # the next session start tries again instead of silently stopping
        # forever on a truncated index.
        repowise_dir = root / ".repowise"
        if repowise_dir.is_dir():
            shutil.rmtree(repowise_dir, ignore_errors=True)
        notes.append(f"Repowise: index failed or timed out — see {log_path}.")


def _ensure_graphify(root: Path, notes: list) -> None:
    if (
        shutil.which("graphify") is None
        or (root / "graphify-out" / "graph.json").is_file()
    ):
        return
    log_path = _CACHE_DIR / "graphify-sessionstart.log"
    # `update` handles both a first build and an incremental refresh, and
    # stays AST-only/keyless by design — this hook never installs a CLI or
    # prompts for a key, so it never attempts graphify's full extraction
    # (docs/images indexing needs a working backend; see project-init/
    # SKILL.md's Graphify sub-section, issue #1483). The result here is
    # always the same degraded, code-only graph that sub-section describes.
    if run_logged(["graphify", "update", "."], root, log_path, timeout_seconds=240):
        notes.append(
            "Graphify: built a code-only graph (was missing in this checkout) "
            "— docs/images not indexed; run /project-init for the full index."
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
            except Exception:  # noqa: BLE001, S112 - fail-open per tool: one
                # tool's unexpected failure must never block the others, and
                # there is nothing worth logging for a best-effort probe.
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
    except Exception:  # noqa: BLE001 - never let this hook block or fail session start.
        return 0


if __name__ == "__main__":
    sys.exit(main())
