"""Acceptance tests for Change 2 (global load_all) — injected at grading time only.

Includes regression for Stage-0 core and Change-1 (metadata).
"""
import pytest
from event_store import EventStore, OptimisticConcurrencyError


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_append_versions():
    store = EventStore()
    e1 = store.append("s", "A", {})
    e2 = store.append("s", "B", {})
    assert e1["version"] == 1
    assert e2["version"] == 2


def test_regression_load_empty_stream():
    assert EventStore().load("ghost") == []


def test_regression_project():
    store = EventStore()
    store.append("s", "A", {"n": 5})
    assert store.project("s", lambda acc, e: (acc or 0) + e["data"]["n"]) == 5


# ── regression: change 1 (metadata) ──────────────────────────────────────────

def test_regression_metadata_present():
    store = EventStore()
    event = store.append("s", "A", {}, metadata={"k": "v"})
    assert event.get("metadata") == {"k": "v"}


def test_regression_metadata_none_default():
    store = EventStore()
    event = store.append("s", "A", {})
    assert "metadata" in event and event["metadata"] is None


# ── new: load_all ─────────────────────────────────────────────────────────────

def test_load_all_empty_store():
    assert EventStore().load_all() == []


def test_load_all_returns_all_events():
    store = EventStore()
    store.append("s1", "A", {})
    store.append("s2", "B", {})
    store.append("s1", "C", {})
    all_events = store.load_all()
    assert len(all_events) == 3


def test_load_all_global_insertion_order():
    """Events returned in the order appended, regardless of stream."""
    store = EventStore()
    store.append("s1", "First", {})
    store.append("s2", "Second", {})
    store.append("s1", "Third", {})
    types = [e["event_type"] for e in store.load_all()]
    assert types == ["First", "Second", "Third"]


def test_load_all_returns_snapshot_not_live():
    """Mutating the returned list does not affect subsequent load_all calls."""
    store = EventStore()
    store.append("s", "A", {})
    snapshot = store.load_all()
    snapshot.clear()
    assert len(store.load_all()) == 1


def test_load_stream_still_works_alongside_load_all():
    store = EventStore()
    store.append("s1", "A", {})
    store.append("s2", "B", {})
    assert len(store.load("s1")) == 1
    assert store.load("s1")[0]["event_type"] == "A"
