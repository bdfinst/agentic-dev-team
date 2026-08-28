#!/usr/bin/env python3
"""testimprove_phase_scope_guard.py — PreToolUse Read hook, issue #2094 Slice 2.

Named `testimprove_phase_scope_guard.py` (no underscore after "test") rather
than `test_improve_phase_scope_guard.py` deliberately — this plugin's own
`is_test_file` classifier (`hooks/lib/test_file_classify.py`) matches any
filename against `^(test_.+|.+_test)\\.py$` with no directory scoping, so a
module literally named `test_improve_phase_scope_guard.py` would be
misclassified as a test file by every consumer of that classifier despite
being a production hook (the same naming collision Slice 1 avoided for
`hooks/lib/testimprove_phase_state.py`).

Enforces `/test-improve`'s single-active-phase reading rule mechanically:
blocks (exit 2) a `Read` of `skills/test-improve/references/phase-<m>-*.md`
whenever `m` is not the resolved active phase of the one unambiguous
in-flight `/test-improve` run. Reference files that don't match that
pattern are untouched. Fails OPEN (allows the read) on any ambiguity
(zero or multiple in-flight runs) or internal error, with an audit line in
`.claude/metrics/test-improve-phase-scope.jsonl` — mirrors
`refactor_test_freeze_guard.py`'s shape (stdin JSON via
`stdin_json.read_stdin_json`, a pure `evaluate()` decision function, an
`audit()` helper appending JSONL via `atomic_state.append_line_locked`,
fail-open try/except wrapping all of `main()`).

This is a `PreToolUse:Read`-only control: it does not, and cannot, see a
file read performed via `Bash` (`cat`, `head`, etc.) or any other channel —
that gap is a recorded, out-of-scope limitation for this issue, not an
oversight.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, NamedTuple

_LIB_DIR = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
from atomic_state import append_line_locked
from stdin_json import read_stdin_json
from testimprove_phase_state import (
    BINDING_MODE_KEY,  # noqa: F401 - re-exported for test_test_improve_phase_scope_guard.py
    read_phase0_text,
    resolve_auto,
    resolve_with_phase3_correction,
    scan_phase_files,
)
from testimprove_phase_state import (
    parse_binding_mode as _parse_binding_mode,
)

#: Matches a `/test-improve` phase reference file's basename — captures the
#: phase number. Matched only against the resolved, canonical basename of a
#: file confirmed to live directly inside this plugin's own
#: `skills/test-improve/references/` directory (see `_match_phase_reference`)
#: — never as an unanchored substring search over the raw request string.
_PHASE_REF_BASENAME_RE = re.compile(r"^phase-(\d+)-.*\.md$")

#: Reference files that match `_PHASE_REF_BASENAME_RE` by name but are
#: shared, cross-phase content rather than a single phase's own reference —
#: always readable regardless of active phase. `phase-0-approach-contract.md`
#: hosts `--from-phase`/`--analyze-only` semantics and the Phase-6 prompt
#: reference, needed throughout a run, not just while Phase 0 is active.
_ALWAYS_ALLOWED_BASENAMES = frozenset({"phase-0-approach-contract.md"})

#: The literal `phase-0.md` key `/test-improve` records its refactor-mode
#: knob under (`refactor-mode: <no-refactor|refactor-allowed>` — see
#: `phase-0-approach-contract.md`). Single production consumer (this hook),
#: so — unlike `BINDING_MODE_KEY` — it stays local rather than moving to
#: `hooks/lib/testimprove_phase_state.py`.
REFACTOR_MODE_KEY = "refactor-mode"
_REFACTOR_MODE_RE = re.compile(rf"^[ \t]*{REFACTOR_MODE_KEY}:\s*(\S+)", re.MULTILINE)

#: The closed set of legal `refactor-mode` values (`phase-0-approach-contract.md`
#: knob 3). Mirrors `testimprove_phase_state.VALID_BINDING_MODES`'s
#: validation: a value outside this set (a truncated/garbled write) is
#: treated as absent, never as an implicit `"no-refactor"` — see
#: `_read_refactor_mode` and the Phase-6/7 check in `_resolve_active_phase`.
VALID_REFACTOR_MODES = frozenset({"no-refactor", "refactor-allowed"})

# --- Audit event / reason string constants -------------------------------

EVENT_BLOCK = "block"
EVENT_FAIL_OPEN = "fail-open"

REASON_NO_IN_FLIGHT_RUN = "no in-flight run found"
REASON_MALFORMED_PHASE0 = "malformed or missing phase-0.md"
REASON_AMBIGUOUS_MULTIPLE = "ambiguous: multiple candidates"
REASON_PHASE_6_7_AMBIGUOUS = (
    "ambiguous: phase-6/7 boundary undecidable from persisted state"
)
REASON_ANALYZE_ONLY_AMBIGUOUS = (
    "ambiguous: --analyze-only vs normal Phase-2-next window"
)

#: Max length of a value interpolated into the printed `[BLOCK]` message
#: (not the JSONL audit line, which is already `json.dumps`-safe).
_MESSAGE_VALUE_MAX_LEN = 200
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize_for_message(value: str | None) -> str:
    """Strip control characters/newlines and bound the length of a
    caller-controlled value (`file_path`) or an on-disk-derived value
    (`result.slug`) before it is interpolated into the printed `[BLOCK]`
    message — the message is terminal/log output, not a trust boundary the
    rest of the hook relies on, but neither should be printed unsanitized."""
    if not value:
        return ""
    cleaned = _CONTROL_CHARS_RE.sub(" ", value)
    if len(cleaned) > _MESSAGE_VALUE_MAX_LEN:
        cleaned = cleaned[:_MESSAGE_VALUE_MAX_LEN] + "…(truncated)"
    return cleaned


class ActivePhaseResult(NamedTuple):
    """The outcome of resolving `/test-improve`'s single active phase.

    `status`: `"ok"` — exactly one in-flight run resolved to a phase;
    `"ambiguous"` — two or more in-flight candidates; `"none_in_flight"` —
    zero candidates, OR the sole candidate's resolution could not be
    determined confidently (malformed `phase-0.md`, or a genuinely
    undecidable window such as the Phase-6/7 boundary — see `reason` to
    tell these apart literally).

    `highest` is the highest completed phase token for the sole in-flight
    candidate (`None` when `status != "ok"` and no candidate was scanned far
    enough to know it) — carried so `evaluate()` can recognize a narrow
    resolution window (e.g. only `phase-0.md` done) without re-scanning the
    directory it was just computed from.
    """

    status: Literal["ok", "ambiguous", "none_in_flight"]
    slug: str | None
    phase: str | None
    reason: str
    highest: str | None = None


def _memory_root(project_dir: Path) -> Path:
    """`<project_dir>/.claude/memory/test-improve/` — the root under which
    every `/test-improve` run's slug directory lives."""
    return artifact_paths.category_dir("memory", project_dir) / "test-improve"


def _find_in_flight_slugs(project_dir: Path) -> list[tuple[str, list[str]]]:
    """List the `(slug, tokens)` pairs for subdirectories of
    `.claude/memory/test-improve/` that qualify as an in-flight
    `/test-improve` run.

    Returning each slug's already-scanned phase tokens alongside its name
    lets `_resolve()` pass them straight to `_resolve_active_phase()` for
    the chosen candidate, instead of re-scanning that same directory a
    second time.

    A slug is EXCLUDED when `resolve_with_phase3_correction`'s underlying
    `complete` flag (keyed on `phase-9.md`, via `testimprove_phase_state`)
    says the run is done — the primary completion signal — or, defensively,
    when a completed report already exists at
    `.dev-team-reports/test-improve/<slug>/report-*.md` (the narrow window
    between `phase-9.md` landing and the report file being written; never an
    independent definition of "complete" on its own). A slug with no
    completed phase files at all is skipped too — it has nothing to resolve.

    Migrates any pre-existing top-level `memory/test-improve/` tree into
    `.claude/memory/test-improve/` first (mirrors
    `scripts/test_improve_resume.py`'s `resolve_memory_dir` — see
    `artifact_paths.migrate_dir()`), so an in-flight run under the legacy
    location is not invisible to this guard and does not silently fail open
    for every read of that run's phase reference files.
    """
    artifact_paths.migrate_dir(
        "memory", "test-improve", root=project_dir, exclude={"refactor-backlog.md"}
    )
    memory_root = _memory_root(project_dir)
    if not memory_root.is_dir():
        return []
    reports_root = artifact_paths.dev_team_reports_dir(project_dir) / "test-improve"

    candidates: list[tuple[str, list[str]]] = []
    for entry in sorted(memory_root.iterdir()):
        if not entry.is_dir():
            continue
        tokens = scan_phase_files(entry)
        if not tokens:
            continue
        _, _, complete = resolve_with_phase3_correction(entry, tokens)
        if complete:
            continue
        report_dir = reports_root / entry.name
        if report_dir.is_dir() and any(report_dir.glob("report-*.md")):
            continue
        candidates.append((entry.name, tokens))
    return candidates


def _parse_refactor_mode(text: str) -> str | None:
    """Extract the `refactor-mode` value from `phase-0.md`'s raw text.
    `None` when the key is absent or the captured value is not one of
    `VALID_REFACTOR_MODES` — mirrors `testimprove_phase_state.parse_binding_mode`'s
    validation. A caller must treat `None` as "malformed or missing
    phase-0.md", never as `refactor-mode: no-refactor`."""
    match = _REFACTOR_MODE_RE.search(text)
    if not match:
        return None
    value = match.group(1)
    return value if value in VALID_REFACTOR_MODES else None


def _resolve_active_phase(
    memory_dir: Path, tokens: list[str]
) -> tuple[str | None, str | None, str]:
    """Resolve the active phase for one slug's memory directory, given its
    already-scanned phase tokens (see `_find_in_flight_slugs` — avoids
    re-scanning the directory the caller just scanned).

    Returns `(active_phase, highest, reason)`. `active_phase` is `None` when
    nothing can be resolved confidently:

    - `reason == REASON_MALFORMED_PHASE0` when `phase-0.md` itself is
      missing (`"0" not in tokens` — mirrors
      `scripts/test_improve_resume.py`'s `build_result()`, which hard-requires
      it for every resolution, not just Phase-3/Phase-6/7's), OR the Phase-3
      correction needed `phase-0.md`'s `binding_mode` and couldn't read or
      parse it, OR the highest completed phase is `"6"` and `phase-0.md`'s
      `refactor-mode` couldn't be read or parsed — in every case failing
      open rather than silently falling through to the phase's ordinary
      (non-ambiguous) resolution on a garbled/missing file.
    - `reason == REASON_PHASE_6_7_AMBIGUOUS` when the highest completed
      phase is `"6"`, `refactor-mode: refactor-allowed` is recorded, and
      `phase-7.md` doesn't exist yet — unlike Phase 3 (a clean
      `binding_mode` + `gherkin.md` signal), whether Phase 7 will run next
      is genuinely undecidable from persisted state alone (the `[y/b/q]`
      decision is not itself persisted).

    When the highest completed phase is `"2"` (Baseline), Phase 3 (Derive
    Gherkin — no numbered progress file of its own) may be the active phase
    instead of the ordinary next phase (`"1"`, Analyze) — see
    `resolve_with_phase3_correction`.

    Reads `phase-0.md` at most once (via `phase0_text`, threaded into
    `resolve_with_phase3_correction` and reused for the `binding_mode`/
    `refactor-mode` parses below) rather than once per key/branch.
    """
    if "0" not in tokens:
        _, highest, _complete = resolve_auto(tokens)
        return None, highest, REASON_MALFORMED_PHASE0

    phase0_text = read_phase0_text(memory_dir)
    resolved, highest, _complete = resolve_with_phase3_correction(
        memory_dir, tokens, phase0_text=phase0_text
    )
    binding_mode = _parse_binding_mode(phase0_text) if phase0_text is not None else None

    if highest == "2" and resolved != "3" and binding_mode is None:
        # phase-0.md was required to decide the Phase-3 window and could not
        # be read/parsed (missing, unreadable, or an invalid/garbled
        # binding_mode value) -- fail open rather than silently assume
        # "none".
        return None, highest, REASON_MALFORMED_PHASE0

    if resolved == "3":
        return "3", highest, f"phase-3 active (binding_mode: {binding_mode})"

    if highest == "6":
        refactor_mode = _parse_refactor_mode(phase0_text) if phase0_text is not None else None
        if refactor_mode is None:
            # phase-0.md's refactor-mode was required to rule the Phase-6/7
            # boundary in or out and could not be read/parsed (missing,
            # unreadable, or an invalid/garbled value) -- fail open rather
            # than silently fall through to the "no-refactor" (phase 8)
            # branch below, the same asymmetry the Phase-3 check above
            # already guards against.
            return None, highest, REASON_MALFORMED_PHASE0
        if refactor_mode == "refactor-allowed" and not (memory_dir / "phase-7.md").exists():
            return None, highest, REASON_PHASE_6_7_AMBIGUOUS

    return resolved, highest, f"latest completed: phase-{highest}.md"


def _resolve(project_dir: Path) -> ActivePhaseResult:
    """Resolve the single active phase across every in-flight
    `/test-improve` run under `project_dir`. Never raises — malformed input
    resolves to `status == "none_in_flight"` with a descriptive `reason`
    rather than propagating an exception (callers still wrap this in a
    try/except as defense-in-depth for anything unforeseen)."""
    candidates = _find_in_flight_slugs(project_dir)

    if not candidates:
        return ActivePhaseResult(
            status="none_in_flight", slug=None, phase=None,
            reason=REASON_NO_IN_FLIGHT_RUN,
        )
    if len(candidates) > 1:
        ordered = sorted(slug for slug, _tokens in candidates)
        reason = f"{REASON_AMBIGUOUS_MULTIPLE}: " + ", ".join(ordered)
        return ActivePhaseResult(status="ambiguous", slug=None, phase=None, reason=reason)

    slug, tokens = candidates[0]
    memory_dir = _memory_root(project_dir) / slug
    phase, highest, reason = _resolve_active_phase(memory_dir, tokens)
    if phase is None:
        return ActivePhaseResult(
            status="none_in_flight", slug=slug, phase=None, reason=reason, highest=highest,
        )
    return ActivePhaseResult(
        status="ok", slug=slug, phase=phase, reason=reason, highest=highest,
    )


def audit(
    project_dir: Path,
    event: str,
    file: str | None = None,
    result: ActivePhaseResult | None = None,
) -> None:
    """Append one JSONL audit line under
    `.claude/metrics/test-improve-phase-scope.jsonl`.

    `phase`/`slug`/`reason` come from `result` (when given) rather than
    being separate parameters — keeps this call site under the 5-parameter
    threshold and ties the logged fields to one coherent resolution outcome.

    Best-effort — a failure to resolve the path, create the directory, or
    write the line is fail-open: log a diagnostic and never crash the guard
    (mirrors `refactor_test_freeze_guard.py`'s own `audit()`).
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hook": "testimprove_phase_scope_guard",
        "event": event,
        "file": file,
        "phase": result.phase if result else None,
        "slug": result.slug if result else None,
        "reason": result.reason if result else None,
    }
    try:
        path = artifact_paths.resolve_file(
            "metrics", "test-improve-phase-scope.jsonl", project_dir
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        append_line_locked(path, json.dumps(entry) + "\n", fail_open=False)
    except OSError as exc:
        sys.stderr.write(
            f"[testimprove_phase_scope_guard] failed to write audit line: {exc}\n"
        )


def _extract_file_path(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return ""
    value = tool_input.get("file_path")
    return value if isinstance(value, str) else ""


def _plugin_root() -> Path:
    """This plugin's own root directory (parent of `hooks/`) — the anchor
    for `_references_dir()`, resolved fresh from `__file__` so it always
    matches wherever this module physically lives (a repo checkout during
    tests, or the versioned plugin cache at runtime)."""
    return Path(__file__).resolve().parent.parent


def _references_dir() -> Path:
    """The canonical, resolved `skills/test-improve/references/` directory
    under this plugin's own root."""
    return (_plugin_root() / "skills" / "test-improve" / "references").resolve()


def _match_phase_reference(file_path: str) -> str | None:
    """Return the phase number when `file_path` names a real file directly
    inside this plugin's own `skills/test-improve/references/` directory
    whose basename matches `phase-<m>-*.md` (case-insensitively) — `None`
    otherwise.

    Canonicalizes the path first (`Path.resolve()`, after normalizing any
    Windows-style backslash separators to forward slashes) so a double
    separator, a `/../` parent-traversal segment, or — on a
    case-insensitive filesystem — a different-case path all still resolve
    to the same real `references/` directory and match correctly. The
    comparison is anchored to this plugin's own resolved `references/`
    directory (not a bare `references/` substring test), so an unrelated
    file elsewhere on disk that happens to share the `phase-<m>-*.md` name
    is never matched either. A relative `file_path` (as used directly by
    tests) is resolved against this plugin's own root, matching the
    convention every real `Read` target already uses (an absolute path
    under wherever this plugin is installed).

    A file that is itself a symlink is the one case `Path.resolve()`
    does NOT keep anchored here: it follows the symlink to its real
    target, so a `phase-<m>-*.md`-named symlink whose target lives outside
    `references/` resolves to a `parent` that fails the directory check
    below and returns `None` (unmatched — this guard does not scope that
    read at all, rather than blocking it). No real reference file is ever a
    symlink, so this is a latent gap, not an active one.

    `phase-0-approach-contract.md` matches the name pattern (phase "0") but
    is shared, cross-phase content — see `_ALWAYS_ALLOWED_BASENAMES` — so it
    is exempted here and returns `None`, the same as any other non-matching
    path (AC2: no resolution work, no audit line, no exit-code change).
    """
    if not file_path:
        return None
    normalized = file_path.replace("\\", "/")
    try:
        candidate = Path(normalized).expanduser()
        if not candidate.is_absolute():
            candidate = _plugin_root() / candidate
        resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError):
        return None

    references_dir = _references_dir()
    if resolved.parent.as_posix().lower() != references_dir.as_posix().lower():
        return None

    basename = resolved.name.lower()
    if basename in _ALWAYS_ALLOWED_BASENAMES:
        return None

    match = _PHASE_REF_BASENAME_RE.match(basename)
    return match.group(1) if match else None


def evaluate(file_path: str, project_dir: Path) -> tuple[int, list[str]]:
    """Return (exit_code, stdout_lines) for one Read decision.

    A non-matching path (AC2) is a silent no-op — no resolution work, no
    audit line, no exit-code change. A match against a phase reference file
    triggers `_resolve()`; the two fail-open statuses (`"ambiguous"`,
    `"none_in_flight"`) audit and allow the read; `"ok"` blocks only when
    the matched phase number differs from the resolved active phase —
    Phase 3 (`phase-3-derive-gherkin.md`, matched phase `"3"`) falls out of
    this same equality check with no separate code path, since its active
    phase is likewise the literal token `"3"` when `_resolve_active_phase`
    determines Phase 3 is open.

    One additional, narrow exemption: when only `phase-0.md` is complete
    (`result.highest == "0"`), ordinary resolution says the active phase is
    `"2"` (Baseline) — but `/test-improve --analyze-only` legitimately reads
    Phase 1 directly in this same state, and nothing persisted in
    `phase-0.md` distinguishes the two modes (adding that persistence is a
    larger, out-of-scope change to `/test-improve` itself). A Read of
    `phase-1-analyze.md` in this narrow window fails open rather than
    blocking the common (non-`--analyze-only`) case's legitimate Phase-1
    read; a Read of `phase-2-baseline.md` in the same window still blocks,
    since that is the common case's own active-phase file.
    """
    matched_phase = _match_phase_reference(file_path)
    if matched_phase is None:
        return 0, []

    result = _resolve(project_dir)

    if result.status != "ok":
        audit(project_dir, EVENT_FAIL_OPEN, file=file_path, result=result)
        return 0, []

    if matched_phase == result.phase:
        return 0, []

    if matched_phase == "1" and result.phase == "2" and result.highest == "0":
        audit(
            project_dir, EVENT_FAIL_OPEN, file=file_path,
            result=result._replace(reason=REASON_ANALYZE_ONLY_AMBIGUOUS),
        )
        return 0, []

    audit(project_dir, EVENT_BLOCK, file=file_path, result=result)
    slug_display = _sanitize_for_message(result.slug)
    file_display = _sanitize_for_message(file_path)
    active_phase_note = (
        f"[BLOCK] /test-improve's in-flight run (slug: {slug_display}) is on "
        f"Phase {result.phase}, not Phase {matched_phase}."
    )
    return 2, [
        active_phase_note,
        "Reading a stale (already-completed) or premature (not-yet-reached)",
        "phase's reference file risks executing out-of-sequence instructions.",
        f"File: {file_display}",
        f"Recovery: read skills/test-improve/references/phase-{result.phase}-*.md instead.",
    ]


def _project_dir() -> Path:
    """Resolve the project root via git, not the possibly-unset/stale
    CLAUDE_PROJECT_DIR env var."""
    return artifact_paths.project_root()


def main() -> int:
    """Resolve `project_dir` (a `git rev-parse` subprocess) only once a
    match against `_PHASE_REF_BASENAME_RE` is confirmed — this hook is
    registered on `PreToolUse:Read`, the highest-frequency tool call in a
    session, and the overwhelming majority of Reads never match, so paying
    the subprocess cost unconditionally on every Read is wasted work on the
    hot path. `_project_dir()` stays reachable from inside the `except`
    below so the fail-open audit call can still resolve a project root even
    when the exception happened before a match was confirmed (e.g.
    `read_stdin_json()` itself raising)."""
    project_dir: Path | None = None
    try:
        payload = read_stdin_json()
        file_path = _extract_file_path(payload)
        if _match_phase_reference(file_path) is None:
            return 0
        project_dir = _project_dir()
        exit_code, lines = evaluate(file_path, project_dir)
    except Exception as exc:  # noqa: BLE001 - fail open, a broken guard never blocks work
        audit(
            project_dir if project_dir is not None else _project_dir(),
            EVENT_FAIL_OPEN,
            result=ActivePhaseResult(
                status="none_in_flight", slug=None, phase=None,
                reason=f"internal error: {exc}",
            ),
        )
        return 0
    for line in lines:
        print(line)
        if exit_code == 2:
            # docs/python-hook-contract.md's dual-write rule: mirror exit-2
            # block messages to stderr in addition to stdout, since some
            # Claude Code hook-error wrappers surface only stderr on a
            # nonzero hook exit.
            sys.stderr.write(line + "\n")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
