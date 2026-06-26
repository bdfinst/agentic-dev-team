"""CHANGE 2 acceptance: post-tax garnishment inside net_pay(). Injected at grading.

The garnishment is withheld AFTER tax and must NOT reduce taxable income — tax
is unchanged from the no-garnishment case.
"""
import pytest
from payroll import net_pay


def test_garnishment_subtracted_after_tax():
    # tax 30000, then - 5000
    assert net_pay(200000, garnishment_cents=5000) == 165000


def test_garnishment_does_not_reduce_taxable_income():
    # If garnishment were (wrongly) pre-tax, taxable would drop and tax would be
    # lower. Tax stays 30000; only the flat 5000 comes off the end.
    assert net_pay(200000, garnishment_cents=5000) == net_pay(200000) - 5000


def test_garnishment_with_pretax_retirement():
    # pre-tax 20000, taxable 180000, tax 26000, net 154000, then - 5000
    assert net_pay(200000, retirement_pct=10, garnishment_cents=5000) == 149000


def test_garnishment_default_is_zero():
    assert net_pay(200000, garnishment_cents=0) == 170000


def test_negative_garnishment_rejected():
    with pytest.raises(ValueError):
        net_pay(200000, garnishment_cents=-1)
