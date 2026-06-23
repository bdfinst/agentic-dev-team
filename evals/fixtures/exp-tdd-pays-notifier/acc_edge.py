"""Edge-case acceptance tests for notifier.py — injected at grading time only.

Tests behaviours described in spec_clear.md but OMITTED from spec_vague.md.
Under the vague spec implementations may or may not pass these.
"""
import pytest
from notifier import NotificationService


def test_priority_ordering_channels_none():
    """When channels=None, higher-priority channels are called first.

    Insert low-priority first to catch insertion-order naivety.
    """
    order = []
    svc = NotificationService()
    svc.register_channel("sms", lambda r, m: order.append("sms") or True, priority=1)
    svc.register_channel("push", lambda r, m: order.append("push") or True, priority=10)
    svc.send("alice", "hi")
    assert order.index("push") < order.index("sms"), \
        f"push (priority=10) should come before sms (priority=1), got order={order}"


def test_handler_exception_caught_recorded_false():
    """A handler that raises is caught; channel recorded as False; others still run."""
    other_calls = []
    svc = NotificationService()
    svc.register_channel("bad", lambda r, m: (_ for _ in ()).throw(RuntimeError("boom")))
    svc.register_channel("good", lambda r, m: other_calls.append(1) or True)
    result = svc.send("alice", "hi")
    assert result.get("bad") is False
    assert result.get("good") is True
    assert len(other_calls) == 1


def test_duplicate_channel_in_explicit_list_called_once():
    """Duplicate channel names in channels=[...] result in one call, not two."""
    calls = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: calls.append(1) or True)
    result = svc.send("alice", "hi", channels=["email", "email"])
    assert len(calls) == 1
    assert len(result) == 1


def test_empty_channels_list_returns_empty_dict():
    """channels=[] means no channels called; result is {}."""
    calls = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: calls.append(1) or True)
    result = svc.send("alice", "hi", channels=[])
    assert result == {}
    assert calls == []


def test_empty_message_is_valid():
    """Empty string message is forwarded to the handler without raising."""
    received = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: received.append(m) or True)
    svc.send("alice", "")
    assert received == [""]


def test_re_register_same_channel_replaces_handler():
    """Re-registering an existing channel name replaces the old handler."""
    log = []
    svc = NotificationService()
    svc.register_channel("email", lambda r, m: log.append("v1") or True)
    svc.register_channel("email", lambda r, m: log.append("v2") or True)
    svc.send("alice", "hi")
    assert log == ["v2"]
