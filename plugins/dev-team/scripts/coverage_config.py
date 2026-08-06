#!/usr/bin/env python3
"""coverage_config.py — shared coverage-config module for multi-project
coverage discovery (issue #1759).

`coverage-baseline` and `coverage-delta` previously relied on a single,
hand-maintained coverage command per manifest. For a multi-project .NET
solution or JS/TS workspace, that meant a hand-picked, never-revisited
inclusion/exclusion list — the incident's root cause. This module owns the
mechanics both skills share: bootstrapping/loading `coverage-config.json`,
drift-checking it against fresh discovery, weighted-merging per-project
coverage reports, and flagging a changed measurement basis after a
bootstrap.

**Identity contract.** An accounting unit's "path" is always the exact,
unmodified string the corresponding `discover_*` function returns for that
entry — whatever each stack calls the unit natively (a .NET *project*, a JS/TS
*package*, a Maven *module*, a Gradle *subproject*). No cross-stack
normalization, case-folding, or
separator translation is ever applied when matching a discovered path
against `included`/`excluded` entries — a POSIX-style path and an arbitrary
opaque label are both treated as opaque strings and compared for exact
equality only.

Stdlib-only (ADR 0014/0015).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class TestClassification(Enum):
    """How a discovered project/package was classified by a `discover_*`
    function. `AMBIGUOUS` covers markers this repo's discovery deliberately
    declines to resolve with certainty (e.g. a conditioned MSBuild property)
    — it is never treated as a negative ("not a test project") result."""

    TEST = "test"
    NOT_TEST = "not_test"
    AMBIGUOUS = "ambiguous"


def needs_accounting(classification: TestClassification) -> bool:
    """True when a discovered project must appear in `included` or
    `excluded` (with a reason) — true for `TEST` and `AMBIGUOUS`, false only
    for `NOT_TEST`."""
    return classification in (TestClassification.TEST, TestClassification.AMBIGUOUS)


# Shared discovery-result signals — one canonical contract, imported by every
# `coverage_discovery_<stack>.py` module rather than each independently
# converging on a matching shape.
DISCOVERY_NOT_APPLICABLE = {"signal": "not_applicable"}


def discovery_error(message: str) -> dict:
    """Return the shared discovery-error signal shape, naming `message`."""
    return {"signal": "error", "message": message}


def is_within(resolved: Path, root: Path) -> bool:
    """True when `resolved` (already resolved — this performs no resolution
    of its own) equals `root` or is nested inside it. The shared containment
    predicate every `discover_<stack>` module applies before reading or
    classifying a resolved path — previously factored only in
    `coverage_discovery_java.py` and open-coded independently in
    `coverage_discovery_js.py` and `coverage_discovery_dotnet.py` (issues
    #1839/#1848/#1851).

    Canonical argument order — read this before adding a new call site:
    `is_within(item, container)`. The FIRST argument is the path whose
    containment is being checked; the SECOND is the directory it must be
    inside. Equivalently, `is_within(item, container)` reads as "is `item`
    within `container`?" — same order as `coverage_discovery_dotnet.py`'s and
    `stryker_shard_setup.py`'s calls. #1903 found an independent
    reimplementation in `run_integration_eval.py` with this order inverted
    (container first); that inversion is exactly what a reader moving
    between files cannot safely assume is consistent, hence this note.
    """
    return resolved == root or root in resolved.parents


# Namespace prefix stripped by `local_name` below. Anchored to a leading
# `{...}` only, rather than searching for the LAST `}` in the tag string —
# the anchored form is what stays correct for a local name that itself
# legitimately contains `}` (never happens in practice, but the anchoring
# costs nothing and is strictly safer).
_XML_NS_RE = re.compile(r"^\{[^}]*\}")


def local_name(tag) -> str:
    """The namespace-stripped local name of an ElementTree tag (`{ns}Tag` ->
    `Tag`). Tolerates a non-`str` tag (returns `""`) — ElementTree gives
    comment/processing-instruction nodes a non-string, callable `tag`, which
    a `tag.split("}", 1)`-style implementation raises on. The shared,
    canonical implementation: `coverage_discovery_java.py` originally had
    this exact regex-anchored, non-str-safe version; `coverage_discovery_dotnet.py`
    had a second, less-safe `tag.split("}", 1)[-1]` implementation (issues
    #1839/#1848/#1851)."""
    return _XML_NS_RE.sub("", tag if isinstance(tag, str) else "")


# A build file consumed by discovery never legitimately carries a DOCTYPE or
# ENTITY declaration — presence of either is a zero-false-positive signal of
# an entity-expansion attempt, not a legitimate build file.
UNSAFE_XML_MARKERS = ("<!DOCTYPE", "<!ENTITY")


def find_unsafe_xml_marker(data: bytes):
    """Return the first disallowed marker (`UNSAFE_XML_MARKERS`) found in
    `data`'s raw bytes, or in `data` decoded as UTF-16LE/UTF-16BE — the other
    encodings expat auto-detects and natively parses besides UTF-8.
    ASCII/Latin-1 are byte-identical to UTF-8 for these ASCII-only tokens, so
    no separate check is needed for those; decoding the raw bytes as Latin-1
    (a total, never-raising 1:1 byte<->codepoint mapping) covers the
    UTF-8/ASCII/Latin-1 case in one pass. Returns `None` when no marker is
    found in any of the three views."""
    raw_text = data.decode("latin-1")
    utf16le_text = data.decode("utf-16le", errors="ignore")
    utf16be_text = data.decode("utf-16be", errors="ignore")
    for marker in UNSAFE_XML_MARKERS:
        if marker in raw_text or marker in utf16le_text or marker in utf16be_text:
            return marker
    return None


def read_and_screen_xml(path: Path):
    """Read `path` ONCE as bytes and screen the FULL content — never only a
    fixed-size prefix — for a disallowed `<!DOCTYPE`/`<!ENTITY` declaration
    (XML entity-expansion hardening). `xml.etree.ElementTree` is explicitly
    not secure against maliciously constructed data, and discovery parses
    repository-supplied build files, so every stack's XML read routes through
    this one screen.

    Returns `(data, None)` when the file looks safe to parse — the caller
    parses these SAME already-read bytes via `ET.fromstring`, never re-opening
    `path`, which closes the check-then-use double-open gap a
    `read`-then-`ET.parse(path)` pair leaves open. Returns
    `(None, discovery_error(...))` otherwise (unreadable file, or a
    disallowed marker found).

    Shared by every discovery stack that parses repository-supplied XML — a
    second copy of this screen is a review finding, not a style choice: one
    stack once shipped without a screen at all, which is exactly the drift a
    single shared implementation prevents. Callers are deliberately not
    enumerated here; a shared helper should not name its consumers."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, discovery_error(f"Could not read '{path}': {exc}")
    marker = find_unsafe_xml_marker(data)
    if marker is not None:
        return None, discovery_error(
            f"Refusing to parse '{path}': contains a disallowed "
            f"'{marker}' declaration (XML entity-expansion hardening)."
        )
    return data, None


# `coverage-config.json`'s exclusion schema (`excluded: [{"path", "reason"}]`)
# is intentionally NOT the same schema as the sibling `mutation_exclude_policy.py`
# module's `mutation-exclude-policy.json` (`{schema_version, always: [...],
# propose_and_ask: [...]}`, unit key `file` rather than `path`) — issue #1853.
# The two are different bounded contexts (coverage-accounting ledger vs.
# mutation-exclude proposals) with no shared consumer today; do not assume
# they should be interchangeable or unify them.
def load_or_bootstrap(
    config_path: Path, discovered_projects: list, now_iso: str
) -> tuple:
    """Load `config_path`, or bootstrap it from `discovered_projects` if
    absent (including malformed/corrupt — treated as absent, matching
    `coverage-baseline`'s existing-baseline guard precedent).

    `discovered_projects` uses the SAME shape `drift_check` expects: a list
    of `{"path": ..., "classification": TestClassification}` entries. Only
    entries where `needs_accounting(classification)` is true are written to
    `included` — a `NOT_TEST` entry is correctly excluded, and the raw
    `TestClassification` enum value never reaches `atomic_write_json` (it is
    not JSON-serializable).

    Returns `(config, notice)`. `notice` is `None` when an existing config
    was read verbatim (no write happens on this path — `baseline-coverage.json`
    is never touched by this function either way). On bootstrap, `notice` is
    the exact operator-facing string naming how many projects were included.

    `now_iso` must use the identical ISO-8601 UTC format (with a literal `Z`
    suffix) as `baseline-coverage.json`'s `captured_at` values — this is what
    makes `measurement_basis_notice`'s later datetime comparison valid.

    **Concurrency.** Two invocations racing against the same absent
    `config_path` are mutually excluded by a create-exclusive `.lock`
    sibling file (`os.O_CREAT | os.O_EXCL`) rather than the plain existence
    check above, which is subject to a TOCTOU gap between the check and the
    write. The loser of the lock never writes — it re-reads `config_path`
    (the winner should have just written it) and returns that content
    instead of overwriting it. The lock file is removed in a `finally` by
    whichever call created it.
    """
    existing = _read_existing_config(config_path)
    if existing is not None:
        return existing, None

    included = [
        entry["path"]
        for entry in discovered_projects
        if needs_accounting(entry["classification"])
    ]
    config = {
        "schema_version": 1,
        "included": included,
        "excluded": [],
        "bootstrapped_at": now_iso,
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{config_path}.lock")
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # Another call is concurrently bootstrapping the same config path —
        # it should have just written config_path; return that content
        # rather than racing it to overwrite. If it hasn't written yet (a
        # genuinely stuck concurrent bootstrapper), fail loudly rather than
        # silently proceeding to overwrite.
        winner = _read_existing_config(config_path)
        if winner is not None:
            return winner, None
        raise RuntimeError(
            f"'{lock_path}' is held by a concurrent load_or_bootstrap call, "
            f"but '{config_path}' has not been written yet; refusing to "
            f"overwrite it. Re-run once the concurrent call completes."
        )

    try:
        os.close(lock_fd)
        # Double-checked locking: another call may have won the race between
        # our existence check above and acquiring this lock, written
        # config_path, and already released its own lock before we got here.
        # Re-check now, inside the lock, so we never overwrite that write.
        winner = _read_existing_config(config_path)
        if winner is not None:
            return winner, None
        atomic_write_json(config_path, config)
    finally:
        lock_path.unlink(missing_ok=True)

    notice = (
        f"coverage-config.json did not exist; created it from fresh discovery "
        f"with {len(included)} project(s) included and zero "
        f"exclusions. Review and add exclusions (with a reason) if any "
        f"project should not count toward coverage."
    )
    return config, notice


def _read_existing_config(config_path: Path) -> dict | None:
    """Return the parsed config, or `None` if absent/malformed."""
    if not config_path.is_file():
        return None
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_excluded(excluded_entries: list) -> list:
    """Normalize `excluded` entries to `{"path": ..., "reason": ...}` dicts,
    tolerating a bare path string (normalized to `{"path": s, "reason":
    ""}`) — the shared normalization `drift_check` and
    `format_active_exclusions` both need, extracted so they share one
    implementation rather than two byte-identical copies."""
    return [
        {"path": entry, "reason": ""} if isinstance(entry, str) else entry
        for entry in excluded_entries
    ]


def _validate_config_shape(config: dict) -> None:
    """Validate `config`'s `included`/`excluded` shape, raising `ValueError`
    naming the malformed field or entry. Extracted from `drift_check` so
    shape validation and drift computation are each independently readable
    — the same extraction precedent as `_format_hard_failure_message`/
    `_format_stale_warning` below (issue #1858). Raises before any drift
    computation runs; callers never see a partially-computed result on a
    malformed config."""
    included_list = config.get("included", [])
    excluded_entries = config.get("excluded", [])

    if "included" in config and not isinstance(config["included"], list):
        raise ValueError(
            "coverage-config.json \"included\" must be a list of path "
            f"strings; got {type(config['included']).__name__} instead."
        )
    if "excluded" in config and not isinstance(config["excluded"], list):
        raise ValueError(
            "coverage-config.json \"excluded\" must be a list of "
            "{\"path\": ..., \"reason\": ...} entries; got "
            f"{type(config['excluded']).__name__} instead."
        )

    for entry in included_list:
        if not isinstance(entry, str):
            raise ValueError(  # noqa: TRY004 — ValueError is the documented, tested contract for malformed config (see docstring; test_coverage_config.py asserts ValueError)
                "coverage-config.json \"included\" entries must all be "
                f"path strings; got {entry!r} instead."
            )
    for entry in excluded_entries:
        if not isinstance(entry, str) and (
            not isinstance(entry, dict) or "path" not in entry
        ):
            raise ValueError(
                "coverage-config.json \"excluded\" entries must all be a "
                "path string or a {\"path\": ..., \"reason\": ...} entry "
                f"carrying a \"path\" key; got {entry!r} instead."
            )


def drift_check(config: dict, discovered_projects: list) -> dict:
    """Compare `config`'s `included`/`excluded` entries against fresh
    `discovered_projects` (a list of `{"path": ..., "classification":
    TestClassification}` entries).

    Returns a structured result:

    - `unaccounted`: discovered paths needing accounting
      (`needs_accounting(classification)` true) that are in neither
      `included` nor `excluded`.
    - `unaccounted_ambiguous`: the subset of `unaccounted` classified
      `AMBIGUOUS`.
    - `conflicts`: paths present in both `included` and `excluded`.
    - `stale_exclusions`: `excluded` entries whose path no longer appears in
      `discovered_projects` at all (regardless of classification).
    - `hard_failure`: true iff `unaccounted` or `conflicts` is non-empty.
    - `hard_failure_message`: the exact operator-facing failure text, or
      `None` when `hard_failure` is false.
    - `stale_warning_message`: the exact non-blocking warning text (one
      line per stale entry), or `None` when `stale_exclusions` is empty.

    Malformed-but-parseable configs degrade gracefully rather than raising,
    matching `_read_existing_config`'s own "malformed → treated as absent"
    tolerance: a bare string in `excluded` (instead of `{"path": ...,
    "reason": ...}`) is normalized to `{"path": s, "reason": ""}`, and an
    excluded entry missing `"reason"` renders as `<no reason recorded>`
    rather than raising `KeyError`. A schema violation this module cannot
    silently coerce without failing in the wrong direction — `"included"` or
    `"excluded"` present but not a list at all — raises `ValueError` naming
    the malformed field, rather than degrading `path in included_list` to a
    substring test.
    """
    _validate_config_shape(config)

    included_list = config.get("included", [])
    excluded_entries = config.get("excluded", [])

    normalized_excluded = _normalize_excluded(excluded_entries)
    excluded_by_path = {entry["path"]: entry for entry in normalized_excluded}
    excluded_paths = set(excluded_by_path)
    included_paths = set(included_list)

    conflicts = [path for path in included_list if path in excluded_paths]

    unaccounted: list = []
    unaccounted_ambiguous: list = []
    for entry in discovered_projects:
        path = entry["path"]
        classification = entry["classification"]
        if not needs_accounting(classification):
            continue
        if path in included_paths or path in excluded_paths:
            continue
        unaccounted.append(path)
        if classification is TestClassification.AMBIGUOUS:
            unaccounted_ambiguous.append(path)

    discovered_paths = {entry["path"] for entry in discovered_projects}
    stale_exclusions = [
        excluded_by_path[path]
        for path in excluded_by_path
        if path not in discovered_paths
    ]

    hard_failure = bool(unaccounted) or bool(conflicts)
    hard_failure_message = (
        _format_hard_failure_message(unaccounted, unaccounted_ambiguous, conflicts)
        if hard_failure
        else None
    )
    stale_warning_message = (
        _format_stale_warning(stale_exclusions) if stale_exclusions else None
    )

    return {
        "unaccounted": unaccounted,
        "unaccounted_ambiguous": unaccounted_ambiguous,
        "conflicts": conflicts,
        "stale_exclusions": stale_exclusions,
        "hard_failure": hard_failure,
        "hard_failure_message": hard_failure_message,
        "stale_warning_message": stale_warning_message,
    }


def _format_hard_failure_message(
    unaccounted: list, unaccounted_ambiguous: list, conflicts: list
) -> str:
    """Build the exact operator-facing failure text for `drift_check`'s
    `unaccounted`/`conflicts` findings. Pure string formatting, extracted
    from `drift_check` so the data analysis above stays readable."""
    sentences = []
    if unaccounted:
        sentences.append(
            f"Coverage capture stopped: {len(unaccounted)} discovered "
            f"project(s) are not accounted for in coverage-config.json: "
            f"{', '.join(unaccounted)}. Add each to \"included\", or to "
            f"\"excluded\" with a \"reason\", then re-run."
        )
    if unaccounted_ambiguous:
        sentences.append(
            f"{len(unaccounted_ambiguous)} of these could not be classified "
            f"with certainty from their test markers: "
            f"{', '.join(unaccounted_ambiguous)}."
        )
    if conflicts:
        conflict_sentence = (
            f"{len(conflicts)} project(s) are listed in both "
            f"\"included\" and \"excluded\": {', '.join(conflicts)}. "
            f"Remove each from one list, then re-run."
        )
        if sentences:
            sentences.append(conflict_sentence)
        else:
            sentences.append(f"Coverage capture stopped: {conflict_sentence}")
    return " ".join(sentences)


def _format_stale_warning(stale_exclusions: list) -> str:
    """Build the exact non-blocking warning text for `drift_check`'s
    `stale_exclusions` — one line per entry, in `excluded`'s order. A
    missing `"reason"` (malformed-but-parseable config) renders as
    `<no reason recorded>` rather than raising `KeyError`."""
    return "\n".join(
        f"Warning: excluded entry '{entry['path']}' (reason: "
        f"'{entry.get('reason', '<no reason recorded>')}') no longer "
        f"matches any discovered project — it may have been removed, "
        f"renamed, or the config is out of date. This does not block the "
        f"run."
        for entry in stale_exclusions
    )


def format_active_exclusions(config: dict) -> str | None:
    """Render `config`'s currently-active `excluded` entries as one line per
    entry: `"Excluded: '<path>' (reason: '<reason>')"`, joined with
    newlines. Returns `None` when `excluded` is empty.

    This is informational, always-shown context — printed on EVERY run
    regardless of staleness — distinct from `drift_check`'s
    `stale_warning_message`, which flags a DIFFERENT problem: an excluded
    path no longer being discovered at all. An exclusion can be active
    (still discovered, reason unchanged) and still worth surfacing so an
    operator sees what is currently excluded and why, on every run — not
    only when something about it goes stale.

    Same bare-string/missing-`"reason"` tolerance as `_format_stale_warning`."""
    excluded_entries = config.get("excluded", [])
    if not excluded_entries:
        return None
    normalized = _normalize_excluded(excluded_entries)
    return "\n".join(
        f"Excluded: '{entry['path']}' (reason: "
        f"'{entry.get('reason', '<no reason recorded>')}')"
        for entry in normalized
    )


_WEIGHTED_MERGE_REQUIRED_FIELDS = (
    "covered_statements",
    "total_statements",
    "covered_branches",
    "total_branches",
)


def weighted_merge(project_reports: list) -> dict:
    """Merge per-project coverage reports, weighted by statement/branch
    count — never a per-project average.

    Each entry in `project_reports` carries `{covered_statements,
    total_statements, covered_branches, total_branches}` — a plain dict, or
    a `coverage_report_parse.CoverageRecord` (e.g. `aggregate()`'s output)
    consumed directly, with no translation layer, since both already use
    this same field-name vocabulary. Returns `{line_pct, branch_pct}`,
    summed across all reports before dividing. Either percentage is `None`
    (JSON `null`) when its total is 0 across all reports, matching
    `coverage-baseline`'s existing Go-coverage `null` convention. A field
    valued `None` in a per-project report (this repo's own Go-coverage
    convention for a tool with no native branch coverage) coerces to 0
    rather than raising `TypeError`, degrading to the same zero-total →
    `None` result.

    A count field **entirely absent** from a report dict is a different,
    louder case: it means the report is incomplete (a per-project report
    carrying only percentages with no raw counts), never the legitimate
    zero-total-for-this-metric convention above. This is validated in an
    upfront pass, before any summing, and returns the shared
    `discovery_error(...)` signal naming the missing field(s) rather than
    silently proceeding to a null/0 baseline — "key entirely absent" and
    "key present with value `None`" must never be treated identically.
    """
    project_reports = [
        dataclasses.asdict(report) if dataclasses.is_dataclass(report) else report
        for report in project_reports
    ]
    for report in project_reports:
        missing_fields = [
            field for field in _WEIGHTED_MERGE_REQUIRED_FIELDS if field not in report
        ]
        if missing_fields:
            return discovery_error(
                f"Coverage report is missing required count field(s): {missing_fields}"
            )

    total_statements = sum(
        (report.get("total_statements") or 0) for report in project_reports
    )
    covered_statements = sum(
        (report.get("covered_statements") or 0) for report in project_reports
    )
    total_branches = sum(
        (report.get("total_branches") or 0) for report in project_reports
    )
    covered_branches = sum(
        (report.get("covered_branches") or 0) for report in project_reports
    )

    line_pct = (
        covered_statements / total_statements * 100 if total_statements else None
    )
    branch_pct = covered_branches / total_branches * 100 if total_branches else None

    return {"line_pct": line_pct, "branch_pct": branch_pct}


def _parse_iso8601(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, substituting a trailing `Z` with
    `+00:00` first (`datetime.fromisoformat` doesn't accept a bare `Z`).
    Returns `None` on any unparseable input rather than raising — callers
    treat that as "cannot compare, no notice".

    A parsed value with no timezone (naive — no explicit `Z`/offset in the
    input) is assumed UTC. `bootstrapped_at` is always `Z`-suffixed (per
    `load_or_bootstrap`), but `captured_at` may come from a pre-existing
    `baseline-coverage.json` written before this feature, with no timezone
    guarantee at all — comparing a naive and an aware `datetime` raises
    `TypeError`, so every value returned here is aware, treating an absent
    offset as the safe, conservative UTC assumption this codebase already
    uses elsewhere."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def measurement_basis_notice(bootstrapped_at, captured_at: str):
    """Return a non-blocking notice when `captured_at` predates
    `bootstrapped_at` — the comparison baseline was captured before
    multi-project discovery existed, so a delta against it may reflect a
    widened measurement scope rather than a real coverage change.

    Returns `None` when `bootstrapped_at` is `None` (config was never
    bootstrapped, or predates this feature), when either value fails to
    parse as ISO-8601, or when `captured_at >= bootstrapped_at` (compared as
    parsed `datetime` objects, not raw strings — this correctly orders
    equivalent-but-differently-spelled timestamps, e.g. a `Z` suffix vs an
    explicit `+00:00` offset for the same instant). A same-instant capture
    is not "predates" and also returns `None`.
    """
    if bootstrapped_at is None:
        return None
    bootstrapped_dt = _parse_iso8601(bootstrapped_at)
    captured_dt = _parse_iso8601(captured_at)
    if bootstrapped_dt is None or captured_dt is None:
        return None
    if captured_dt >= bootstrapped_dt:
        return None
    return (
        f"Note: this baseline predates multi-project discovery (bootstrapped "
        f"{bootstrapped_at}). This delta may reflect a widened measurement "
        f"scope, not only a real coverage change. Consider re-running "
        f"/coverage-baseline for a directly comparable baseline."
    )


def atomic_write_json(path: Path, obj: dict) -> None:
    """Write `obj` as JSON to `path` atomically (temp-file-then-rename),
    matching `baseline-coverage.json`'s existing write convention. Shared
    across this module's own callers and Slice 4/5's — reuse this instead of
    re-implementing temp-file-then-rename.

    On any failure (e.g. `obj` is not JSON-serializable), the temp file is
    removed before the exception propagates — the caller never leaks a
    `.tmp` file it has no handle to."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
