"""Acceptance tests for Change 1 (fallback channels) — injected at grading time only.

Includes regression for Stage-0 core behaviour.
"""
import pytest
from notifier import NotificationService


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_send_returns_result():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    result = svc.send("alice", "hi")
    assert result.get("email") is True


def test_regression_false_handler_no_raise():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False)
    result = svc.send("alice", "hi")
    assert result.get("email") is False


def test_regression_unregistered_raises():
    svc = NotificationService()
    with pytest.raises(ValueError):
        svc.send("alice", "hi", channels=["ghost"])


def test_regression_send_bulk_empty():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    assert svc.send_bulk([], "hi") == {}


# ── new: fallback channels ────────────────────────────────────────────────────

def test_fallback_not_tried_when_primary_succeeds():
    fallback_calls = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    svc.register_channel("sms", lambda r, m: fallback_calls.append(1) or True,
                         fallback_for="email")
    svc.send("alice", "hi")
    assert fallback_calls == []


def test_fallback_tried_when_primary_returns_false():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False)
    svc.register_channel("sms", lambda r, m: True, fallback_for="email")
    result = svc.send("alice", "hi")
    assert result.get("email") is False
    assert result.get("sms") is True


def test_fallback_tried_when_primary_raises():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: 1/0)  # raises ZeroDivisionError
    svc.register_channel("sms", lambda r, m: True, fallback_for="email")
    result = svc.send("alice", "hi")
    assert result.get("email") is False
    assert result.get("sms") is True


def test_no_fallback_only_primary_in_result_when_none():
    """When channels=None, fallback channels are not included unless triggered."""
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    svc.register_channel("sms", lambda r, m: True, fallback_for="email")
    result = svc.send("alice", "hi")
    # email succeeded → sms fallback not in result
    assert "email" in result
    assert "sms" not in result
