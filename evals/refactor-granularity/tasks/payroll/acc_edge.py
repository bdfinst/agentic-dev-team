"""Hidden EDGE acceptance for `payroll` — boundary and rounding cases.

Stated in the clear spec, but the cases a thin suite tends to miss. Injected
only at grading.
"""
import pytest
from payroll import net_pay


def test_bracket_boundary_belongs_to_lower_rate():
    # exactly 100000 taxable is fully in the 10% band: tax 10000
    assert net_pay(100000) == 90000
    # exactly 300000 taxable: 10000 + 20% * 200000 = 50000
    assert net_pay(300000) == 250000


def test_just_above_boundary_taxes_next_band():
    # 100001 taxable: 10000 + 20% * 1 = 10000.2 -> net 90000.8 -> 90001
    assert net_pay(100001) == 90001
    # 300001 taxable: 50000 + 30% * 1 = 50000.3 -> net 250000.7 -> 250001
    assert net_pay(300001) == 250001


def test_half_up_rounding_on_pretax_fraction():
    # pre-tax 15, taxable 285, tax 28.5, net 256.5 -> 257 (half UP, not banker's)
    assert net_pay(300, retirement_pct=5) == 257


def test_full_retirement_leaves_zero_taxable():
    # 100% pre-tax: taxable 0, tax 0, net 0
    assert net_pay(200000, retirement_pct=100) == 0


def test_retirement_out_of_range_rejected():
    with pytest.raises(ValueError):
        net_pay(50000, retirement_pct=-1)
    with pytest.raises(ValueError):
        net_pay(50000, retirement_pct=101)


def test_zero_gross_is_zero_net():
    assert net_pay(0) == 0
    assert net_pay(0, retirement_pct=10) == 0
