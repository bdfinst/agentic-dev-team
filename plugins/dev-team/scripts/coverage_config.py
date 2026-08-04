#!/usr/bin/env python3
r"""coverage_config.py — shared multi-project coverage discovery config (#1780).

The foundation both stacks' discovery slices build on:

* `coverage_discovery_dotnet.py` — `.sln` solutions (#1781)
* `coverage_discovery_js.py` — npm/yarn/pnpm/Lerna workspaces (#1782)

Root-cause fix for #1759: a hand-picked, never-revisited project exclusion let a
real coverage delta be underreported ~30x. Nothing here holds a frozen project
list — discovery is re-derived every run, and this module reconciles that fresh
discovery against a persisted, human-reasoned `coverage-config.json`:

    {
      "included": ["<project-or-package-path>", ...],
      "excluded": [{"path": "<path>", "reason": "<human-readable>"}],
      "bootstrapped_at": "<ISO-8601>"
    }

The four operations, in the order a caller uses them:

1. `load_or_bootstrap()` — read the config, or bootstrap it from a fresh
   discovery pass (everything included, zero exclusions) when it is absent or
   unreadable. Never overwrites a *valid* existing config.
2. `drift_check()` — hard-fail on a discovered project that is in neither list,
   or a config entry that contradicts itself; warn on a stale exclusion.
3. `weighted_merge()` — merge per-project coverage weighted by statement/branch
   counts. Never a simple average.
4. `measurement_basis_notice()` — flag a delta measured against a baseline that
   predates this feature's bootstrap, and is therefore not comparable.

Path identity is an **exact, unmodified string match**. There is deliberately no
cross-stack path normalization: `tests/A/A.csproj` and `tests\A\A.csproj` are
different identities. Each stack's discovery emits paths in its own native form
and the config records exactly what discovery emitted, so a silent normalization
bug can never make an unaccounted-for project look accounted for.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import NamedTuple, NoReturn

# ---------------------------------------------------------------------------
# Shared constants, enum, and error helper
# ---------------------------------------------------------------------------

CONFIG_FILENAME = "coverage-config.json"

#: The pinned, shared wire format for every timestamp this feature writes.
ISO_8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class _NotApplicable:
    """Type of the `DISCOVERY_NOT_APPLICABLE` singleton."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "DISCOVERY_NOT_APPLICABLE"

    def __bool__(self) -> bool:
        return False


#: Returned by a stack's `discover()` when that stack's multi-project signal is
#: absent (no `.sln`, no workspace config) — the caller keeps its existing
#: single-command path untouched. Callers compare with `is`, so this must stay a
#: single shared object; an empty list would be indistinguishable from
#: "multi-project repo where discovery found nothing", which is a hard failure.
DISCOVERY_NOT_APPLICABLE = _NotApplicable()


class TestClassification(Enum):
    """How confidently a discovered project was classified by structural marker."""

    __test__ = False  # not a pytest collection target

    #: Marker found, unconditionally — definitely a real test project.
    TEST = "test"
    #: No marker anywhere — definitely not a test project.
    NOT_TEST = "not_test"
    #: Marker found behind a condition this discovery never evaluates. Never
    #: silently negative: a human must decide.
    AMBIGUOUS = "ambiguous"


class DiscoveryError(RuntimeError):
    """A hard-failure condition. CLI entry points catch this and report
    `error: <message>` — never a raw traceback."""


def discovery_error(message: str) -> NoReturn:
    """Raise a `DiscoveryError`. The single, shared way every discovery path
    signals a hard failure, so no caller has to invent its own exception type."""
    raise DiscoveryError(message)


class DiscoveredProject(NamedTuple):
    """One project/package a discovery pass found, with its classification.

    `path` is the stack-native identity string, recorded verbatim.
    """

    path: str
    classification: TestClassification


def needs_accounting(classification: TestClassification) -> bool:
    """True when a classification obliges the config to account for the project.

    `AMBIGUOUS` counts: an undecidable marker must reach a human, never be
    treated as a silent negative (that is the #1759 failure shape).
    """
    return classification in (TestClassification.TEST, TestClassification.AMBIGUOUS)


# ---------------------------------------------------------------------------
# Operator-visible message templates. Verbatim by contract — tests pin them and
# `coverage-baseline`/`coverage-delta` print them as their own distinct block.
# ---------------------------------------------------------------------------

BOOTSTRAP_NOTICE_TEMPLATE = (
    "coverage-config.json was absent — bootstrapped it from a fresh discovery pass at "
    "{bootstrapped_at} with {count} discovered project(s) in 'included' and zero "
    "exclusions. Review {config_path} and record a reason for anything that should not "
    "be measured; from now on a newly-discovered project in neither list is a hard "
    "failure."
)

BOOTSTRAP_AFTER_UNREADABLE_NOTICE_TEMPLATE = (
    "coverage-config.json at {config_path} could not be read as a valid config "
    "({reason}) — treated as absent and re-bootstrapped from a fresh discovery pass at "
    "{bootstrapped_at} with {count} discovered project(s) in 'included' and zero "
    "exclusions. Any exclusion reasons the unreadable file held are gone; re-record "
    "them before the next run."
)

UNACCOUNTED_TEST_PROJECT_TEMPLATE = (
    "unaccounted-for test project: {path}. Discovery classified it as a real test "
    "project by structural marker, but it appears in neither 'included' nor 'excluded' "
    "in coverage-config.json. Add it to 'included' to measure its coverage, or add an "
    "'excluded' entry {{\"path\": \"{path}\", \"reason\": \"<why its coverage is not "
    "measured>\"}}. No baseline is written until this is resolved."
)

UNACCOUNTED_AMBIGUOUS_PROJECT_TEMPLATE = (
    "unaccounted-for ambiguous project: {path}. Discovery found a test marker it could "
    "not resolve mechanically — the reference is conditioned, and this discovery never "
    "evaluates build conditions — so the project is neither definitely a test project "
    "nor definitely not one. A human must decide: add it to 'included' if it is a real "
    "test project, or add an 'excluded' entry {{\"path\": \"{path}\", \"reason\": "
    "\"<why its coverage is not measured>\"}} if it is not. No baseline is written "
    "until this is resolved."
)

CONFLICTING_ENTRY_TEMPLATE = (
    "conflicting coverage-config.json entry: {path} appears in both 'included' and "
    "'excluded'. Remove it from exactly one — a project cannot be both measured and "
    "deliberately skipped. No baseline is written until this is resolved."
)

EXCLUSION_MISSING_REASON_TEMPLATE = (
    "reasonless coverage-config.json exclusion: {path} is excluded with no reason "
    "recorded. An exclusion is only accepted when it says why the project's coverage "
    "is not measured, so a human can question it later. Fill in the 'reason', or move "
    "the path to 'included'. No baseline is written until this is resolved."
)

STALE_EXCLUSION_TEMPLATE = (
    "stale exclusion: {path} is recorded as excluded (reason: {reason}) but no longer "
    "matches any discovered project. Remove the entry, or correct its path if the "
    "project moved. This is a warning, not a failure — the run continues."
)

MEASUREMENT_BASIS_NOTICE_TEMPLATE = (
    "measurement basis: the baseline was captured at {captured_at}, which predates the "
    "multi-project discovery bootstrap at {bootstrapped_at}. That baseline may reflect "
    "a single project rather than the full merged set, so a delta against it is not "
    "comparable — re-capture the baseline before treating this delta as authoritative."
)


# ---------------------------------------------------------------------------
# ISO-8601 helpers — one pinned format, shared by every artifact this writes
# ---------------------------------------------------------------------------


def format_iso8601(moment: datetime) -> str:
    """Render an instant in the pinned shared format (UTC, second precision)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(ISO_8601_FORMAT)


def utc_now_iso() -> str:
    """Now, in the pinned shared format."""
    return format_iso8601(datetime.now(tz=timezone.utc))


def parse_iso8601(value: str) -> datetime:
    """Parse a timestamp into a timezone-aware UTC `datetime`.

    Strict on the pinned format first, then tolerant of the wider ISO-8601
    shapes real coverage artifacts carry (explicit offsets, microseconds), so a
    pre-existing `baseline-coverage.json` written before this feature still
    compares. A value that parses as neither is a hard failure naming it — a
    malformed timestamp in our own artifact is a bug, not something to guess at.
    """
    try:
        return datetime.strptime(value, ISO_8601_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    # `datetime.fromisoformat` does not accept a trailing `Z` before 3.11.
    candidate = value[:-1] + "+00:00" if isinstance(value, str) and value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except (TypeError, ValueError):
        discovery_error(
            f"unparseable timestamp {value!r} — expected the pinned ISO-8601 format "
            f"{ISO_8601_FORMAT!r} (e.g. 2026-08-04T12:00:00Z)"
        )
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# load_or_bootstrap
# ---------------------------------------------------------------------------


class ConfigLoad(NamedTuple):
    """Outcome of `load_or_bootstrap`."""

    config: dict
    #: Operator-visible notice, or `None` when a valid config was simply read.
    notice: str | None
    bootstrapped: bool


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON via temp-file-then-rename, so a reader never observes a
    partially-written file — the same convention `baseline-coverage.json` uses."""
    # Serialize before the temp file exists, so an unserializable payload cannot
    # leave a stray `.tmp` behind — the failure the cleanup branch below cannot
    # catch, because `json.dumps` raises `TypeError`/`ValueError`, not `OSError`.
    payload = json.dumps(data, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(payload)
        os.replace(tmp_name, path)
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def config_shape_problem(config: object) -> str | None:
    """Return a human-readable reason the value is not a usable config, or
    `None` when the shape is fine. Shape problems are treated exactly like a
    missing file (bootstrap), never like a drift failure — a config we cannot
    read is not evidence about the projects.

    The recognized-shape check is deliberately positive rather than permissive:
    an object must actually carry this feature's keys. Otherwise a *different*
    tool's file of the same name — notably the legacy
    `{"known_projects": [...], "exclusions": [...]}` config that
    `skills/coverage-baseline/scripts/discover_coverage_projects.py` (#1759)
    writes — would read as an empty-but-valid config, and every discovered
    project would then hard-fail as unaccounted-for while the operator's real
    exclusion reasons sat unread in the keys we ignored.
    """
    if not isinstance(config, dict):
        return "top-level value is not an object"
    if "included" not in config and "excluded" not in config:
        return (
            "object carries neither 'included' nor 'excluded' — not a "
            "coverage-config.json for multi-project coverage discovery"
        )
    included = config.get("included", [])
    if not isinstance(included, list):
        return "'included' is not a list"
    if any(not isinstance(entry, str) for entry in included):
        return "'included' contains a non-string entry"
    excluded = config.get("excluded", [])
    if not isinstance(excluded, list):
        return "'excluded' is not a list"
    for entry in excluded:
        if not isinstance(entry, dict):
            return f"'excluded' entry is not an object: {entry!r}"
        if "path" not in entry:
            return f"'excluded' entry has no 'path': {entry!r}"
        if not isinstance(entry["path"], str):
            return f"'excluded' entry 'path' is not a string: {entry!r}"
        if "reason" in entry and not isinstance(entry["reason"], str):
            return f"'excluded' entry 'reason' is not a string: {entry!r}"
    bootstrapped_at = config.get("bootstrapped_at")
    if not isinstance(bootstrapped_at, str) or not bootstrapped_at.strip():
        return "'bootstrapped_at' is absent or not a non-empty string"
    return None


def load_or_bootstrap(
    config_path: Path,
    discovered_projects: Sequence[DiscoveredProject],
    now_iso: str,
) -> ConfigLoad:
    """Read `coverage-config.json`, or bootstrap it from this run's discovery.

    A valid existing config is returned untouched — never overwritten, so a
    human's recorded exclusions and reasons survive every run.

    An absent config bootstraps: every discovered project that
    `needs_accounting()` goes into `included`, `excluded` is empty, and
    `bootstrapped_at` records when. This is what keeps a pre-existing workflow
    from hard-failing the moment this feature ships (epic #1766, criterion 5).

    An unreadable config (bad JSON, or valid JSON of the wrong shape) is treated
    as absent and re-bootstrapped, matching `/coverage-baseline` Step 2's
    established "malformed tracked artifact → capture fresh" convention. The
    returned notice names why, because re-bootstrapping discards whatever
    exclusion reasons the unreadable file held.
    """
    if discovered_projects is DISCOVERY_NOT_APPLICABLE:
        discovery_error(
            "load_or_bootstrap was handed DISCOVERY_NOT_APPLICABLE. A caller must check "
            "`result is DISCOVERY_NOT_APPLICABLE` and keep its single-command path "
            "instead of reconciling a config that should not exist for this repo."
        )

    problem: str | None = None
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problem = str(exc)
        else:
            problem = config_shape_problem(raw)
            if problem is None:
                return ConfigLoad(config=raw, notice=None, bootstrapped=False)

    included = sorted(
        project.path
        for project in discovered_projects
        if needs_accounting(project.classification)
    )
    config = {"included": included, "excluded": [], "bootstrapped_at": now_iso}
    atomic_write_json(config_path, config)

    if problem is None:
        notice = BOOTSTRAP_NOTICE_TEMPLATE.format(
            bootstrapped_at=now_iso, count=len(included), config_path=config_path
        )
    else:
        notice = BOOTSTRAP_AFTER_UNREADABLE_NOTICE_TEMPLATE.format(
            config_path=config_path,
            reason=problem,
            bootstrapped_at=now_iso,
            count=len(included),
        )
    return ConfigLoad(config=config, notice=notice, bootstrapped=True)


# ---------------------------------------------------------------------------
# drift_check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriftReport:
    """Result of reconciling a fresh discovery against the persisted config."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """False when the caller must stop and write no baseline."""
        return not self.errors


def drift_check(
    config: dict, discovered_projects: Sequence[DiscoveredProject]
) -> DriftReport:
    """Reconcile a fresh discovery pass against the persisted config.

    Hard failures (caller stops, writes no baseline):

    * a discovered `TEST` project in neither `included` nor `excluded`
    * a discovered `AMBIGUOUS` project in neither list — reported with a
      distinct message, because "we could not decide" needs a different human
      response from "we know this is a test project"
    * a path in both `included` and `excluded`
    * an `excluded` entry with no reason recorded

    Warning (non-blocking): an `excluded` entry matching no discovered project.
    Surfacing it every run is what keeps an exclusion questionable by a human;
    this check deliberately does not try to decide whether a *reason* has gone
    stale (epic #1766 non-goal).

    Messages are ordered by path so two runs over the same inputs produce
    byte-identical output.
    """
    included = set(config.get("included", []))
    excluded_entries = list(config.get("excluded", []))
    excluded_reasons = {entry["path"]: entry.get("reason") for entry in excluded_entries}
    accounted = included | set(excluded_reasons)

    errors: list[str] = []
    warnings: list[str] = []

    for path in sorted(included & set(excluded_reasons)):
        errors.append(CONFLICTING_ENTRY_TEMPLATE.format(path=path))

    # Per *entry*, not per collapsed path: two entries for the same path must not
    # let a later reasoned one mask an earlier reasonless one (or vice versa —
    # the outcome would otherwise depend on entry order).
    reasonless = {
        entry["path"]
        for entry in excluded_entries
        if not str(entry.get("reason") or "").strip()
    }
    for path in sorted(reasonless - included):
        # A path already reported as a conflict gets one message, not two.
        errors.append(EXCLUSION_MISSING_REASON_TEMPLATE.format(path=path))

    for project in sorted(discovered_projects, key=lambda item: item.path):
        if not needs_accounting(project.classification):
            continue
        if project.path in accounted:
            continue
        template = (
            UNACCOUNTED_AMBIGUOUS_PROJECT_TEMPLATE
            if project.classification is TestClassification.AMBIGUOUS
            else UNACCOUNTED_TEST_PROJECT_TEMPLATE
        )
        errors.append(template.format(path=project.path))

    discovered_paths = {project.path for project in discovered_projects}
    for path in sorted(set(excluded_reasons) - discovered_paths):
        warnings.append(
            STALE_EXCLUSION_TEMPLATE.format(path=path, reason=excluded_reasons[path])
        )

    return DriftReport(errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# weighted_merge
# ---------------------------------------------------------------------------

_MERGE_DIMENSIONS = (
    ("line_pct", "statements_total"),
    ("branch_pct", "branches_total"),
)


#: Every key a per-project coverage report must carry. Presence is required
#: rather than defaulted: a producer that misspells or omits `statements_total`
#: would otherwise contribute weight 0 and drop silently out of the merged
#: percentage — the underreporting shape this whole module exists to prevent.
_REQUIRED_REPORT_KEYS = (
    "path",
    "line_pct",
    "statements_total",
    "branch_pct",
    "branches_total",
)


def _validated_count(report: dict, key: str) -> int:
    value = report[key]
    if isinstance(value, bool) or not isinstance(value, int):
        discovery_error(
            f"project coverage report for {report.get('path')!r} has a non-integer "
            f"{key}: {value!r}"
        )
    if value < 0:
        discovery_error(
            f"project coverage report for {report.get('path')!r} has a negative "
            f"{key}: {value!r}"
        )
    return value


def _validated_pct(report: dict, key: str) -> float | None:
    value = report.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        discovery_error(
            f"project coverage report for {report.get('path')!r} has a non-numeric "
            f"{key}: {value!r}"
        )
    if not 0.0 <= float(value) <= 100.0:
        discovery_error(
            f"project coverage report for {report.get('path')!r} has an out-of-range "
            f"{key}: {value!r} (expected 0-100)"
        )
    return float(value)


def weighted_merge(project_reports: Sequence[dict]) -> dict:
    """Merge per-project coverage into one percentage per dimension, weighted by
    each project's total statement/branch count.

    A simple average is provably wrong across differently-sized projects: a
    10-statement project at 100% and a 1000-statement project at 50% merge to
    ~50.5%, not 75%. That gap is the #1759 incident in miniature.

    Each report must carry all of `{"path", "line_pct", "statements_total",
    "branch_pct", "branches_total"}` — a missing key is a hard failure, never a
    zero-weighted silent skip. A `None` percentage means the project did not
    measure that dimension, and its weight is excluded from that dimension only
    — so one branchless project cannot drag the merged branch number toward
    zero. When no project measured a dimension, that merged percentage is `None`.

    The returned `statements_total`/`branches_total` are the **denominators of
    the returned percentages**: they sum only the projects that actually
    contributed to that dimension. A consumer can therefore reconstruct covered
    counts as `pct * total / 100` without over-counting a project whose
    percentage was excluded.

    An empty input is a hard failure, not a `None` baseline: "no test projects
    were included" must never be persisted as a measurement.
    """
    if not project_reports:
        discovery_error(
            "cannot merge coverage: no included test projects were measured. Discovery "
            "recognizes a real test project only by its structural marker — see "
            "coverage-baseline/references/multi-project-discovery.md for the exact "
            "markers per stack — so either the config excludes every project, or no "
            "project carries a marker."
        )

    for report in project_reports:
        missing = [key for key in _REQUIRED_REPORT_KEYS if key not in report]
        if missing:
            discovery_error(
                "project coverage report is missing required key(s) "
                f"{', '.join(missing)}: {report!r}"
            )
        if not isinstance(report["path"], str):
            discovery_error(
                f"project coverage report 'path' is not a string: {report['path']!r}"
            )

    merged: dict = {}
    for pct_key, total_key in _MERGE_DIMENSIONS:
        weight_sum = 0
        covered_sum = 0.0
        for report in project_reports:
            total = _validated_count(report, total_key)
            pct = _validated_pct(report, pct_key)
            if pct is None or total == 0:
                continue
            weight_sum += total
            covered_sum += total * pct / 100.0
        merged[pct_key] = (
            round(covered_sum / weight_sum * 100.0, 2) if weight_sum else None
        )
        merged[total_key] = weight_sum

    merged["projects"] = sorted(report["path"] for report in project_reports)
    return merged


# ---------------------------------------------------------------------------
# measurement_basis_notice
# ---------------------------------------------------------------------------


def measurement_basis_notice(
    bootstrapped_at: str | None, captured_at: str | None
) -> str | None:
    """Notice when a baseline predates this feature's config bootstrap.

    A baseline captured before discovery existed may reflect a single project
    rather than the merged set, so a delta against it is not comparable. Fires
    only when `captured_at` is strictly earlier than `bootstrapped_at`; returns
    `None` when either timestamp is absent (nothing to compare) and hard-fails
    on a timestamp that parses as neither the pinned format nor wider ISO-8601.
    """
    if not bootstrapped_at or not captured_at:
        return None
    if parse_iso8601(captured_at) >= parse_iso8601(bootstrapped_at):
        return None
    return MEASUREMENT_BASIS_NOTICE_TEMPLATE.format(
        bootstrapped_at=bootstrapped_at, captured_at=captured_at
    )
