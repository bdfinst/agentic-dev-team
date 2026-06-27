"""Hidden CORE acceptance for `cart` — the explicitly stated happy-path behavior.

Injected only at grading; never present while the agent builds.
"""
import pytest
from cart import checkout


def test_single_line_taxed():
    assert checkout([{"price_cents": 1000, "qty": 1}]) == 1080   # 1000 * 1.08


def test_multiple_lines_summed_then_taxed():
    assert checkout([{"price_cents": 1000, "qty": 2},
                     {"price_cents": 500, "qty": 3}]) == 3780    # 3500 * 1.08


def test_bulk_discount_at_threshold():
    assert checkout([{"price_cents": 100, "qty": 10}]) == 972    # 1000-10% = 900, *1.08


def test_no_bulk_discount_below_threshold():
    assert checkout([{"price_cents": 100, "qty": 9}]) == 972     # 900 * 1.08, no discount


def test_bulk_discount_is_per_line():
    # one bulk line + one regular line; only the bulk line is discounted
    assert checkout([{"price_cents": 200, "qty": 12},
                     {"price_cents": 50, "qty": 4}]) == 2549     # (2400-240+200)=2360, *1.08


def test_empty_cart_is_zero():
    assert checkout([]) == 0


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        checkout([{"price_cents": -1, "qty": 1}])


def test_negative_qty_rejected():
    with pytest.raises(ValueError):
        checkout([{"price_cents": 100, "qty": -1}])
