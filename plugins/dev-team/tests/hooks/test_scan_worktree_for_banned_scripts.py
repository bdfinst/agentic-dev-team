"""Unit tests for hooks/scan_worktree_for_banned_scripts.py (#1755).

PostToolUse working-tree backstop for scan_bash_command_for_banned_scripts.py
— runs after EVERY tool call and inspects `git status --porcelain`, so it
catches a banned-extension file under plugins/dev-team/ regardless of which
tool created it (the PreToolUse half only scans Bash command strings).
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_TESTS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "scan_worktree_for_banned_scripts.py"

# Loaded by explicit file path (mirrors test_code_intelligence_nudge.py) so
# the #1861 guard test can monkeypatch `subprocess.run` and call `main()`
# in-process, without spawning a subprocess per assertion.
_spec = importlib.util.spec_from_file_location("scan_worktree_for_banned_scripts_lib", _HOOK)
assert _spec is not None and _spec.loader is not None
scan_worktree_for_banned_scripts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_worktree_for_banned_scripts)


def _run(cwd: Path, env: dict) -> subprocess.CompletedProcess[str]:
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": str(cwd)}
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, dict]:
    """A hermetic git repo with the plugins/dev-team/ dir already present."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "plugins" / "dev-team" / "hooks").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "hooks" / "keep.py").write_text("pass\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, env=env, check=True)
    return tmp_path, env


def test_passes_clean_repo(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    result = _run(cwd, env)
    assert result.returncode == 0


def test_blocks_untracked_banned_file(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "rogue.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/rogue.sh" in result.stdout
    assert "plugins/dev-team/hooks/rogue.sh" in result.stderr
    assert result.stdout.startswith("[BLOCK]")


def test_blocks_staged_banned_file(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "rogue.bat").write_text("echo hi\n")
    subprocess.run(
        ["git", "add", "plugins/dev-team/hooks/rogue.bat"], cwd=cwd, env=env, check=True
    )
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "rogue.bat" in result.stdout


def test_ignores_banned_file_outside_plugin_scope(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "scripts").mkdir()
    (cwd / "scripts" / "dev-setup.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_allows_install_sh_carveout(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "install.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_allows_py_sh_carveout(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "py.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_ignores_untracked_python_file(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "new_module.py").write_text("pass\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_not_a_git_repo_passes_open(tmp_path: Path) -> None:
    (tmp_path / "plugins" / "dev-team" / "hooks").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "hooks" / "rogue.sh").write_text("echo hi\n")
    result = _run(tmp_path, {**hermetic_git_env(home=tmp_path)})
    assert result.returncode == 0


def test_blocks_renamed_destination(repo: tuple[Path, dict]) -> None:
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "old_name.py").write_text("pass\n")
    subprocess.run(
        ["git", "add", "plugins/dev-team/hooks/old_name.py"], cwd=cwd, env=env, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "add old_name.py"], cwd=cwd, env=env, check=True
    )
    subprocess.run(
        [
            "git",
            "mv",
            "plugins/dev-team/hooks/old_name.py",
            "plugins/dev-team/hooks/new_name.sh",
        ],
        cwd=cwd,
        env=env,
        check=True,
    )
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/new_name.sh" in result.stdout


def test_ignores_worktree_deleted_banned_file(repo: tuple[Path, dict]) -> None:
    """(#1864 sub-claim 1) A tracked banned file removed from the worktree
    (unstaged delete, porcelain status " D") no longer exists on disk — it
    must not be flagged."""
    cwd, env = repo
    banned = cwd / "plugins" / "dev-team" / "hooks" / "old.sh"
    banned.write_text("echo hi\n")
    subprocess.run(
        ["git", "add", "plugins/dev-team/hooks/old.sh"], cwd=cwd, env=env, check=True
    )
    subprocess.run(["git", "commit", "-q", "-m", "seed old.sh"], cwd=cwd, env=env, check=True)
    banned.unlink()
    result = _run(cwd, env)
    assert result.returncode == 0


def test_ignores_staged_deleted_banned_file(repo: tuple[Path, dict]) -> None:
    """(#1864 sub-claim 1) A tracked banned file staged for deletion
    (`git rm`, porcelain status "D ") is gone from disk too — must not be
    flagged."""
    cwd, env = repo
    banned = cwd / "plugins" / "dev-team" / "hooks" / "old2.sh"
    banned.write_text("echo hi\n")
    subprocess.run(
        ["git", "add", "plugins/dev-team/hooks/old2.sh"], cwd=cwd, env=env, check=True
    )
    subprocess.run(["git", "commit", "-q", "-m", "seed old2.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(
        ["git", "rm", "-q", "plugins/dev-team/hooks/old2.sh"], cwd=cwd, env=env, check=True
    )
    result = _run(cwd, env)
    assert result.returncode == 0


def test_modified_file_with_literal_arrow_in_name_not_mis_split(
    repo: tuple[Path, dict],
) -> None:
    """(#1864 sub-claim 2) A plain modification (status " M", not a rename)
    of a file whose name happens to contain the literal substring "-> "
    must not have its path truncated by the rename-arrow split — the split
    is only valid for an actual R/C status."""
    cwd, env = repo
    odd_rel = "plugins/dev-team/hooks/before -> after.sh"
    odd_path = cwd / odd_rel
    odd_path.write_text("echo hi\n")
    subprocess.run(["git", "add", odd_rel], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed odd name"], cwd=cwd, env=env, check=True)
    odd_path.write_text("echo hi again\n")
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "before -> after.sh" in result.stdout


def test_flags_untracked_banned_file_with_non_ascii_name(repo: tuple[Path, dict]) -> None:
    """Closing-pass regression: git C-quotes a non-ASCII path by default
    (`?? "plugins/dev-team/hooks/caf\\303\\251.sh"`), and the exists()-based
    D-status fix must not silently drop it — the path exists, just under an
    escaped spelling `_porcelain_paths` never decoded."""
    cwd, env = repo
    (cwd / "plugins" / "dev-team" / "hooks" / "café.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "café.sh" in result.stdout


def test_recurses_into_untracked_directory(repo: tuple[Path, dict]) -> None:
    """(#1879) A wholly-new untracked directory collapses to one porcelain
    line — recurse into it on disk to find a banned file inside."""
    cwd, env = repo
    newdir = cwd / "plugins" / "dev-team" / "newfeature"
    newdir.mkdir()
    (newdir / "rogue.sh").write_text("echo hi\n")
    (newdir / "keep.py").write_text("pass\n")
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "plugins/dev-team/newfeature/rogue.sh" in result.stdout


def test_ignores_untracked_directory_outside_plugin_scope(repo: tuple[Path, dict]) -> None:
    """(#1879) The directory-recursion fix must stay scoped — an untracked
    directory outside plugins/dev-team/ is never walked."""
    cwd, env = repo
    newdir = cwd / "scripts" / "newstuff"
    newdir.mkdir(parents=True)
    (newdir / "rogue.sh").write_text("echo hi\n")
    result = _run(cwd, env)
    assert result.returncode == 0


def test_flags_unresolved_merge_conflict_deleted_by_us_modified_by_them(
    repo: tuple[Path, dict],
) -> None:
    """Security-review regression: a plain `D`-in-status skip is wrong for
    an unresolved-merge conflict code (`DU`/`UD`) — the path IS present in
    the working tree despite the status containing `D`."""
    cwd, env = repo
    main_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd, env=env, capture_output=True, text=True, check=True,
    ).stdout.strip()
    evil = cwd / "plugins" / "dev-team" / "hooks" / "evil.sh"
    evil.write_text("echo A\n")
    subprocess.run(["git", "add", "plugins/dev-team/hooks/evil.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add evil.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "other"], cwd=cwd, env=env, check=True)
    evil.write_text("echo B\n")
    subprocess.run(["git", "add", "plugins/dev-team/hooks/evil.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "modify evil.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "checkout", "-q", main_branch], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "rm", "-q", "plugins/dev-team/hooks/evil.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "delete evil.sh"], cwd=cwd, env=env, check=True)
    subprocess.run(["git", "merge", "other"], cwd=cwd, env=env, check=False)

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout
    assert "DU" in status or "UD" in status, f"expected an unresolved D-conflict, got: {status!r}"
    assert evil.exists(), "the conflicted file must still be present on disk"

    result = _run(cwd, env)
    assert result.returncode == 2
    assert "evil.sh" in result.stdout


def test_symlink_in_untracked_directory_is_flagged_not_silently_dropped(
    repo: tuple[Path, dict], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Security-review regression: resolving a symlink's target to relativize
    it can land outside `root` and raise ValueError, silently dropping the
    entry — the sibling non-directory scan path never resolves and would
    catch this. The untracked-directory walk must not be weaker."""
    cwd, env = repo
    outside = tmp_path_factory.mktemp("outside-link-target")
    newdir = cwd / "plugins" / "dev-team" / "newfeature"
    newdir.mkdir()
    link = newdir / "evil.sh"
    link.symlink_to(outside / "does-not-need-to-exist.sh")
    result = _run(cwd, env)
    assert result.returncode == 2
    assert "evil.sh" in result.stdout


def test_missing_plugin_scope_dir_never_calls_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(#1861) The early-exit guard is a plain `Path.is_dir()` check — it
    must return before `find_banned_files` (which shells out to
    `git status`) ever runs, so a downstream install with no
    plugins/dev-team/ tree pays zero git subprocess cost. `project_root()`
    itself legitimately calls `git rev-parse` to resolve the root, so this
    mocks the scan function specifically rather than all of `subprocess`."""

    def _fail_if_called(root: object) -> None:
        raise AssertionError("find_banned_files must not run when plugins/dev-team/ is absent")

    monkeypatch.setattr(scan_worktree_for_banned_scripts, "find_banned_files", _fail_if_called)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(tmp_path)})))
    assert scan_worktree_for_banned_scripts.main() == 0


# --- (#1904 item 8) untracked-directory scan truncation signal --------------


def test_files_in_untracked_dir_reports_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory with more entries than the cap must signal truncation
    via the returned flag, not silently claim the walk was exhaustive."""
    monkeypatch.setattr(scan_worktree_for_banned_scripts, "_MAX_UNTRACKED_DIR_ENTRIES", 0)
    newdir = tmp_path / "newfeature"
    newdir.mkdir()
    (newdir / "rogue.sh").write_text("echo hi\n")
    hits, truncated = scan_worktree_for_banned_scripts._files_in_untracked_dir(
        tmp_path, "newfeature"
    )
    assert truncated is True
    assert hits == []


def test_files_in_untracked_dir_not_truncated_when_under_cap(tmp_path: Path) -> None:
    newdir = tmp_path / "newfeature"
    newdir.mkdir()
    (newdir / "keep.py").write_text("pass\n")
    hits, truncated = scan_worktree_for_banned_scripts._files_in_untracked_dir(
        tmp_path, "newfeature"
    )
    assert truncated is False
    assert hits == []


def test_truncated_scan_still_blocks_and_notes_incompleteness(
    repo: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hit found within the capped portion of the walk still blocks —
    but the message must also say the scan was truncated, since anything
    past the cap was never inspected."""
    cwd, env = repo
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.setattr(scan_worktree_for_banned_scripts, "_MAX_UNTRACKED_DIR_ENTRIES", 1)
    newdir = cwd / "plugins" / "dev-team" / "newfeature"
    newdir.mkdir()
    # All banned extensions: whichever one `rglob` visits first, the single
    # entry the cap allows through is still a hit, so this scenario is
    # deterministic regardless of filesystem enumeration order.
    (newdir / "a.sh").write_text("echo hi\n")
    (newdir / "b.bat").write_text("echo hi\n")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(cwd)})))
    exit_code = scan_worktree_for_banned_scripts.main()
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "[BLOCK]" in captured.out
    assert "stopped after 1 entries" in captured.out
    assert "result may be incomplete" in captured.out
    assert "stopped after 1 entries" in captured.err


def test_truncated_scan_with_no_hits_still_exits_clean_but_notes_incompleteness(
    repo: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No banned file was found WITHIN the capped portion of the walk —
    that must not be silently reported as "no banned scripts exist"; the
    hook still fails open (exit 0), but the note must say the result may be
    incomplete."""
    cwd, env = repo
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.setattr(scan_worktree_for_banned_scripts, "_MAX_UNTRACKED_DIR_ENTRIES", 0)
    newdir = cwd / "plugins" / "dev-team" / "newfeature"
    newdir.mkdir()
    (newdir / "rogue.sh").write_text("echo hi\n")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(cwd)})))
    exit_code = scan_worktree_for_banned_scripts.main()
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "stopped after 0 entries" in captured.out
    assert "result may be incomplete" in captured.out
