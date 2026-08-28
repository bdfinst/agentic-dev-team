"""testimprove_phase_state.py — shared /test-improve phase-state resolution
(issue #2094 Slice 1).

Named `testimprove_phase_state.py` (no underscore after "test") rather than
`test_improve_phase_state.py` deliberately — this plugin's own `is_test_file`
classifier (`hooks/lib/test_file_classify.py`) matches any filename against
`^(test_.+|.+_test)\\.py$` with no directory scoping, so a module literally
named `test_improve_phase_state.py` would be misclassified as a test file by
every consumer of that classifier despite being a production library.

Extracted verbatim from `scripts/test_improve_resume.py` (issue #1151) so
there is one source of truth for "what phase is `/test-improve` on" —
consumed by `scripts/test_improve_resume.py` (the `--from-phase` auto-detect
CLI) and, going forward, by `hooks/test_improve_phase_scope_guard.py` (the
Read-scope guard hook, issue #2094 Slice 2) — rather than maintaining two
copies of the same phase-rank tables.

Deterministic rules (spec = issue #1151; execution order reordered by
issue #1422 so Baseline and Derive-Gherkin land before Analyze):

- Scan ONLY the resolved slug's directory for completed-phase progress files
  `phase-0.md` … `phase-9.md`, excluding `phase-3.md` (Phase 3 — Gherkin
  derive — is conditional and tracked via `gherkin.md`, not a numbered
  progress file; see below). The slug derives from the `<repo-path>` (last
  path segment), so a run is never conflated with an unrelated slug under the
  same `.claude/memory/test-improve/` root.
- Find the HIGHEST-completed phase, ordered by the pipeline's EXECUTION
  sequence `0, 2, 1, 4, 5, 6, 7, 8, 9` (phase identities keep their historical
  numbers — Phase 1 is still Analyze, Phase 2 is still Baseline — only the
  order in which they execute changed; see `test-improve/SKILL.md`'s
  "Execution order" note).
- Resume at the NEXT phase in that execution sequence, with two deliberate
  skips: a completed `phase-2.md` resumes at Phase 1 directly (Phase 3 has no
  tracked progress file, so the auto-detect skips over it the same way it
  always has — this is unchanged by the reorder, only the skip TARGET moved
  from Phase 4 to Phase 1), a completed `phase-6.md` resumes at Phase 8
  (matching the Phase-6 `[b]`/`[q]` skip-to-8 flow), and a completed
  `phase-5.md` with no `phase-6.md` resumes at Phase 6.

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

import re
from pathlib import Path

# Execution order (issue #1422), skipping `3` (Phase 3 has no numbered
# progress file — see module docstring). Phase identities are unchanged
# (Phase 1 is still Analyze, Phase 2 is still Baseline); rank reflects the
# order they now EXECUTE in (0 -> 2 -> 1 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9), not
# their identity numbers. Rank is used only to pick the highest completed
# file; NEXT_PHASE encodes where to resume from each.
PHASE_RANK: dict[str, int] = {
    "0": 0,
    "2": 1,
    "1": 2,
    "4": 3,
    "5": 4,
    "6": 5,
    "7": 6,
    "8": 7,
    "9": 8,
}

# Where to resume given the highest completed phase. `2` skips Phase 3 (no
# tracked progress file) and resumes at Phase 1 — the skip is unchanged by
# the reorder, only its target moved from Phase 4 (old sequential order) to
# Phase 1 (new execution order). `6` skips Phase 7 and resumes at Phase 8
# (matching the `[b]`/`[q]` skip-to-8 flow); `7` also resumes at Phase 8. `9`
# (last phase) has no successor — the run is complete.
NEXT_PHASE: dict[str, str | None] = {
    "0": "2",
    "2": "1",
    "1": "4",
    "4": "5",
    "5": "6",
    "6": "8",
    "7": "8",
    "8": "9",
    "9": None,
}

_PHASE_FILE_RE = re.compile(r"^phase-(0|1|2|4|5|6|7|8|9)\.md$")

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
    """Return the phase tokens (e.g. '0', '4') whose progress files exist in
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

    resolved_phase is None when the run is already complete (phase-9 done).

    Precondition: tokens must be non-empty (raises ValueError otherwise) —
    callers must guard this, e.g. by only calling this after confirming at
    least phase-0.md exists."""
    highest = max(tokens, key=lambda t: PHASE_RANK[t])
    nxt = NEXT_PHASE[highest]
    return nxt, highest, nxt is None
