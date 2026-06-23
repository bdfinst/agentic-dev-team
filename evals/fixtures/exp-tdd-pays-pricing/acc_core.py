"""Core acceptance tests for pricing.py — injected at grading time only.

These test behaviors stated explicitly in both spec_clear.md and spec_vague.md.
A correct implementation should pass all of these regardless of design approach.
"""
import pytest
from pricing import PricingEngine, Discount


def test_empty_cart():
    engine = PricingEngine()
    assert engine.calculate([]) == 0.0


def test_no_discounts():
    engine = PricingEngine()
    result = engine.calculate([{"price": 25.0, "qty": 3}])
    assert result == 75.0


def test_single_percent_discount():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    result = engine.calculate([{"price": 100.0}])
    assert result == 90.0


def test_single_fixed_discount():
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 15))
    result = engine.calculate([{"price": 100.0}])
    assert result == 85.0


def test_two_discounts_both_reduce_total():
    """Both discounts must reduce the price vs. either alone."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    engine.add_discount(Discount("fixed", 5))
    result = engine.calculate([{"price": 100.0}])
    assert result < 90.0   # less than 10% alone
    assert result < 95.0   # less than $5 fixed alone
    assert result >= 0.0


def test_negative_floor():
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 50))
    result = engine.calculate([{"price": 20.0}])
    assert result == 0.0


def test_rounding_two_decimal_places():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 33))
    result = engine.calculate([{"price": 10.0}])
    assert result == 6.70


def test_multi_item_qty():
    """Quantities multiply unit prices before discounts."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    items = [{"price": 30.0, "qty": 2}, {"price": 40.0, "qty": 1}]
    # subtotal = 60 + 40 = 100; 10% off = 90
    assert engine.calculate(items) == 90.0
