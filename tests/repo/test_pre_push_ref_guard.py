"""Post-hook ref-integrity guard in .husky/pre-push - issue #546.

Runs the shipped .husky/pre-push against a scratch repo (isolated via
hermetic_env). Only scripts/ci-local.sh is shadowed with a per-scenario
stub that induces the ref-mutation-or-not the scenario needs; the hook
itself is the shipped artifact so the test verifies the actual guard, not
a reimplementation.

Ported from tests/repo/pre_push_ref_guard_tests.bats (#673).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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


@pytest.fixture
def scratch(tmp_path: Path, hermetic_env: dict[str, str]) -> dict[str, object]:
    # Build a scratch repo with a copy of the shipped pre-push hook.
    _git(tmp_path, hermetic_env, "init", "-q", "-b", "main")
    _git(tmp_path, hermetic_env, "config", "user.email", "t@t")
    _git(tmp_path, hermetic_env, "config", "user.name", "T")
    _git(tmp_path, hermetic_env, "commit", "-q", "--allow-empty", "-m", "init")

    # Stage a feature branch with one commit.
    _git(tmp_path, hermetic_env, "checkout", "-q", "-b", "feature")
    _git(tmp_path, hermetic_env, "commit", "-q", "--allow-empty", "-m", "feat")

    # Install the shipped hook + a scripts/ dir we'll populate per scenario.
    (tmp_path / ".husky").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".husky" / "pre-push").write_text(REAL_HOOK.read_text())
    (tmp_path / ".husky" / "pre-push").chmod(0o755)

    # Realistic pre-push stdin: <local-ref> <local-sha> <remote-ref>
    # <remote-sha>. remote-sha is all-zeros to simulate a brand-new branch
    # push.
    feature_sha = _git(tmp_path, hermetic_env, "rev-parse", "HEAD").stdout.strip()
    stdin = (
        f"refs/heads/feature {feature_sha} refs/heads/feature "
        "0000000000000000000000000000000000000000\n"
    )

    return {"root": tmp_path, "env": hermetic_env, "stdin": stdin}


def _stub_ci_local(root: Path, body: str) -> None:
    (root / "scripts" / "ci-local.sh").write_text(f"#!/usr/bin/env bash\n{body}\n")
    (root / "scripts" / "ci-local.sh").chmod(0o755)


def _run_hook(
    scratch: dict[str, object], stdin: str | None = None
) -> subprocess.CompletedProcess:
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = dict(scratch["env"])  # type: ignore[arg-type]
    env["HUSKY_RUN_EVALS"] = "0"
    return subprocess.run(
        ["sh", "-e", ".husky/pre-push"],
        cwd=str(root),
        env=env,
        input=scratch["stdin"] if stdin is None else stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _add_sibling_worktree(
    root: Path, env: dict[str, str], branch: str, name: str = "sibling-wt"
) -> Path:
    """Register a second worktree on `branch`, sharing root's ref store.

    Sibling of `root`, not a child: `root` is itself the scratch repo. The
    per-test `root.name` keeps the path unique — `root.parent` is shared by
    every test in the run.
    """
    path = root.parent / f"{root.name}-{name}"
    _git(root, env, "worktree", "add", "-q", "-b", branch, str(path), "main")
    return path


def test_guard_refs_stable_and_ci_local_passes_hook_exits_0(
    scratch: dict[str, object],
) -> None:
    _stub_ci_local(scratch["root"], ":")  # no-op, exit 0
    result = _run_hook(scratch)
    assert result.returncode == 0
    output = (result.stdout + result.stderr).lower()
    # No drift diagnostic.
    assert "ref" not in output or (
        "drift" not in output and "changed during hook" not in output
    )


def test_guard_pushing_branchs_ref_mutated_during_hook(
    scratch: dict[str, object],
) -> None:
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    orig = _git(root, env, "rev-parse", "refs/heads/feature").stdout.strip()
    # Stub rewrites feature to a different commit while ci-local "runs".
    _stub_ci_local(
        root,
        f'cd "{root}" && git commit -q --allow-empty -m evil && '
        "git update-ref refs/heads/feature HEAD",
    )
    result = _run_hook(scratch)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    # Diagnostic names the ref and both SHAs.
    assert "refs/heads/feature" in output
    assert orig in output
    # Recovery hint present.
    assert "git update-ref" in output


def test_guard_unrelated_ref_main_mutated_hook_still_exits_nonzero(
    scratch: dict[str, object],
) -> None:
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    orig_main = _git(root, env, "rev-parse", "refs/heads/main").stdout.strip()
    _stub_ci_local(
        root,
        f'cd "{root}" && git checkout -q main && git commit -q --allow-empty -m evil && '
        "git update-ref refs/heads/main HEAD && git checkout -q feature",
    )
    result = _run_hook(scratch)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "refs/heads/main" in output
    assert orig_main in output


def test_guard_ref_deleted_during_hook_exits_nonzero(
    scratch: dict[str, object],
) -> None:
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    _git(root, env, "branch", "victim")
    orig_victim = _git(root, env, "rev-parse", "refs/heads/victim").stdout.strip()
    _stub_ci_local(root, f'cd "{root}" && git update-ref -d refs/heads/victim')
    result = _run_hook(scratch)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "refs/heads/victim" in output
    assert orig_victim in output
    assert "deleted" in output


def test_guard_ref_created_during_hook_exits_nonzero(
    scratch: dict[str, object],
) -> None:
    root: Path = scratch["root"]  # type: ignore[assignment]
    _stub_ci_local(root, f'cd "{root}" && git update-ref refs/heads/stray HEAD')
    result = _run_hook(scratch)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "refs/heads/stray" in output
    assert "created" in output or "absent" in output


def test_guard_sibling_worktree_branch_drift_is_noted_not_blocking(
    scratch: dict[str, object],
) -> None:
    """A branch owned by another worktree may legitimately move — issue #1815.

    All worktrees of a clone share one ref store, and ci-local runs for
    minutes; a sibling session committing during that window is concurrency,
    not corruption.
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    sibling = _add_sibling_worktree(root, env, "sibling")
    orig = _git(root, env, "rev-parse", "refs/heads/sibling").stdout.strip()
    # The sibling worktree commits on its own branch while ci-local "runs".
    _stub_ci_local(root, f'cd "{sibling}" && git commit -q --allow-empty -m concurrent')

    result = _run_hook(scratch)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ABORT" not in output
    # The drift is still surfaced, with both SHAs, as a non-blocking note.
    assert "refs/heads/sibling" in output
    assert orig in output
    assert "not blocking" in output


def test_guard_pushed_branch_never_exempt_even_when_a_worktree_owns_it(
    scratch: dict[str, object],
) -> None:
    """The ref being pushed is guarded even if a sibling worktree holds it."""
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    sibling = _add_sibling_worktree(root, env, "sibling")
    orig = _git(root, env, "rev-parse", "refs/heads/sibling").stdout.strip()
    _stub_ci_local(root, f'cd "{sibling}" && git commit -q --allow-empty -m concurrent')

    stdin = f"refs/heads/sibling {orig} refs/heads/sibling {'0' * 40}\n"
    result = _run_hook(scratch, stdin=stdin)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "ABORT" in output
    assert "refs/heads/sibling" in output
    assert orig in output


def test_guard_this_worktrees_own_branch_never_exempt(
    scratch: dict[str, object],
) -> None:
    """Our own checked-out branch stays guarded despite being in the worktree list."""
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    _add_sibling_worktree(root, env, "sibling")
    orig = _git(root, env, "rev-parse", "refs/heads/feature").stdout.strip()
    _stub_ci_local(
        root,
        f'cd "{root}" && git commit -q --allow-empty -m evil && '
        "git update-ref refs/heads/feature HEAD",
    )
    result = _run_hook(scratch)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "refs/heads/feature" in output
    assert orig in output


def test_guard_ci_local_fails_and_refs_drifted_still_names_the_drift(
    scratch: dict[str, object],
) -> None:
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    orig = _git(root, env, "rev-parse", "refs/heads/feature").stdout.strip()
    _stub_ci_local(
        root,
        f'cd "{root}" && git commit -q --allow-empty -m evil && '
        "git update-ref refs/heads/feature HEAD; exit 1",
    )
    result = _run_hook(scratch)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "refs/heads/feature" in output
    assert orig in output


def test_guard_ci_local_fails_but_refs_stable_hook_exits_nonzero_from_ci_local(
    scratch: dict[str, object],
) -> None:
    _stub_ci_local(scratch["root"], "exit 3")
    result = _run_hook(scratch)
    assert result.returncode != 0
    output = (result.stdout + result.stderr).lower()
    # No drift diagnostic since no refs changed.
    assert "ref.*drift" not in output
    assert "changed during hook" not in output
    assert "refs/heads/feature" not in output


def test_guard_worktree_paths_snapshot_captured_before_ci_local_runs(
    scratch: dict[str, object],
) -> None:
    """PRE_WORKTREE_PATHS_FILE exists and is non-empty before ci-local.sh starts.

    Step 2.1 of #1871: the pre-run worktree-path snapshot is the input the
    later exemption-computation fix will gate on, so it must be captured
    strictly before ci-local.sh's body runs, not after. Point TMPDIR at a
    test-controlled directory so the stub (a separate process with no
    visibility into the hook's own shell variables) can locate the
    mktemp-generated snapshot file by its fixed filename prefix and read it.
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    tmpdir = root.parent / f"{root.name}-tmpdir"
    tmpdir.mkdir()
    env["TMPDIR"] = str(tmpdir)

    check_result = root / "snapshot-check.txt"
    _stub_ci_local(
        root,
        (
            f'snap="$(ls "{tmpdir}"/prepush-worktree-paths-pre-* 2>/dev/null | head -n1)"\n'
            f'if [ -n "$snap" ] && [ -s "$snap" ]; then echo present > "{check_result}"; '
            f'else echo missing > "{check_result}"; fi'
        ),
    )
    result = _run_hook(scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert check_result.read_text().strip() == "present"


def test_guard_worktree_created_during_hook_cannot_self_enroll(
    scratch: dict[str, object],
) -> None:
    """A worktree created *during* the hook window cannot exempt its branch — #1871.

    Mirrors test_guard_sibling_worktree_branch_drift_is_noted_not_blocking, but
    the stubbed ci-local.sh body itself creates the worktree (not a pre-existing
    one), so its path is absent from the pre-run snapshot. The new worktree's
    branch must be reported as blocking, not as a non-blocking sibling note.
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    newbie = root.parent / f"{root.name}-newbie"
    _stub_ci_local(
        root,
        f'git -C "{root}" worktree add -q -b newbie "{newbie}" main && '
        f'cd "{newbie}" && git commit -q --allow-empty -m concurrent',
    )

    result = _run_hook(scratch)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "ABORT" in output
    assert "refs/heads/newbie" in output


def test_guard_mixed_pre_existing_and_mid_hook_worktrees_judged_independently(
    scratch: dict[str, object],
) -> None:
    """Pre-existing and mid-hook-created worktrees are judged independently — #1871.

    One sibling worktree pre-exists (branch mutated mid-hook, stays exempt) and
    one worktree is created mid-hook (commits, must block), in the same run.
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    sibling = _add_sibling_worktree(root, env, "sibling")
    sibling_orig = _git(root, env, "rev-parse", "refs/heads/sibling").stdout.strip()
    newbie = root.parent / f"{root.name}-newbie"
    _stub_ci_local(
        root,
        f'cd "{sibling}" && git commit -q --allow-empty -m concurrent && '
        f'git -C "{root}" worktree add -q -b newbie "{newbie}" main && '
        f'cd "{newbie}" && git commit -q --allow-empty -m concurrent',
    )

    result = _run_hook(scratch)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "ABORT" in output
    assert "refs/heads/newbie" in output
    assert "refs/heads/sibling" in output
    assert sibling_orig in output
    assert "not blocking" in output


def test_guard_worktree_recreated_at_same_path_is_exempt_known_limitation(
    scratch: dict[str, object],
) -> None:
    """Characterization test — pins today's accepted, documented limitation.

    A worktree removed and recreated at an *identical, pre-existing* path
    during the hook window inherits exemption, because the join key is
    worktree path and `git worktree list --porcelain` exposes no stable
    per-worktree identity beyond path (no inode/creation-time/generation
    field to key on instead). This is a deliberate, documented trade-off
    (see .husky/pre-push's rationale comment and plan issue #1871), not a
    silent gap — a future tightening of this logic would need this test to
    change on purpose.
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    sibling_path = root.parent / f"{root.name}-reuse-path"
    # The worktree must exist at P when the hook *starts* so the pre-run
    # snapshot (captured before ci-local.sh runs) includes P. The
    # remove-and-recreate-at-P happens inside the stubbed ci-local.sh body,
    # simulating it occurring mid-hook.
    _git(root, env, "worktree", "add", "-q", "-b", "original", str(sibling_path), "main")

    _stub_ci_local(
        root,
        f'git -C "{root}" worktree remove -f "{sibling_path}" && '
        f'git -C "{root}" worktree add -q -b reincarnated "{sibling_path}" main && '
        f'cd "{sibling_path}" && git commit -q --allow-empty -m concurrent',
    )

    result = _run_hook(scratch)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ABORT" not in output
    assert "refs/heads/reincarnated" in output
    assert "not blocking" in output


def test_guard_worktree_moved_mid_hook_is_conservatively_blocking(
    scratch: dict[str, object],
) -> None:
    """Second documented trade-off — a mid-hook `git worktree move` blocks.

    A pre-existing sibling worktree relocated (not recreated) mid-hook keeps
    its branch/identity but changes its path; the new path was never in the
    pre-run snapshot, so it is conservatively treated as blocking rather than
    silently exempted. This is the safe direction for a guard whose failure
    mode to avoid is a false negative, not a false positive — see
    .husky/pre-push's rationale comment and plan issue #1871.
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    sibling = _add_sibling_worktree(root, env, "relocatable")
    orig = _git(root, env, "rev-parse", "refs/heads/relocatable").stdout.strip()
    relocated = root.parent / f"{root.name}-relocated"

    _stub_ci_local(
        root,
        f'git -C "{root}" worktree move "{sibling}" "{relocated}" && '
        f'cd "{relocated}" && git commit -q --allow-empty -m concurrent',
    )

    result = _run_hook(scratch)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "ABORT" in output
    assert "refs/heads/relocatable" in output
    assert orig in output


def test_guard_worktree_path_with_space_captured_intact_in_snapshot(
    scratch: dict[str, object],
) -> None:
    """A worktree path containing a space is snapshotted whole, not truncated.

    Step 2.1 of #1871: the snapshot awk must use sub() to strip only the
    fixed "worktree " prefix, not default $1/$2 field-splitting — a
    worktree path may legitimately contain a space (unlike a branch
    refname, which git forbids from containing one).
    """
    root: Path = scratch["root"]  # type: ignore[assignment]
    env: dict[str, str] = scratch["env"]  # type: ignore[assignment]
    tmpdir = root.parent / f"{root.name}-tmpdir2"
    tmpdir.mkdir()
    env["TMPDIR"] = str(tmpdir)

    spaced_path = root.parent / f"{root.name} spaced sibling"
    _git(root, env, "worktree", "add", "-q", "-b", "spaced-branch", str(spaced_path), "main")

    check_result = root / "space-check.txt"
    _stub_ci_local(
        root,
        (
            f'snap="$(ls "{tmpdir}"/prepush-worktree-paths-pre-* 2>/dev/null | head -n1)"\n'
            f'if grep -qxF "{spaced_path}" "$snap"; then echo intact > "{check_result}"; '
            f'else echo missing > "{check_result}"; fi'
        ),
    )
    result = _run_hook(scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert check_result.read_text().strip() == "intact"
