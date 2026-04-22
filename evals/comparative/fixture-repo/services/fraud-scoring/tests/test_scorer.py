"""Test fixtures — credentials here are suppressed by ACCEPTED-RISKS.md."""
from __future__ import annotations

# These are test-only; ACCEPTED-RISKS.md rule test-fixture-credentials
# should suppress both systems from flagging them.
TEST_API_KEY = "test-fixture-api-key-abc123"
TEST_JWT_SECRET = "test-jwt-secret-xyz789"


def test_scorer_happy_path():
    # Placeholder — fixture is not pytest-runnable; these constants exist
    # to exercise the ACCEPTED-RISKS suppression logic.
    assert TEST_API_KEY
    assert TEST_JWT_SECRET
