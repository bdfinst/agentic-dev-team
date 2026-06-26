"""CHANGE 1 acceptance: overtime gross via gross_from_hours(). Injected at grading.

Hours beyond 40 are paid at 1.5x and feed into net_pay() as gross.
"""
import pytest
from payroll import gross_from_hours, net_pay


def test_no_overtime_under_threshold():
    assert gross_from_hours(40, 2500) == 100000
    assert gross_from_hours(30, 2500) == 75000


def test_overtime_paid_at_time_and_a_half():
    # 40 * 2500 = 100000 regular, + 5 * 2500 * 1.5 = 18750 overtime
    assert gross_from_hours(45, 2500) == 118750
    # 80000 regular + 10 * 2000 * 1.5 = 30000 overtime
    assert gross_from_hours(50, 2000) == 110000


def test_overtime_gross_flows_into_net_pay():
    # gross 118750, tax 10000 + 20% * 18750 = 13750, net 105000
    assert net_pay(gross_from_hours(45, 2500)) == 105000


def test_negative_hours_rejected():
    with pytest.raises(ValueError):
        gross_from_hours(-1, 2500)


def test_negative_rate_rejected():
    with pytest.raises(ValueError):
        gross_from_hours(40, -1)
