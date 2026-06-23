"""Edge-case acceptance tests for pricing.py — injected at grading time only.

These test behaviors described in spec_clear.md but OMITTED from spec_vague.md.
Under the vague spec, implementations may or may not pass these; under the clear
spec, a correct implementation should pass all of them.
"""
import pytest
from pricing import PricingEngine, Discount


def test_priority_ordering():
    """Higher-priority discount applies before lower-priority one.

    Added in reverse insertion order to catch naive insertion-order implementations.
    $10 fixed (priority=1, inserted first) and 50% (priority=10, inserted second):
      correct (priority-order): 100 * 0.5 = 50, then -10 = 40.0
      naive (insertion-order): 100 - 10 = 90, then * 0.5 = 45.0
    """
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 10, priority=1))   # inserted first, lower priority
    engine.add_discount(Discount("percent", 50, priority=10))  # inserted second, higher priority
    result = engine.calculate([{"price": 100.0}])
    assert result == 40.0, f"Expected 40.0 (priority order), got {result}"


def test_exclusive_group_only_highest_priority_applies():
    """Within an exclusive group only the highest-priority discount applies.

    Two discounts in group='promo': 10% (priority=2) beats 20% (priority=1).
    Naive implementations applying all discounts would return 72.0.
    """
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10, priority=2, group="promo"))
    engine.add_discount(Discount("percent", 20, priority=1, group="promo"))
    result = engine.calculate([{"price": 100.0}])
    # priority=2 wins → only 10% applied → 90.0
    # naive (both applied): 100 * 0.9 * 0.8 = 72.0
    assert result == 90.0, f"Expected 90.0 (only highest-priority in group), got {result}"


def test_group_winner_and_standalone_both_apply():
    """A group winner and a standalone discount are both applied."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 20, group="promo"))  # only one in group, so it wins
    engine.add_discount(Discount("fixed", 5))                    # standalone, always applies
    result = engine.calculate([{"price": 100.0}])
    # 100 * 0.8 = 80, then -5 = 75.0
    assert result == 75.0


def test_group_tied_priority_first_inserted_wins():
    """When two group members tie on priority, the first-inserted discount wins."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 30, priority=0, group="g"))  # first inserted
    engine.add_discount(Discount("percent", 10, priority=0, group="g"))  # second inserted
    result = engine.calculate([{"price": 100.0}])
    # First-inserted (30%) wins the tie → 70.0
    assert result == 70.0, f"Expected 70.0 (first-inserted wins tie), got {result}"


def test_zero_value_discount_is_noop():
    """Discount with value=0 does not raise and does not change the total."""
    engine = PricingEngine()
    engine.add_discount(Discount("fixed", 0))
    assert engine.calculate([{"price": 50.0}]) == 50.0


def test_item_without_qty_defaults_to_one():
    """Items without 'qty' key default to quantity 1."""
    engine = PricingEngine()
    engine.add_discount(Discount("percent", 10))
    # No 'qty' key; should be treated as qty=1
    result = engine.calculate([{"price": 100.0}])
    assert result == 90.0
