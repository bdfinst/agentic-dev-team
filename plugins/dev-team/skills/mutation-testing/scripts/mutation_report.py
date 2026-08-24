#!/usr/bin/env python3
"""mutation_report.py — parse a native mutation report and compute scores.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). Carries no repo-specific literal —
project names, controller names, and test-library names live in the report
being parsed, never in this module.

Two native report shapes are supported, normalized to the same internal
``{"files": {"<path>": {"mutants": [...]}}}`` dict before scoring:

- Stryker / Stryker.NET's own ``mutation-report.json`` — read directly via
  the path-based functions (``score_report``, ``survivors_by_mutator``, …).
- mutmut's ``mutmut junitxml`` output — mutmut has no JSON report of its
  own; ``parse_mutmut_junitxml`` converts it into the same internal shape so
  every downstream function (scoring, survivor extraction, file discovery)
  works identically regardless of which tool produced the data.

Two scores are computed side by side:

- **honest score** = Killed / (Killed + Survived + NoCoverage)
  A Timeout is *not* a demonstrated kill — the test never asserted anything;
  the mutant merely ran too long. Counting Timeouts as kills inflates the
  score, so the honest score excludes them from the numerator entirely.

- **reported score** = (Killed + Timeout) / (Killed + Survived + Timeout + NoCoverage)
  The score Stryker itself reports, kept alongside for parity so the gap
  between "what the tool claims" and "what the tests actually prove" is
  visible rather than hidden.

Both scores are expressed as percentages in [0, 100]. An absent or empty
report yields zeroed scores rather than raising.

Stryker.NET mutant statuses: Killed, Survived, Timeout, NoCoverage, Ignored,
CompileError. Only the first four participate in scoring; Ignored and
CompileError are excluded from both numerator and denominator.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# Stryker.NET mutant-status vocabulary — the single source of truth for these
# literals across the whole pipeline. Sibling modules import these constants
# rather than re-typing the raw strings, so the status vocabulary lives in one
# place (AC4). Only these four participate in the score denominators.
STATUS_KILLED = "Killed"
STATUS_SURVIVED = "Survived"
STATUS_TIMEOUT = "Timeout"
STATUS_NO_COVERAGE = "NoCoverage"

# Mutant dict key carrying Stryker's "this mutant sits in module-init code,
# not per-test code" flag. Centralized here alongside the status vocabulary
# above so the literal isn't repeated across the functions that read it.
MUTANT_STATIC_KEY = "static"

# Fixed reason string attached to every accepted-static-survivor entry
# (see ``accepted_static_survivors``) — a static-flagged Survived mutant is
# not equivalent and not fixed; it is deliberately deferred because killing
# it would require a full-suite re-run rather than a single-mutant one.
ACCEPTED_STATIC_REASON = "static — verification requires a full-suite re-run"

# ``status`` value for every accepted-static-survivor entry — a sibling
# constant to ``ACCEPTED_STATIC_REASON`` so the entry's ``"status"`` field is
# never a bare string literal, matching every other status value in this
# module (``STATUS_KILLED`` etc. above).
ACCEPTED_STATIC_ENTRY_STATUS = "accepted"


@dataclass(frozen=True)
class ScoreSummary:
    """Both scores plus the two counts that distinguish them.

    ``honest_score`` and ``reported_score`` are percentages in [0, 100].
    ``timeout`` and ``no_coverage`` are raw mutant counts, surfaced so a
    caller can show *why* the two scores diverge.
    """

    killed: int
    survived: int
    timeout: int
    no_coverage: int
    honest_score: float
    reported_score: float


def load_report(report_path: Path) -> dict:
    """Return the parsed report, or ``{}`` when the file is absent, empty,
    malformed JSON, or valid JSON that isn't a dict (e.g. a report file
    containing ``[]`` or ``42``) — never raises."""
    path = Path(report_path)
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iter_mutants(data: dict):
    """Yield every mutant dict across all files in a parsed report."""
    for info in data.get("files", {}).values():
        yield from info.get("mutants", [])


def _find_file_entry(data: dict, file_path: str) -> tuple[str, dict] | None:
    """Return the matched ``(report_key, info)`` pair for one file from an
    already-parsed report dict.

    Matches ``file_path`` against report keys by exact match first, then by
    basename, so a caller can pass either the full report key or just the
    filename. Returns ``None`` when no file matches. ``report_key`` is the
    key exactly as the report emits it — a caller that only passed a
    basename (or an absolute path) gets back the matched report key, not an
    echo of its own input.
    """
    files = data.get("files", {})

    info = files.get(file_path)
    if info is not None:
        return file_path, info

    target = Path(file_path).name
    for key, value in files.items():
        if Path(key).name == target:
            return key, value
    return None


def _find_file_info(data: dict, file_path: str) -> dict | None:
    """Return one file's report entry (the ``{"mutants": [...]}`` dict) from
    an already-parsed report dict.

    Matches ``file_path`` against report keys by exact match first, then by
    basename, so a caller can pass either the full report key or just the
    filename. Returns ``None`` when no file matches. Thin wrapper around
    ``_find_file_entry`` that discards the matched key — callers that need
    the matched key too (e.g. ``_accepted_static_survivors_from_data``) call
    ``_find_file_entry`` directly instead.
    """
    entry = _find_file_entry(data, file_path)
    return entry[1] if entry is not None else None


def _tally(mutants: list[dict]) -> ScoreSummary:
    """Compute the honest and reported scores for a flat list of mutant
    dicts (one file's ``mutants`` list, or every file's combined)."""
    killed = survived = timeout = no_coverage = 0
    for mutant in mutants:
        status = mutant.get("status")
        if status == STATUS_KILLED:
            killed += 1
        elif status == STATUS_SURVIVED:
            survived += 1
        elif status == STATUS_TIMEOUT:
            timeout += 1
        elif status == STATUS_NO_COVERAGE:
            no_coverage += 1

    honest_denom = killed + survived + no_coverage
    reported_denom = killed + survived + timeout + no_coverage

    honest_score = (killed / honest_denom * 100) if honest_denom else 0.0
    reported_score = (
        (killed + timeout) / reported_denom * 100 if reported_denom else 0.0
    )

    return ScoreSummary(
        killed=killed,
        survived=survived,
        timeout=timeout,
        no_coverage=no_coverage,
        honest_score=honest_score,
        reported_score=reported_score,
    )


def _score_data(data: dict) -> ScoreSummary:
    """Compute the honest and reported scores for an already-parsed report
    dict (the ``{"files": {...}}`` shape shared by every supported tool)."""
    return _tally(list(_iter_mutants(data)))


def score_report(report_path: Path) -> ScoreSummary:
    """Compute the honest and reported scores for a Stryker-shaped mutation
    report on disk.

    Returns a fully zeroed :class:`ScoreSummary` when the report is absent
    or empty — never raises for a missing file.
    """
    return _score_data(load_report(report_path))


def _score_data_for_file(data: dict, file_path: str) -> ScoreSummary:
    """Compute the honest and reported scores for one file within an
    already-parsed report dict.

    Matches ``file_path`` the same way ``_find_file_info`` does (exact key,
    then basename). Returns a fully zeroed :class:`ScoreSummary` when the
    file is not matched — never raises.
    """
    info = _find_file_info(data, file_path)
    if info is None:
        return _tally([])
    return _tally(info.get("mutants", []))


def score_report_for_file(report_path: Path, file_path: str) -> ScoreSummary:
    """Compute the honest and reported scores for one file within a
    Stryker-shaped mutation report on disk.

    Matches ``file_path`` against report keys by exact match first, then by
    basename (same rule as ``survivors_by_mutator``). Returns a fully zeroed
    :class:`ScoreSummary` when the report is absent/empty or the file is not
    matched — never raises.
    """
    return _score_data_for_file(load_report(report_path), file_path)


def _survivors_from_data(
    data: dict, file_path: str, skip_static: bool = False
) -> dict[str, list[dict]]:
    """Return the Survived mutants for one source file, grouped by mutator
    name, from an already-parsed report dict.

    Matches ``file_path`` against report keys by exact match first, then by
    basename, so a caller can pass either the full report key or just the
    filename. Only ``Survived`` mutants are returned — killed, timed-out, and
    uncovered mutants are not survivors. Returns ``{}`` when the file is not
    in the report or has no survivors.

    When ``skip_static`` is ``True``, a mutant is excluded only when it
    carries ``static: true``; absence of the key (or ``static: false``)
    never excludes it. This function stays a pure data transform — the CLI
    wrapper owns any user-facing "skip is inapplicable" notice.
    """
    info = _find_file_info(data, file_path)
    if info is None:
        return {}

    mutants = info.get("mutants", [])
    if skip_static:
        mutants = [
            mutant for mutant in mutants if mutant.get(MUTANT_STATIC_KEY) is not True
        ]

    grouped: dict[str, list[dict]] = {}
    for mutant in mutants:
        if mutant.get("status") != STATUS_SURVIVED:
            continue
        mutator = mutant.get("mutatorName", "")
        grouped.setdefault(mutator, []).append(mutant)
    return grouped


def survivors_by_mutator(
    report_path: Path, file_path: str, skip_static: bool = False
) -> dict[str, list[dict]]:
    """Return the Survived mutants for one source file, grouped by mutator
    name, from a Stryker-shaped mutation report on disk.

    See ``_survivors_from_data`` for the ``skip_static`` behavior.
    """
    return _survivors_from_data(
        load_report(report_path), file_path, skip_static=skip_static
    )


def survivors_by_mutator_from_data(
    data: dict, file_path: str, skip_static: bool = False
) -> dict[str, list[dict]]:
    """Return the Survived mutants for one source file, grouped by mutator
    name, from an already-parsed report dict.

    Thin public wrapper around ``_survivors_from_data`` — lets a caller that
    already holds a parsed report (e.g. the CLI's ``--skip-static`` path,
    which loads the report once to run ``has_static_field``/
    ``is_file_in_report`` diagnostics before computing survivors) reuse that
    dict instead of triggering a second, redundant ``load_report`` call. See
    ``_survivors_from_data`` for the ``skip_static`` behavior.
    """
    return _survivors_from_data(data, file_path, skip_static=skip_static)


def has_static_field(data: dict, file_path: str) -> bool:
    """Return whether any mutant in the matched file's list carries a
    ``"static"`` key, from an already-parsed report dict.

    Matches ``file_path`` the same way ``_find_file_info`` does (exact key,
    then basename). Returns ``False`` uniformly both when the matched file
    has no mutant carrying a ``"static"`` key and when ``file_path`` isn't
    present in the report at all (``_find_file_info`` returns ``None``) —
    the two cases are not distinguished by this function's return value; use
    ``is_file_in_report`` alongside it to tell them apart.

    Data-based (takes an already-parsed ``data`` dict) rather than
    ``Path``-based. This module's public API is not uniformly ``Path``-based
    — ``parse_mutmut_junitxml``/``score_mutmut_junitxml``/
    ``survivors_from_mutmut_junitxml`` already take raw input — so this is
    an established shape, not a new one. It exists to serve the CLI's
    pre-dispatch diagnostic, which already holds the parsed report; a
    ``Path``-based signature would force the ``--skip-static`` path to
    parse the report an extra, redundant time instead of reusing the dict
    it already loaded once (see ``survivors_by_mutator_from_data``, which
    the same CLI path reuses this dict with, for the same reason).
    """
    info = _find_file_info(data, file_path)
    if info is None:
        return False
    return any(MUTANT_STATIC_KEY in mutant for mutant in info.get("mutants", []))


def is_file_in_report(data: dict, file_path: str) -> bool:
    """Return whether ``file_path`` matches any report key, from an
    already-parsed report dict.

    Matches the same way ``_find_file_info`` does (exact key, then
    basename). Lets a caller distinguish "file matched but has no static
    field" from "file never matched any report key" — the two causes
    ``has_static_field`` collapses into a single ``False`` return value.
    """
    return _find_file_info(data, file_path) is not None


def _resolve_survivor_line(mutant: dict) -> int | None:
    """Resolve one mutant's source line from its ``location.start.line``
    field, or ``None`` when that shape is missing or malformed.

    Never raises: a missing/non-dict ``location``, a missing/non-dict
    ``start``, or a ``line`` that isn't a plain ``int`` (``None``, a
    non-int value, or a ``bool`` — ``bool`` is an ``int`` subclass in
    Python but is never a real line number) all resolve to ``None``. This
    matches the module's never-raise-on-bad-input posture (see the module
    docstring, ``load_report``'s "never raises" note, and
    ``parse_mutmut_junitxml``'s "malformed input returns empty rather than
    raising"). Extracted from ``_survivors_by_line_from_data``'s original
    inline unwrap so ``_accepted_static_survivors_from_data`` can reuse the
    same hardened logic instead of duplicating it.
    """
    loc = mutant.get("location")
    loc = loc if isinstance(loc, dict) else {}
    start = loc.get("start")
    start = start if isinstance(start, dict) else {}
    line = start.get("line")
    if not isinstance(line, int) or isinstance(line, bool):
        return None
    return line


def _survivors_by_line_from_data(data: dict, file_path: str) -> dict:
    """Return the Survived mutants for one source file, clustered by source
    line, from an already-parsed report dict.

    Matches ``file_path`` against report keys the same way
    ``_survivors_from_data`` does (via ``_find_file_info`` — exact key, then
    basename). Only ``Survived`` mutants participate; a mutant of any other
    status (Killed, Timeout, NoCoverage, ...) sharing a line with survivors
    never appears in the result.

    Return shape: ``{"clusters": [{"line": int, "survivors": [dict, ...]}, ...],
    "unclustered": [dict, ...]}``.

    - ``clusters`` groups survivors by ``mutant["location"]["start"]["line"]``
      and is sorted by ``len(survivors)`` descending; ties are broken by
      ``line`` ascending.
    - ``unclustered`` holds every survivor whose line isn't a resolvable
      plain ``int`` — ``None`` (e.g. mutmut's no-resolvable-line case), a
      non-int value, a ``bool`` (``bool`` is an ``int`` subclass in Python
      but is never a real line number), or a missing/non-dict ``location``/
      ``start`` value of any shape — such a survivor never forms or joins a
      cluster. This matches the module's never-raise-on-bad-input posture
      (see the module docstring, ``load_report``'s "never raises" note, and
      ``parse_mutmut_junitxml``'s "malformed input returns empty rather
      than raising"): no ``location``/``start``/``line`` shape, however
      malformed, raises ``AttributeError``/``TypeError`` here.
    - Returns ``{"clusters": [], "unclustered": []}`` when the file is not in
      the report or has no survivors.
    """
    info = _find_file_info(data, file_path)
    if info is None:
        return {"clusters": [], "unclustered": []}

    by_line: dict[int, list[dict]] = {}
    unclustered: list[dict] = []
    for mutant in info.get("mutants", []):
        if mutant.get("status") != STATUS_SURVIVED:
            continue
        line = _resolve_survivor_line(mutant)
        if line is None:
            unclustered.append(mutant)
            continue
        by_line.setdefault(line, []).append(mutant)

    clusters = [
        {"line": line, "survivors": survivors} for line, survivors in by_line.items()
    ]
    clusters.sort(key=lambda cluster: (-len(cluster["survivors"]), cluster["line"]))

    return {"clusters": clusters, "unclustered": unclustered}


def survivors_by_line(report_path: Path, file_path: str) -> dict:
    """Return the Survived mutants for one source file, clustered by source
    line, from a Stryker-shaped mutation report on disk.

    See ``_survivors_by_line_from_data`` for the return shape and ordering
    rule.
    """
    return _survivors_by_line_from_data(load_report(report_path), file_path)


def _accepted_static_survivors_from_data(
    data: dict, file_path: str, *, skip_static_active: bool
) -> list[dict]:
    """Return each Survived mutant carrying ``static: true`` for one source
    file as an accepted-survivor entry, from an already-parsed report dict.

    ``skip_static_active`` is the required evidence that a static-flagged
    survivor was *deliberately* deferred, not merely present. Stryker's
    ``static: true`` flag alone proves nothing about operator intent — the
    deliberateness lives one layer up, in whether the CLI's own
    ``--skip-static`` flag was active for this run. When
    ``skip_static_active`` is ``False``, this function returns ``[]``
    immediately, before any other computation: a run where the skip was
    never active has no accepted survivors to report, regardless of how many
    mutants carry ``static: true``. When ``True``, behavior matches the
    unconditional version this function used to be.

    Matches ``file_path`` against report keys the same way
    ``_survivors_from_data`` does (via ``_find_file_entry`` — exact key, then
    basename). Only a mutant with ``status == STATUS_SURVIVED`` *and*
    ``mutant.get(MUTANT_STATIC_KEY) is True`` qualifies — a
    Killed/Timeout/NoCoverage/CompileError mutant carrying ``static: true``
    is never returned, and a Survived mutant without the static flag is
    never returned either.

    Each entry has the shape ``{"id": ..., "file": str, "line": int | None,
    "operator": str, "status": ACCEPTED_STATIC_ENTRY_STATUS, "reason":
    ACCEPTED_STATIC_REASON}``. ``id`` is the mutant's own ``"id"`` field
    (``None`` when absent) — stable mutant identity, not just a file/line
    pair. ``file`` is the *matched report key* (from ``_find_file_entry``),
    not an echo of the caller's ``file_path`` argument — a caller that
    passed a basename gets back the full report key. ``line`` is resolved
    via ``_resolve_survivor_line`` (``None`` for any missing/malformed
    location/start/line shape — never raises).

    Returns ``[]`` when the file is not in the report or has no matching
    survivors.
    """
    if not skip_static_active:
        return []

    entry = _find_file_entry(data, file_path)
    if entry is None:
        return []
    matched_key, info = entry

    return [
        {
            "id": mutant.get("id"),
            "file": matched_key,
            "line": _resolve_survivor_line(mutant),
            "operator": mutant.get("mutatorName", ""),
            "status": ACCEPTED_STATIC_ENTRY_STATUS,
            "reason": ACCEPTED_STATIC_REASON,
        }
        for mutant in info.get("mutants", [])
        if mutant.get("status") == STATUS_SURVIVED
        and mutant.get(MUTANT_STATIC_KEY) is True
    ]


def accepted_static_survivors(
    report_path: Path, file_path: str, *, skip_static_active: bool
) -> list[dict]:
    """Return each Survived mutant carrying ``static: true`` for one source
    file, as accepted-survivor entries, from a Stryker-shaped mutation
    report on disk.

    See ``_accepted_static_survivors_from_data`` for the return shape,
    matching rule, and the required ``skip_static_active`` gating.
    """
    return _accepted_static_survivors_from_data(
        load_report(report_path), file_path, skip_static_active=skip_static_active
    )


def accepted_static_survivors_from_data(
    data: dict, file_path: str, *, skip_static_active: bool
) -> list[dict]:
    """Return each Survived mutant carrying ``static: true`` for one source
    file, as accepted-survivor entries, from an already-parsed report dict.

    Thin public wrapper around ``_accepted_static_survivors_from_data``,
    mirroring the established pair-per-function convention set by
    ``survivors_by_mutator``/``survivors_by_mutator_from_data``. Called by
    the CLI's ``--accepted-static-survivors`` branch, which already holds a
    parsed report (loaded once to run
    ``_maybe_warn_skip_static_inapplicable`` first) and reuses that dict
    here instead of triggering a second, redundant ``load_report`` call.
    """
    return _accepted_static_survivors_from_data(
        data, file_path, skip_static_active=skip_static_active
    )


def _files_with_status_from_data(data: dict, status: str) -> list[str]:
    """Return the sorted report file keys having >= 1 mutant of ``status``,
    from an already-parsed report dict.

    The report keys are the file identifiers exactly as the tool emits them
    (relative source paths); the caller decides how to interpret them.
    """
    return sorted(
        key
        for key, info in data.get("files", {}).items()
        if any(m.get("status") == status for m in info.get("mutants", []))
    )


def _files_with_status(report_path: Path, status: str) -> list[str]:
    """Return the sorted report file keys having >= 1 mutant of ``status``,
    from a Stryker-shaped mutation report on disk. Returns ``[]`` for an
    absent/empty report — never raises."""
    return _files_with_status_from_data(load_report(report_path), status)


def files_with_survivors(report_path: Path) -> list[str]:
    """Return the sorted report file keys that have >= 1 Survived mutant.

    This is the single source of truth for survivor-file discovery — sibling
    modules call it instead of re-walking the report (AC4).
    """
    return _files_with_status(report_path, STATUS_SURVIVED)


def files_with_timeouts(report_path: Path) -> list[str]:
    """Return the sorted report file keys that have >= 1 Timeout mutant.

    This is the single source of truth for timeout-file discovery — sibling
    modules call it instead of re-walking the report (AC4).
    """
    return _files_with_status(report_path, STATUS_TIMEOUT)


# =============================================================================
# mutmut — no native JSON report; junitxml is its only structured output.
# =============================================================================
def _testcase_to_entry(testcase) -> tuple[str, dict] | None:
    """Derive the status and build the mutant dict for one ``<testcase>``
    element from ``mutmut junitxml`` output.

    Returns ``None`` when the testcase carries no ``file`` attribute — there
    is nothing to key it into the ``files`` dict by, so it is skipped.

    mutmut marks a survived mutant with a ``<failure>`` child
    (``message="bad_survived"``) and a timed-out mutant with a distinct
    ``<error>`` child (``message="bad_timeout"``, ``error_type="timeout"``) —
    the two are never conflated, so a real Timeout is never miscounted as a
    Survived. Every other ``<testcase>`` — including a suspicious-but-ignored
    mutant under mutmut's default ``suspicious_policy="ignore"`` — is Killed;
    mutmut's default reporting granularity cannot distinguish "cleanly
    killed" from "suspicious but ignored" any further than that.
    """
    file_key = testcase.get("file")
    if not file_key:
        return None
    if testcase.find("failure") is not None:
        status = STATUS_SURVIVED
    elif testcase.find("error") is not None:
        status = STATUS_TIMEOUT
    else:
        status = STATUS_KILLED
    line = testcase.get("line")
    mutant = {
        "id": testcase.get("name", "?"),
        "mutatorName": "mutmut",
        "status": status,
        "location": {
            "start": {"line": int(line) if line and line.isdigit() else None}
        },
        "replacement": "",
    }
    return file_key, mutant


def parse_mutmut_junitxml(xml_text: str) -> dict:
    """Convert ``mutmut junitxml`` output into the internal ``{"files": {...}}``
    shape every scoring/survivor function above already consumes.

    mutmut has no NoCoverage concept (it always runs the full scoped test
    command against every mutant), so that count is always zero here.

    Malformed or empty input returns an empty ``{"files": {}}`` rather than
    raising — callers see it as an empty report, same as a missing file.
    """
    files: dict[str, dict] = {}
    if not xml_text.strip():
        return {"files": files}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"files": files}

    for testcase in root.iter("testcase"):
        entry = _testcase_to_entry(testcase)
        if entry is None:
            continue
        file_key, mutant = entry
        files.setdefault(file_key, {"mutants": []})["mutants"].append(mutant)

    return {"files": files}


def score_mutmut_junitxml(xml_text: str) -> ScoreSummary:
    """Compute the honest and reported scores directly from ``mutmut
    junitxml`` output (no report file on disk needed)."""
    return _score_data(parse_mutmut_junitxml(xml_text))


def survivors_from_mutmut_junitxml(
    xml_text: str, file_path: str
) -> dict[str, list[dict]]:
    """Return the Survived mutants for one file from ``mutmut junitxml``
    output, grouped by mutator name (always ``"mutmut"`` — the tool names no
    per-mutation operator the way Stryker/pitest do)."""
    return _survivors_from_data(parse_mutmut_junitxml(xml_text), file_path)
