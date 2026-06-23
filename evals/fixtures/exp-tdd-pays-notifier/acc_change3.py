"""Acceptance tests for Change 3 (audit log) — injected at grading time only.

Includes regression for Stage-0 core, Change-1 (fallback), and Change-2 (retry).
"""
import pytest
from notifier import NotificationService


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_send_basic():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    assert svc.send("alice", "hi").get("email") is True


def test_regression_bulk_empty():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    assert svc.send_bulk([], "hi") == {}


# ── regression: change 2 (retry) ─────────────────────────────────────────────

def test_regression_retry_success():
    n = [0]

    def flaky(r, m):
        n[0] += 1
        return n[0] >= 2

    svc = NotificationService()
    svc.register_channel("email", flaky, max_retries=2)
    assert svc.send("alice", "hi").get("email") is True


# ── new: audit log ────────────────────────────────────────────────────────────

def test_audit_log_records_successful_send():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    svc.send("alice", "hello")
    log = svc.get_audit_log()
    assert len(log) >= 1
    entry = log[0]
    assert entry["recipient"] == "alice"
    assert entry["channel"] == "email"
    assert entry["message"] == "hello"
    assert entry["success"] is True


def test_audit_log_records_failed_send():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False)
    svc.send("alice", "hi")
    log = svc.get_audit_log()
    assert any(e["channel"] == "email" and e["success"] is False for e in log)


def test_audit_log_has_entry_per_attempt_with_retry():
    """Each attempt (including retries) creates its own log entry."""
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False, max_retries=2)
    svc.send("alice", "hi")
    log = [e for e in svc.get_audit_log() if e["channel"] == "email"]
    assert len(log) == 3  # 1 original + 2 retries


def test_audit_log_persists_across_sends():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    svc.send("alice", "first")
    svc.send("bob", "second")
    assert len(svc.get_audit_log()) >= 2


def test_clear_audit_log_empties_log():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    svc.send("alice", "hi")
    svc.clear_audit_log()
    assert svc.get_audit_log() == []


def test_get_audit_log_returns_snapshot():
    """Mutating the returned list does not affect the internal log."""
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    svc.send("alice", "hi")
    log1 = svc.get_audit_log()
    log1.clear()
    log2 = svc.get_audit_log()
    assert len(log2) >= 1
