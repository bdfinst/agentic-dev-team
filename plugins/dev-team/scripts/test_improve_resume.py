#!/usr/bin/env python3
"""test_improve_resume.py — resolve the `--from-phase` resume point for
`/test-improve` (issue #1151).

`/test-improve --from-phase <n>` used to require an explicit phase number.
This helper makes the number optional: when `--from-phase` is passed with no
argument, the orchestrator calls this script to auto-detect the resume point
from the run's memory directory `.claude/memory/test-improve/<slug>/`. A
pre-existing top-level `memory/test-improve/` tree (from before this
directory moved under `.claude/`) is migrated file-by-file on the first
resume that resolves the memory directory; git-tracked files and
`refactor-backlog.md` are left in place (see `artifact_paths.migrate_dir()`).

This module owns the CLI interface (argument parsing, JSON stdout shape,
`--memory-dir`/`--slug`/`--memory-root` resolution, the legacy-directory
migration, and the `phase-0.md`-required / `--explicit`-overrides error
handling). The phase-ordering rules themselves — which phase is "next," the
Phase 3 skip, the Phase 6/7 skip-to-8 — are documented once, in
`hooks/lib/testimprove_phase_state.py`, the shared module this script
re-imports from.

Output is JSON on stdout so the skill can consume it deterministically:

    {"resolved_phase": "7", "latest_completed": "phase-6.md",
     "reason": "latest completed: phase-6.md",
     "message": "Resuming at Phase 7 (latest completed: phase-6.md).",
     "complete": false, "error": null}

Exit codes: 0 = resolved (or already complete), 2 = error (message on
stderr and in the JSON `error` field).

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HOOKS_LIB_DIR = Path(__file__).resolve().parent.parent / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

import artifact_paths
from testimprove_phase_state import (
    PHASE_RANK,
    derive_slug,
    resolve_with_phase3_correction,
    scan_phase_files,
    slugify,
)

__all__ = [
    "derive_slug",
    "scan_phase_files",
    "slugify",
]


def build_result(memory_dir: Path, explicit: str | None) -> tuple[int, dict]:
    """Compute the resume result. Returns (exit_code, payload)."""
    tokens = scan_phase_files(memory_dir)

    # Precondition shared by auto-detect AND explicit resume: phase-0.md must
    # exist. `--from-phase` never re-prompts Phase-0 inputs, so without a
    # persisted phase-0.md there is nothing to resume onto.
    if "0" not in tokens:
        if tokens:
            lead = (
                f"phase-0.md missing from {memory_dir} (found: "
                f"{', '.join('phase-' + t + '.md' for t in tokens)})"
            )
        else:
            lead = f"No completed phase files found in {memory_dir}"
        msg = (
            f"{lead} — nothing to resume. Run /test-improve <repo-path> "
            f"from Phase 0 first."
        )
        return 2, {
            "resolved_phase": None,
            "latest_completed": None,
            "reason": None,
            "message": msg,
            "complete": False,
            "error": msg,
        }

    if explicit is not None:
        phase = explicit.strip().lower()
        reason = f"explicit --from-phase {phase} (overrides auto-detect)"
        return 0, {
            "resolved_phase": phase,
            "latest_completed": f"phase-{max(tokens, key=lambda t: PHASE_RANK[t])}.md",
            "reason": reason,
            "message": f"Resuming at Phase {phase} ({reason}).",
            "complete": False,
            "error": None,
        }

    resolved, highest, complete = resolve_with_phase3_correction(memory_dir, tokens)
    latest_file = f"phase-{highest}.md"
    if complete:
        msg = (
            f"Run already complete (latest completed: {latest_file}). "
            f"Nothing to resume."
        )
        return 0, {
            "resolved_phase": None,
            "latest_completed": latest_file,
            "reason": f"latest completed: {latest_file}",
            "message": msg,
            "complete": True,
            "error": None,
        }

    reason = f"latest completed: {latest_file}"
    return 0, {
        "resolved_phase": resolved,
        "latest_completed": latest_file,
        "reason": reason,
        "message": f"Resuming at Phase {resolved} ({reason}).",
        "complete": False,
        "error": None,
    }


def resolve_memory_dir(args: argparse.Namespace) -> Path:
    # Migrate any pre-existing top-level memory/test-improve/ tree (every
    # slug at once, not just the one being resumed) before resolving this
    # run's directory. refactor-backlog.md is a user-facing report, not
    # phase-state — excluded from this sweep; it moves to neither
    # .claude/memory/ nor .dev-team-reports/ automatically (disclosed
    # limitation, see plan Slice 5 AC18).
    artifact_paths.migrate_dir(
        "memory", "test-improve", exclude={"refactor-backlog.md"}
    )
    if args.memory_dir:
        return Path(args.memory_dir).expanduser()
    slug = args.slug or derive_slug(args.repo_path or ".")
    root = Path(args.memory_root).expanduser()
    return root / slug


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the --from-phase resume point for /test-improve.",
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Repo path; its last segment resolves the memory slug.",
    )
    parser.add_argument(
        "--slug",
        help="Override the memory slug (default: slugified last path segment).",
    )
    default_memory_root = str(artifact_paths.category_dir("memory") / "test-improve")
    parser.add_argument(
        "--memory-root",
        default=default_memory_root,
        help=f"Root under which <slug>/ lives (default: {default_memory_root}).",
    )
    parser.add_argument(
        "--memory-dir",
        help="Scan this directory directly (overrides repo_path/--slug/--memory-root).",
    )
    parser.add_argument(
        "--explicit",
        help="Explicit phase number given by the operator; overrides auto-detect.",
    )
    args = parser.parse_args(argv)

    memory_dir = resolve_memory_dir(args)
    exit_code, payload = build_result(memory_dir, args.explicit)

    print(json.dumps(payload))
    if exit_code != 0 and payload.get("error"):
        print(payload["error"], file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
