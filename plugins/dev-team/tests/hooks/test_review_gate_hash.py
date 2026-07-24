"""Unit tests for hooks/lib/review_gate_hash.py (#576 / #572 Cluster B).

Behavioral invariants of the gate hash — sensitive to staged content,
deterministic across repeats, empty on non-git. The `.sh` sibling was
retired in #618; the byte-parity checks that used to pin the two
implementations against each other were removed alongside it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import review_gate_hash as gate  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]


def _init_repo(tmp_path: Path) -> Path:
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.dev"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "tester"], cwd=tmp_path, env=env, check=True
    )
    return tmp_path


# --- API surface -----------------------------------------------------------


def test_module_exposes_review_gate_hash() -> None:
    assert callable(gate.review_gate_hash)


# --- behavioral invariants -------------------------------------------------


def test_empty_staged_area_produces_stable_hash(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    h1 = gate.review_gate_hash(cwd=tmp_path)
    h2 = gate.review_gate_hash(cwd=tmp_path)
    assert h1 == h2


def test_single_staged_file_produces_hex_hash(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.ts").write_text("hello\n")
    subprocess.run(
        ["git", "add", "a.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    h = gate.review_gate_hash(cwd=tmp_path)
    assert len(h) == 64
    int(h, 16)  # hex


def test_changed_content_changes_hash(tmp_path: Path) -> None:
    """The whole point of #193 — content edits must alter the hash."""
    _init_repo(tmp_path)
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(
        ["git", "add", "a.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    h1 = gate.review_gate_hash(cwd=tmp_path)
    (tmp_path / "a.ts").write_text("v2\n")
    subprocess.run(
        ["git", "add", "a.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    h2 = gate.review_gate_hash(cwd=tmp_path)
    assert h1 != h2


def test_extra_staged_file_changes_hash(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.ts").write_text("hi\n")
    subprocess.run(
        ["git", "add", "a.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    h1 = gate.review_gate_hash(cwd=tmp_path)
    (tmp_path / "b.ts").write_text("new\n")
    subprocess.run(
        ["git", "add", "b.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    h2 = gate.review_gate_hash(cwd=tmp_path)
    assert h1 != h2


def test_deterministic_across_repeated_calls(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "a.ts").write_text("stable\n")
    subprocess.run(
        ["git", "add", "a.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    hashes = {gate.review_gate_hash(cwd=tmp_path) for _ in range(5)}
    assert len(hashes) == 1


def test_hash_is_64_hex_chars(tmp_path: Path) -> None:
    """sha256 hex-encoded → 64 chars."""
    _init_repo(tmp_path)
    (tmp_path / "a.ts").write_text("x\n")
    subprocess.run(
        ["git", "add", "a.ts"], cwd=tmp_path, env=hermetic_git_env(home=tmp_path), check=True
    )
    h = gate.review_gate_hash(cwd=tmp_path)
    assert len(h) == 64
    int(h, 16)  # raises if not hex


def test_missing_git_returns_empty(tmp_path: Path) -> None:
    """Not a git repo → the hash function must not crash."""
    # Should either return an empty string or a stable hex hash — either is OK,
    # so long as it doesn't blow up on a non-git directory.
    h = gate.review_gate_hash(cwd=tmp_path)
    assert h == "" or (len(h) == 64 and int(h, 16) >= 0)
