"""Acceptance tests for Change 2 (category-scoped discounts, TRAP) — injected at grading.

Includes regression for Stage-0 core and Change-1 behaviour.
"""
import pytest
from pricing import PricingEngine, Discount


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_core_percent():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    assert engine.calculate([{"price": 100.0}]) == 90.0


def test_regression_core_fixed_floor():
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 50))
    assert engine.calculate([{"price": 20.0}]) == 0.0


# ── regression: change 1 (min_qty) ───────────────────────────────────────────

def test_regression_min_qty_met():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10, min_qty=2))
    assert engine.calculate([{"price": 100.0, "qty": 2}]) == 180.0


def test_regression_min_qty_not_met():
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10, min_qty=3))
    assert engine.calculate([{"price": 100.0, "qty": 2}]) == 200.0


# ── new: category-scoped discounts ───────────────────────────────────────────

def test_category_discount_applies_only_to_matching_items():
    """A category discount reduces only the subtotal of matching items."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 20, category="Electronics"))
    items = [
        {"price": 100.0, "category": "Electronics"},
        {"price": 50.0, "category": "Books"},
    ]
    # Electronics: 100 * 0.2 = 20 saved; Books: unchanged
    # total = 150 - 20 = 130.0
    assert engine.calculate(items) == 130.0


def test_category_discount_ignores_non_matching_items():
    """Items in a different category are not discounted."""
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 10, category="Books"))
    items = [
        {"price": 100.0, "category": "Electronics"},
        {"price": 50.0, "category": "Books"},
    ]
    # Books: $10 fixed off $50 = $10 saved; Electronics: unchanged
    # total = 150 - 10 = 140.0
    assert engine.calculate(items) == 140.0


def test_items_without_category_not_matched():
    """Items missing the 'category' key do not match any category discount."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 50, category="Electronics"))
    items = [{"price": 100.0}]   # no category key
    assert engine.calculate(items) == 100.0


def test_global_discount_still_works_alongside_category():
    """A global (category=None) discount applies to the running total as normal."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 20, category="Electronics"))
    engine.add_discount(Discount("fixed", 5))   # global
    items = [
        {"price": 100.0, "category": "Electronics"},
        {"price": 50.0, "category": "Books"},
    ]
    # Electronics 20%: saves 20 → running total = 130
    # Global $5: saves 5 → total = 125.0
    assert engine.calculate(items) == 125.0


def test_multiple_category_discounts():
    """Multiple category discounts each apply to their own subtotals."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 20, category="Electronics"))
    engine.add_discount(Discount("percent", 10, category="Books"))
    items = [
        {"price": 100.0, "category": "Electronics"},
        {"price": 50.0, "category": "Books"},
    ]
    # Electronics saves 20, Books saves 5 → total = 150 - 25 = 125.0
    assert engine.calculate(items) == 125.0


def test_category_discount_no_match_leaves_total_unchanged():
    """If no items match the category, the total is unchanged."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 50, category="Clothing"))
    items = [{"price": 100.0, "category": "Electronics"}]
    assert engine.calculate(items) == 100.0
