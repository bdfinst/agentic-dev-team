#!/usr/bin/env python3
"""test_improve_resume.py — resolve the `--from-phase` resume point for
`/test-improve` (issue #1151).

`/test-improve --from-phase <n>` used to require an explicit phase number.
This helper makes the number optional: when `--from-phase` is passed with no
argument, the orchestrator calls this script to auto-detect the resume point
from the run's memory directory `memory/test-improve/<slug>/`.

Deterministic rules (spec = issue #1151):

- Scan ONLY the resolved slug's directory for completed-phase progress files
  `phase-0.md` … `phase-7.md`, plus `phase-4b.md`. The slug derives from the
  `<repo-path>` (last path segment), so a run is never conflated with an
  unrelated slug under the same `memory/test-improve/` root.
- Find the HIGHEST-numbered completed phase, ordering `phase-4b` BETWEEN
  `phase-4` and `phase-5`.
- Resume at the NEXT phase in the pipeline sequence
  `0, 1, 2, 3, 4, 4b, 5, 6, 7`, with one deliberate skip: a completed
  `phase-4b.md` resumes at Phase 6 (matching the Phase-4b `[b]`/`[q]`
  skip-to-6 flow), and a completed `phase-4.md` with no `phase-4b.md`
  resumes at Phase 4b.
- No memory dir / no phase files → ERROR (do NOT silently start at Phase 0).
- `phase-0.md` must exist or the resume errors, for BOTH auto-detect and an
  explicit `--explicit <n>` — `--from-phase` never re-prompts Phase-0 inputs.
- An explicit `--explicit <n>` OVERRIDES auto-detection (still requires
  `phase-0.md`).

Output is JSON on stdout so the skill can consume it deterministically:

    {"resolved_phase": "5", "latest_completed": "phase-4b.md",
     "reason": "latest completed: phase-4b.md",
     "message": "Resuming at Phase 5 (latest completed: phase-4b.md).",
     "complete": false, "error": null}

Exit codes: 0 = resolved (or already complete), 2 = error (message on
stderr and in the JSON `error` field).

Stdlib-only. Python 3.8+ (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Pipeline order. `4b` sits between `4` and `5`; rank is used only to pick the
# highest completed file, NEXT_PHASE encodes where to resume from each.
PHASE_RANK: dict[str, int] = {
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "4b": 5,
    "5": 6,
    "6": 7,
    "7": 8,
}

# Where to resume given the highest completed phase. `4b` skips Phase 5 and
# resumes at Phase 6 (matching the `[b]`/`[q]` skip-to-6 flow); `5` also
# resumes at Phase 6. `7` (last phase) has no successor — the run is complete.
NEXT_PHASE: dict[str, str | None] = {
    "0": "1",
    "1": "2",
    "2": "3",
    "3": "4",
    "4": "4b",
    "4b": "6",
    "5": "6",
    "6": "7",
    "7": None,
}

# `4b` before `4` so the anchored match is unambiguous (both still parse
# correctly thanks to backtracking, but this reads clearest).
_PHASE_FILE_RE = re.compile(r"^phase-(0|1|2|3|4b|4|5|6|7)\.md$")

# Slugify: lowercase, drop chars outside [a-z0-9 -], spaces->hyphens, collapse,
# trim. Matches build_knowledge_index.slugify so slugs stay consistent.
_SLUG_DROP_RE = re.compile(r"[^a-z0-9 \-]+")
_SLUG_SPACE_RE = re.compile(r" +")
_SLUG_DASH_RE = re.compile(r"-+")


def slugify(text: str) -> str:
    s = text.lower()
    s = _SLUG_DROP_RE.sub("", s)
    s = _SLUG_SPACE_RE.sub("-", s)
    s = _SLUG_DASH_RE.sub("-", s)
    return s.strip("-")


def derive_slug(repo_path: str) -> str:
    """Slug = slugified last path segment of the repo path (the convention
    shared with /coverage-baseline, /gherkin-derive, /test-audit-disable)."""
    name = Path(repo_path).expanduser().resolve().name
    return slugify(name) or slugify(repo_path)


def scan_phase_files(memory_dir: Path) -> list[str]:
    """Return the phase tokens (e.g. '0', '4b') whose progress files exist in
    `memory_dir`, sorted by pipeline rank. Non-phase files are ignored."""
    if not memory_dir.is_dir():
        return []
    tokens: list[str] = []
    for entry in memory_dir.iterdir():
        if not entry.is_file():
            continue
        m = _PHASE_FILE_RE.match(entry.name)
        if m:
            tokens.append(m.group(1))
    return sorted(set(tokens), key=lambda t: PHASE_RANK[t])


def resolve_auto(tokens: list[str]) -> tuple[str | None, str, bool]:
    """Given the completed phase tokens, return
    (resolved_phase, highest_token, complete).

    resolved_phase is None when the run is already complete (phase-7 done)."""
    highest = max(tokens, key=lambda t: PHASE_RANK[t])
    nxt = NEXT_PHASE[highest]
    return nxt, highest, nxt is None


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

    resolved, highest, complete = resolve_auto(tokens)
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
    parser.add_argument(
        "--memory-root",
        default="memory/test-improve",
        help="Root under which <slug>/ lives (default: memory/test-improve).",
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
