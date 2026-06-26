"""Hidden CORE acceptance for `fare` — the explicitly stated happy-path behavior.

Injected only at grading; never present while the agent builds.
"""
import pytest
from fare import fare


@pytest.mark.parametrize("distance,expected", [
    (0, 200), (3, 200), (5, 200),      # band 0..5 km
    (7, 350), (10, 350),               # band 5..10 km
    (12, 500), (50, 500),              # band above 10 km
])
def test_distance_bands_adult_offpeak(distance, expected):
    assert fare(distance) == expected


def test_peak_multiplier_adult():
    assert fare(3, peak=True) == 300          # 200 * 1.5
    assert fare(7, peak=True) == 525          # 350 * 1.5


def test_passenger_discounts_offpeak():
    assert fare(7, "adult") == 350
    assert fare(7, "child") == 175            # 50% off
    assert fare(7, "senior") == 245           # 30% off


def test_discount_applied_after_peak():
    assert fare(7, "child", peak=True) == 263   # 350*1.5=525, *0.5=262.5 -> 263
    assert fare(7, "senior", peak=True) == 368  # 525*0.70=367.5 -> 368


def test_unknown_passenger_rejected():
    with pytest.raises(ValueError):
        fare(5, "toddler")


def test_negative_distance_rejected():
    with pytest.raises(ValueError):
        fare(-1)
