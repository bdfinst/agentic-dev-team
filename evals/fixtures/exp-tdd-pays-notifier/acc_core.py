"""Core acceptance tests for notifier.py — injected at grading time only.

Tests behaviours stated in both spec_clear.md and spec_vague.md.
"""
import pytest
from notifier import NotificationService


def test_register_and_send_calls_handler():
    calls = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: calls.append((r, m)) or True)
    svc.send("alice", "hello")
    assert ("alice", "hello") in calls


def test_send_returns_result_dict():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    result = svc.send("alice", "hello")
    assert isinstance(result, dict)
    assert result.get("email") is True


def test_handler_returning_false_is_recorded():
    svc = NotificationService()
    svc.register_channel("sms", lambda r, m: False)
    result = svc.send("bob", "hi")
    assert result.get("sms") is False


def test_handler_returning_false_does_not_raise():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: False)
    # Must not raise
    svc.send("alice", "hello")


def test_unregistered_channel_raises_value_error():
    svc = NotificationService()
    with pytest.raises(ValueError):
        svc.send("alice", "hi", channels=["ghost"])


def test_channels_filter_limits_dispatch():
    """Only the listed channels are called when channels=[...] is given."""
    email_calls, sms_calls = [], []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: email_calls.append(1) or True)
    svc.register_channel("sms", lambda r, m: sms_calls.append(1) or True)
    svc.send("alice", "hi", channels=["email"])
    assert len(email_calls) == 1
    assert len(sms_calls) == 0


def test_send_bulk_dispatches_to_each_recipient():
    calls = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: calls.append(r) or True)
    svc.send_bulk(["alice", "bob"], "hello")
    assert "alice" in calls
    assert "bob" in calls


def test_send_bulk_returns_per_recipient_dict():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    results = svc.send_bulk(["alice", "bob"], "hi")
    assert isinstance(results, dict)
    assert "alice" in results
    assert "bob" in results


def test_send_bulk_empty_recipients_returns_empty_dict():
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: True)
    assert svc.send_bulk([], "hello") == {}
