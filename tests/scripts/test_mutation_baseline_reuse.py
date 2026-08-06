"""Pytest tests for mutation_baseline_reuse.py — baseline consumption
tracking and the git-backed resolve/mark-consumed CLI (Slice 2 of
plans/mutation-kill-baseline-reuse-round-1.md, #1545).

Each test maps to a Slice 2 Gherkin scenario in that plan. Every git
subprocess is mocked — no real git calls run in the CLI tests — mirroring
``test_mutation_kill_loop.py``'s existing ``git_revert``/``git_commit`` mock
pattern (``monkeypatch.setattr(loop.subprocess, "run", ...)``).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from _mutation_test_helpers import FORBIDDEN_LITERALS, SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_baseline_reuse as mbr


# =============================================================================
# read_tracking
# =============================================================================
def test_read_tracking_returns_empty_dict_when_file_absent(tmp_path: Path):
    assert mbr.read_tracking(tmp_path / "does-not-exist.json") == {}


def test_read_tracking_returns_empty_dict_for_malformed_json(tmp_path: Path):
    path = tmp_path / "tracking.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert mbr.read_tracking(path) == {}


def test_read_tracking_returns_parsed_dict_when_present(tmp_path: Path):
    path = tmp_path / "tracking.json"
    payload = {"src/Foo.cs": {"capture_commit": "abc123", "recorded_at": "x"}}
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert mbr.read_tracking(path) == payload


def test_read_tracking_returns_empty_dict_for_non_dict_json(tmp_path: Path):
    """A tracking file containing valid but non-dict JSON (e.g. a list or a
    bare number) is treated the same as malformed/absent — never raised."""
    path = tmp_path / "tracking.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    assert mbr.read_tracking(path) == {}


def test_non_dict_tracking_file_never_raises_in_eligibility_or_mark_consumed(
    tmp_path: Path,
):
    path = tmp_path / "tracking.json"
    path.write_text(json.dumps(42), encoding="utf-8")

    tracking = mbr.read_tracking(path)
    assert tracking == {}
    assert (
        mbr.is_eligible_for_reuse(
            tracking, "src/Foo.cs", "capture-sha", is_ancestor=True
        )
        is True
    )
    result = mbr.mark_consumed(path, "src/Foo.cs", "capture-sha")
    assert result == {"success": True}


# =============================================================================
# is_eligible_for_reuse — decision matrix
# =============================================================================
def test_not_ancestor_is_not_eligible():
    assert (
        mbr.is_eligible_for_reuse({}, "src/Foo.cs", "capture-sha", is_ancestor=False)
        is False
    )


def test_ancestor_and_unconsumed_is_eligible():
    assert (
        mbr.is_eligible_for_reuse({}, "src/Foo.cs", "capture-sha", is_ancestor=True)
        is True
    )


def test_self_ancestor_boundary_is_eligible(monkeypatch: pytest.MonkeyPatch):
    """git's own ``--is-ancestor`` treats a commit as its own ancestor —
    exercise ``_git_is_ancestor`` directly with commit_a == commit_b,
    mocking ``subprocess.run`` to return success (returncode 0) for the
    matching SHAs. This is the actual git-level boundary property the
    module's docstring describes; ``is_eligible_for_reuse`` itself is pure
    and takes ``is_ancestor`` as a given, so it has no boundary of its own to
    test here (that's already covered by
    ``test_ancestor_and_unconsumed_is_eligible``)."""
    same_sha = "abc123"

    monkeypatch.setattr(
        mbr.subprocess,
        "run",
        lambda argv, **_k: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
    )

    assert mbr._git_is_ancestor(same_sha, same_sha) is True


def test_consumed_at_same_capture_commit_is_not_eligible():
    tracking = {"src/Foo.cs": {"capture_commit": "capture-sha", "recorded_at": "x"}}

    assert (
        mbr.is_eligible_for_reuse(
            tracking, "src/Foo.cs", "capture-sha", is_ancestor=True
        )
        is False
    )


def test_consumed_at_older_commit_is_eligible_again_under_different_baseline():
    tracking = {"src/Foo.cs": {"capture_commit": "older-sha", "recorded_at": "x"}}

    assert (
        mbr.is_eligible_for_reuse(
            tracking, "src/Foo.cs", "newer-sha", is_ancestor=True
        )
        is True
    )


# =============================================================================
# mark_consumed
# =============================================================================
def test_mark_consumed_creates_tracking_file_atomically(tmp_path: Path):
    path = tmp_path / "tracking.json"

    result = mbr.mark_consumed(path, "src/Foo.cs", "capture-sha")

    assert result == {"success": True}
    assert not (tmp_path / "tracking.json.tmp").exists()
    reread = mbr.read_tracking(path)
    assert reread["src/Foo.cs"]["capture_commit"] == "capture-sha"
    assert "recorded_at" in reread["src/Foo.cs"]


def test_mark_consumed_preserves_other_files_entries(tmp_path: Path):
    path = tmp_path / "tracking.json"
    mbr.mark_consumed(path, "src/A.cs", "capture-sha")

    result = mbr.mark_consumed(path, "src/B.cs", "capture-sha")

    assert result == {"success": True}
    reread = mbr.read_tracking(path)
    assert reread["src/A.cs"]["capture_commit"] == "capture-sha"
    assert reread["src/B.cs"]["capture_commit"] == "capture-sha"


def test_mark_consumed_write_failure_returns_error_and_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "tracking.json"

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(mbr.os, "replace", boom)

    result = mbr.mark_consumed(path, "src/Foo.cs", "capture-sha")

    assert result["success"] is False
    assert "disk full" in result["error"]
    # Left as not-yet-consumed — the target file was never created.
    assert mbr.read_tracking(path) == {}
    # The .tmp written just before the failed os.replace does not survive.
    assert not (tmp_path / "tracking.json.tmp").exists()


# =============================================================================
# _git_last_commit_sha / _git_is_ancestor
# =============================================================================
def test_mark_consumed_second_failure_during_cleanup_never_masks_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``os.replace`` fails, and the best-effort ``tmp.unlink()`` cleanup that
    follows it *also* raises ``OSError``. The inner failure must be swallowed
    — never overwriting or masking the original ``os.replace`` error, and
    never propagating to the caller."""
    path = tmp_path / "tracking.json"

    def replace_boom(_src, _dst):
        raise OSError("disk full")

    def unlink_boom(self, missing_ok=False):
        raise OSError("permission denied")

    monkeypatch.setattr(mbr.os, "replace", replace_boom)
    monkeypatch.setattr(mbr.Path, "unlink", unlink_boom)

    result = mbr.mark_consumed(path, "src/Foo.cs", "capture-sha")

    assert result == {"success": False, "error": "disk full"}


# =============================================================================
# Concurrency — today's unlocked lost-update race (Step 1.2 of #1941/#1920).
# No production code change in this step: this proves the defect exists
# against TODAY's unlocked mark_consumed. Step 1.3 wraps the read-modify-write
# in hooks/lib/atomic_state.py::locked_state(strict=True) and removes the
# xfail marker below, keeping this test as a permanent passing regression
# test from that point on.
# =============================================================================
@pytest.mark.xfail(
    strict=True,
    reason=(
        "today's mark_consumed has no interprocess lock around its "
        "read-modify-write; fixed in Step 1.3 (#1920), which will remove "
        "this xfail marker"
    ),
)
def test_unlocked_mark_consumed_loses_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Two concurrent mark-consumed calls for two *different* file_path keys
    against a not-yet-existing tracking file lose one entry, because
    today's ``mark_consumed`` has no lock around its read-modify-write.

    Interleaving is forced deterministically (no sleep-based timing, no
    real race on the shared ``.tmp`` file): the first call ("A")'s read of
    the tracking file happens immediately, but is held back from returning
    to ``mark_consumed`` until the second call ("B") has fully completed
    its own read-modify-write. This reproduces exactly the scenario in
    Slice 1's Gherkin — "the second process's read forced to occur before
    the first process's write completes" — while keeping the outcome
    deterministic: A's stale (pre-B) snapshot is what A eventually writes,
    so A's write clobbers B's already-completed write and B's entry is
    lost.
    """
    path = tmp_path / "tracking.json"
    original_read_tracking = mbr.read_tracking
    a_has_read = threading.Event()
    b_has_written = threading.Event()
    thread_a: threading.Thread

    def delayed_read_tracking(tracking_path):
        result = original_read_tracking(tracking_path)
        if threading.current_thread() is thread_a:
            a_has_read.set()
            assert b_has_written.wait(timeout=5), "b never finished writing"
        return result

    monkeypatch.setattr(mbr, "read_tracking", delayed_read_tracking)

    results: dict[str, dict] = {}

    def call_a():
        results["a"] = mbr.mark_consumed(path, "src/A.cs", "capture-sha")

    def call_b():
        assert a_has_read.wait(timeout=5), "a never reached its read"
        results["b"] = mbr.mark_consumed(path, "src/B.cs", "capture-sha")
        b_has_written.set()

    thread_a = threading.Thread(target=call_a)
    thread_b = threading.Thread(target=call_b)
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert results["a"] == {"success": True}
    assert results["b"] == {"success": True}

    tracking = original_read_tracking(path)
    assert "src/A.cs" in tracking
    assert "src/B.cs" in tracking, "src/B.cs's entry was lost to the race"


def test_git_last_commit_sha_returns_stripped_sha(monkeypatch: pytest.MonkeyPatch):
    seen: list = []

    def fake_run(argv, **_k):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="abc123\n", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    assert mbr._git_last_commit_sha("src/Foo.cs") == "abc123"
    assert seen == [["git", "log", "-1", "--format=%H", "--", "src/Foo.cs"]]


def test_git_last_commit_sha_returns_none_for_empty_result(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        mbr.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""),
    )

    assert mbr._git_last_commit_sha("src/Untracked.cs") is None


def test_git_last_commit_sha_returns_none_when_git_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    def explode(*_a, **_k):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(mbr.subprocess, "run", explode)

    assert mbr._git_last_commit_sha("src/Foo.cs") is None


def test_git_last_commit_sha_returns_none_on_timeout(monkeypatch: pytest.MonkeyPatch):
    def explode(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git log", timeout=30)

    monkeypatch.setattr(mbr.subprocess, "run", explode)

    assert mbr._git_last_commit_sha("src/Foo.cs") is None


def test_git_is_ancestor_true_on_zero_returncode(monkeypatch: pytest.MonkeyPatch):
    seen: list = []

    def fake_run(argv, **_k):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    assert mbr._git_is_ancestor("aaa", "bbb") is True
    assert seen == [["git", "merge-base", "--is-ancestor", "--", "aaa", "bbb"]]


def test_git_is_ancestor_false_on_nonzero_returncode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        mbr.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr=""),
    )

    assert mbr._git_is_ancestor("aaa", "bbb") is False


def test_git_is_ancestor_false_when_git_missing(monkeypatch: pytest.MonkeyPatch):
    def explode(*_a, **_k):
        raise OSError("no git")

    monkeypatch.setattr(mbr.subprocess, "run", explode)

    assert mbr._git_is_ancestor("aaa", "bbb") is False


def test_git_is_ancestor_false_on_timeout(monkeypatch: pytest.MonkeyPatch):
    def explode(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git merge-base", timeout=30)

    monkeypatch.setattr(mbr.subprocess, "run", explode)

    assert mbr._git_is_ancestor("aaa", "bbb") is False


# =============================================================================
# CLI — resolve
# =============================================================================
def test_cli_resolve_eligible_true_for_ancestor_unconsumed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"

    def fake_run(argv, **_k):
        if argv[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(argv, 0, stdout="filesha\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    rc = mbr._cli(
        [
            "resolve",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "eligible": True,
        "file": "src/Foo.cs",
        "capture_commit": "capture-sha",
    }


def test_cli_resolve_eligible_false_for_non_ancestor_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"

    def fake_run(argv, **_k):
        if argv[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(argv, 0, stdout="filesha\n", stderr="")
        # merge-base --is-ancestor: non-zero == not an ancestor
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    rc = mbr._cli(
        [
            "resolve",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["eligible"] is False


def test_cli_resolve_eligible_false_for_already_consumed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"
    mbr.mark_consumed(tracking_path, "src/Foo.cs", "capture-sha")

    def fake_run(argv, **_k):
        if argv[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(argv, 0, stdout="filesha\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    rc = mbr._cli(
        [
            "resolve",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["eligible"] is False


def test_cli_resolve_eligible_false_never_raises_when_git_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"

    def explode(*_a, **_k):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(mbr.subprocess, "run", explode)

    rc = mbr._cli(
        [
            "resolve",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["eligible"] is False


def test_cli_resolve_eligible_false_for_no_commit_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"

    monkeypatch.setattr(
        mbr.subprocess,
        "run",
        lambda argv, **_k: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
    )

    rc = mbr._cli(
        [
            "resolve",
            "--file",
            "src/Untracked.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["eligible"] is False


def test_cli_resolve_forwards_cwd_to_git_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"
    seen_cwds: list = []

    def fake_run(argv, **kwargs):
        seen_cwds.append(kwargs.get("cwd"))
        if argv[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(argv, 0, stdout="filesha\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    rc = mbr._cli(
        [
            "resolve",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
            "--cwd",
            "/some/repo",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["eligible"] is True
    assert seen_cwds == ["/some/repo", "/some/repo"]


# =============================================================================
# CLI — mark-consumed
# =============================================================================
def test_cli_mark_consumed_success_true_on_normal_write(
    tmp_path: Path, capsys
):
    tracking_path = tmp_path / "tracking.json"

    rc = mbr._cli(
        [
            "mark-consumed",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"success": True}
    assert mbr.read_tracking(tracking_path)["src/Foo.cs"]["capture_commit"] == (
        "capture-sha"
    )


def test_cli_mark_consumed_success_false_with_error_on_forced_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    tracking_path = tmp_path / "tracking.json"

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(mbr.os, "replace", boom)

    rc = mbr._cli(
        [
            "mark-consumed",
            "--file",
            "src/Foo.cs",
            "--capture-commit",
            "capture-sha",
            "--tracking",
            str(tracking_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "disk full" in payload["error"]


# =============================================================================
# Scenario: the module carries no repo-specific literal
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_baseline_reuse.py").read_text(encoding="utf-8")

    present = [lit for lit in FORBIDDEN_LITERALS if lit in source]

    assert present == [], f"repo-specific literals leaked into module: {present}"
