"""CHANGE 3 acceptance: zone surcharge applied BEFORE the peak multiplier.

fare(..., zones=N) adds (N-1)*100 cents to the base, and because it is added
before the peak multiplier, peak rides multiply the surcharge too. Injected at
grading.
"""
import pytest
from fare import fare


def test_zone_surcharge_offpeak():
    assert fare(7, zones=2) == 450        # 350 + 100
    assert fare(7, zones=3) == 550        # 350 + 200


def test_surcharge_is_multiplied_by_peak():
    assert fare(7, peak=True, zones=2) == 675   # (350+100)*1.5
    assert fare(7, "child", peak=True, zones=2) == 338  # 675*0.5=337.5 -> 338


def test_zones_one_is_unchanged():
    assert fare(7, zones=1) == 350


def test_zones_below_one_rejected():
    with pytest.raises(ValueError):
        fare(7, zones=0)
