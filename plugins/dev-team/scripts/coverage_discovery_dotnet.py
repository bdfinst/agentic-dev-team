#!/usr/bin/env python3
"""coverage_discovery_dotnet.py — discover and classify every project in a
.NET solution for multi-project coverage discovery (issue #1759, Slice 2).

Enumerates every project via `dotnet sln <solution> list` and classifies
each `.csproj` using `coverage_config.TestClassification`, checking in
order:

1. An inline `Microsoft.NET.Test.Sdk` `PackageReference` in the `.csproj`
   itself (matched on `Include="Microsoft.NET.Test.Sdk"`, case-insensitively
   per NuGet package ID convention, regardless of attribute order or
   whether a `Version` attribute is present — this also covers Central
   Package Management's version-less inline form) -> `TEST`.
2. If absent inline, walk every `Directory.Build.props` from the project's
   directory up to the solution root (inclusive). An **unconditioned** match
   (no `Condition` attribute on the `PackageReference` itself or its
   enclosing `ItemGroup`) -> `TEST`. A match that exists only inside a
   `Condition` -> `AMBIGUOUS` (this script deliberately never evaluates
   MSBuild conditions, matching this repo's stdlib-only,
   no-runner-execution convention already established by
   `coverage_readiness.py`).
3. No match anywhere -> `NOT_TEST`.

**Known, documented limitation.** A `GlobalPackageReference` declared in
`Directory.Packages.props` (MSBuild Central Package Management's other,
zero-inline-reference mechanism, distinct from the `Directory.Build.props`
ancestor walk above) is not walked. A project relying solely on it
classifies `NOT_TEST` — see the plan's Risks section.

**Security hardening.** Every resolved project path is verified to stay
within the resolved repository root before it is read or classified — a
`.sln` entry containing `..` or an absolute path can never cause this
module to read or XML-parse a file outside the repository. Separator
normalization (see `_parse_sln_list_output`, issue #1828) happens before
that check, so a backslash-separated `..\\outside\\Evil.csproj` is refused
like its forward-slash form instead of slipping past as one opaque
filename. Every `.csproj`
and `Directory.Build.props` file is also screened for `<!DOCTYPE`/
`<!ENTITY` declarations before being parsed (entity-expansion hardening) —
neither file legitimately carries either.

The `dotnet` subprocess boundary (`shutil.which("dotnet")` and
`subprocess.run([...])`) is mocked/stubbed in this module's unit tests — no
real .NET SDK is required to run them, keeping this module inside the
required `ci-local.sh`/pre-push pytest gate.

Stdlib-only (ADR 0014/0015).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import coverage_config
from coverage_config import TestClassification

_TEST_SDK_PACKAGE = "Microsoft.NET.Test.Sdk"

# `dotnet sln ... list` per-run wall-clock timeout, matching this repo's
# convention in sibling scripts (e.g. codebase_recon.py).
_SLN_LIST_TIMEOUT_SECONDS = 120

# A .csproj / Directory.Build.props file never legitimately carries a
# DOCTYPE or ENTITY declaration — presence of either is a zero-false-positive
# signal of an entity-expansion attempt, not a legitimate MSBuild file.
_UNSAFE_XML_MARKERS = ("<!DOCTYPE", "<!ENTITY")


def discover_dotnet_projects(repo_root):
    """Discover and classify every project in `repo_root`'s `.sln`.

    Returns a list of `{"path": <repo-relative project path as returned by
    "dotnet sln list">, "classification": TestClassification}` entries on
    success, `coverage_config.DISCOVERY_NOT_APPLICABLE` when no `.sln` is
    present, or `coverage_config.discovery_error(...)` for any
    tooling/parsing failure.
    """
    root = Path(repo_root).resolve()

    sln_files = sorted(root.glob("*.sln"))
    if not sln_files:
        return coverage_config.DISCOVERY_NOT_APPLICABLE
    if len(sln_files) > 1:
        names = ", ".join(f.name for f in sln_files)
        return coverage_config.discovery_error(
            f"Multiple .sln files found at repository root: {names}. "
            "Multi-solution repositories are not supported for discovery; "
            "leave exactly one .sln at the repository root."
        )
    sln_path = sln_files[0]

    dotnet_path = shutil.which("dotnet")
    if dotnet_path is None:
        return coverage_config.discovery_error(
            "The `dotnet` CLI is not on PATH; install the .NET SDK to "
            "enable solution discovery."
        )

    try:
        result = subprocess.run(  # noqa: PLW1510 — returncode is checked explicitly below to return a discovery_error rather than raise
            [dotnet_path, "sln", str(sln_path.resolve()), "list"],
            cwd=str(root),
            capture_output=True,
            text=True,
            env={**os.environ, "DOTNET_CLI_UI_LANGUAGE": "en"},
            timeout=_SLN_LIST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return coverage_config.discovery_error(
            f"`dotnet sln {sln_path.name} list` timed out after "
            f"{_SLN_LIST_TIMEOUT_SECONDS}s."
        )
    except OSError as exc:
        return coverage_config.discovery_error(
            f"Failed to run `dotnet sln {sln_path.name} list`: {exc}"
        )

    if result.returncode != 0:
        return coverage_config.discovery_error(
            f"`dotnet sln {sln_path.name} list` failed: {result.stderr.strip()}"
        )

    project_rel_paths = _parse_sln_list_output(result.stdout)

    projects = []
    for rel_path in project_rel_paths:
        absolute_problem = _absolute_entry_problem(rel_path)
        if absolute_problem is not None:
            return coverage_config.discovery_error(
                f"Solution '{sln_path.name}' references project "
                f"'{rel_path}', which {absolute_problem}. Only "
                "solution-relative project paths are supported; refusing to "
                "read or classify it."
            )
        csproj_path = (root / rel_path).resolve()
        if not (csproj_path == root or root in csproj_path.parents):
            return coverage_config.discovery_error(
                f"Solution '{sln_path.name}' references project "
                f"'{rel_path}', which resolves outside the repository "
                f"root ('{root}'); refusing to read or classify it."
            )
        if not csproj_path.is_file():
            return coverage_config.discovery_error(
                f"Solution '{sln_path.name}' references project "
                f"'{rel_path}' but the file does not exist on disk."
            )
        classification = _classify_project(csproj_path, root)
        if isinstance(classification, dict):
            return classification  # a discovery_error propagated up
        projects.append({"path": rel_path, "classification": classification})

    return projects


def _absolute_entry_problem(rel_path: str) -> str | None:
    """Return a reason when a (already separator-normalized) `.sln` entry is an
    absolute path rather than a solution-relative one, else `None`.

    Checked explicitly rather than left to `PurePosixPath.is_absolute()`,
    which is platform-divergent for exactly the shapes a Windows-authored
    solution produces: a drive-letter path like `C:/Projects/App.csproj` is
    NOT absolute on POSIX, so it would silently become a nonsense subpath of
    the repo root and fail with a misleading "does not exist on disk" instead
    of naming the real problem. A UNC path normalizes to a leading `//`, which
    IS absolute on POSIX — so without this check the same input produces two
    different diagnostics depending on the runner's OS."""
    if len(rel_path) >= 2 and rel_path[1] == ":" and rel_path[0].isalpha():
        return "is an absolute Windows path (drive letter)"
    if rel_path.startswith("//"):
        return "is an absolute UNC network path"
    if rel_path.startswith("/"):
        return "is an absolute path"
    return None


def _parse_sln_list_output(stdout: str) -> list:
    """Parse `dotnet sln list`'s stdout into a list of repo-relative project
    paths in POSIX form, skipping the `Project(s)` header and its underline.

    **Separator normalization (issue #1828).** `dotnet sln list` echoes the
    separators the `.sln` was authored with, and a Windows-authored solution
    emits backslashes. On POSIX `pathlib` treats `src\\App\\App.csproj` as a
    single opaque filename — `PurePath(...).name` returns the whole string —
    so the `.csproj` is never found and every project in the solution fails
    the "does not exist on disk" check even though the file is present. Since
    most enterprise .NET solutions are Windows-authored and their CI is
    commonly Linux, that made .NET discovery non-functional for them.

    Backslashes are therefore normalized to `/` here, once, at parse time.
    This is deliberately unconditional rather than POSIX-only: it keeps the
    recorded path identity — the string every caller compares against
    `included`/`excluded` entries — byte-identical across platforms, so a
    `coverage-config.json` written on Windows still reconciles on Linux.
    Normalizing before the caller's containment check also keeps the `..`
    traversal guard effective on backslash-separated escapes, which
    previously slipped past it as opaque filenames.

    Accepted limitation: a genuine POSIX filename containing a literal
    backslash would be rewritten. MSBuild solution files always use `\\` as a
    separator, so such a path does not occur in `.sln` output."""
    projects = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "Project(s)":
            continue
        if set(line) == {"-"}:
            continue
        projects.append(line.replace("\\", "/"))
    return projects


def _contains_unsafe_xml_marker(data: bytes) -> str | None:
    """Return the first disallowed marker (`_UNSAFE_XML_MARKERS`) found in
    `data`'s raw bytes, or in `data` decoded as UTF-16LE/UTF-16BE — the
    other encodings expat auto-detects and natively parses besides UTF-8.
    ASCII/Latin-1 are byte-identical to UTF-8 for these ASCII-only tokens,
    so no separate check is needed for those; decoding the raw bytes as
    Latin-1 (a total, never-raising 1:1 byte<->codepoint mapping) is
    sufficient to cover the UTF-8/ASCII/Latin-1 case in one pass. Returns
    `None` when no marker is found in any of the three views."""
    raw_text = data.decode("latin-1")
    utf16le_text = data.decode("utf-16le", errors="ignore")
    utf16be_text = data.decode("utf-16be", errors="ignore")
    for marker in _UNSAFE_XML_MARKERS:
        if marker in raw_text or marker in utf16le_text or marker in utf16be_text:
            return marker
    return None


def _read_and_screen_xml(path: Path):
    """Read `path` ONCE as bytes and screen the FULL content — never only a
    fixed-size prefix — for a disallowed `<!DOCTYPE`/`<!ENTITY` declaration
    (entity-expansion hardening); a `.csproj`/`Directory.Build.props` file
    never legitimately carries either.

    Returns `(data, None)` when the file looks safe to parse — the caller
    parses these SAME already-read bytes via `ET.fromstring`, never
    re-opening `path`, which closes the check-then-use double-open gap a
    `read`-then-`ET.parse(path)` pair leaves open. Returns
    `(None, coverage_config.discovery_error(...))` otherwise (unreadable
    file, or a disallowed marker found)."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, coverage_config.discovery_error(f"Could not read '{path}': {exc}")
    marker = _contains_unsafe_xml_marker(data)
    if marker is not None:
        return None, coverage_config.discovery_error(
            f"Refusing to parse '{path}': contains a disallowed "
            f"'{marker}' declaration (XML entity-expansion hardening)."
        )
    return data, None


def _classify_project(csproj_path: Path, solution_root: Path):
    """Classify a single project's `.csproj`, walking ancestor
    `Directory.Build.props` files (never climbing above `solution_root`)
    when no inline marker is found. Each `Directory.Build.props` found is
    resolved and containment-checked against `solution_root` before being
    read or parsed — mirroring the JS module's symlinked-manifest handling
    (`coverage_discovery_js._classify_package`) — so a symlinked
    `Directory.Build.props` pointing outside the solution root is refused
    rather than read. Returns a `TestClassification` value, or
    `coverage_config.discovery_error(...)` if the `.csproj` (or an ancestor
    `Directory.Build.props`) is not well-formed XML, is unreadable, escapes
    `solution_root`, or fails the entity-expansion safety check."""
    data, unsafe = _read_and_screen_xml(csproj_path)
    if unsafe is not None:
        return unsafe
    try:
        csproj_root = ET.fromstring(data)
    except ET.ParseError as exc:
        return coverage_config.discovery_error(
            f"Could not parse '{csproj_path}' as XML: {exc}"
        )

    if _test_sdk_reference_kind(csproj_root) is not None:
        return TestClassification.TEST

    found_conditioned = False
    current_dir = csproj_path.parent
    while current_dir == solution_root or solution_root in current_dir.parents:
        props_path = current_dir / "Directory.Build.props"
        if props_path.is_file():
            try:
                resolved_props_path = props_path.resolve()
            except OSError as exc:
                return coverage_config.discovery_error(
                    f"Could not resolve '{props_path}': {exc}"
                )
            if not (
                resolved_props_path == solution_root
                or solution_root in resolved_props_path.parents
            ):
                return coverage_config.discovery_error(
                    f"'{props_path}' resolves to '{resolved_props_path}', "
                    f"which is outside the solution root "
                    f"('{solution_root}'); refusing to read or parse it."
                )
            props_data, unsafe = _read_and_screen_xml(resolved_props_path)
            if unsafe is not None:
                return unsafe
            try:
                props_root = ET.fromstring(props_data)
            except ET.ParseError as exc:
                return coverage_config.discovery_error(
                    f"Could not parse '{props_path}' as XML: {exc}"
                )
            kind = _test_sdk_reference_kind(props_root)
            if kind == "unconditioned":
                return TestClassification.TEST
            if kind == "conditioned":
                found_conditioned = True
        if current_dir == solution_root:
            break
        current_dir = current_dir.parent

    if found_conditioned:
        return TestClassification.AMBIGUOUS
    return TestClassification.NOT_TEST


def _test_sdk_reference_kind(root) -> str | None:
    """Return `"unconditioned"`, `"conditioned"`, or `None` for whether
    `root` contains a `Microsoft.NET.Test.Sdk` `PackageReference` (matched
    case-insensitively, per NuGet package ID convention), and whether it (or
    its enclosing `ItemGroup`) carries an MSBuild `Condition` attribute.
    This script deliberately never evaluates the condition's truth value —
    presence alone drives the distinction."""
    found_conditioned = False
    for item_group in root.iter():
        if _local_name(item_group.tag) != "ItemGroup":
            continue
        group_conditioned = "Condition" in item_group.attrib
        for child in item_group:
            if _local_name(child.tag) != "PackageReference":
                continue
            include = (child.get("Include") or "").strip().casefold()
            if include != _TEST_SDK_PACKAGE.casefold():
                continue
            if group_conditioned or "Condition" in child.attrib:
                found_conditioned = True
            else:
                return "unconditioned"
    return "conditioned" if found_conditioned else None


def _local_name(tag: str) -> str:
    """Strip an XML namespace prefix (`{ns}Tag` -> `Tag`) if present."""
    return tag.split("}", 1)[-1] if "}" in tag else tag
