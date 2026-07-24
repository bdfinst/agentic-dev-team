"""Shared primitives for the Defects4J / BugsJS /code-review benchmark harness (#821).

BenchmarkCase is the common record both dataset adapters normalize to.
unified_diff_hunks() parses a standard unified diff (verified against a real
Defects4J patch and BugsJS's git-diff output, both plain `diff --git` /
`--- a/...` / `+++ b/...` / `@@ -a,b +c,d @@` format) into per-file line
ranges. Ground truth uses the OLD-file ("-") side of each hunk, because
/code-review runs against the buggy (pre-fix) checkout, whose line numbers
match the old-file side of the fix's diff.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(?P<path>.+?)(?:\t.*)?$", re.MULTILINE)
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@",
    re.MULTILINE,
)
_DIFF_GIT_RE = re.compile(r"^diff --git a/.+? b/(?P<path>.+)$")


@dataclass
class Hunk:
    file: str
    old_start: int
    old_end: int
    new_start: int
    new_end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "start_line": self.old_start,
            "end_line": self.old_end,
        }


@dataclass
class BenchmarkCase:
    dataset: str  # "defects4j" | "bugsjs"
    project: str
    bug_id: str
    language: str  # "java" | "javascript"
    ground_truth_files: list[str] = field(default_factory=list)
    ground_truth_hunks: list[dict[str, Any]] = field(default_factory=list)
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return f"{self.dataset}:{self.project}:{self.bug_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def unified_diff_hunks(diff_text: str) -> list[Hunk]:
    """Parse a unified diff into (file, old_start, old_end, new_start, new_end) hunks.

    Skips binary diffs (no `+++ b/` header pair for a `diff --git` block) and
    `/dev/null` file-header sides (pure adds/deletes have no meaningful line
    range to score against). Multiple files and multiple hunks per file are
    both supported — each hunk keeps its own file, taken from the nearest
    preceding `+++ b/<path>` header.
    """
    hunks: list[Hunk] = []
    current_file: str | None = None
    lines = diff_text.splitlines()
    for line in lines:
        file_match = _FILE_HEADER_RE.match(line)
        if file_match:
            path = file_match.group("path")
            current_file = None if path == "dev/null" else path
            continue
        hunk_match = _HUNK_HEADER_RE.match(line)
        if hunk_match and current_file is not None:
            old_start = int(hunk_match.group("old_start"))
            old_count = int(hunk_match.group("old_count") or "1")
            new_start = int(hunk_match.group("new_start"))
            new_count = int(hunk_match.group("new_count") or "1")
            old_end = old_start + max(old_count - 1, 0)
            new_end = new_start + max(new_count - 1, 0)
            hunks.append(
                Hunk(
                    file=current_file,
                    old_start=old_start,
                    old_end=old_end,
                    new_start=new_start,
                    new_end=new_end,
                )
            )
    return hunks


def run_with_timeout(
    seconds: int,
    argv: Sequence[str],
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """Run `argv` with a wall-clock cap. Mirrors
    `plugins/dev-team/hooks/mutation_adapters/lib.py`'s `run_with_timeout`:
    prefers `timeout`/`gtimeout` on PATH, falls back to `subprocess.run(timeout=...)`.
    Callers pass `check=False` (the default) to inspect the exit code themselves.
    """
    kwargs.setdefault("check", False)
    timeout_bin = shutil.which("timeout") or shutil.which("gtimeout")
    if timeout_bin is not None:
        return subprocess.run([timeout_bin, str(seconds), *argv], **kwargs)
    sys.stderr.write(
        "code-review-benchmark: timeout unavailable (install coreutils for "
        "gtimeout); run is unbounded\n"
    )
    try:
        return subprocess.run(list(argv), timeout=seconds, **kwargs)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=list(argv),
            returncode=124,
            stdout=exc.stdout or b"",
            stderr=exc.stderr or b"",
        )
