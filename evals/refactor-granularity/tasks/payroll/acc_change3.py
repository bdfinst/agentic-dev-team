"""CHANGE 3 acceptance: married filing status with its own brackets.

net_pay(..., filing_status="married") uses wider brackets (10% to 200000, 20%
to 500000, 30% above). The "single" brackets are unchanged, and the post-tax
garnishment from Change 2 still applies last. Injected at grading.
"""
import pytest
from payroll import net_pay


def test_married_first_bracket_is_wider():
    # taxable 200000 all at 10% = 20000 tax (single would be 30000)
    assert net_pay(200000, "married") == 180000


def test_married_second_bracket():
    # 10% * 200000 + 20% * 200000 = 60000 tax
    assert net_pay(400000, "married") == 340000


def test_married_top_bracket():
    # 20000 + 60000 + 30% * 100000 = 110000 tax
    assert net_pay(600000, "married") == 490000


def test_single_brackets_unchanged():
    assert net_pay(400000, "single") == 320000


def test_married_with_retirement_and_garnishment():
    # pre-tax 40000, taxable 360000 married: 20000 + 20% * 160000 = 52000 tax,
    # net 400000 - 40000 - 52000 = 308000, then - 8000 garnishment
    assert net_pay(400000, "married", retirement_pct=10, garnishment_cents=8000) == 300000


def test_unknown_status_still_rejected():
    with pytest.raises(ValueError):
        net_pay(200000, "single_parent")
