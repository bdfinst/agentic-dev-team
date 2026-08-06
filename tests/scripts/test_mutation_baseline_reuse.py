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
import time
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


def test_mark_consumed_lock_acquisition_failure_reports_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A lock-acquisition failure inside ``atomic_state.locked_state(...,
    strict=True)`` (here: the lock directory's ``mkdir`` raising ``OSError``,
    forcing the ``strict=True`` ``RuntimeError`` path) is caught by
    ``mark_consumed`` and reported as ``{"success": False, "error": ...}``
    rather than propagating an uncaught exception — and the pre-existing
    on-disk tracking file is left byte-for-byte unchanged (#1920/#1941 Step
    1.4)."""
    path = tmp_path / "tracking.json"
    mbr.mark_consumed(path, "src/Existing.cs", "older-sha")
    original_bytes = path.read_bytes()

    def boom(self, *_a, **_k):
        raise OSError("permission denied creating lock directory")

    monkeypatch.setattr(mbr.atomic_state.Path, "mkdir", boom)

    result = mbr.mark_consumed(path, "src/New.cs", "capture-sha")

    assert result["success"] is False
    assert "permission denied" in result["error"]
    # The pre-existing entry survives untouched; no new entry was added and
    # no partial/corrupt file resulted.
    assert path.read_bytes() == original_bytes


def test_mark_consumed_lock_acquisition_failure_leaves_no_file_when_none_existed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Same lock-acquisition failure as above, but for a tracking file that
    does not yet exist on disk — no partial/corrupt file must be created."""
    path = tmp_path / "does-not-exist" / "tracking.json"

    def boom(self, *_a, **_k):
        raise OSError("permission denied creating lock directory")

    monkeypatch.setattr(mbr.atomic_state.Path, "mkdir", boom)

    result = mbr.mark_consumed(path, "src/New.cs", "capture-sha")

    assert result["success"] is False
    assert "permission denied" in result["error"]
    assert not path.exists()
    assert not (tmp_path / "does-not-exist").exists()


def test_mark_consumed_lock_acquisition_failure_never_touches_an_unrelated_tmp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A lock-acquisition failure must never delete a tmp file this call did
    not itself create (#1920 correctness review) — even one sitting at what
    used to be the shared, predictable ``<tracking_path>.tmp`` name a
    different, still-in-flight concurrent caller could be writing to.
    ``mark_consumed`` now names its own tmp file via ``tempfile.mkstemp``
    inside the lock, and never even reaches that call when lock acquisition
    itself fails — so the cleanup path (guarded on a local variable that
    stays ``None`` until ``mkstemp`` actually returns a name) has nothing to
    clean up and never touches this pre-existing, unrelated file."""
    path = tmp_path / "tracking.json"
    other_callers_tmp = Path(str(path) + ".tmp")
    other_callers_tmp.write_text(
        "in-flight write from a different caller", encoding="utf-8"
    )

    def boom(self, *_a, **_k):
        raise OSError("permission denied creating lock directory")

    monkeypatch.setattr(mbr.atomic_state.Path, "mkdir", boom)

    result = mbr.mark_consumed(path, "src/New.cs", "capture-sha")

    assert result["success"] is False
    assert other_callers_tmp.read_text(encoding="utf-8") == (
        "in-flight write from a different caller"
    )


# =============================================================================
# Concurrency — mark_consumed's lost-update race, now closed (Step 1.3 of
# #1941/#1920). This test originated in Step 1.2 as an xfail proving TODAY's
# unlocked mark_consumed loses an update; Step 1.3 wrapped the read-modify-
# write in hooks/lib/atomic_state.py::locked_state(strict=True) and removed
# the xfail marker, keeping this test as a permanent passing regression test.
#
# Step 1.2's forced-interleave harness (hold call "A" inside its read via a
# threading.Event pair until call "B" fully completes) assumed unlocked
# execution: it doesn't survive the fix, because with the lock now held for
# A's *entire* critical section, B can never even begin its own critical
# section — let alone finish it — while A holds the lock, so B's own
# mark_consumed call would time out waiting for A's lock instead of the two
# ever truly interleaving. The lock supplies the ordering guarantee the old
# harness manufactured by hand; a plain concurrent-start race (barrier plus a
# widened read-then-write window, no cross-call event dependency) is what
# actually exercises the guarantee now.
# =============================================================================
def test_concurrent_mark_consumed_does_not_lose_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Two concurrent mark-consumed calls for two *different* file_path keys
    against a not-yet-existing tracking file both succeed and both entries
    land — Step 1.3's lock serializes each call's read-modify-write span so
    the second caller's read can never observe a state older than the first
    caller's completed write.

    Both threads start via a ``threading.Barrier`` at (as close to) the same
    instant, and ``read_tracking`` is patched to sleep briefly before
    returning — widening the window in which an unlocked implementation
    would race — so whichever call wins the lock still has ample opportunity
    for the other to attempt (and be forced to wait for) the same lock.
    """
    path = tmp_path / "tracking.json"
    original_read_tracking = mbr.read_tracking
    start_barrier = threading.Barrier(2)

    def delayed_read_tracking(tracking_path):
        result = original_read_tracking(tracking_path)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(mbr, "read_tracking", delayed_read_tracking)

    results: dict[str, dict] = {}

    def call(key: str, file_path: str) -> None:
        start_barrier.wait(timeout=5)
        results[key] = mbr.mark_consumed(path, file_path, "capture-sha")

    thread_a = threading.Thread(target=call, args=("a", "src/A.cs"))
    thread_b = threading.Thread(target=call, args=("b", "src/B.cs"))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert results["a"] == {"success": True}
    assert results["b"] == {"success": True}

    tracking = original_read_tracking(path)
    assert "src/A.cs" in tracking
    assert "src/B.cs" in tracking, "src/B.cs's entry was lost to the race"


def _run_concurrent_mark_consumed(
    monkeypatch: pytest.MonkeyPatch, path: Path, calls: list[tuple[str, str]]
) -> list[dict]:
    """Run ``mark_consumed(path, file_path, capture_commit)`` for each
    ``(file_path, capture_commit)`` pair in ``calls`` concurrently against
    the same ``path``, starting every thread via a barrier at (as close to)
    the same instant and widening the post-read window with a short sleep —
    the same forced-race shape as
    ``test_unlocked_mark_consumed_loses_an_update`` above. Returns results in
    the same order as ``calls``.
    """
    original_read_tracking = mbr.read_tracking
    barrier = threading.Barrier(len(calls))

    def delayed_read_tracking(tracking_path):
        result = original_read_tracking(tracking_path)
        time.sleep(0.05)
        return result

    monkeypatch.setattr(mbr, "read_tracking", delayed_read_tracking)

    results: list[dict | None] = [None] * len(calls)

    def run(index: int, file_path: str, capture_commit: str) -> None:
        barrier.wait(timeout=5)
        results[index] = mbr.mark_consumed(path, file_path, capture_commit)

    threads = [
        threading.Thread(target=run, args=(i, file_path, capture_commit))
        for i, (file_path, capture_commit) in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    return results


def test_locked_mark_consumed_survives_concurrent_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """All three concurrent-writer scenarios from Slice 1's Gherkin: with
    the lock (#1920) in place, none of them loses an update, and the
    tracking file remains valid, parseable JSON throughout.
    """
    # Scenario 1: two different keys race to create the tracking file.
    path_create = tmp_path / "create" / "tracking.json"
    results = _run_concurrent_mark_consumed(
        monkeypatch,
        path_create,
        [("src/A.cs", "capture-sha"), ("src/B.cs", "capture-sha")],
    )
    assert results == [{"success": True}, {"success": True}]
    tracking = mbr.read_tracking(path_create)
    assert set(tracking) == {"src/A.cs", "src/B.cs"}

    # Scenario 2: two different, not-yet-consumed keys race against an
    # already-existing file that already has one unrelated entry.
    path_existing = tmp_path / "existing" / "tracking.json"
    mbr.mark_consumed(path_existing, "src/Existing.cs", "older-sha")
    results = _run_concurrent_mark_consumed(
        monkeypatch,
        path_existing,
        [("src/C.cs", "capture-sha"), ("src/D.cs", "capture-sha")],
    )
    assert results == [{"success": True}, {"success": True}]
    tracking = mbr.read_tracking(path_existing)
    assert set(tracking) == {"src/Existing.cs", "src/C.cs", "src/D.cs"}

    # Scenario 3: two calls race on the SAME key/capture-commit — idempotent
    # single-entry outcome, no corruption.
    path_same_key = tmp_path / "same-key" / "tracking.json"
    results = _run_concurrent_mark_consumed(
        monkeypatch,
        path_same_key,
        [("src/E.cs", "capture-sha"), ("src/E.cs", "capture-sha")],
    )
    assert results == [{"success": True}, {"success": True}]
    tracking = mbr.read_tracking(path_same_key)
    assert list(tracking.keys()) == ["src/E.cs"]
    assert tracking["src/E.cs"]["capture_commit"] == "capture-sha"
    # Re-parse the raw bytes directly (not through read_tracking's own
    # malformed-JSON tolerance) to prove the file itself is not corrupted.
    raw = json.loads(path_same_key.read_text(encoding="utf-8"))
    assert raw == tracking


def test_resolve_does_not_block_behind_mark_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """``resolve`` never blocks behind ``mark_consumed``'s lock — held here
    for a *different* file for >= 2s — because ``resolve``/``read_tracking``
    are lock-free by design (#1920): a stale read can only under-count
    eligibility, never double-consume, since ``mark_consumed`` is the sole,
    now-serialized writer.
    """
    tracking_path = tmp_path / "tracking.json"
    tracking_path.write_text("{}", encoding="utf-8")
    lock_held = threading.Event()
    hold_seconds = 2.0

    def hold_lock():
        with mbr.atomic_state.locked_state(tracking_path, strict=True):
            lock_held.set()
            time.sleep(hold_seconds)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert lock_held.wait(timeout=2), "holder thread never acquired the lock"

        def fake_run(argv, **_k):
            if argv[:2] == ["git", "log"]:
                return subprocess.CompletedProcess(
                    argv, 0, stdout="filesha\n", stderr=""
                )
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr(mbr.subprocess, "run", fake_run)

        start = time.monotonic()
        rc = mbr._cli(
            [
                "resolve",
                "--file",
                "src/Other.cs",
                "--capture-commit",
                "capture-sha",
                "--tracking",
                str(tracking_path),
            ]
        )
        elapsed = time.monotonic() - start
    finally:
        holder.join(timeout=hold_seconds + 3)

    assert not holder.is_alive(), "holder thread never released the lock"
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["eligible"] is True
    assert elapsed < 0.2, f"resolve blocked behind mark_consumed's lock: {elapsed}s"


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
# Absolute-path invocation from an unrelated cwd (#1920/#1941 Step 1.4) —
# simulates a --concurrency > 1 worktree: the process's actual cwd (and
# resolve's --cwd) point somewhere unrelated to the tracking file's own
# directory, with --tracking passed as an absolute path elsewhere. Neither
# resolve/_resolve nor mark-consumed/mark_consumed ever resolves --tracking,
# --file, or --cwd relative to this script's own location — only to the
# caller-supplied --cwd/CWD (confirmed by reading _cli/_resolve/
# _mark_consumed/_git_last_commit_sha/_git_is_ancestor: every path value is
# used as-is, and mutation_report.load_report's Path(report_path) is never
# joined with Path(__file__)) — so no production code change was needed for
# this to already work.
# =============================================================================
def test_baseline_reuse_absolute_path_from_unrelated_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **_k):
        if argv[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(argv, 0, stdout="filesha\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mbr.subprocess, "run", fake_run)

    def run_resolve_then_mark_consumed(
        *, cwd_for_process: Path, tracking_path: Path, cwd_flag: str
    ) -> tuple[int, dict, int, dict, dict]:
        monkeypatch.chdir(cwd_for_process)
        rc_resolve = mbr._cli(
            [
                "resolve",
                "--file",
                "src/Foo.cs",
                "--capture-commit",
                "capture-sha",
                "--tracking",
                str(tracking_path),
                "--cwd",
                cwd_flag,
            ]
        )
        resolve_payload = json.loads(capsys.readouterr().out)

        rc_mark = mbr._cli(
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
        mark_payload = json.loads(capsys.readouterr().out)
        entry = mbr.read_tracking(tracking_path)["src/Foo.cs"]
        return rc_resolve, resolve_payload, rc_mark, mark_payload, entry

    # Same-directory invocation: process cwd IS the tracking file's own
    # directory, and --cwd matches it too.
    same_dir = tmp_path / "same-dir"
    same_dir.mkdir()
    same_dir_tracking = same_dir / "tracking.json"
    (
        rc_resolve_same,
        resolve_payload_same,
        rc_mark_same,
        mark_payload_same,
        entry_same,
    ) = run_resolve_then_mark_consumed(
        cwd_for_process=same_dir,
        tracking_path=same_dir_tracking,
        cwd_flag=str(same_dir),
    )

    # Unrelated-cwd invocation: absolute --tracking path lives elsewhere,
    # and both the process's actual cwd and resolve's --cwd point at a
    # third, unrelated temp directory — exactly the --concurrency > 1
    # worktree shape (worktree cwd, main-checkout absolute tracking path).
    unrelated_cwd = tmp_path / "unrelated-worktree"
    unrelated_cwd.mkdir()
    elsewhere_tracking = tmp_path / "elsewhere" / "tracking.json"
    elsewhere_tracking.parent.mkdir(parents=True)
    (
        rc_resolve_unrelated,
        resolve_payload_unrelated,
        rc_mark_unrelated,
        mark_payload_unrelated,
        entry_unrelated,
    ) = run_resolve_then_mark_consumed(
        cwd_for_process=unrelated_cwd,
        tracking_path=elsewhere_tracking,
        cwd_flag=str(unrelated_cwd),
    )

    assert rc_resolve_unrelated == rc_resolve_same == 0
    assert rc_mark_unrelated == rc_mark_same == 0
    assert (
        resolve_payload_unrelated
        == resolve_payload_same
        == {
            "eligible": True,
            "file": "src/Foo.cs",
            "capture_commit": "capture-sha",
        }
    )
    assert mark_payload_unrelated == mark_payload_same == {"success": True}
    assert (
        entry_unrelated["capture_commit"]
        == entry_same["capture_commit"]
        == ("capture-sha")
    )


# =============================================================================
# Scenario: the module carries no repo-specific literal
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "mutation_baseline_reuse.py").read_text(encoding="utf-8")

    present = [lit for lit in FORBIDDEN_LITERALS if lit in source]

    assert present == [], f"repo-specific literals leaked into module: {present}"
