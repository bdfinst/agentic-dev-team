"""End-to-end proof for issue #546: a full pre-push run against a real git
push leaves refs stable.

Depends on: slices 1 (hermetic helper), 2 (ci-local env scrub), 4 (ref
guard). This test drives a real `git push` inside a hermetic scratch repo -
the same class of operation that caused the original incident - so it is
guarded from itself by the hermetic_env fixture and only enabled after
slices 1-4 land.

Ported from tests/repo/pre_push_end_to_end_tests.bats (#673).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from _repo_root import REPO_ROOT

REAL_HOOK = REPO_ROOT / ".husky" / "pre-push"


def _git(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _refs_snapshot(git_dir: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        [
            "git",
            "--git-dir",
            str(git_dir),
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads/",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_e2e_real_git_push_through_shipped_hook_leaves_refs_stable(
    tmp_path: Path, hermetic_env: dict[str, str]
) -> None:
    # Build a scratch bare + worktree scaffold.
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    bare.mkdir()
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main"],
        cwd=str(bare),
        env=hermetic_env,
        check=True,
    )

    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(work)], env=hermetic_env, check=True
    )
    _git(work, hermetic_env, "config", "user.email", "t@t")
    _git(work, hermetic_env, "config", "user.name", "T")
    _git(work, hermetic_env, "commit", "-q", "--allow-empty", "-m", "seed")
    _git(work, hermetic_env, "remote", "add", "origin", str(bare))
    _git(work, hermetic_env, "push", "-q", "origin", "main")

    _git(work, hermetic_env, "checkout", "-q", "-b", "feature")
    _git(work, hermetic_env, "commit", "-q", "--allow-empty", "-m", "feat")

    # Install the real hook + a fast-passing ci-local.sh stub. The stub is
    # necessary because the shipped ci-local.sh runs the entire suite - too
    # heavy for this test. We are asserting on ref-stability under the
    # *shipped hook framework*, not re-running the CI mirror.
    (work / ".husky").mkdir()
    (work / "scripts").mkdir()
    (work / ".husky" / "pre-push").write_text(REAL_HOOK.read_text())
    (work / ".husky" / "pre-push").chmod(0o755)
    (work / "scripts" / "ci-local.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    (work / "scripts" / "ci-local.sh").chmod(0o755)

    # Configure the local hooks path (the real repo uses husky's .husky/_,
    # which resolves relatively; for the scratch, wire the hook directly).
    _git(work, hermetic_env, "config", "core.hooksPath", str(work / ".husky"))

    # Snapshot refs on BOTH the bare and the worktree BEFORE the push.
    pre_bare = _refs_snapshot(bare, hermetic_env)
    pre_work = _git(
        work,
        hermetic_env,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/heads/",
    ).stdout

    # Drive the push. HUSKY_RUN_EVALS=0 short-circuits the live-eval prompt.
    push_env = dict(hermetic_env)
    push_env["HUSKY_RUN_EVALS"] = "0"
    subprocess.run(
        ["git", "push", "-q", "origin", "feature"],
        cwd=str(work),
        env=push_env,
        check=True,
    )

    # Snapshot after.
    post_bare = _refs_snapshot(bare, hermetic_env)
    post_work = _git(
        work,
        hermetic_env,
        "for-each-ref",
        "--format=%(refname) %(objectname)",
        "refs/heads/",
    ).stdout

    # The bare's feature ref DID advance (that was the push's purpose). But
    # the worktree's local refs must be byte-identical before and after.
    assert pre_work == post_work
    # And the bare's `main` (unrelated to the push) must be unchanged.
    pre_main = [line for line in pre_bare.splitlines() if "refs/heads/main" in line]
    post_main = [line for line in post_bare.splitlines() if "refs/heads/main" in line]
    assert pre_main == post_main


def test_e2e_shipped_pre_push_refuses_to_complete_if_ref_moves_during_hook(
    tmp_path: Path, hermetic_env: dict[str, str]
) -> None:
    # Build a scratch worktree + bare.
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    bare.mkdir()
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main"],
        cwd=str(bare),
        env=hermetic_env,
        check=True,
    )

    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(work)], env=hermetic_env, check=True
    )
    _git(work, hermetic_env, "config", "user.email", "t@t")
    _git(work, hermetic_env, "config", "user.name", "T")
    _git(work, hermetic_env, "commit", "-q", "--allow-empty", "-m", "seed")
    _git(work, hermetic_env, "remote", "add", "origin", str(bare))
    _git(work, hermetic_env, "push", "-q", "origin", "main")

    _git(work, hermetic_env, "checkout", "-q", "-b", "feature")
    _git(work, hermetic_env, "commit", "-q", "--allow-empty", "-m", "feat")

    # Install the real hook + an evil ci-local.sh stub that mutates
    # refs/heads/main during the hook (simulating a fixture bug).
    (work / ".husky").mkdir()
    (work / "scripts").mkdir()
    (work / ".husky" / "pre-push").write_text(REAL_HOOK.read_text())
    (work / ".husky" / "pre-push").chmod(0o755)
    (work / "scripts" / "ci-local.sh").write_text(
        "#!/usr/bin/env bash\n"
        f'cd "{work}"\n'
        "git checkout -q main\n"
        "git commit -q --allow-empty -m evil\n"
        "git update-ref refs/heads/main HEAD\n"
        "git checkout -q feature\n"
        "exit 0\n"
    )
    (work / "scripts" / "ci-local.sh").chmod(0o755)

    _git(work, hermetic_env, "config", "core.hooksPath", str(work / ".husky"))

    # Attempt the push. The ref-guard should refuse it.
    push_env = dict(hermetic_env)
    push_env["HUSKY_RUN_EVALS"] = "0"
    result = subprocess.run(
        ["git", "push", "-q", "origin", "feature"],
        cwd=str(work),
        env=push_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0

    # Assert the guard fired for the RIGHT reason - the diagnostic must name
    # the drifted ref and mention the "changed during hook" wording.
    output = result.stdout + result.stderr
    assert "refs/heads/main" in output
    assert "changed during hook" in output

    # The bare's feature ref must NOT have been created (push refused).
    verify = subprocess.run(
        ["git", "--git-dir", str(bare), "show-ref", "--verify", "refs/heads/feature"],
        env=hermetic_env,
        capture_output=True,
        text=True,
    )
    assert verify.returncode != 0
