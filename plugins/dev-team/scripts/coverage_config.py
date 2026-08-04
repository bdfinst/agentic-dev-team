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

**Identity contract.** A project/package "path" is always the exact,
unmodified string the corresponding `discover_*` function (Slice 2/3)
returns for that entry. No cross-stack normalization, case-folding, or
separator translation is ever applied when matching a discovered path
against `included`/`excluded` entries — a POSIX-style path and an arbitrary
opaque label are both treated as opaque strings and compared for exact
equality only.

Stdlib-only (ADR 0014/0015).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
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


# Shared discovery-result signals — one canonical contract, imported by both
# Slice 2's `coverage_discovery_dotnet.py` and Slice 3's
# `coverage_discovery_js.py` rather than each independently converging on a
# matching shape.
DISCOVERY_NOT_APPLICABLE = {"signal": "not_applicable"}


def discovery_error(message: str) -> dict:
    """Return the shared discovery-error signal shape, naming `message`."""
    return {"signal": "error", "message": message}


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

    normalized_excluded = [
        {"path": entry, "reason": ""} if isinstance(entry, str) else entry
        for entry in excluded_entries
    ]
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
    normalized = [
        {"path": entry, "reason": ""} if isinstance(entry, str) else entry
        for entry in excluded_entries
    ]
    return "\n".join(
        f"Excluded: '{entry['path']}' (reason: "
        f"'{entry.get('reason', '<no reason recorded>')}')"
        for entry in normalized
    )


def weighted_merge(project_reports: list) -> dict:
    """Merge per-project coverage reports, weighted by statement/branch
    count — never a per-project average.

    Each entry in `project_reports` carries `{covered_statements,
    total_statements, covered_branches, total_branches}`. Returns
    `{line_pct, branch_pct}`, summed across all reports before dividing.
    Either percentage is `None` (JSON `null`) when its total is 0 across
    all reports, matching `coverage-baseline`'s existing Go-coverage `null`
    convention. A field valued `None` in a per-project report (this repo's
    own Go-coverage convention for a tool with no native branch coverage)
    coerces to 0 rather than raising `TypeError`, degrading to the same
    zero-total → `None` result.
    """
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
    treat that as "cannot compare, no notice"."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None


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
