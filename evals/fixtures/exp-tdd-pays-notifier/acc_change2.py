"""Acceptance tests for Change 2 (per-channel retry, TRAP) — injected at grading.

Includes regression for Stage-0 core and Change-1 (fallback).
"""
import pytest
from notifier import NotificationService


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_basic_send():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    assert svc.send("alice", "hi").get("email") is True


def test_regression_unregistered_raises():
    svc = NotificationService()
    with pytest.raises(ValueError):
        svc.send("alice", "hi", channels=["ghost"])


# ── regression: change 1 (fallback) ──────────────────────────────────────────

def test_regression_fallback_triggers_on_failure():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False)
    svc.register_channel("sms", lambda r, m: True, fallback_for="email")
    result = svc.send("alice", "hi")
    assert result.get("sms") is True


# ── new: per-channel retry ────────────────────────────────────────────────────

def test_retry_succeeds_on_later_attempt():
    """Handler fails twice then succeeds; result is True."""
    attempts = []

    def flaky(r, m):
        attempts.append(1)
        return len(attempts) >= 3  # True on 3rd attempt

    svc = NotificationService()
    svc.register_channel("email", flaky, max_retries=2)
    result = svc.send("alice", "hi")
    assert result.get("email") is True
    assert len(attempts) == 3


def test_retry_exhausted_records_false():
    """All retry attempts fail → channel recorded as False."""
    attempts = []

    def always_fails(r, m):
        attempts.append(1)
        return False

    svc = NotificationService()
    svc.register_channel("email", always_fails, max_retries=2)
    result = svc.send("alice", "hi")
    assert result.get("email") is False
    assert len(attempts) == 3  # 1 original + 2 retries


def test_retry_zero_means_no_retry():
    """max_retries=0 (default) means exactly one attempt."""
    attempts = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: attempts.append(1) or False, max_retries=0)
    svc.send("alice", "hi")
    assert len(attempts) == 1


def test_retry_on_exception_counts_as_failure():
    """An exception during a retry counts as a failed attempt; retrying continues."""
    call_count = [0]

    def raises_then_succeeds(r, m):
        call_count[0] += 1
        if call_count[0] < 3:
            raise RuntimeError("transient")
        return True

    svc = NotificationService()
    svc.register_channel("email", raises_then_succeeds, max_retries=3)
    result = svc.send("alice", "hi")
    assert result.get("email") is True
    assert call_count[0] == 3


def test_retry_does_not_affect_other_channels():
    """Retrying a failing channel does not delay or skip other channels."""
    other_called = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False, max_retries=2)
    svc.register_channel("push", lambda r, m: other_called.append(1) or True)
    svc.send("alice", "hi")
    assert len(other_called) == 1
