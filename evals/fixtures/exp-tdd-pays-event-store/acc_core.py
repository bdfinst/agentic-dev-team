"""Core acceptance tests for event_store.py — injected at grading time only.

Tests behaviours stated in both spec_clear.md and spec_vague.md.
"""
import pytest
from event_store import EventStore, OptimisticConcurrencyError


def test_append_returns_event_dict():
    store = EventStore()
    event = store.append("orders", "OrderPlaced", {"item": "book"})
    assert isinstance(event, dict)
    assert event["stream_id"] == "orders"
    assert event["event_type"] == "OrderPlaced"
    assert event["data"]["item"] == "book"


def test_first_event_has_version_one():
    store = EventStore()
    event = store.append("orders", "OrderPlaced", {})
    assert event["version"] == 1


def test_second_event_has_version_two():
    store = EventStore()
    store.append("orders", "OrderPlaced", {})
    event2 = store.append("orders", "OrderShipped", {})
    assert event2["version"] == 2


def test_load_nonexistent_stream_returns_empty_list():
    store = EventStore()
    assert store.load("ghost") == []


def test_load_returns_events_in_append_order():
    store = EventStore()
    store.append("s", "A", {})
    store.append("s", "B", {})
    events = store.load("s")
    assert [e["event_type"] for e in events] == ["A", "B"]


def test_optimistic_concurrency_success():
    store = EventStore()
    store.append("orders", "OrderPlaced", {}, expected_version=0)  # empty → ok


def test_optimistic_concurrency_conflict_raises():
    store = EventStore()
    store.append("orders", "OrderPlaced", {})
    with pytest.raises(OptimisticConcurrencyError):
        store.append("orders", "OrderShipped", {}, expected_version=0)


def test_project_reduces_events():
    store = EventStore()
    store.append("cart", "ItemAdded", {"price": 10})
    store.append("cart", "ItemAdded", {"price": 25})
    total = store.project("cart", lambda acc, e: (acc or 0) + e["data"]["price"])
    assert total == 35


def test_project_nonexistent_stream_returns_initial_state():
    store = EventStore()
    assert store.project("ghost", lambda a, e: a, initial_state={}) == {}


def test_two_streams_independent():
    store = EventStore()
    store.append("a", "E1", {})
    store.append("b", "E2", {})
    assert len(store.load("a")) == 1
    assert len(store.load("b")) == 1
    assert store.load("a")[0]["event_type"] == "E1"
