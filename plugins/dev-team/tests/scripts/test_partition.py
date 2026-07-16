"""Unit tests for skills/code-review/scripts/partition.py.

Covers partition_files: module-aligned grouping, oversized-directory split,
sibling coalescing, empty/single-file scopes, cap validation, and determinism.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import partition  # noqa: E402


def _files(*paths: str):
    return list(paths)


def test_empty_scope_yields_no_slices():
    assert partition.partition_files([], cap=50) == []


def test_single_file_yields_one_slice():
    result = partition.partition_files(_files("src/a.ts"), cap=50)
    assert len(result) == 1
    assert result[0]["files"] == ["src/a.ts"]
    assert result[0]["id"] == "0001"


def test_small_siblings_coalesce_under_large_cap():
    files = _files("src/auth/a.ts", "src/auth/b.ts", "src/api/c.ts")
    result = partition.partition_files(files, cap=50)
    # Small siblings coalesce into a single slice under the cap.
    assert len(result) == 1
    assert sorted(result[0]["files"]) == ["src/api/c.ts", "src/auth/a.ts", "src/auth/b.ts"]


def test_oversized_directory_splits_across_slices():
    files = _files(*[f"src/big/f{i:03d}.ts" for i in range(7)])
    result = partition.partition_files(files, cap=3)
    # 7 files / cap 3 -> 3 slices of 3,3,1, none exceeding the cap.
    assert [len(s["files"]) for s in result] == [3, 3, 1]
    assert all(len(s["files"]) <= 3 for s in result)


def test_directory_at_exactly_cap_coalesces_not_split():
    # Split uses strict >, so a dir holding exactly `cap` files takes the
    # coalescing path (one slice), not the oversized-split path.
    files = _files(*[f"src/big/f{i}.ts" for i in range(3)])
    result = partition.partition_files(files, cap=3)
    assert len(result) == 1
    assert len(result[0]["files"]) == 3


def test_accumulated_siblings_flush_before_oversized_directory():
    # A small sibling dir ("src/a") sorts before an oversized dir ("src/big").
    # The accumulated sibling slice must flush first, keeping id order correct.
    files = _files("src/a/one.ts", *[f"src/big/f{i}.ts" for i in range(4)])
    result = partition.partition_files(files, cap=3)
    assert result[0]["files"] == ["src/a/one.ts"]
    assert result[0]["id"] == "0001"
    # Then the oversized dir in cap-sized chunks: 4 files / cap 3 -> 3, 1.
    assert [s["id"] for s in result] == ["0001", "0002", "0003"]
    assert [len(s["files"]) for s in result] == [1, 3, 1]


def test_small_siblings_coalesce_up_to_cap():
    files = _files(
        "src/a/one.ts",
        "src/b/two.ts",
        "src/c/three.ts",
        "src/d/four.ts",
    )
    result = partition.partition_files(files, cap=3)
    # 4 single-file dirs, cap 3 -> first slice packs 3, second holds 1.
    assert [len(s["files"]) for s in result] == [3, 1]


def test_slice_ids_are_sequential_and_zero_padded():
    files = _files(*[f"src/big/f{i:03d}.ts" for i in range(5)])
    result = partition.partition_files(files, cap=2)
    assert [s["id"] for s in result] == ["0001", "0002", "0003"]


def test_partitioning_is_deterministic():
    files = _files(
        "src/api/c.ts",
        "src/auth/a.ts",
        "src/auth/b.ts",
        "src/util/d.ts",
        "src/util/e.ts",
    )
    first = partition.partition_files(files, cap=2)
    # Same input, different insertion order -> identical ids/files/order.
    second = partition.partition_files(list(reversed(files)), cap=2)
    assert first == second


@pytest.mark.parametrize("bad_cap", [0, -1, -50, 1.5, "5", True, None])
def test_cap_must_be_positive_integer(bad_cap):
    with pytest.raises(ValueError):
        partition.partition_files(["src/a.ts"], cap=bad_cap)
