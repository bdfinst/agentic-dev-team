"""CHANGE 1 acceptance: an order-level coupon via coupon_pct. Injected at grading.

The coupon is applied after the per-line bulk discount and before sales tax.
"""
import pytest
from cart import checkout


def test_coupon_before_tax():
    assert checkout([{"price_cents": 1000, "qty": 1}], coupon_pct=10) == 972   # 900 * 1.08


def test_coupon_stacks_after_bulk_discount():
    # bulk 900, then -10% = 810, * 1.08 = 874.8 -> 875
    assert checkout([{"price_cents": 100, "qty": 10}], coupon_pct=10) == 875


def test_coupon_applies_to_whole_order():
    assert checkout([{"price_cents": 1000, "qty": 1},
                     {"price_cents": 500, "qty": 2}], coupon_pct=25) == 1620   # 1500 * 1.08


def test_default_coupon_is_unchanged():
    assert checkout([{"price_cents": 1000, "qty": 1}]) == 1080
    assert checkout([{"price_cents": 1000, "qty": 1}], coupon_pct=0) == 1080


def test_coupon_out_of_range_rejected():
    with pytest.raises(ValueError):
        checkout([{"price_cents": 100, "qty": 1}], coupon_pct=-1)
    with pytest.raises(ValueError):
        checkout([{"price_cents": 100, "qty": 1}], coupon_pct=150)
