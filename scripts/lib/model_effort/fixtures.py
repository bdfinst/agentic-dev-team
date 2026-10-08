"""Find the fixtures an agent is graded on.

A fixture is runnable when an `evals/expected` entry names the agent and a
fixture file or directory with the same stem exists. Everything here takes
directories as arguments and does no printing.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .errors import UsageError

EXPECTED_STATUS_CLEAN = "pass"


class FixtureKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class ResolvedFixture:
    stem: str
    path: Path
    kind: FixtureKind
    expected_clean: bool


def is_expected_clean(expected_entry: dict, agent: str) -> bool:
    """True when the expected entry says `agent` should report no problems."""
    expectation = expected_entry.get("agents", {}).get(agent, {})
    return expectation.get("expectedStatus") == EXPECTED_STATUS_CLEAN


def describe_fixture(path: Path) -> tuple[str, FixtureKind]:
    """Return a fixture's stem and kind: a directory's stem is its name, a file's drops one extension."""
    if path.is_dir():
        return path.name, FixtureKind.DIRECTORY
    return path.stem, FixtureKind.FILE


def copy_fixture(fixture: Path, target: Path) -> None:
    """Copy a file or directory fixture to `target`, keeping symlinks inside a directory."""
    if fixture.is_dir():
        shutil.copytree(fixture, target, symlinks=True)
    else:
        shutil.copy2(fixture, target)


def expected_entries(agent: str, expected_dir: Path) -> dict[str, dict]:
    """Map fixture stem to its expected entry, for entries that name `agent`.

    Raises:
        UsageError: an expected file is not valid JSON.
    """
    entries = {}
    for path in sorted(expected_dir.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise UsageError(
                f"malformed expected entry {path}: {error}. Fix the JSON."
            ) from error
        if agent in entry.get("agents", {}):
            entries[path.stem] = entry
    return entries


def fixture_index(fixtures_dir: Path) -> dict[str, tuple[Path, FixtureKind]]:
    """Map stem to (path, kind) for everything in `fixtures_dir`.

    Raises:
        UsageError: `fixtures_dir` is not a directory.
    """
    if not fixtures_dir.is_dir():
        raise UsageError(
            f"fixtures directory {fixtures_dir} does not exist: run from a repo "
            "checkout that has evals/fixtures"
        )
    index = {}
    for path in sorted(fixtures_dir.iterdir()):
        stem, kind = describe_fixture(path)
        index[stem] = (path, kind)
    return index


def resolve_fixtures(
    agent: str,
    requested: list[str] | None,
    expected_dir: Path,
    fixtures_dir: Path,
) -> list[ResolvedFixture]:
    """Return the fixtures to run: `requested` stems, or every runnable one.

    Raises:
        UsageError: an expected file is malformed, the fixtures directory is
            missing, a requested stem is not runnable, or no fixture is runnable
            for the agent.
    """
    entries = expected_entries(agent, expected_dir)
    index = fixture_index(fixtures_dir)
    runnable = sorted(stem for stem in entries if stem in index)
    stems = _choose_stems(agent, requested, entries, runnable)
    return [
        ResolvedFixture(
            stem=stem,
            path=index[stem][0],
            kind=index[stem][1],
            expected_clean=is_expected_clean(entries[stem], agent),
        )
        for stem in stems
    ]


def _choose_stems(
    agent: str,
    requested: list[str] | None,
    entries: dict[str, dict],
    runnable: list[str],
) -> list[str]:
    if requested is None:
        if not entries:
            raise UsageError(
                f"no fixtures were found for agent {agent!r}: no evals/expected entry "
                "names it. Pass --fixtures with stems from evals/expected, or choose "
                "an agent that has entries"
            )
        if not runnable:
            raise UsageError(
                f"no fixtures were found for agent {agent!r}: evals/expected entries "
                f"exist but no fixture matches: {', '.join(sorted(entries))}. "
                "Add the fixtures or fix the entry names"
            )
        return runnable
    if not requested:
        raise UsageError("--fixtures named no stems: list at least one fixture stem")
    unknown = [stem for stem in requested if stem not in runnable]
    if unknown:
        raise UsageError(
            f"unknown fixture {', '.join(unknown)} for agent {agent!r}: it needs both an "
            "evals/expected entry naming the agent and a fixture. "
            f"Valid fixtures: {', '.join(runnable) or '(none)'}"
        )
    return requested
