"""Hidden CORE acceptance for `payroll` — the explicitly stated happy-path behavior.

Injected only at grading; never present while the agent builds.
"""
import pytest
from payroll import net_pay


@pytest.mark.parametrize("gross,expected", [
    (0, 0),            # zero gross
    (50000, 45000),    # all in 10% band: tax 5000
    (100000, 90000),   # boundary of 10% band: tax 10000
    (200000, 170000),  # 10000 + 20% * 100000 = 30000
    (300000, 250000),  # 10000 + 20% * 200000 = 50000
    (400000, 320000),  # 10000 + 40000 + 30% * 100000 = 80000
])
def test_progressive_tax_single_no_retirement(gross, expected):
    assert net_pay(gross) == expected


def test_pretax_retirement_reduces_taxable_income():
    # pre-tax 20000, taxable 180000, tax 10000 + 20% * 80000 = 26000
    assert net_pay(200000, retirement_pct=10) == 154000


def test_retirement_default_is_zero():
    assert net_pay(200000) == net_pay(200000, retirement_pct=0)


def test_filing_status_default_is_single():
    assert net_pay(200000) == net_pay(200000, "single")


def test_unknown_filing_status_rejected():
    with pytest.raises(ValueError):
        net_pay(50000, "head_of_household")


def test_negative_gross_rejected():
    with pytest.raises(ValueError):
        net_pay(-1)
