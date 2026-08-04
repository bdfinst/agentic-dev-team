#!/usr/bin/env python3
"""discover_coverage_projects.py — deterministic .NET test-project discovery
for `/coverage-baseline` (#1759).

Replaces a single, caller-supplied `dotnet test ...` command with a
deterministic per-run discovery of every test project in the solution:

    dotnet sln <sln> list
    → keep only projects whose .csproj carries a Microsoft.NET.Test.Sdk
      PackageReference (marker-only match, no path/naming filter)

A `coverage-config.json` file next to the `.sln` tracks which discovered
projects have been triaged (`known_projects`) or deliberately excluded
(`exclusions`, each recording why and a test-count snapshot). A project
discovered for the first time — absent from BOTH lists — is a hard failure
naming it, so a newly-added test project can never be silently skipped.
An absent config file self-bootstraps (writes the initial baseline from
today's discovery, exits 0) rather than failing.

Usage:
    discover_coverage_projects.py <path-to-.sln>

Stdout (on success): JSON `{"projects": [...], "warnings": [...]}` — the
included project paths (relative to the solution directory, forward-slash
normalized) plus any non-fatal stale-exclusion warnings. Warnings are also
printed to stderr, prefixed `warning:`.

On hard failure: prints `error: <message>` to stderr naming the offending
path, exits 1. Never a raw traceback.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

TEST_SDK_MARKER = "Microsoft.NET.Test.Sdk"
CONFIG_FILENAME = "coverage-config.json"

# Noise lines `dotnet test --list-tests` prints before/around the actual
# per-test lines. Any non-blank line that doesn't start with one of these
# (case-insensitive) counts as one listed test method.
_LIST_TESTS_NOISE_PREFIXES = (
    "the following tests are available",
    "build succeeded",
    "build started",
    "restore complete",
    "determining projects to restore",
)


class DiscoveryError(RuntimeError):
    """Raised for any hard-failure condition. `main()` catches this and
    reports it as `error: <message>` without a traceback — never let it
    escape to the top level uncaught."""


def _fail(message: str) -> None:
    raise DiscoveryError(message)


def normalize_path(path: str) -> str:
    """Normalize a project path to forward-slash form so paths compare
    equal regardless of the platform `dotnet sln list` ran on."""
    return path.strip().replace("\\", "/")


def _resolve_project_path(sln_dir: Path, rel_path: str) -> Path:
    """Validate a solution-relative project path and return its resolved
    absolute path. Rejects (via `_fail`) a path that is absolute, contains
    a `..` segment, or resolves outside the solution directory — required
    before any filesystem read or subprocess use of a discovered or
    configured project path."""
    candidate = Path(rel_path)
    if candidate.is_absolute():
        _fail(f"unsafe project path (absolute): {rel_path}")
    if ".." in candidate.parts:
        _fail(f"unsafe project path (contains '..'): {rel_path}")
    sln_dir_resolved = sln_dir.resolve()
    abs_path = (sln_dir_resolved / candidate).resolve()
    try:
        abs_path.relative_to(sln_dir_resolved)
    except ValueError:
        _fail(f"unsafe project path (escapes solution directory): {rel_path}")
    return abs_path


def _reject_option_like(path_str: str, description: str) -> None:
    """Reject (via `_fail`) a path string beginning with `-` — dotnet/MSBuild
    could otherwise parse it as a CLI option rather than a path."""
    if path_str.startswith("-"):
        _fail(f"unsafe {description} (looks like a CLI option, not a path): {path_str}")


# Shell metacharacters that would let a discovered path break out of the
# unquoted `dotnet test <project> ...` interpolation described in
# coverage-baseline/SKILL.md's `.sln`/`.csproj` manifest row.
_SHELL_METACHARACTERS = frozenset(";&|$`\n<>()")


def _reject_shell_metacharacters(path_str: str, description: str) -> None:
    """Reject (via `_fail`) a path string containing a shell metacharacter."""
    found = sorted(ch for ch in _SHELL_METACHARACTERS if ch in path_str)
    if found:
        _fail(
            f"unsafe {description} (contains shell metacharacter {found[0]!r}): {path_str}"
        )


_TEST_PROJECT_EXTENSIONS = (".csproj", ".fsproj", ".vbproj")


def parse_sln_list_output(output: str) -> list[str]:
    """Parse `dotnet sln <sln> list` stdout into normalized project paths.
    Accepts `.csproj`, `.fsproj`, and `.vbproj` — inclusion is still gated
    solely by the Test.Sdk marker check in `discover_test_projects`."""
    projects = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("project(s)"):
            continue
        if set(line) <= {"-"}:
            continue
        if line.lower().endswith(_TEST_PROJECT_EXTENSIONS):
            projects.append(normalize_path(line))
    return projects


def run_dotnet_sln_list(sln_path: Path) -> list[str]:
    """Run `dotnet sln <sln> list` and return the project paths it lists."""
    _reject_option_like(str(sln_path), "solution path")
    try:
        result = subprocess.run(
            ["dotnet", "sln", str(sln_path), "list"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        _fail(f"dotnet CLI not found: {exc}")
    except subprocess.TimeoutExpired as exc:
        _fail(f"dotnet sln list timed out after 60s: {exc}")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        _fail(f"dotnet sln list failed for {sln_path} (exit {exc.returncode}): {stderr}")
    return parse_sln_list_output(result.stdout)


def has_test_sdk_marker(csproj_abs_path: Path) -> bool:
    """True when the .csproj at this path references Microsoft.NET.Test.Sdk.
    No path/naming filter — the marker is the only signal."""
    try:
        content = csproj_abs_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return TEST_SDK_MARKER in content


def discover_test_projects(sln_path: Path) -> list[str]:
    """Return the normalized, solution-relative paths of every project in
    the solution whose .csproj carries the Microsoft.NET.Test.Sdk marker."""
    all_projects = run_dotnet_sln_list(sln_path)
    sln_dir = sln_path.parent
    discovered = []
    for rel_path in all_projects:
        _reject_option_like(rel_path, "discovered project path")
        _reject_shell_metacharacters(rel_path, "discovered project path")
        abs_path = _resolve_project_path(sln_dir, rel_path)
        if has_test_sdk_marker(abs_path):
            discovered.append(rel_path)
    return discovered


def _parse_test_list_count(output: str) -> int:
    """Count listed test methods from `dotnet test --list-tests` stdout —
    every non-blank line that isn't one of the known noise/header lines."""
    count = 0
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in _LIST_TESTS_NOISE_PREFIXES):
            continue
        count += 1
    return count


def count_test_methods(csproj_abs_path: Path) -> int | None:
    """Run `dotnet test <csproj> --list-tests` and return the listed test
    count, or `None` when the count can't be determined (missing dotnet,
    timeout, or a failing invocation) — a stale-exclusion check that can't
    run is skipped, not a hard failure."""
    _reject_option_like(str(csproj_abs_path), "project path")
    try:
        result = subprocess.run(
            ["dotnet", "test", str(csproj_abs_path), "--list-tests"],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return None
    return _parse_test_list_count(result.stdout)


def config_path_for(sln_path: Path) -> Path:
    """`coverage-config.json` lives next to the `.sln`."""
    return sln_path.parent / CONFIG_FILENAME


def load_config(config_path: Path) -> dict | None:
    """Return the parsed `coverage-config.json`, or `None` when the file
    doesn't exist (the self-bootstrap case). Malformed JSON is a hard
    failure naming the config path — never a raw traceback."""
    if not config_path.exists():
        return None
    try:
        text = config_path.read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"malformed coverage-config.json at {config_path}: {exc}")


def write_config(config_path: Path, known_projects: list[str], exclusions: list[dict]) -> None:
    """Write `coverage-config.json` atomically — temp-file-then-rename, so a
    reader never observes a partially-written file."""
    data = {"known_projects": known_projects, "exclusions": exclusions}
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(config_path.parent), prefix=f".{config_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp_name, config_path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _validate_config(config: dict, config_path: Path) -> None:
    """Validate `coverage-config.json`'s shape. Hard-fails (via `_fail`),
    naming the config path and the offending issue, so a valid-JSON-but-
    wrong-shape config never raises a raw KeyError/AttributeError/TypeError
    later in `discover()` — never a raw traceback."""
    if not isinstance(config, dict):
        _fail(f"malformed coverage-config.json at {config_path}: top-level value must be an object")
    known_projects = config.get("known_projects", [])
    if not isinstance(known_projects, list):
        _fail(f"malformed coverage-config.json at {config_path}: 'known_projects' must be a list")
    exclusions = config.get("exclusions", [])
    if not isinstance(exclusions, list):
        _fail(f"malformed coverage-config.json at {config_path}: 'exclusions' must be a list")
    for entry in exclusions:
        if not isinstance(entry, dict):
            _fail(
                f"malformed coverage-config.json at {config_path}: "
                f"exclusion entry must be an object: {entry!r}"
            )
        if "path" not in entry:
            _fail(
                f"malformed coverage-config.json at {config_path}: "
                f"exclusion entry missing required 'path': {entry!r}"
            )
        if not isinstance(entry["path"], str):
            _fail(
                f"malformed coverage-config.json at {config_path}: "
                f"exclusion entry 'path' must be a string: {entry!r}"
            )


def discover(sln_path: Path) -> dict:
    """Discover test projects and reconcile them against
    `coverage-config.json`. Returns `{"projects": [...], "warnings": [...]}`.

    Absent config file: self-bootstrap — write a fresh config with
    `known_projects` = everything discovered today, `exclusions: []`.

    Present config file: any discovered project absent from BOTH
    `known_projects` and `exclusions` is a hard failure naming it (a
    genuinely new, untriaged project). A project already in
    `known_projects` is included with no config change required.

    A missing/unreadable `.sln` path is a hard failure naming that path.

    Each exclusion entry may record an `excluded_test_count` snapshot; if
    the project's current test-method count no longer matches it, a
    non-fatal stale-exclusion warning is added — a real, re-checkable
    signal (the test count changed since exclusion), distinct from the
    marker match that made the project a candidate in the first place.
    """
    if not sln_path.is_file():
        _fail(f"solution file not found: {sln_path}")

    discovered = discover_test_projects(sln_path)
    config_path = config_path_for(sln_path)
    config = load_config(config_path)

    if config is None:
        write_config(config_path, sorted(discovered), [])
        return {"projects": sorted(discovered), "warnings": []}

    _validate_config(config, config_path)

    known_projects = config.get("known_projects", [])
    exclusions = config.get("exclusions", [])
    excluded_paths = {entry["path"] for entry in exclusions}

    new_untriaged = sorted(
        p for p in discovered if p not in known_projects and p not in excluded_paths
    )
    if new_untriaged:
        _fail(
            "new, untriaged test project(s) discovered (absent from both "
            f"known_projects and exclusions): {', '.join(new_untriaged)}"
        )

    included = sorted(p for p in discovered if p not in excluded_paths)
    warnings = _stale_exclusion_warnings(sln_path.parent, exclusions)
    return {"projects": included, "warnings": warnings}


def _stale_exclusion_warnings(sln_dir: Path, exclusions: list[dict]) -> list[str]:
    warnings = []
    for entry in exclusions:
        path = entry.get("path")
        if path is None:
            continue
        recorded_count = entry.get("excluded_test_count")
        if recorded_count is None:
            warnings.append(
                f"staleness check skipped for {path} — no excluded_test_count "
                "recorded; this exclusion will never be flagged as stale"
            )
            continue
        abs_path = _resolve_project_path(sln_dir, path)
        current_count = count_test_methods(abs_path)
        if current_count is not None and current_count != recorded_count:
            warnings.append(
                f"stale exclusion for {path} — recorded test count "
                f"{recorded_count}, current {current_count}"
            )
    return warnings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sln", help="path to the .sln file")
    args = parser.parse_args(argv)

    sln_path = Path(args.sln)

    try:
        result = discover(sln_path)
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for warning in result["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
