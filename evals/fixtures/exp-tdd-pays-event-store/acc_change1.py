"""Acceptance tests for Change 1 (event metadata) — injected at grading time only.

Includes regression for Stage-0 core behaviour.
"""
import pytest
from event_store import EventStore, OptimisticConcurrencyError


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_append_returns_event():
    store = EventStore()
    e = store.append("s", "A", {"x": 1})
    assert e["version"] == 1
    assert e["stream_id"] == "s"


def test_regression_load_empty():
    assert EventStore().load("ghost") == []


def test_regression_optimistic_concurrency():
    store = EventStore()
    store.append("s", "A", {})
    with pytest.raises(OptimisticConcurrencyError):
        store.append("s", "B", {}, expected_version=0)


def test_regression_project():
    store = EventStore()
    store.append("s", "A", {"n": 3})
    store.append("s", "B", {"n": 4})
    assert store.project("s", lambda acc, e: (acc or 0) + e["data"]["n"]) == 7


# ── new: metadata ─────────────────────────────────────────────────────────────

def test_metadata_stored_and_returned():
    store = EventStore()
    meta = {"correlation_id": "abc-123"}
    event = store.append("s", "A", {}, metadata=meta)
    assert event.get("metadata") == meta


def test_metadata_none_by_default():
    store = EventStore()
    event = store.append("s", "A", {})
    # metadata field must be present even when not supplied
    assert "metadata" in event
    assert event["metadata"] is None


def test_metadata_present_in_loaded_events():
    store = EventStore()
    store.append("s", "A", {}, metadata={"tag": "test"})
    events = store.load("s")
    assert events[0].get("metadata") == {"tag": "test"}


def test_metadata_present_in_project_events():
    store = EventStore()
    store.append("s", "A", {}, metadata={"ref": "x"})
    refs = store.project("s", lambda acc, e: (acc or []) + [e.get("metadata", {}).get("ref")])
    assert refs == ["x"]


def test_metadata_none_when_not_supplied_in_loaded_events():
    store = EventStore()
    store.append("s", "A", {})
    events = store.load("s")
    assert "metadata" in events[0]
    assert events[0]["metadata"] is None
