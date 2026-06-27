"""CHANGE 3 acceptance: tax-exempt categories. Injected at grading.

Groceries and books are not taxed; only the taxed subtotal is multiplied by 1.08,
so a single whole-order tax rate is wrong once an exempt line is present.
"""
from cart import checkout


def test_grocery_line_is_untaxed():
    assert checkout([{"price_cents": 1000, "qty": 1,
                      "category": "groceries"}]) == 1000


def test_books_line_is_untaxed():
    assert checkout([{"price_cents": 1000, "qty": 1,
                      "category": "books"}]) == 1000


def test_mixed_taxed_and_exempt_order():
    # groceries 1000 untaxed + plain 1000 taxed -> 1000 + 1080
    assert checkout([{"price_cents": 1000, "qty": 1, "category": "groceries"},
                     {"price_cents": 1000, "qty": 1}]) == 2080


def test_exempt_line_still_gets_discounts():
    # groceries: bulk 900, coupon -10% = 810, exempt -> no tax
    assert checkout([{"price_cents": 100, "qty": 10,
                      "category": "groceries"}], coupon_pct=10) == 810


def test_three_way_mix_of_caps_and_exemption():
    # electronics 5000: bulk 500 (under cap), taxed net 4500
    # groceries 2000: exempt net 2000
    # plain 1000: taxed net 1000
    # taxed subtotal 5500 * 1.08 = 5940, + 2000 exempt = 7940
    assert checkout([{"price_cents": 500, "qty": 10, "category": "electronics"},
                     {"price_cents": 1000, "qty": 2, "category": "groceries"},
                     {"price_cents": 1000, "qty": 1}]) == 7940
