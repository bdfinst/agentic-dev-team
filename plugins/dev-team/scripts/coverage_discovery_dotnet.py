#!/usr/bin/env python3
"""coverage_discovery_dotnet.py — .NET solution test-project discovery (#1781).

Discovers every project in a `.sln` via `dotnet sln <sln> list` and classifies
each one by structural marker — a `Microsoft.NET.Test.Sdk` `PackageReference`:

1. An inline reference in the project file → `TEST`. Matched by parsing the
   project XML, so attribute order is irrelevant and a version-less Central
   Package Management form counts.
2. No inline reference, but an **unconditioned** reference in an ancestor
   `Directory.Build.props`/`Directory.Build.targets` (up to and including the
   solution directory) → `TEST`. A **conditioned** one → `AMBIGUOUS`: this
   discovery never evaluates MSBuild conditions, and a marker it cannot resolve
   must reach a human rather than become a silent negative. That silent-negative
   direction is the #1759 incident's failure shape.
3. No match anywhere → `NOT_TEST`.

No `.sln` directly in the repo root → `DISCOVERY_NOT_APPLICABLE`, and the caller
keeps its existing single-command path untouched. `dotnet` missing from PATH, a
malformed project file, a repo path that is not a directory, or a project the
solution lists but that is not on disk are all discovery errors naming the
offender — never an empty list and never a silent `NOT_TEST`.

Paths are recorded **exactly as `dotnet sln list` printed them** (surrounding
whitespace aside). `coverage_config` matches project identity as an exact
string, so rewriting separators in the recorded identity would be the very
normalization bug that rule exists to prevent. Filesystem reads use a
separator-normalized copy (`filesystem_relative`) so a Windows-authored
solution still resolves on POSIX — the identity and the I/O path are two
different things.

**Known limitations, out of scope** (epic #1766 Risks):

* `Directory.Packages.props`'s `GlobalPackageReference` mechanism is not walked.
* A reference reached through an `<Import Project="…" />` inside a
  `Directory.Build.*` file is not followed.

A solution supplying the test SDK exclusively either way classifies `NOT_TEST`.

Usage:
    coverage_discovery_dotnet.py <repo-path> [--solution <path-to-.sln>]

Stdout: `{"applicable": <bool>, "projects": [{"path", "classification"}, ...]}`.
On a hard failure: `error: <message>` on stderr, exit 1, never a traceback.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from xml.etree import ElementTree

from coverage_config import (
    DISCOVERY_NOT_APPLICABLE,
    DiscoveredProject,
    DiscoveryError,
    TestClassification,
    discovery_error,
)

TEST_SDK_MARKER = "Microsoft.NET.Test.Sdk"

#: MSBuild auto-imports both of these by the same ancestor-directory walk, so a
#: marker declared in either is inherited. A reference reached through an
#: `<Import Project="…" />` inside one of them is *not* followed — see the
#: module docstring's known-limitations note.
DIRECTORY_BUILD_FILENAMES = ("Directory.Build.props", "Directory.Build.targets")

#: Project-file extensions this discovery classifies. A `dotnet sln list` line
#: with any other extension is out of scope and skipped; inclusion is still
#: gated solely by the marker check, so the extension only identifies a project
#: line. Matched case-insensitively.
PROJECT_EXTENSIONS = (
    ".csproj",
    ".fsproj",
    ".vbproj",
    ".vcxproj",
    ".sqlproj",
    ".shproj",
    ".esproj",
)

_SLN_LIST_TIMEOUT_SECONDS = 60

#: Shell metacharacters that would let a discovered path break out of a
#: `dotnet test <project> …` interpolation. A space is deliberately *not* here:
#: `src/My Project/My Project.csproj` is an ordinary .NET path, so the calling
#: skill quotes the interpolated path rather than this rejecting valid layouts.
_SHELL_METACHARACTERS = frozenset(";&|$`\n\r<>()*?'\"")


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _reject_option_like(path_str: str, description: str) -> None:
    if path_str.startswith("-"):
        discovery_error(
            f"unsafe {description} (looks like a CLI option, not a path): {path_str}"
        )


def _reject_shell_metacharacters(path_str: str, description: str) -> None:
    found = sorted(char for char in _SHELL_METACHARACTERS if char in path_str)
    if found:
        discovery_error(
            f"unsafe {description} (contains shell metacharacter {found[0]!r}): "
            f"{path_str}"
        )


def filesystem_relative(rel_path: str) -> str:
    """Convert a `dotnet sln list` path into a form this platform can resolve.

    A Windows-authored solution yields backslash-separated paths. On POSIX those
    are ordinary filename characters, so `Path("tests\\A\\A.csproj")` is a
    *single* component: the file never resolves, the `..` guard never fires, and
    discovery hard-fails on every such solution.

    This is used for filesystem reads and the safety checks **only**. The
    recorded `DiscoveredProject.path` stays exactly what the tool printed,
    because `coverage_config` matches identity as an exact string.
    """
    return rel_path.replace("\\", "/")


def resolve_project_path(solution_dir: Path, rel_path: str) -> Path:
    """Validate a solution-relative project path and return its absolute form.

    Rejects an absolute path, a `..` segment, or anything resolving outside the
    solution directory — required before any filesystem read of a path that came
    from a subprocess's stdout. Takes the separator-normalized form from
    `filesystem_relative`, so the guards apply on every platform.
    """
    candidate = Path(rel_path)
    if candidate.is_absolute():
        discovery_error(f"unsafe project path (absolute): {rel_path}")
    if ".." in candidate.parts:
        discovery_error(f"unsafe project path (contains '..'): {rel_path}")
    solution_dir_resolved = solution_dir.resolve()
    absolute = (solution_dir_resolved / candidate).resolve()
    try:
        absolute.relative_to(solution_dir_resolved)
    except ValueError:
        discovery_error(f"unsafe project path (escapes solution directory): {rel_path}")
    return absolute


# ---------------------------------------------------------------------------
# `dotnet sln list`
# ---------------------------------------------------------------------------


def parse_sln_list_output(output: str) -> list[str]:
    """Parse `dotnet sln <sln> list` stdout into project paths, verbatim.

    Drops the `Project(s)` header, its `-----` rule, blank lines, and anything
    that is not a recognized project file.
    """
    projects: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("project(s)"):
            continue
        if set(line) <= {"-"}:
            continue
        if line.lower().endswith(PROJECT_EXTENSIONS):
            projects.append(line)
    return projects


def run_dotnet_sln_list(solution: Path) -> list[str]:
    """Run `dotnet sln <sln> list` and return the project paths it printed."""
    _reject_option_like(str(solution), "solution path")
    try:
        result = subprocess.run(
            ["dotnet", "sln", str(solution), "list"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_SLN_LIST_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        discovery_error(
            "the 'dotnet' CLI is not on PATH, so the solution's test projects cannot "
            "be discovered. Install the .NET SDK, or exclude this repo from .NET "
            "coverage discovery — an empty project list is never assumed."
        )
    except UnicodeDecodeError as exc:
        discovery_error(f"'dotnet sln {solution} list' emitted undecodable output: {exc}")
    except subprocess.TimeoutExpired:
        discovery_error(
            f"'dotnet sln {solution} list' timed out after "
            f"{_SLN_LIST_TIMEOUT_SECONDS}s"
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        discovery_error(
            f"'dotnet sln {solution} list' failed (exit {exc.returncode}): {stderr}"
        )
    except OSError as exc:
        # e.g. a non-executable `dotnet` on PATH raises PermissionError, which is
        # an OSError but not a FileNotFoundError.
        discovery_error(f"could not invoke 'dotnet': {exc}")
    return parse_sln_list_output(result.stdout)


# ---------------------------------------------------------------------------
# Marker classification
# ---------------------------------------------------------------------------


def _local_name(tag: str) -> str:
    """Strip any XML namespace, so legacy `xmlns`-bearing project files parse the
    same as modern SDK-style ones."""
    return tag.rpartition("}")[2]


def _parse_project_xml(path: Path, description: str) -> ElementTree.Element:
    try:
        return ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        discovery_error(f"malformed {description}: {path} could not be parsed ({exc})")
    except OSError as exc:
        discovery_error(f"unreadable {description}: {path} ({exc})")


def _names_the_marker(attribute_value: str) -> bool:
    """True when a `PackageReference` `Include`/`Update` names the test SDK.

    NuGet package IDs are case-insensitive, and MSBuild expands a semicolon
    item list into separate items — so `Include="xunit;Microsoft.Net.Test.Sdk"`
    carries the marker just as much as the canonical single-ID form. Matching
    only the exact canonical string would classify both as `NOT_TEST`, the
    silent-negative direction `classify` exists to avoid.
    """
    marker = TEST_SDK_MARKER.casefold()
    return any(part.strip().casefold() == marker for part in attribute_value.split(";"))


def _marker_references(root: ElementTree.Element) -> Iterable[list[ElementTree.Element]]:
    """Yield the ancestor chain (root-first) of every `PackageReference` naming
    the test SDK. Parsing the XML — rather than substring-matching the raw file —
    is what makes attribute order irrelevant and keeps a commented-out reference
    from counting."""

    def walk(
        element: ElementTree.Element, ancestors: list[ElementTree.Element]
    ) -> Iterable[list[ElementTree.Element]]:
        for child in element:
            chain = [*ancestors, element, child]
            if _local_name(child.tag) == "PackageReference":
                name = child.get("Include") or child.get("Update")
                if name is not None and _names_the_marker(name):
                    yield chain
            yield from walk(child, [*ancestors, element])

    return walk(root, [])


def _is_unconditioned(chain: Sequence[ElementTree.Element]) -> bool:
    """True when neither the `PackageReference` nor any ancestor carries a
    `Condition`. A condition is never evaluated here — see the module docstring."""
    return not any(
        (element.get("Condition") or "").strip() for element in chain
    )


def classify_project_file(project_path: Path) -> TestClassification | None:
    """Classify by the project file's own references alone.

    Returns `TEST` for an unconditioned inline marker, `AMBIGUOUS` for a
    conditioned one, and `None` when the file names no marker at all — the
    caller then consults the ancestor `Directory.Build.props` chain.
    """
    root = _parse_project_xml(project_path, "project file")
    chains = list(_marker_references(root))
    if not chains:
        return None
    if any(_is_unconditioned(chain) for chain in chains):
        return TestClassification.TEST
    return TestClassification.AMBIGUOUS


def classify_from_props_chain(
    project_path: Path, solution_dir: Path
) -> TestClassification | None:
    """Classify from every `Directory.Build.props`/`.targets` between the project
    directory and the solution directory, inclusive.

    Every ancestor is consulted rather than only MSBuild's nearest-wins import,
    because a false negative here is the #1759 failure shape: a real test project
    silently omitted from coverage. Over-inclusion, by contrast, surfaces as a
    hard failure a human resolves once.
    """
    solution_dir_resolved = solution_dir.resolve()
    found_conditioned = False
    directory = project_path.parent.resolve()
    while True:
        for filename in DIRECTORY_BUILD_FILENAMES:
            build_file = directory / filename
            if not build_file.is_file():
                continue
            root = _parse_project_xml(build_file, filename)
            for chain in _marker_references(root):
                if _is_unconditioned(chain):
                    return TestClassification.TEST
                found_conditioned = True
        if directory == solution_dir_resolved or directory == directory.parent:
            break
        directory = directory.parent
    return TestClassification.AMBIGUOUS if found_conditioned else None


def classify(project_path: Path, solution_dir: Path) -> TestClassification:
    """Classify one project by structural marker. Never silently negative: only
    the total absence of a marker yields `NOT_TEST`."""
    inline = classify_project_file(project_path)
    if inline is TestClassification.TEST:
        return inline
    inherited = classify_from_props_chain(project_path, solution_dir)
    if inherited is TestClassification.TEST:
        return inherited
    if inline is not None or inherited is not None:
        return TestClassification.AMBIGUOUS
    return TestClassification.NOT_TEST


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_solution(repo_path: Path) -> Path | None:
    """Return the single `.sln` directly in the repo root, or `None` when there
    is none. Matched case-insensitively.

    The search is deliberately root-only, not recursive: a repo whose solution
    lives at `src/App.sln` passes it explicitly via `--solution`. Recursing would
    make the measured set depend on directory layout, and would pick up nested
    sample/fixture solutions.

    More than one is a hard failure naming them all: picking one by sort order
    would silently measure part of the repo, and which part would depend on
    filenames rather than on a human's decision.
    """
    solutions = sorted(
        entry
        for entry in repo_path.iterdir()
        if entry.is_file() and entry.suffix.lower() == ".sln"
    )
    if not solutions:
        return None
    if len(solutions) > 1:
        names = ", ".join(solution.name for solution in solutions)
        discovery_error(
            f"more than one solution found in {repo_path}: {names}. Pass the one to "
            "measure with --solution — discovery will not choose for you."
        )
    return solutions[0]


def discover(
    repo_path: Path, solution: Path | None = None
) -> list[DiscoveredProject] | object:
    """Discover and classify every project in the repo's solution.

    Returns `DISCOVERY_NOT_APPLICABLE` when there is no `.sln` — a single
    `.csproj` repo has no ambiguous project list, so the caller's existing
    single-command path is left untouched (epic #1766, criterion 10).
    """
    repo_path = Path(repo_path)
    if not repo_path.is_dir():
        # Not the same condition as "no .sln here" — a path that is not a repo at
        # all must not read as "this stack does not apply".
        discovery_error(f"repo path is not a directory: {repo_path}")
    if solution is None:
        solution = find_solution(repo_path)
        if solution is None:
            return DISCOVERY_NOT_APPLICABLE
    if not solution.is_file():
        discovery_error(f"solution file not found: {solution}")

    solution_dir = solution.parent
    discovered: list[DiscoveredProject] = []
    for rel_path in run_dotnet_sln_list(solution):
        _reject_option_like(rel_path, "discovered project path")
        _reject_shell_metacharacters(rel_path, "discovered project path")
        absolute = resolve_project_path(solution_dir, filesystem_relative(rel_path))
        if not absolute.is_file():
            discovery_error(
                f"the solution lists {rel_path}, but no project file exists at "
                f"{absolute}. Discovery will not guess whether it is a test project."
            )
        discovered.append(
            DiscoveredProject(
                path=rel_path, classification=classify(absolute, solution_dir)
            )
        )
    return sorted(discovered, key=lambda project: project.path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("repo", help="repo root to discover from")
    parser.add_argument(
        "--solution",
        default=None,
        help="explicit .sln to use (required when the repo has more than one)",
    )
    args = parser.parse_args(argv)

    try:
        result = discover(
            Path(args.repo),
            solution=Path(args.solution) if args.solution else None,
        )
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - the docstring promises no traceback
        print(f"error: unexpected failure: {exc!r}", file=sys.stderr)
        return 1

    if result is DISCOVERY_NOT_APPLICABLE:
        print(json.dumps({"applicable": False, "projects": []}, indent=2))
        return 0

    print(
        json.dumps(
            {
                "applicable": True,
                "projects": [
                    {
                        "path": project.path,
                        "classification": project.classification.value,
                    }
                    for project in result
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
