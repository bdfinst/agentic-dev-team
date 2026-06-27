"""Hidden EDGE acceptance for `cart` — boundary and rounding cases.

Stated in the clear spec, but the cases a thin suite tends to miss. Injected
only at grading.
"""
import pytest
from cart import checkout


def test_half_up_rounding_on_tax():
    # 999 * 1.08 = 1078.92 -> 1079
    assert checkout([{"price_cents": 333, "qty": 3}]) == 1079


def test_exact_half_rounds_up_not_bankers():
    # gross 375 (qty>=10 -> *0.9 = 337.5) * 1.08 = 364.5 -> 365 (banker's would be 364)
    assert checkout([{"price_cents": 25, "qty": 15}]) == 365


def test_bulk_threshold_is_inclusive_at_ten():
    assert checkout([{"price_cents": 100, "qty": 10}]) == 972     # discounted: 900 * 1.08
    assert checkout([{"price_cents": 100, "qty": 11}]) == 1069    # 1100-110=990, *1.08=1069.2->1069


def test_qty_zero_line_is_free():
    assert checkout([{"price_cents": 999, "qty": 0}]) == 0
    assert checkout([{"price_cents": 999, "qty": 0},
                     {"price_cents": 1000, "qty": 1}]) == 1080


def test_unknown_fields_ignored():
    assert checkout([{"price_cents": 1000, "qty": 1,
                      "sku": "ABC", "name": "widget"}]) == 1080


def test_negative_price_in_later_line_rejected():
    with pytest.raises(ValueError):
        checkout([{"price_cents": 100, "qty": 1},
                  {"price_cents": -5, "qty": 2}])
