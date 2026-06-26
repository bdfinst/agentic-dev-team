"""CHANGE 2 acceptance: per-category discount caps. Injected at grading.

The combined bulk+coupon discount on a single line is clamped to its category's
cap, measured per line against that line's own gross.
"""
from cart import checkout


def test_bulk_discount_clamped_to_category_cap():
    # electronics: gross 30000, bulk 3000 -> capped at 2000, net 28000, *1.08
    assert checkout([{"price_cents": 1000, "qty": 30,
                      "category": "electronics"}]) == 30240


def test_apparel_has_a_lower_cap():
    # apparel: gross 6000, bulk 600 -> capped at 500, net 5500, *1.08
    assert checkout([{"price_cents": 300, "qty": 20,
                      "category": "apparel"}]) == 5940


def test_coupon_plus_bulk_still_clamped_to_cap():
    # bulk 600 + coupon 50% of 5400 = 2700, total 3300 -> capped at 500
    assert checkout([{"price_cents": 300, "qty": 20,
                      "category": "apparel"}], coupon_pct=50) == 5940


def test_under_cap_discount_is_untouched():
    # electronics: gross 5000, bulk 500 < cap 2000, net 4500, *1.08
    assert checkout([{"price_cents": 500, "qty": 10,
                      "category": "electronics"}]) == 4860


def test_caps_apply_per_category_independently():
    # electronics capped to 2000 (net 28000) + apparel capped to 500 (net 5500)
    # taxed subtotal 33500 * 1.08 = 36180
    assert checkout([{"price_cents": 1000, "qty": 30, "category": "electronics"},
                     {"price_cents": 300, "qty": 20, "category": "apparel"}]) == 36180
