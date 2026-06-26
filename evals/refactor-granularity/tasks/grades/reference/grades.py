"""Reference solution for the `grades` task — FINAL state (after change1-3).

Used only to validate the hidden acceptance suites. Never given to an agent.
"""
from decimal import Decimal, ROUND_HALF_UP

_SCALE = ((90, "A"), (80, "B"), (70, "C"), (60, "D"))  # (min_percent, letter)
_LOWEST = "F"


def _round_half_up(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _letter(percent: int) -> str:
    for threshold, grade in _SCALE:
        if percent >= threshold:
            return grade
    return _LOWEST


def _category_average(category) -> Decimal:
    """Mean of a category's scores after the change-chain adjustments.

    Order (change1 + change2 make this load-bearing): validate -> drop the
    single lowest score (change1) -> mean -> add per-category extra credit
    (change2) -> cap the resulting average at 100.
    """
    scores = category["scores"]
    if not scores:
        raise ValueError(f"category {category.get('name')!r} has no scores")
    for score in scores:
        if score < 0 or score > 100:
            raise ValueError(f"score out of range 0..100: {score!r}")

    kept = list(scores)
    if len(kept) > 1:
        kept.remove(min(kept))  # change1: drop the single lowest score

    average = Decimal(sum(kept)) / Decimal(len(kept))
    average += Decimal(str(category.get("extra_credit", 0)))  # change2
    if average > 100:
        average = Decimal(100)
    return average


def final_grade(categories, curve=0):
    """Weighted final grade as ``(percent: int, letter: str)``.

    Order of operations (change3 makes this load-bearing): per-category average
    -> x weight -> sum -> + final curve (change3) -> cap at 100 -> round-half-up
    -> letter lookup. The curve is applied AFTER weighting but BEFORE the letter
    lookup, so it can push a grade across a letter boundary.
    """
    total_weight = sum((Decimal(str(c["weight"])) for c in categories), Decimal(0))
    if total_weight != Decimal("1.0"):
        raise ValueError("weights must sum to 1.0")

    weighted = Decimal(0)
    for category in categories:
        weighted += Decimal(str(category["weight"])) * _category_average(category)

    weighted += Decimal(str(curve))  # change3: final curve before the letter lookup
    if weighted > 100:
        weighted = Decimal(100)

    percent = _round_half_up(weighted)
    return percent, _letter(percent)
