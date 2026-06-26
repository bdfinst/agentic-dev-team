"""Hidden EDGE acceptance for `fare` — boundary and rounding cases.

Stated in the clear spec, but the cases a thin suite tends to miss. Injected
only at grading.
"""
import pytest
from fare import fare


def test_band_boundaries_are_inclusive_lower():
    # exactly on a boundary belongs to the lower band
    assert fare(5.0) == 200
    assert fare(10.0) == 350


def test_just_above_boundary_crosses_band():
    assert fare(5.0001) == 350
    assert fare(10.0001) == 500


def test_half_up_rounding_on_discounted_peak():
    # 262.5 and 367.5 must round half-UP, not banker's rounding
    assert fare(7, "child", peak=True) == 263
    assert fare(7, "senior", peak=True) == 368


def test_zero_distance_is_lowest_band():
    assert fare(0) == 200
    assert fare(0, "child") == 100


def test_child_and_senior_peak_on_top_band():
    assert fare(20, "child", peak=True) == 375   # 500*1.5=750, *0.5=375
    assert fare(20, "senior", peak=True) == 525  # 750*0.70=525


def test_unknown_passenger_message_is_value_error():
    with pytest.raises(ValueError):
        fare(5, passenger="staff")
