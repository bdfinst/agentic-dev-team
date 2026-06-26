"""CHANGE 1 acceptance: drop each category's single lowest score before averaging.

Only categories with more than one score drop a score. Injected at grading.
"""
from grades import final_grade


def test_drops_single_lowest_score():
    # drop the 60, mean of [90, 90] is 90
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [60, 90, 90]}]) == (90, "A")


def test_two_scores_drops_lower():
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [70, 90]}]) == (90, "A")


def test_single_score_is_not_dropped():
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [60]}]) == (60, "D")


def test_ties_drop_exactly_one():
    # [80, 80, 100] -> drop one 80 -> mean of [80, 100] = 90
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [80, 80, 100]}]) == (90, "A")


def test_drop_lowest_per_category_then_weighted():
    # hw: drop 50 -> mean 95 ; ex: drop one 80 -> 80 ; 0.5*95 + 0.5*80 = 87.5 -> 88
    assert final_grade([{"name": "hw", "weight": 0.5, "scores": [50, 100, 90]},
                        {"name": "ex", "weight": 0.5, "scores": [80, 80]}]) == (88, "B")
