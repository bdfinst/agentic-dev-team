"""Acceptance tests for Change 1 (min_qty threshold) — injected at grading time only.

Includes regression for core Stage-0 behaviour.
"""
import pytest
from pricing import PricingEngine, Discount


# ── regression: core behaviour must still work ───────────────────────────────

def test_regression_empty_cart():
    assert PricingEngine().calculate([]) == 0.0


def test_regression_percent_discount():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    assert engine.calculate([{"price": 100.0}]) == 90.0


def test_regression_fixed_discount():
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 15))
    assert engine.calculate([{"price": 100.0}]) == 85.0


def test_regression_negative_floor():
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 50))
    assert engine.calculate([{"price": 20.0}]) == 0.0


# ── new: min_qty threshold ────────────────────────────────────────────────────

def test_min_qty_met_discount_applies():
    """Discount applies when cart total qty meets the threshold."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10, min_qty=3))
    items = [{"price": 30.0, "qty": 1}, {"price": 20.0, "qty": 2}]
    # total qty = 3, threshold = 3 → applies; subtotal = 70, -10% = 63.0
    assert engine.calculate(items) == 63.0


def test_min_qty_not_met_discount_skipped():
    """Discount is skipped when cart total qty is below the threshold."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10, min_qty=5))
    items = [{"price": 100.0, "qty": 1}]
    # total qty = 1 < 5 → discount skipped → 100.0
    assert engine.calculate(items) == 100.0


def test_min_qty_default_always_applies():
    """Default min_qty=1 means discount always applies (backward compatible)."""
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 5))  # min_qty defaults to 1
    assert engine.calculate([{"price": 20.0}]) == 15.0


def test_min_qty_skipped_discount_excluded_from_group():
    """A min_qty-disqualified discount does not participate in group resolution."""
    engine = PricingEngine()
    # Both in same group; first has min_qty=5 (not met), second has min_qty=1
    engine.add_discount(Discount("percent", 50, priority=10, group="g", min_qty=5))
    engine.add_discount(Discount("percent", 10, priority=1, group="g", min_qty=1))
    items = [{"price": 100.0, "qty": 1}]
    # total qty=1 < 5 → first disqualified; second is only eligible in group → 10% off
    assert engine.calculate(items) == 90.0


def test_min_qty_uses_sum_of_all_item_qtys():
    """min_qty counts total items across all cart entries."""
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 20, min_qty=4))
    items = [{"price": 25.0, "qty": 2}, {"price": 10.0, "qty": 2}]
    # qty sum = 4 ≥ 4 → applies; subtotal = 70, -20 = 50.0
    assert engine.calculate(items) == 50.0
