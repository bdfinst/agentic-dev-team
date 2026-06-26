"""CHANGE 1 acceptance: a daily fare cap via day_total(). Injected at grading."""
import pytest
from fare import day_total


def test_simple_sum_under_cap():
    assert day_total([{"distance_km": 3}, {"distance_km": 7}]) == 550   # 200 + 350


def test_cap_clips_the_crossing_ride():
    # 350 + 350 + 350 = 1050, capped at 1000 (third ride clipped to 300)
    assert day_total([{"distance_km": 7}] * 3) == 1000


def test_rides_after_cap_are_free():
    assert day_total([{"distance_km": 12}] * 5) == 1000   # 500+500=1000, rest free


def test_custom_cap():
    assert day_total([{"distance_km": 7}, {"distance_km": 7}], daily_cap_cents=400) == 400


def test_passenger_and_peak_flow_through():
    assert day_total([{"distance_km": 7, "passenger": "child"},
                      {"distance_km": 3, "peak": True}]) == 475   # 175 + 300
