"""Tests for autoship_state.py (#989)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "lib"))

import autoship_state  # noqa: E402


def test_format_round_timestamp_returns_iso8601_z_suffixed() -> None:
    dt = datetime(2026, 7, 8, 12, 0, 0)
    assert autoship_state.format_round_timestamp(dt) == "2026-07-08T12:00:00Z"


def test_is_stale_true_when_elapsed_exceeds_threshold() -> None:
    labeled_at = datetime(2026, 7, 1, 0, 0, 0)
    now = datetime(2026, 7, 3, 0, 0, 0)
    assert autoship_state.is_stale(labeled_at, 24, now) is True


def test_is_stale_false_when_recently_labeled() -> None:
    labeled_at = datetime(2026, 7, 3, 5, 0, 0)
    now = datetime(2026, 7, 3, 6, 0, 0)
    assert autoship_state.is_stale(labeled_at, 24, now) is False


def test_is_stale_inclusive_at_exact_threshold() -> None:
    labeled_at = datetime(2026, 7, 1, 0, 0, 0)
    now = datetime(2026, 7, 2, 0, 0, 0)
    assert autoship_state.is_stale(labeled_at, 24, now) is True
