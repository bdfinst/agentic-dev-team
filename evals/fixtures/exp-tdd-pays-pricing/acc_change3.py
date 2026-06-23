"""Acceptance tests for Change 3 (max_discount_pct cap) — injected at grading.

Includes regression for Stage-0 core, Change-1 (min_qty), and Change-2 (category).
"""
import pytest
from pricing import PricingEngine, Discount


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_core_no_cap():
    """Engine without a cap behaves as before."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    assert engine.calculate([{"price": 100.0}]) == 90.0


def test_regression_core_floor():
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 50))
    assert engine.calculate([{"price": 20.0}]) == 0.0


# ── regression: change 2 (category) ──────────────────────────────────────────

def test_regression_category_discount():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 20, category="Electronics"))
    items = [
        {"price": 100.0, "category": "Electronics"},
        {"price": 50.0, "category": "Books"},
    ]
    assert engine.calculate(items) == 130.0


# ── new: global discount cap ──────────────────────────────────────────────────

def test_cap_triggers_when_discount_exceeds_threshold():
    """When combined discounts exceed the cap, total is set to subtotal*(1-cap/100)."""
    engine = PricingEngine(max_discount_pct=50)
    engine.add_discount(Discount("percent", 80))  # would give $20 on $100 cart
    result = engine.calculate([{"price": 100.0}])
    # 80% would bring to $20; cap is 50% → floor at $50.00
    assert result == 50.0


def test_cap_does_not_trigger_when_discount_within_threshold():
    """When combined discounts are within the cap, result is unchanged."""
    engine = PricingEngine(max_discount_pct=50)
    engine.add_discount(Discount("percent", 30))
    result = engine.calculate([{"price": 100.0}])
    # 30% → $70; cap is 50% → not triggered → $70.00
    assert result == 70.0


def test_no_cap_by_default():
    """Engine constructed without max_discount_pct has no cap."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 90))
    assert engine.calculate([{"price": 100.0}]) == 10.0


def test_cap_zero_means_no_discount_applies():
    """max_discount_pct=0 means the total equals the original subtotal."""
    engine = PricingEngine(max_discount_pct=0)
    engine.add_discount(Discount("percent", 50))
    assert engine.calculate([{"price": 100.0}]) == 100.0


def test_cap_combined_with_category_discount():
    """Cap applies after all discounts (including category-scoped) are resolved."""
    engine = PricingEngine(max_discount_pct=10)
    engine.add_discount(Discount("percent", 20, category="Electronics"))
    items = [{"price": 100.0, "category": "Electronics"}]
    # Category saves 20 → total $80; cap at 10% means floor at $90.00
    assert engine.calculate(items) == 90.0
