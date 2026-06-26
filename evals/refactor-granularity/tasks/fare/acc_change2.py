"""CHANGE 2 acceptance: transfer discount inside day_total(). Injected at grading.

A ride starting within 90 minutes after the previous ride's start is charged at
half, computed BEFORE the running daily cap is applied.
"""
from fare import day_total


def test_transfer_within_window_is_half():
    # second ride 60 min later -> half of 350 = 175
    assert day_total([{"distance_km": 7, "start_min": 0},
                      {"distance_km": 7, "start_min": 60}]) == 525


def test_window_boundary_inclusive_at_90():
    assert day_total([{"distance_km": 7, "start_min": 0},
                      {"distance_km": 7, "start_min": 90}]) == 525


def test_just_outside_window_is_full():
    assert day_total([{"distance_km": 7, "start_min": 0},
                      {"distance_km": 7, "start_min": 91}]) == 700


def test_transfer_then_cap():
    # 500, then +250 (half), +250, +250 -> 1000 then capped (4th clipped to 0)
    rides = [{"distance_km": 12, "start_min": m} for m in (0, 30, 40, 50)]
    assert day_total(rides) == 1000


def test_chain_of_transfers_measured_from_previous_start():
    # each ride within 90 of the prior start -> all but first are half
    rides = [{"distance_km": 3, "start_min": m} for m in (0, 80, 160)]
    assert day_total(rides) == 200 + 100 + 100   # 400
