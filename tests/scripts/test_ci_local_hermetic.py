"""Tests that scripts/ci-local.sh scrubs the git env vars git exports into
pre-push hooks (GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE / GIT_PREFIX /
GIT_REFLOG_ACTION) before any of its own logic runs, and that a hostile
GIT_DIR pointing at a decoy bare repo does NOT get mutated by ci-local.sh.

Uses CI_LOCAL_PROBE_ENV=1 to short-circuit ci-local: it prints the
post-scrub set of GIT_* env vars and exits 0, so the assertion runs in
milliseconds instead of triggering the full CI suite.

Issue #546. Ported from tests/scripts/ci_local_hermetic_tests.bats (issue
#676). scripts/ci-local.sh stays bash (out of scope per issue note); only
the test harness moves to pytest. pytest's own tmp_path fixture replaces
the bash hermetic helper's mktemp -d + rm -rf, and each subprocess.run
call is given an explicit env dict (never the ambient os.environ), which
is the pytest-native equivalent of scrubbing GIT_* before invocation.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"


def _base_env() -> dict:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "CI_LOCAL_PROBE_ENV": "1"}


def _sha256_tree(root: Path) -> list[str]:
    digests = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}")
    return digests


def test_env_scrub_probe_reports_every_targeted_var_as_unset(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy.git"
    decoy.mkdir()
    subprocess.run(["git", "init", "-q", "--bare"], cwd=decoy, check=True)

    env = _base_env()
    env.update(
        {
            "GIT_DIR": str(decoy),
            "GIT_INDEX_FILE": str(decoy / "index"),
            "GIT_WORK_TREE": str(tmp_path / "decoy-wt"),
            "GIT_PREFIX": "subdir/",
            "GIT_REFLOG_ACTION": "push",
            # An UNRELATED GIT_* variable that the probe MUST NOT leak,
            # simulating a real developer env with e.g. GIT_HTTP_EXTRAHEADER
            # carrying a bearer token.
            "GIT_HTTP_EXTRAHEADER": "Authorization: bearer SUPER_SECRET_TOKEN_XYZ",
        }
    )

    result = subprocess.run(
        ["bash", str(CI_LOCAL)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    output = result.stdout + result.stderr

    for var in (
        "GIT_DIR",
        "GIT_INDEX_FILE",
        "GIT_WORK_TREE",
        "GIT_PREFIX",
        "GIT_REFLOG_ACTION",
    ):
        assert f"{var}=__unset__" in output

    # Unrelated GIT_* secrets never appear in probe output.
    assert "SUPER_SECRET_TOKEN_XYZ" not in output
    assert "GIT_HTTP_EXTRAHEADER" not in output


def test_hostile_git_dir_does_not_mutate_the_decoy_bare_repo(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy.git"
    decoy.mkdir()
    subprocess.run(["git", "init", "-q", "--bare"], cwd=decoy, check=True)

    pre = _sha256_tree(decoy)
    head_path = decoy / "HEAD"
    pre_head = head_path.read_text() if head_path.exists() else ""

    env = _base_env()
    env.update(
        {
            "GIT_DIR": str(decoy),
            "GIT_INDEX_FILE": str(decoy / "index"),
            "GIT_WORK_TREE": str(tmp_path),
        }
    )

    result = subprocess.run(
        ["bash", str(CI_LOCAL)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0

    post = _sha256_tree(decoy)
    post_head = head_path.read_text() if head_path.exists() else ""

    assert pre == post
    assert pre_head == post_head
