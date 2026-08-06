"""Unit tests for hooks/lib/review_gate_hash.py (#576 / #572 Cluster B).

Behavioral invariants of the gate hash — sensitive to staged content,
deterministic across repeats, empty on non-git. The `.sh` sibling was
retired in #618; the byte-parity checks that used to pin the two
implementations against each other were removed alongside it.
"""

from __future__ import annotations

import hashlib
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


def test_external_diff_driver_config_does_not_collapse_the_hash(tmp_path: Path) -> None:
    """#1461 FOURTH security re-review (error severity): a `diff.external`
    config replaces git's own diff rendering entirely — including the
    `diff --git`/`index` headers this hash is computed over — which would
    otherwise collapse this function's output to `sha256(b"")` for EVERY
    changeset regardless of actual content, turning the dispatch-ledger
    gate's `subject_hash` binding into a constant (one honest review's
    genuine ledger evidence would then corroborate any future arbitrary
    changeset). `--no-ext-diff`/`--no-textconv` must keep the hash
    content-sensitive even with an external diff driver configured."""
    _init_repo(tmp_path)
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(
        ["git", "config", "diff.external", "/bin/true"],
        cwd=tmp_path, env=env, check=True,
    )
    (tmp_path / "a.ts").write_text("v1\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    h1 = gate.review_gate_hash(cwd=tmp_path)
    (tmp_path / "a.ts").write_text("v2-different\n")
    subprocess.run(["git", "add", "a.ts"], cwd=tmp_path, env=env, check=True)
    h2 = gate.review_gate_hash(cwd=tmp_path)
    assert h1 != h2
    empty_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert h1 != empty_hash
    assert h2 != empty_hash


# --- branch_diff_gate_hash / default_base_ref (#1886) ----------------------


def _init_repo_with_main(tmp_path: Path) -> tuple[Path, dict]:
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.dev"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "base.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_default_base_ref_falls_back_to_local_main_without_a_remote(tmp_path: Path) -> None:
    _init_repo_with_main(tmp_path)
    assert gate.default_base_ref(cwd=tmp_path) == "main"


def test_default_base_ref_returns_none_when_nothing_resolves(tmp_path: Path) -> None:
    """Issue #1904 Bug 1: total resolution failure (no git, no candidate
    resolves — a routine state in a shallow/single-branch clone) must
    return `None`, NOT `"HEAD"`. The old `"HEAD"` fallback let
    `branch_diff_gate_hash("HEAD", ...)` succeed with an empty diff
    (`git diff HEAD...HEAD`), silently passing the gate on a constant hash
    instead of hard-blocking as a setup failure."""
    # Not a git repo at all — every candidate fails to verify.
    assert gate.default_base_ref(cwd=tmp_path) is None


def test_branch_diff_gate_hash_empty_on_a_branch_with_no_new_commits(tmp_path: Path) -> None:
    _init_repo_with_main(tmp_path)
    h = gate.branch_diff_gate_hash("main", cwd=tmp_path)
    assert h == hashlib.sha256(b"").hexdigest()


def test_branch_diff_gate_hash_sensitive_to_new_commits_on_the_branch(tmp_path: Path) -> None:
    tmp_path, env = _init_repo_with_main(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "feature.txt").write_text("new\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature commit"], cwd=tmp_path, env=env, check=True)
    h = gate.branch_diff_gate_hash("main", cwd=tmp_path)
    assert h != hashlib.sha256(b"").hexdigest()
    assert len(h) == 64
    int(h, 16)


def test_branch_diff_gate_hash_covers_the_whole_branch_not_just_the_last_commit(
    tmp_path: Path,
) -> None:
    """The whole point of #1886: a multi-commit branch's PR-time hash must
    reflect EVERY commit since the base, not just the most recent one."""
    tmp_path, env = _init_repo_with_main(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "commit 1"], cwd=tmp_path, env=env, check=True)
    h_after_first = gate.branch_diff_gate_hash("main", cwd=tmp_path)
    (tmp_path / "b.txt").write_text("b\n")
    subprocess.run(["git", "add", "b.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "commit 2"], cwd=tmp_path, env=env, check=True)
    h_after_second = gate.branch_diff_gate_hash("main", cwd=tmp_path)
    assert h_after_first != h_after_second


def test_branch_diff_gate_hash_unresolvable_base_ref_fails_closed(tmp_path: Path) -> None:
    _init_repo_with_main(tmp_path)
    h = gate.branch_diff_gate_hash("no-such-ref", cwd=tmp_path)
    assert h == hashlib.sha256(b"").hexdigest()


def test_branch_diff_gate_hash_external_diff_driver_does_not_collapse_the_hash(
    tmp_path: Path,
) -> None:
    """Same #1461 fourth-security-re-review concern as
    `test_external_diff_driver_config_does_not_collapse_the_hash`, applied
    to the sibling branch-diff hash: `--no-ext-diff`/`--no-textconv` must
    keep it content-sensitive even with an external diff driver
    configured."""
    tmp_path, env = _init_repo_with_main(tmp_path)
    subprocess.run(
        ["git", "config", "diff.external", "/bin/true"], cwd=tmp_path, env=env, check=True
    )
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "feature.txt").write_text("new\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature commit"], cwd=tmp_path, env=env, check=True)
    h = gate.branch_diff_gate_hash("main", cwd=tmp_path)
    empty_hash = hashlib.sha256(b"").hexdigest()
    assert h != empty_hash


# --- EMPTY_DIGEST (#1904 Bug 1) ---------------------------------------------


def test_empty_digest_constant_matches_sha256_of_empty_bytes() -> None:
    assert gate.EMPTY_DIGEST == hashlib.sha256(b"").hexdigest()


# --- CLI: --branch-diff (#1886, #1904) --------------------------------------


def test_cli_branch_diff_matches_branch_diff_gate_hash(tmp_path: Path) -> None:
    tmp_path, env = _init_repo_with_main(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "feature.txt").write_text("new\n")
    subprocess.run(["git", "add", "feature.txt"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feature commit"], cwd=tmp_path, env=env, check=True)

    expected = gate.branch_diff_gate_hash(gate.default_base_ref(cwd=tmp_path), cwd=tmp_path)
    completed = subprocess.run(
        [sys.executable, str(_HOOKS_LIB / "review_gate_hash.py"), "--branch-diff"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )
    assert completed.stdout.strip() == expected
    assert expected != hashlib.sha256(b"").hexdigest()


def test_cli_without_flag_still_prints_review_gate_hash(tmp_path: Path) -> None:
    _init_repo_with_main(tmp_path)
    env = hermetic_git_env(home=tmp_path)
    completed = subprocess.run(
        [sys.executable, str(_HOOKS_LIB / "review_gate_hash.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )
    assert completed.stdout.strip() == gate.review_gate_hash(cwd=tmp_path)


def test_cli_branch_diff_exits_nonzero_and_prints_nothing_when_base_ref_unresolvable(
    tmp_path: Path,
) -> None:
    """Issue #1904 Bug 1: when `default_base_ref()` can't resolve any
    candidate (not a git repo at all here), `--branch-diff` mode must exit
    non-zero with empty stdout — never fall back to hashing `HEAD...HEAD`
    and printing the resulting `EMPTY_DIGEST` as if it were a valid hash."""
    env = hermetic_git_env(home=tmp_path)
    completed = subprocess.run(
        [sys.executable, str(_HOOKS_LIB / "review_gate_hash.py"), "--branch-diff"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode != 0
    assert completed.stdout.strip() == ""
