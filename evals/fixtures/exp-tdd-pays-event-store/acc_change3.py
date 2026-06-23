"""Acceptance tests for Change 3 (snapshots, TRAP) — injected at grading time only.

Includes regression for Stage-0 core, Change-1 (metadata), Change-2 (load_all).
"""
import pytest
from event_store import EventStore, OptimisticConcurrencyError


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_append_and_load():
    store = EventStore()
    store.append("s", "A", {"n": 1})
    assert store.load("s")[0]["event_type"] == "A"


def test_regression_project():
    store = EventStore()
    store.append("s", "A", {"n": 3})
    assert store.project("s", lambda acc, e: (acc or 0) + e["data"]["n"]) == 3


# ── regression: change 2 (load_all) ──────────────────────────────────────────

def test_regression_load_all():
    store = EventStore()
    store.append("s1", "A", {})
    store.append("s2", "B", {})
    assert len(store.load_all()) == 2


# ── new: snapshots ────────────────────────────────────────────────────────────

def test_get_snapshot_returns_none_when_no_snapshot():
    store = EventStore()
    store.append("s", "A", {})
    assert store.get_snapshot("s") is None


def test_snapshot_stores_and_retrieves_state():
    store = EventStore()
    store.append("s", "A", {})
    store.snapshot("s", {"count": 1}, at_version=1)
    snap = store.get_snapshot("s")
    assert snap is not None
    assert snap["state"] == {"count": 1}
    assert snap["version"] == 1


def test_project_uses_snapshot_as_starting_point():
    """project() must start from snapshot state, not from version 1."""
    store = EventStore()
    store.append("ledger", "Credit", {"amount": 100})
    store.append("ledger", "Credit", {"amount": 200})
    # Manually set a snapshot at version 2 with pre-computed state
    store.snapshot("ledger", 300, at_version=2)
    # Append one more event after the snapshot
    store.append("ledger", "Credit", {"amount": 50})
    total = store.project("ledger", lambda acc, e: (acc or 0) + e["data"]["amount"])
    # Should start from snapshot (300) and add only event at version 3 (50)
    assert total == 350, (
        f"Expected 350 (snapshot=300 + new event=50), got {total}. "
        "project() may not be using the snapshot."
    )


def test_project_without_snapshot_unchanged():
    """Streams without a snapshot still project from the beginning."""
    store = EventStore()
    store.append("s", "A", {"n": 10})
    store.append("s", "B", {"n": 20})
    assert store.project("s", lambda acc, e: (acc or 0) + e["data"]["n"]) == 30


def test_snapshot_at_version_exceeding_stream_raises():
    """snapshot() with at_version > stream length raises ValueError."""
    store = EventStore()
    store.append("s", "A", {})
    with pytest.raises(ValueError):
        store.snapshot("s", "state", at_version=5)


def test_snapshot_replaced_by_re_snapshot():
    """Re-snapshotting replaces the previous snapshot."""
    store = EventStore()
    store.append("s", "A", {"n": 1})
    store.append("s", "B", {"n": 2})
    store.snapshot("s", 1, at_version=1)
    store.snapshot("s", 3, at_version=2)
    snap = store.get_snapshot("s")
    assert snap["state"] == 3
    assert snap["version"] == 2
