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
CLI) and by `hooks/testimprove_phase_scope_guard.py` (the Read-scope guard
hook, issue #2094 Slice 2) — rather than maintaining two copies of the same
phase-rank tables.

The Phase-3 (Derive Gherkin) correction — substituting phase "3" for the
ordinary next phase "1" when Phase 2 (Baseline) just completed and BDD work
is wanted — also lives here (`resolve_with_phase3_correction`), so both
consumers agree on when Phase 3 is open (issue #2094 Slice 2 review fix):
previously the correction lived only inside the guard hook, so
`scripts/test_improve_resume.py --from-phase` (with no number) could tell an
operator to resume at Phase 1 while the guard hook — computing the correct
active phase "3" independently — blocked the very read that resume advice
sent them to.

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


# --- Phase-3 (Derive Gherkin) correction --------------------------------
#
# Phase 3 has no numbered progress file of its own (see module docstring),
# so `resolve_auto` alone can never know it should be the active/next phase
# instead of Phase 1. The correction below is the single place that decides
# this, from `phase-0.md`'s persisted `binding_mode` value plus whether
# `gherkin.md` has been written yet.

#: The literal `phase-0.md` key `/test-improve` persists the resolved BDD
#: binding mode under (pinned in `phase-0-approach-contract.md`). Shared by
#: the doc-text assertion (tests), this module's own parser, and
#: `hooks/testimprove_phase_scope_guard.py` (which re-exports this name for
#: its own tests) so none of the three can diverge without one shared symbol
#: changing.
BINDING_MODE_KEY = "binding_mode"

#: The closed set of legal `binding_mode` values — matches `SKILL.md`,
#: `phase-3-derive-gherkin.md`, and `knowledge/telemetry-schema.md`. A value
#: outside this set (a truncated/garbled write, or a stray line that happens
#: to match the regex) is treated as absent, never as an implicit `"none"` —
#: see `parse_binding_mode`.
VALID_BINDING_MODES = frozenset({"none", "xunit-with-annotations", "bdd-runner"})

#: Review fix (issue #2094 follow-up): the gap between the colon and the
#: captured value is `[ \t]*`, not `\s*` — `\s` matches `\n`, so `\s*` let a
#: truncated `binding_mode:` line (no value on it) capture an unrelated
#: token from a LATER line as its value instead of failing to match at all.
_BINDING_MODE_RE = re.compile(rf"^[ \t]*{BINDING_MODE_KEY}:[ \t]*(\S+)", re.MULTILINE)


def parse_binding_mode(text: str) -> str | None:
    """Extract the `binding_mode` value from `phase-0.md`'s raw text.

    Returns `None` when the key is absent, or when the captured value is not
    one of `VALID_BINDING_MODES` — an unvalidated value previously let a
    truncated/garbled write (e.g. `binding_mode: x`) be treated as "some
    non-none mode", which confidently forced Phase 3 active off garbage
    input. Callers treat `None` as "malformed or missing phase-0.md", never
    as `binding_mode: none`.
    """
    match = _BINDING_MODE_RE.search(text)
    if not match:
        return None
    value = match.group(1)
    return value if value in VALID_BINDING_MODES else None


def read_phase0_text(memory_dir: Path) -> str | None:
    """Read `<memory_dir>/phase-0.md`'s raw text. `None` when the file is
    missing, unreadable, or not valid UTF-8 (`UnicodeDecodeError` is a
    `ValueError`, not an `OSError` — caught explicitly so a garbled/binary
    `phase-0.md` fails open the same way a missing one does, rather than
    raising uncaught through an unguarded caller such as
    `scripts/test_improve_resume.py`'s `build_result()`). The single I/O
    primitive `read_binding_mode` and `resolve_with_phase3_correction`
    build on, and that a caller needing more than one `phase-0.md` key
    (e.g. `hooks/testimprove_phase_scope_guard.py`'s
    `_resolve_active_phase`, which also needs `refactor-mode`) can call
    once and parse from repeatedly, instead of re-reading the file per
    key."""
    try:
        return (memory_dir / "phase-0.md").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def read_binding_mode(memory_dir: Path) -> str | None:
    """Read and parse `<memory_dir>/phase-0.md`'s `binding_mode` value.

    Returns `None` when the file is missing, unreadable, or its value is
    absent/invalid — see `parse_binding_mode`.
    """
    text = read_phase0_text(memory_dir)
    if text is None:
        return None
    return parse_binding_mode(text)


#: Sentinel distinguishing "`phase0_text` not supplied — read it" from
#: "the caller already tried and confirmed `phase-0.md` is missing/unreadable
#: (`None`)" in `resolve_with_phase3_correction`'s optional `phase0_text`
#: parameter. `None` is itself a legal, meaningful value there, so a
#: dedicated sentinel is needed instead of reusing `None` as the default.
_UNSET = object()


def resolve_with_phase3_correction(
    memory_dir: Path,
    tokens: list[str] | None = None,
    *,
    phase0_text: str | None = _UNSET,  # type: ignore[assignment]
) -> tuple[str | None, str, bool]:
    """Like `resolve_auto`, but substitutes Phase 3 ("Derive Gherkin") for
    the ordinary next phase when Phase 2 (Baseline) just completed,
    `binding_mode` says BDD work is wanted, and Phase 3 hasn't already run
    (no `gherkin.md` yet). Returns `(resolved_phase, highest_token,
    complete)` — the same shape as `resolve_auto`.

    Best-effort on `phase-0.md`: when it is missing or `binding_mode` is
    missing/invalid, the correction is silently skipped and ordinary
    `resolve_auto` resolution is returned unchanged — this function never
    raises and never blocks a resume decision on a malformed file. A caller
    that must distinguish "phase-0.md unreadable" from "no correction
    needed" (to fail open on that ambiguity rather than guess) should call
    `read_binding_mode` itself — see
    `hooks/testimprove_phase_scope_guard.py`'s `_resolve_active_phase`.

    `tokens`, when provided, must already be `scan_phase_files(memory_dir)`
    for this same directory — passed through to avoid a redundant directory
    scan when the caller has already done one. `phase0_text`, when provided
    (including explicitly as `None`, meaning "already confirmed missing or
    unreadable"), is used as-is instead of this function reading
    `phase-0.md` itself — lets a caller that already read the file for its
    own purposes (again, `_resolve_active_phase`) avoid a second, redundant
    read; the default (unsupplied) still reads fresh, matching every
    existing caller's behavior unchanged.

    DELIBERATELY NOT unified with the Phase-6/7 boundary (repeatedly
    flagged in review as an asymmetry with this Phase-3 correction, both
    living in `hooks/testimprove_phase_scope_guard.py`'s
    `_resolve_active_phase` — see `REASON_PHASE_6_7_AMBIGUOUS` there): the
    two corrections aren't the same shape. Phase 3's correction always
    resolves to a DEFINITE phase token ("3" or the ordinary next phase) —
    `resolve_auto`'s `(resolved_phase, highest, complete)` contract has
    room for that. The Phase-6/7 boundary can be genuinely UNDECIDABLE from
    persisted state (the `[y/b/q]` decision itself is never written to
    disk) — there is no single phase token this function could return for
    that case without either guessing or widening its return type to a
    tri-state the CLI script's caller (`build_result()`) doesn't expect.
    `scripts/test_improve_resume.py --from-phase` (no explicit number)
    therefore still confidently reports "Phase 8" in that state, while the
    guard hook — computing the identical undecidability independently —
    fails open instead of blocking. This is a known, accepted scope
    boundary for issue #2094 (which added the guard hook's Read-scoping
    behavior, not `--from-phase`'s advisory-text accuracy), not an
    oversight matching Phase 3's fix.
    """
    if tokens is None:
        tokens = scan_phase_files(memory_dir)
    resolved, highest, complete = resolve_auto(tokens)
    if highest == "2":
        text = read_phase0_text(memory_dir) if phase0_text is _UNSET else phase0_text
        binding_mode = parse_binding_mode(text) if text is not None else None
        if (
            binding_mode is not None
            and binding_mode != "none"
            and not (memory_dir / "gherkin.md").exists()
        ):
            return "3", highest, False
    return resolved, highest, complete
