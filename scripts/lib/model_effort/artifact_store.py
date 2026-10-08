"""Persist the run artifact: reserve its path up front, write it atomically at the end.

The path is reserved with an empty placeholder (exclusive create) before any
trial runs, so a run-ID collision is refused before spending and an existing
artifact is never overwritten. The final write goes to a temp file in the same
directory and is moved over the placeholder, so readers never see a truncated
artifact.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import UsageError

ARTIFACT_SUFFIX = ".json"
TEMP_SUFFIX = ".tmp"
JSON_INDENT = 2


def reserve_artifact_path(runs_dir: Path, run_id: str) -> Path:
    """Create an empty placeholder at `<runs_dir>/<run_id>.json` and return its path.

    Raises:
        UsageError: `runs_dir` is missing, the artifact already exists, or the
            placeholder cannot be created.
    """
    if not runs_dir.is_dir():
        raise UsageError(
            f"runs directory {runs_dir} does not exist: create it or pass --runs-dir"
        )
    path = runs_dir / f"{run_id}{ARTIFACT_SUFFIX}"
    try:
        with open(path, "x", encoding="utf-8"):
            pass
    except FileExistsError as error:
        raise UsageError(
            f"artifact {path} already exists and is never overwritten: "
            "rerun to get a new run ID, or move the file away"
        ) from error
    except OSError as error:
        raise UsageError(
            f"cannot reserve artifact {path}: {error}. "
            "Make the runs directory writable or pass --runs-dir"
        ) from error
    return path


@contextmanager
def release_if_unwritten(path: Path) -> Iterator[None]:
    """On exit, remove the placeholder if it is still empty.

    A run that ended before writing (no trial started, or the final write failed
    before the file got content) leaves no stray empty artifact behind.
    """
    try:
        yield
    finally:
        _remove_if_empty(path)


def _remove_if_empty(path: Path) -> None:
    try:
        if path.stat().st_size == 0:
            path.unlink()
    except FileNotFoundError:
        pass


def render_artifact(data: dict) -> str:
    return json.dumps(data, indent=JSON_INDENT) + "\n"


def write_artifact(path: Path, text: str) -> None:
    """Atomically replace `path` with `text`; on failure `path` is left as it was.

    Raises:
        OSError: the temp file could not be written or moved into place.
    """
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=TEMP_SUFFIX,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            # The temp file is private by default; keep the placeholder's mode.
            shutil.copymode(path, temp_path)
        os.replace(temp_path, path)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
