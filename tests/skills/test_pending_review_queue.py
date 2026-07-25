"""Tests for the pending-review queue contract: format strings in skill
files and the pending-review-notify hook's notification logic.

The bats original shelled out to the retired hooks/session-model-banner.sh
(#572 Phase 2 ported it to hooks/session_model_banner.py — #586, #1284/#1288
split its pending-review responsibility into hooks/pending_review_notify.py
when the model-routing responsibilities it also carried were retired); this
port invokes the Python hook directly with `subprocess.run([sys.executable,
...])` and a hermetic `tmp_path` in place of `mktemp -d` + `rm -rf`.

Ported from tests/skills/pending_review_queue_tests.bats (issue #674).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT, REPO_ROOT

SESSION_REVIEW = PLUGIN_ROOT / "skills" / "session-review" / "SKILL.md"
FEEDBACK_LEARNING = PLUGIN_ROOT / "skills" / "feedback-learning" / "SKILL.md"
BANNER = PLUGIN_ROOT / "hooks" / "pending_review_notify.py"


# ---------------------------------------------------------------------------
# Schema contract: skills reference the queue and required fields
# ---------------------------------------------------------------------------


def test_session_review_references_pending_review_jsonl():
    assert "pending-review.jsonl" in SESSION_REVIEW.read_text()


def test_session_review_references_queued_at_schema_field():
    assert "queued_at" in SESSION_REVIEW.read_text()


def test_feedback_learning_references_reviewed_at_field():
    assert "reviewed_at" in FEEDBACK_LEARNING.read_text()


def test_feedback_learning_references_approved_by_field():
    assert "approved_by" in FEEDBACK_LEARNING.read_text()


def test_feedback_learning_references_rejected_at_field():
    assert "rejected_at" in FEEDBACK_LEARNING.read_text()


def test_feedback_learning_references_rejected_by_field():
    assert "rejected_by" in FEEDBACK_LEARNING.read_text()


def test_session_model_banner_references_pending_review_jsonl():
    assert "pending-review.jsonl" in BANNER.read_text()


# ---------------------------------------------------------------------------
# Banner notification: emits N queued finding(s) when unreviewed entries exist
# ---------------------------------------------------------------------------


def _run_banner_stdout(tmp_path: Path) -> str:
    payload = json.dumps(
        {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
        }
    )
    result = subprocess.run(
        [sys.executable, str(BANNER)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
        check=False,
    )
    return result.stdout


def test_banner_silent_when_metrics_pending_review_jsonl_does_not_exist(tmp_path):
    assert "queued finding" not in _run_banner_stdout(tmp_path)


def test_banner_silent_when_all_entries_have_reviewed_at(tmp_path):
    metrics = tmp_path / ".claude" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "pending-review.jsonl").write_text(
        '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1",'
        '"findings":[],"reviewed_at":"2026-06-02T00:00:00Z"}\n'
    )
    assert "queued finding" not in _run_banner_stdout(tmp_path)


def test_banner_emits_count_when_entries_lack_reviewed_at(tmp_path):
    metrics = tmp_path / ".claude" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "pending-review.jsonl").write_text(
        '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[]}\n'
        '{"queued_at":"2026-06-02T00:00:00Z","source":"auto","session_id":"s2","findings":[]}\n'
        '{"queued_at":"2026-06-03T00:00:00Z","source":"auto","session_id":"s3","findings":[]}\n'
    )
    assert "3 queued finding" in _run_banner_stdout(tmp_path)


def test_banner_notification_includes_session_review_instruction(tmp_path):
    metrics = tmp_path / ".claude" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "pending-review.jsonl").write_text(
        '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[]}\n'
    )
    assert "session-review" in _run_banner_stdout(tmp_path)


def test_banner_only_counts_entries_without_reviewed_at(tmp_path):
    metrics = tmp_path / ".claude" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "pending-review.jsonl").write_text(
        '{"queued_at":"2026-06-01T00:00:00Z","source":"auto","session_id":"s1","findings":[]}\n'
        '{"queued_at":"2026-06-02T00:00:00Z","source":"auto","session_id":"s2","findings":[],'
        '"reviewed_at":"2026-06-02T12:00:00Z"}\n'
    )
    assert "1 queued finding" in _run_banner_stdout(tmp_path)
