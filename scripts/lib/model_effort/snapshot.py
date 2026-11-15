"""Freeze a run's inputs at plan time, so editing the repo mid-run cannot change later trials.

The fixtures to run and the knowledge directory are copied into one run-private
temp directory, the expected entries into a second one. Trials stage their fixtures from it, the CLI
reads knowledge from it, and grading reads expected entries from it. The agent file
is read once at plan time, so it is not copied.

Layout under the snapshot root:
  fixtures/             the fixtures to run, under their own names
  plugin/knowledge/     the knowledge directory; `plugin` stands in for the plugin
                        root, so `${CLAUDE_PLUGIN_ROOT}/knowledge/...` in an agent's
                        prompt still resolves inside the one directory the CLI may read

Under the answer root (a separate temp dir):
  expected/             `<stem>.json` for each of those fixtures

A symlink in the knowledge directory or in a directory fixture is copied as a
link, never as its target's content, so nothing outside those trees is copied.

No prompt or CLI flag names the answer root, apart from the Bash sandbox's
deny-read list for a write-capable trial, so the expected entries stay out of
the agent's reach.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from .fixtures import ResolvedFixture, copy_fixture
from .paths import KNOWLEDGE_SUBDIR, EvalPaths, SnapshotPaths
from .temp_tree import remove_tree

SNAPSHOT_DIR_PREFIX = "model-effort-inputs-"
ANSWER_DIR_PREFIX = "model-effort-grading-"
FIXTURES_SUBDIR = "fixtures"
EXPECTED_SUBDIR = "expected"
PLUGIN_SUBDIR = "plugin"


@dataclass(frozen=True)
class InputSnapshot:
    """The frozen copy: where it lives, the paths and fixtures that point into it.

    Use it as a context manager to remove the copy on exit.
    """

    root: Path
    paths: SnapshotPaths
    fixtures: tuple[ResolvedFixture, ...]
    # Where the expected entries are, apart from everything a trial reads.
    answer_root: Path | None = None

    def remove(self) -> None:
        remove_tree(self.root)
        if self.answer_root is not None:
            remove_tree(self.answer_root)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.remove()


def take_snapshot(
    source: EvalPaths, fixtures: Sequence[ResolvedFixture]
) -> InputSnapshot:
    """Copy `fixtures`, their expected entries and the knowledge dir into a new temp dir.

    The agent file is read at plan time and not copied. If copying fails the partial copy is removed before the error propagates.

    Raises:
        OSError: a source file cannot be read or the copy cannot be written.
    """
    root = Path(tempfile.mkdtemp(prefix=SNAPSHOT_DIR_PREFIX))
    answer_root: Path | None = None
    try:
        answer_root = Path(tempfile.mkdtemp(prefix=ANSWER_DIR_PREFIX))
        return _copy_inputs(root, answer_root, source, fixtures)
    except BaseException:
        remove_tree(root)
        if answer_root is not None:
            remove_tree(answer_root)
        raise


def _copy_inputs(
    root: Path,
    answer_root: Path,
    source: EvalPaths,
    fixtures: Sequence[ResolvedFixture],
) -> InputSnapshot:
    fixtures_dir = root / FIXTURES_SUBDIR
    expected_dir = answer_root / EXPECTED_SUBDIR
    plugin_root = root / PLUGIN_SUBDIR
    knowledge_dir = plugin_root / KNOWLEDGE_SUBDIR
    for directory in (fixtures_dir, expected_dir):
        directory.mkdir()
    shutil.copytree(source.knowledge_dir, knowledge_dir, symlinks=True)
    copied = []
    for fixture in fixtures:
        target = fixtures_dir / fixture.path.name
        copy_fixture(fixture.path, target)
        shutil.copy2(source.expected_dir / f"{fixture.stem}.json", expected_dir)
        copied.append(dataclasses.replace(fixture, path=target))
    return InputSnapshot(
        root=root,
        paths=SnapshotPaths(
            expected_dir=expected_dir,
            fixtures_dir=fixtures_dir,
            plugin_root=plugin_root,
        ),
        fixtures=tuple(copied),
        answer_root=answer_root,
    )
