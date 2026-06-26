"""CHANGE 2 acceptance: per-category extra credit, added AFTER drop-lowest and
capped so a category average can't exceed 100. Injected at grading.
"""
from grades import final_grade


def test_extra_credit_added_to_average():
    # drop 80 -> mean 90, + 5 extra -> 95
    assert final_grade([{"name": "a", "weight": 1.0,
                         "scores": [80, 90], "extra_credit": 5}]) == (95, "A")


def test_extra_credit_capped_at_100():
    # drop 95 -> mean 99, + 10 -> 109, capped at 100
    assert final_grade([{"name": "a", "weight": 1.0,
                         "scores": [95, 99], "extra_credit": 10}]) == (100, "A")


def test_extra_credit_applied_after_drop():
    # drop 40 -> mean 80, + 10 -> 90 (not added before the drop)
    assert final_grade([{"name": "a", "weight": 1.0,
                         "scores": [40, 80], "extra_credit": 10}]) == (90, "A")


def test_missing_extra_credit_is_zero():
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [70, 90]}]) == (90, "A")


def test_per_category_extra_credit_then_weighted():
    # hw: drop 70 -> 90 ; ex: drop one 60 -> 60, + 20 -> 80 ; 0.4*90 + 0.6*80 = 84
    assert final_grade([{"name": "hw", "weight": 0.4, "scores": [70, 90]},
                        {"name": "ex", "weight": 0.6,
                         "scores": [60, 60], "extra_credit": 20}]) == (84, "B")
