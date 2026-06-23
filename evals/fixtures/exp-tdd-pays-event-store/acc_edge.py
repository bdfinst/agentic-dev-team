"""Edge-case acceptance tests for event_store.py — injected at grading time only.

Tests behaviours described in spec_clear.md but OMITTED from spec_vague.md.
"""
import pytest
from event_store import EventStore, OptimisticConcurrencyError


def test_load_from_version_filters_events():
    """load(from_version=N) returns only events with version > N."""
    store = EventStore()
    store.append("s", "A", {})
    store.append("s", "B", {})
    store.append("s", "C", {})
    events = store.load("s", from_version=1)
    assert len(events) == 2
    assert events[0]["version"] == 2
    assert events[1]["version"] == 3


def test_load_from_version_zero_returns_all():
    store = EventStore()
    store.append("s", "A", {})
    store.append("s", "B", {})
    assert len(store.load("s", from_version=0)) == 2


def test_expected_version_equals_current_succeeds():
    """Appending with expected_version == current stream length succeeds."""
    store = EventStore()
    store.append("s", "A", {})
    store.append("s", "B", {})
    # current version = 2; expected_version=2 → ok
    event = store.append("s", "C", {}, expected_version=2)
    assert event["version"] == 3


def test_expected_version_greater_than_current_raises():
    """expected_version > current → OptimisticConcurrencyError."""
    store = EventStore()
    store.append("s", "A", {})
    with pytest.raises(OptimisticConcurrencyError):
        store.append("s", "B", {}, expected_version=5)


def test_project_initial_state_none_by_default():
    """project starts from None when initial_state is not given."""
    store = EventStore()
    store.append("s", "A", {"val": 1})
    result = store.project("s", lambda acc, e: (acc or 0) + e["data"]["val"])
    assert result == 1


def test_project_with_explicit_initial_state():
    store = EventStore()
    store.append("s", "A", {"val": 10})
    result = store.project("s", lambda acc, e: acc + e["data"]["val"], initial_state=5)
    assert result == 15


def test_load_returns_copy_not_live_reference():
    """Mutating the returned list does not affect the stored stream."""
    store = EventStore()
    store.append("s", "A", {})
    events = store.load("s")
    events.clear()
    assert len(store.load("s")) == 1


def test_stream_versions_restart_independently():
    """Each stream's version numbering is independent."""
    store = EventStore()
    store.append("s1", "A", {})
    store.append("s1", "B", {})
    store.append("s2", "X", {})
    assert store.load("s2")[0]["version"] == 1
