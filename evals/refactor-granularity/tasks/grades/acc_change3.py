"""CHANGE 3 acceptance: a final curve added AFTER weighting but BEFORE the letter
lookup, capped at 100. The curve can push a grade across a letter boundary, so
the letter must be computed after the curve, not inline with the weighting.
Injected at grading.
"""
from grades import final_grade


def test_curve_added_after_weighting():
    # 0.5*70 + 0.5*86 = 78, + 5 curve -> 83 (would be a "C" without the curve)
    assert final_grade([{"name": "a", "weight": 0.5, "scores": [70]},
                        {"name": "b", "weight": 0.5, "scores": [86]}], curve=5) == (83, "B")


def test_curve_crosses_letter_boundary():
    # 88 + 2 = 90 -> "A"; the letter must be looked up after the curve
    assert final_grade([{"name": "a", "weight": 1.0,
                         "scores": [88]}], curve=2) == (90, "A")


def test_curve_capped_at_100():
    # 98 + 5 = 103, capped at 100
    assert final_grade([{"name": "a", "weight": 1.0,
                         "scores": [98]}], curve=5) == (100, "A")


def test_curve_defaults_to_zero():
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [75]}], curve=0) == (75, "C")
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [75]}]) == (75, "C")
