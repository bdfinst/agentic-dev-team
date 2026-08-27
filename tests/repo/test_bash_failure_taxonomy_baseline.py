"""Bash-failure taxonomy baseline snapshots are dated, schema-valid, and
carry counts only -- never raw command/error text (#2038, plan Step 1.4).

Globs `bash-failure-taxonomy-*.json` rather than pinning a single dated
filename, so a future baseline commit needs no test-file change (per the
plan's Step 1.4 design note).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

BASELINES_DIR = REPO_ROOT / ".dev-team-reports" / "baselines"

EXPECTED_CLASSES = {
    "quoting",
    "tool-not-present",
    "working-directory",
    "timeout",
    "genuine-command-error",
    "unclassified",
}

_DATED_NAME_RE = re.compile(r"^bash-failure-taxonomy-\d{4}-\d{2}-\d{2}\.json$")

# Hermetic: ignore any host-level git ignore/config so the result reflects
# the repo's own .gitignore only (see the "Hermetic local tests" convention).
_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _baseline_files() -> list[Path]:
    return sorted(BASELINES_DIR.glob("bash-failure-taxonomy-*.json"))


def test_at_least_one_baseline_snapshot_exists() -> None:
    assert _baseline_files(), (
        f"No bash-failure-taxonomy-*.json baseline found under {BASELINES_DIR}"
    )


def test_baselines_dir_is_not_gitignored() -> None:
    """The `/.dev-team-reports/*` deny-all must re-include `baselines/` --
    without `!/.dev-team-reports/baselines/` in .gitignore, every baseline
    snapshot is untracked on a fresh clone/CI even though it exists and
    passes locally (verified via `git ls-files`)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", ".dev-team-reports/baselines/probe.json"],
        cwd=REPO_ROOT,
        env=_ENV,
        check=False,
    )
    assert result.returncode in (0, 1), "git check-ignore errored"
    assert result.returncode == 1, (
        ".dev-team-reports/baselines/ is gitignored -- add "
        "!/.dev-team-reports/baselines/ to .gitignore"
    )


def test_baseline_files_are_tracked_in_git() -> None:
    """A baseline snapshot that passes the schema tests locally but is
    untracked would silently vanish on a fresh clone/CI (issue #2038/#2039
    correctness finding #1)."""
    for path in _baseline_files():
        relpath = path.relative_to(REPO_ROOT)
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(relpath)],
            cwd=REPO_ROOT,
            env=_ENV,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{relpath} is not tracked by git (run: git add -f {relpath})"


def test_every_baseline_filename_is_dated() -> None:
    for path in _baseline_files():
        assert _DATED_NAME_RE.match(path.name), (
            f"{path.name} does not match bash-failure-taxonomy-YYYY-MM-DD.json"
        )


def test_every_baseline_matches_the_distribution_schema() -> None:
    for path in _baseline_files():
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert set(payload.keys()) == {
            "counts",
            "total",
            "addressable_count",
            "addressable_percentage",
        }, f"{path.name}: unexpected top-level keys {sorted(payload.keys())}"

        assert set(payload["counts"].keys()) == EXPECTED_CLASSES, (
            f"{path.name}: counts keys {sorted(payload['counts'].keys())} != "
            f"{sorted(EXPECTED_CLASSES)}"
        )
        for cls, count in payload["counts"].items():
            assert isinstance(count, int) and count >= 0, (
                f"{path.name}: counts[{cls!r}] = {count!r} is not a non-negative int"
            )

        assert isinstance(payload["total"], int) and payload["total"] >= 0
        assert (
            isinstance(payload["addressable_count"], int)
            and payload["addressable_count"] >= 0
        )
        assert payload["addressable_percentage"] is None or isinstance(
            payload["addressable_percentage"], (int, float)
        )


def test_every_baseline_is_arithmetically_consistent() -> None:
    """The counts, total, addressable_count, and addressable_percentage
    fields must agree with each other -- a schema-valid baseline could
    still carry a stale or hand-edited number in any one of them."""
    for path in _baseline_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        counts = payload["counts"]
        total = payload["total"]

        assert total == sum(counts.values()), (
            f"{path.name}: total {total} != sum(counts) {sum(counts.values())}"
        )

        expected_addressable_count = (
            total - counts["timeout"] - counts["genuine-command-error"]
        )
        assert payload["addressable_count"] == expected_addressable_count, (
            f"{path.name}: addressable_count {payload['addressable_count']} != "
            f"total - timeout - genuine-command-error ({expected_addressable_count})"
        )

        if total == 0:
            assert payload["addressable_percentage"] is None, (
                f"{path.name}: addressable_percentage should be None for an empty corpus"
            )
        else:
            expected_percentage = round((expected_addressable_count / total) * 100, 2)
            assert payload["addressable_percentage"] == pytest.approx(
                expected_percentage, abs=0.01
            ), (
                f"{path.name}: addressable_percentage {payload['addressable_percentage']} != "
                f"recomputed {expected_percentage}"
            )


def test_no_baseline_contains_a_command_or_path_looking_string() -> None:
    """Counts-only claim, checked directly against the serialized bytes.

    A schema check alone would pass a baseline that smuggled raw text into
    an unexpected key; this asserts the file has no string values at all
    (every value in the payload is numeric), which is stronger.
    """
    for path in _baseline_files():
        payload = json.loads(path.read_text(encoding="utf-8"))

        def _assert_no_strings(node, ctx: str, *, path: Path = path) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    _assert_no_strings(value, f"{ctx}.{key}", path=path)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    _assert_no_strings(value, f"{ctx}[{index}]", path=path)
            else:
                assert not isinstance(node, str), (
                    f"{path.name}: unexpected string value at {ctx} = {node!r} "
                    "-- baseline must carry counts only"
                )

        _assert_no_strings(payload, path.name)
