"""Tests for scripts/ci_tree_cache.py — skip a gate whose tree has not changed
since it last passed (issue #2002).

`chk_hook_units` collects 9,469 tests and is the gate's wall-clock long pole:
1,029 runs in 30 days (27% of all pytest invocations), including 35 sessions
that re-ran the identical command >= 8 times and one that ran it 34 times.

This is a gate-SKIPPING mechanism, so the tests below are weighted toward the
dangerous direction: every failure path must answer "not fresh" (run the
suite), and only a byte-identical tree may answer "fresh".
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import ci_tree_cache


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway git repo with its own cache file, so nothing here can read
    or clobber the developer's real ~/.cache entry."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@e.st"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)

    cache = tmp_path / "cache" / "tree-cache.json"
    monkeypatch.setattr(ci_tree_cache, "cache_path", lambda: cache)
    return root


CHECK = "chk_hook_units"


# --- the core contract ------------------------------------------------------


def test_cold_cache_is_not_fresh(repo):
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_recorded_tree_is_fresh(repo):
    ci_tree_cache.record(repo, CHECK)
    assert ci_tree_cache.is_fresh(repo, CHECK) is True


def test_editing_a_tracked_file_invalidates(repo):
    ci_tree_cache.record(repo, CHECK)
    (repo / "a.py").write_text("print(2)\n", encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_adding_an_untracked_file_invalidates(repo):
    """A brand-new test file nobody has `git add`ed yet still changes what the
    suite collects, so it must invalidate."""
    ci_tree_cache.record(repo, CHECK)
    (repo / "test_new.py").write_text("def test_x(): pass\n", encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_deleting_a_file_invalidates(repo):
    ci_tree_cache.record(repo, CHECK)
    (repo / "a.py").unlink()
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_renaming_a_file_invalidates(repo):
    """Path feeds the digest, so identical bytes at a new path is a new tree."""
    ci_tree_cache.record(repo, CHECK)
    (repo / "a.py").rename(repo / "b.py")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_an_ignored_file_does_not_invalidate(repo):
    """Build output and caches are not inputs to the suite."""
    (repo / ".gitignore").write_text("junk/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "ignore"], check=True)
    ci_tree_cache.record(repo, CHECK)
    (repo / "junk").mkdir()
    (repo / "junk" / "out.bin").write_text("x", encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is True


def test_reverting_an_edit_restores_freshness(repo):
    """The key is content, not a timestamp — restoring the bytes restores the
    verdict. This is what collapses the 34x-in-one-session case."""
    ci_tree_cache.record(repo, CHECK)
    original = (repo / "a.py").read_text(encoding="utf-8")
    (repo / "a.py").write_text("print(2)\n", encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False
    (repo / "a.py").write_text(original, encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is True


# --- every failure path answers "not fresh" ---------------------------------


def test_an_uncacheable_check_is_never_fresh(repo):
    """Allowlist, mirroring the safe default the --changed-only levers use for
    unmapped checks."""
    ci_tree_cache.record(repo, "chk_ruff")
    assert ci_tree_cache.is_fresh(repo, "chk_ruff") is False


def test_recording_an_uncacheable_check_writes_nothing(repo):
    ci_tree_cache.record(repo, "chk_ruff")
    assert not ci_tree_cache.cache_path().exists()


def test_a_corrupt_cache_is_not_fresh(repo):
    ci_tree_cache.record(repo, CHECK)
    ci_tree_cache.cache_path().write_text("{not json", encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_a_non_dict_cache_is_not_fresh(repo):
    ci_tree_cache.record(repo, CHECK)
    ci_tree_cache.cache_path().write_text("[]", encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_a_cache_from_an_older_version_is_not_fresh(repo):
    ci_tree_cache.record(repo, CHECK)
    payload = json.loads(ci_tree_cache.cache_path().read_text(encoding="utf-8"))
    payload["version"] = ci_tree_cache.CACHE_VERSION - 1
    ci_tree_cache.cache_path().write_text(json.dumps(payload), encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_a_non_string_stored_key_is_not_fresh(repo):
    ci_tree_cache.record(repo, CHECK)
    path = ci_tree_cache.cache_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"] = dict.fromkeys(payload["entries"], 12345)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_an_empty_stored_key_is_not_fresh(repo):
    ci_tree_cache.record(repo, CHECK)
    path = ci_tree_cache.cache_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"] = dict.fromkeys(payload["entries"], "")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert ci_tree_cache.is_fresh(repo, CHECK) is False


def test_a_sibling_worktree_does_not_share_a_verdict(repo, tmp_path):
    """Entries are namespaced by repo root: two worktrees have different trees
    at the same check name, and one's green must never skip the other's run."""
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    ci_tree_cache.record(repo, CHECK)
    assert ci_tree_cache.is_fresh(repo, CHECK) is True
    assert ci_tree_cache.is_fresh(other, CHECK) is False


# --- CLI --------------------------------------------------------------------


def _cli(*args, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ci_tree_cache.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
    )


def test_cli_is_fresh_exits_nonzero_when_cold(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert _cli("is-fresh", CHECK, cwd=repo).returncode != 0


def test_cli_record_then_is_fresh_exits_zero(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert _cli("record", CHECK, cwd=repo).returncode == 0
    assert _cli("is-fresh", CHECK, cwd=repo).returncode == 0


def test_cli_outside_a_git_repo_exits_nonzero(tmp_path, monkeypatch):
    """A git failure must never present as a skip."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _cli("is-fresh", CHECK, cwd=plain).returncode != 0


def test_cli_key_is_stable_across_invocations(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    first = _cli("key", cwd=repo)
    second = _cli("key", cwd=repo)
    assert first.returncode == 0
    assert first.stdout.strip() == second.stdout.strip()
    assert len(first.stdout.strip()) == 64


def test_cli_clear_removes_the_cache(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    _cli("record", CHECK, cwd=repo)
    assert _cli("is-fresh", CHECK, cwd=repo).returncode == 0
    assert _cli("clear", cwd=repo).returncode == 0
    assert _cli("is-fresh", CHECK, cwd=repo).returncode != 0


# --- wiring in ci-local.sh --------------------------------------------------


def test_ci_local_records_only_on_a_green_run():
    """A red run must never poison the cache into skipping the very failure it
    just found. Pinned against the script text because reproducing a red
    9,469-test run in a unit test is not worth 80 seconds."""
    text = (REPO_ROOT / "scripts" / "ci-local.sh").read_text(encoding="utf-8")
    assert 'if [ "$rc" -eq 0 ]' in text
    record_line = "ci_tree_cache.py record chk_hook_units"
    assert record_line in text
    guard_index = text.index('if [ "$rc" -eq 0 ]')
    assert text.index(record_line) > guard_index


def test_ci_local_exposes_an_opt_out():
    text = (REPO_ROOT / "scripts" / "ci-local.sh").read_text(encoding="utf-8")
    assert "CI_LOCAL_NO_TREE_CACHE" in text


def test_ci_local_skip_message_says_skipped_not_a_fake_duration():
    """Consistent with the existing --changed-only output contract — never a
    0.00s masquerading as a run."""
    text = (REPO_ROOT / "scripts" / "ci-local.sh").read_text(encoding="utf-8")
    assert "skipped (tree unchanged since this suite last passed" in text
