"""Unit tests for hooks/session_model_banner.py's pending-review queue notice
(issue #732 Fix C).

`_notify_pending_findings` used to read the *entire* unbounded
`metrics/pending-review.jsonl` on every SessionStart with no cap or rotation
on the underlying queue file — so a queue that accumulates disposed
(reviewed/rejected) findings over months of sessions gets slower to scan on
every single session start, forever.

This suite proves the fix: disposed entries (those carrying `reviewed_at` or
`rejected_at`) are rotated out of the queue file each time it's scanned, so
the file stays bounded to the outstanding backlog instead of growing without
limit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import session_model_banner as hook  # noqa: E402


def _entry(**kwargs) -> str:
    base = {
        "queued_at": "2026-06-01T12:00:00Z",
        "source": "session-learning-trigger",
        "session_id": "abc-123",
        "findings": [{"lever": "instruction-rule"}],
    }
    base.update(kwargs)
    return json.dumps(base)


def test_returns_none_when_queue_file_absent(tmp_path):
    assert hook._notify_pending_findings(str(tmp_path)) is None


def test_returns_none_when_no_unreviewed_entries(tmp_path):
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    queue = metrics / "pending-review.jsonl"
    queue.write_text(_entry(reviewed_at="2026-06-02T09:00:00Z") + "\n")

    assert hook._notify_pending_findings(str(tmp_path)) is None


def test_counts_unreviewed_entries(tmp_path):
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    queue = metrics / "pending-review.jsonl"
    queue.write_text(_entry(session_id="a") + "\n" + _entry(session_id="b") + "\n")

    notice = hook._notify_pending_findings(str(tmp_path))
    assert notice is not None
    assert "2 queued finding(s)" in notice


def test_rotates_out_disposed_entries(tmp_path):
    """Reviewed/rejected entries must be dropped from the queue file so it
    doesn't grow without bound; still-pending entries are preserved."""
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    queue = metrics / "pending-review.jsonl"
    queue.write_text(
        _entry(session_id="reviewed", reviewed_at="2026-06-02T09:00:00Z")
        + "\n"
        + _entry(session_id="rejected", rejected_at="2026-06-02T09:00:00Z")
        + "\n"
        + _entry(session_id="pending")
        + "\n"
    )

    notice = hook._notify_pending_findings(str(tmp_path))
    assert notice is not None
    assert "1 queued finding(s)" in notice

    remaining = [json.loads(l) for l in queue.read_text().splitlines() if l.strip()]
    assert len(remaining) == 1
    assert remaining[0]["session_id"] == "pending"


def test_rotation_keeps_file_bounded_across_repeated_session_starts(tmp_path):
    """After rotation, re-scanning the queue must not keep re-processing the
    already-disposed history — the file itself shrinks."""
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    queue = metrics / "pending-review.jsonl"
    disposed = "\n".join(
        _entry(session_id=f"done-{i}", reviewed_at="2026-06-02T09:00:00Z")
        for i in range(50)
    )
    queue.write_text(disposed + "\n" + _entry(session_id="still-pending") + "\n")

    size_before = queue.stat().st_size
    hook._notify_pending_findings(str(tmp_path))
    size_after = queue.stat().st_size

    assert size_after < size_before
    remaining = [json.loads(l) for l in queue.read_text().splitlines() if l.strip()]
    assert len(remaining) == 1
    assert remaining[0]["session_id"] == "still-pending"


def test_malformed_lines_are_preserved_not_silently_dropped(tmp_path):
    """Lines that fail to parse can't be classified as disposed or pending —
    rotation must not destroy them; leave them for /session-review's own
    malformed-line handling."""
    metrics = tmp_path / "metrics"
    metrics.mkdir()
    queue = metrics / "pending-review.jsonl"
    queue.write_text("not-json-at-all\n" + _entry(session_id="pending") + "\n")

    hook._notify_pending_findings(str(tmp_path))

    remaining = queue.read_text().splitlines()
    assert "not-json-at-all" in remaining


def test_respects_pending_review_file_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom-queue.jsonl"
    custom.write_text(_entry() + "\n")
    monkeypatch.setenv("PENDING_REVIEW_FILE", str(custom))

    notice = hook._notify_pending_findings(str(tmp_path))
    assert notice is not None
    assert "1 queued finding(s)" in notice
