"""Hidden CORE acceptance for `grades` — the explicitly stated happy-path behavior.

Injected only at grading; never present while the agent builds. Categories use a
single score each so the later change-chain (drop-lowest, extra credit, curve)
leaves CORE answers unchanged.
"""
import pytest
from grades import final_grade


def test_weighted_average_two_categories():
    assert final_grade([{"name": "hw", "weight": 0.4, "scores": [80]},
                        {"name": "ex", "weight": 0.6, "scores": [90]}]) == (86, "B")


def test_all_high_scores_is_an_a():
    assert final_grade([{"name": "a", "weight": 0.5, "scores": [95]},
                        {"name": "b", "weight": 0.5, "scores": [91]}]) == (93, "A")


def test_round_half_up_before_letter():
    # 0.5*82 + 0.5*83 = 82.5 -> round-half-up -> 83
    assert final_grade([{"name": "a", "weight": 0.5, "scores": [82]},
                        {"name": "b", "weight": 0.5, "scores": [83]}]) == (83, "B")


@pytest.mark.parametrize("score,expected", [
    (75, (75, "C")),
    (65, (65, "D")),
    (40, (40, "F")),
])
def test_lower_letter_grades(score, expected):
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [score]}]) == expected


def test_letter_boundaries_belong_to_higher_band():
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [90]}]) == (90, "A")
    assert final_grade([{"name": "a", "weight": 1.0, "scores": [80]}]) == (80, "B")


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        final_grade([{"name": "a", "weight": 0.5, "scores": [80]}])


def test_empty_scores_rejected():
    with pytest.raises(ValueError):
        final_grade([{"name": "a", "weight": 1.0, "scores": []}])


def test_score_out_of_range_rejected():
    with pytest.raises(ValueError):
        final_grade([{"name": "a", "weight": 1.0, "scores": [101]}])
    with pytest.raises(ValueError):
        final_grade([{"name": "a", "weight": 1.0, "scores": [-1]}])
