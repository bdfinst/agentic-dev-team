"""Tests for the integration eval tier (issue #313): the `integration` grader
(scripts/eval_graders/integration.py, via eval_grade.py), --check-corpus
manifest validation, and the runner (scripts/run_integration_eval.py) worktree
build/teardown + command recording. Hermetic — the runner self-test uses
--skip-dispatch so no model is needed.

Ported from tests/repo/integration_tier_tests.bats (issue #572: bash -> Python).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GRADE = REPO_ROOT / "scripts" / "eval_grade.py"
RUNNER = REPO_ROOT / "scripts" / "run_integration_eval.py"


def _load_runner_module():
    """Import scripts/run_integration_eval.py by path so its functions
    (extract_golden_repo) can be unit-tested directly, in-process, without
    forking a subprocess for every case."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_integration_eval", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner_module = _load_runner_module()


def _tarball_with_member(
    tar_path: Path, member_name: str, content: bytes = b"pwned"
) -> None:
    """Build a tarball containing a single member whose name is a raw,
    attacker-chosen string (bypassing tarfile.add()'s own name normalization,
    the same way a hand-crafted malicious archive would)."""
    import io

    info = tarfile.TarInfo(name=member_name)
    info.size = len(content)
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.addfile(info, io.BytesIO(content))


EXPECTED_DEMO = """{
  "fixture": "demo",
  "applicableSkills": ["orchestrator"],
  "integration": {
    "orchestrator": {
      "grader": "integration",
      "spec": "spec.md",
      "goldenRepo": "golden.tar.gz",
      "testCommands": ["true"]
    }
  }
}
"""


@pytest.fixture
def case(tmp_path: Path) -> Path:
    (tmp_path / "expected").mkdir()
    (tmp_path / "fixtures" / "demo").mkdir(parents=True)
    (tmp_path / "expected" / "demo.json").write_text(EXPECTED_DEMO)
    (tmp_path / "fixtures" / "demo" / "spec.md").write_text("do the thing\n")
    # Golden repo: one file; the test command `true` always exits 0.
    with tempfile.TemporaryDirectory() as b:
        b_path = Path(b)
        (b_path / "file.txt").write_text("x\n")
        with tarfile.open(
            tmp_path / "fixtures" / "demo" / "golden.tar.gz", "w:gz"
        ) as tar:
            tar.add(str(b_path / "file.txt"), arcname="file.txt")
    return tmp_path


def _grade(case: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GRADE), *args],
        capture_output=True,
        text=True,
    )


def _run_runner(
    case: Path, extra_env: dict | None = None, *args: str
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if extra_env is not None:
        env = extra_env
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True,
        text=True,
        env=env,
    )


# --- grader -----------------------------------------------------------------


def test_integration_grader_all_zero_exits_pass(case: Path) -> None:
    (case / "actuals.json").write_text(
        """{ "demo": { "integration": { "orchestrator": { "results": [
  { "command": "true", "exit_code": 0, "stderr_first_line": "" } ] } } } }
"""
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_integration_grader_nonzero_exit_fails_with_details(case: Path) -> None:
    (case / "actuals.json").write_text(
        """{ "demo": { "integration": { "orchestrator": { "results": [
  { "command": "npm test", "exit_code": 2, "stderr_first_line": "TypeError: boom" } ] } } } }
"""
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "'true'" in out  # declared command with no result

    (case / "actuals2.json").write_text(
        """{ "demo": { "integration": { "orchestrator": { "results": [
  { "command": "true", "exit_code": 2, "stderr_first_line": "TypeError: boom" } ] } } } }
"""
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals2.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "exited 2" in out
    assert "TypeError: boom" in out


def test_integration_grader_missing_result_fails(case: Path) -> None:
    (case / "actuals.json").write_text(
        """{ "demo": { "integration": { "orchestrator": { "results": [] } } } }
"""
    )
    res = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "no result recorded" in out


# --- corpus manifest validation ---------------------------------------------


def test_check_corpus_valid_integration_manifest_passes(case: Path) -> None:
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Eval corpus OK" in out


def test_check_corpus_missing_goldenrepo_fails(case: Path) -> None:
    (case / "expected" / "demo.json").write_text(
        """{ "fixture": "demo", "applicableSkills": ["orchestrator"],
  "integration": { "orchestrator": { "grader": "integration",
    "spec": "spec.md", "testCommands": ["true"] } } }
"""
    )
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, out
    assert "missing 'goldenRepo'" in out


def test_check_corpus_empty_testcommands_fails(case: Path) -> None:
    (case / "expected" / "demo.json").write_text(
        """{ "fixture": "demo", "applicableSkills": ["orchestrator"],
  "integration": { "orchestrator": { "grader": "integration",
    "spec": "spec.md", "goldenRepo": "golden.tar.gz", "testCommands": [] } } }
"""
    )
    res = _grade(
        case,
        "--check-corpus",
        "--expected-dir",
        str(case / "expected"),
        "--fixtures-dir",
        str(case / "fixtures"),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, out
    assert "non-empty testCommands" in out


# --- runner -----------------------------------------------------------------


def test_runner_skip_dispatch_builds_worktree_records_exit_zero(case: Path) -> None:
    res = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--skip-dispatch",
            "--expected-dir",
            str(case / "expected"),
            "--fixtures-dir",
            str(case / "fixtures"),
            "--out",
            str(case / "actuals.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    data = json.loads((case / "actuals.json").read_text())
    assert data["demo"]["integration"]["orchestrator"]["results"][0]["exit_code"] == 0
    # And that actual grades PASS through the deterministic grader.
    graded = _grade(
        case,
        "--expected-dir",
        str(case / "expected"),
        "--actuals",
        str(case / "actuals.json"),
    )
    assert graded.returncode == 0, graded.stdout + graded.stderr


def test_runner_ephemeral_worktree_torn_down(case: Path) -> None:
    tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))

    def _count() -> int:
        try:
            return sum(1 for p in tmpdir.iterdir() if p.name.startswith("int-demo-"))
        except FileNotFoundError:
            return 0

    before = _count()
    subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--skip-dispatch",
            "--expected-dir",
            str(case / "expected"),
            "--fixtures-dir",
            str(case / "fixtures"),
            "--out",
            str(case / "actuals.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    after = _count()
    assert before == after


def test_runner_missing_claude_errors_naming_component(case: Path) -> None:
    # Build a clean bin dir holding only python3 + git so claude is genuinely
    # absent. Restricting PATH to python3's own bindir leaks claude on setups
    # where they share a directory (e.g. Homebrew's /opt/homebrew/bin).
    clean = case / "clean-bin"
    clean.mkdir()
    py3 = shutil.which("python3")
    git = shutil.which("git")
    assert py3 and git
    os.symlink(py3, clean / "python3")
    os.symlink(git, clean / "git")
    env = {"PATH": str(clean)}
    # Preserve HOME so python3 can find its stdlib on macOS venvs if needed.
    # Not needed here (system python3), leave PATH-only per bats.
    res = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--expected-dir",
            str(case / "expected"),
            "--fixtures-dir",
            str(case / "fixtures"),
            "--out",
            str(case / "actuals.json"),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    out = res.stdout + res.stderr
    assert res.returncode == 2, out
    assert "claude" in out
    assert "prerequisites missing" in out


# --- extract_golden_repo zip-slip guard --------------------------------------
#
# extract_golden_repo()'s path-traversal guard previously used a naive
# `str(target).startswith(str(dest.resolve()))` string-prefix check with no
# separator boundary — the classic zip-slip-guard-bypass pattern flagged by
# semgrep's trailofbits.python.tarfile-extractall-traversal rule. A sibling
# directory whose name happens to share dest's name as a string prefix (e.g.
# dest="out", sibling="out-evil") passes the naive check even though it is
# not actually inside dest.
#
# test_prefix_sibling_bypass_is_rejected_by_is_within unit-tests the
# containment predicate (_is_within) directly rather than only going
# through a full extract_golden_repo() -> tarfile.extractall() round-trip:
# Python 3.12+'s own tarfile.extractall() added its own PEP 706 traversal
# filter, which independently rejects some crafted members and can mask a
# still-buggy prefix check on newer interpreters, giving a false-negative
# "the code is already fixed" reading. Testing the predicate in isolation
# exercises exactly the logic this repo owns and is responsible for.


def test_prefix_sibling_bypass_is_rejected_by_is_within() -> None:
    # The specific naive-startswith bypass: dest is named "out"; the crafted
    # target resolves one level up into a *sibling* directory "out-evil"
    # whose name has "out" as a string prefix. The old
    # `str(target).startswith(str(dest))` check incorrectly treated this as
    # "inside dest".
    dest = Path("/tmp/case/out")
    sibling_escape = Path("/tmp/case/out-evil/pwned.txt")
    assert runner_module._is_within(dest, sibling_escape) is False


def test_dotdot_traversal_is_rejected_by_is_within() -> None:
    dest = Path("/tmp/case/out")
    assert runner_module._is_within(dest, Path("/etc/passwd")) is False


def test_legitimate_nested_target_is_accepted_by_is_within() -> None:
    dest = Path("/tmp/case/out")
    assert runner_module._is_within(dest, dest / "src" / "app" / "main.py") is True
    assert runner_module._is_within(dest, dest) is True


def test_extract_golden_repo_rejects_dotdot_traversal(tmp_path: Path) -> None:
    dest = tmp_path / "work" / "extracted"
    tarball = tmp_path / "golden.tar.gz"
    _tarball_with_member(tarball, "../../../../../../etc/passwd")

    with pytest.raises(Exception):
        runner_module.extract_golden_repo(tarball, dest)

    assert not (Path("/etc/passwd_pwned")).exists()  # sanity: no stray writes
    assert not any(dest.rglob("passwd"))


def test_extract_golden_repo_rejects_prefix_sibling_bypass(tmp_path: Path) -> None:
    # Regression for the specific naive-startswith bypass: dest is named
    # "out"; a crafted member escapes one level up into a *sibling*
    # directory "out-evil" whose name has "out" as a string prefix. The old
    # `str(target).startswith(str(dest.resolve()))` check incorrectly
    # treated this as "inside dest" and let extractall() write outside it.
    dest = tmp_path / "out"
    sibling_escape = tmp_path / "out-evil" / "pwned.txt"
    tarball = tmp_path / "golden.tar.gz"
    _tarball_with_member(tarball, "../out-evil/pwned.txt")

    with pytest.raises(Exception):
        runner_module.extract_golden_repo(tarball, dest)

    assert not sibling_escape.exists(), (
        f"zip-slip guard bypass: file escaped into sibling directory {sibling_escape}"
    )


def test_extract_golden_repo_allows_legitimate_nested_paths(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    tarball = tmp_path / "golden.tar.gz"
    _tarball_with_member(tarball, "src/app/main.py", content=b"print('hi')\n")

    runner_module.extract_golden_repo(tarball, dest)

    extracted = dest / "src" / "app" / "main.py"
    assert extracted.is_file()
    assert extracted.read_bytes() == b"print('hi')\n"
