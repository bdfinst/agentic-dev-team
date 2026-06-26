"""Hidden EDGE acceptance for `grades` — boundary and rounding cases.

Stated in the clear spec, but the cases a thin suite tends to miss. Categories
use a single score each so the change-chain leaves these CORE answers unchanged.
Injected only at grading.
"""
import pytest
from grades import final_grade


def test_half_up_rounding_crosses_into_a():
    # 0.5*89 + 0.5*90 = 89.5 -> round-half-up -> 90 -> "A"
    assert final_grade([{"name": "a", "weight": 0.5, "scores": [89]},
                        {"name": "b", "weight": 0.5, "scores": [90]}]) == (90, "A")


def test_half_up_rounding_crosses_into_b():
    # 0.5*79 + 0.5*80 = 79.5 -> 80 -> "B"
    assert final_grade([{"name": "a", "weight": 0.5, "scores": [79]},
                        {"name": "b", "weight": 0.5, "scores": [80]}]) == (80, "B")


def test_three_categories_sum_to_one():
    # 0.2*100 + 0.3*60 + 0.5*88 = 20 + 18 + 44 = 82
    assert final_grade([{"name": "a", "weight": 0.2, "scores": [100]},
                        {"name": "b", "weight": 0.3, "scores": [60]},
                        {"name": "c", "weight": 0.5, "scores": [88]}]) == (82, "B")


def test_perfect_and_zero_extremes():
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [100]}]) == (100, "A")
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [0]}]) == (0, "F")


def test_just_below_boundary_stays_lower():
    # 79 rounds to 79 -> "C", not "B"
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [79]}]) == (79, "C")


def test_weights_slightly_off_rejected():
    with pytest.raises(ValueError):
        final_grade([{"name": "a", "weight": 0.5, "scores": [80]},
                     {"name": "b", "weight": 0.6, "scores": [80]}])
