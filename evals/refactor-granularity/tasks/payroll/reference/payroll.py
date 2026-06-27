"""Reference solution for the `payroll` task — FINAL state (after change1-3).

Used only to validate the hidden acceptance suites. Never given to an agent.
"""
from decimal import Decimal, ROUND_HALF_UP

# Progressive brackets per filing status: ((upper_inclusive_cents, rate_pct), ...)
# The last tier uses upper=None (no ceiling). change3 adds "married".
_BRACKETS = {
    "single": ((100000, 10), (300000, 20), (None, 30)),
    "married": ((200000, 10), (500000, 20), (None, 30)),
}
_OVERTIME_THRESHOLD_HOURS = 40       # hours beyond this are overtime
_OVERTIME_MULTIPLIER = Decimal("1.5")


def _round_cents(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _tax(taxable: Decimal, filing_status: str) -> Decimal:
    """Progressive tax on taxable income (Decimal cents) for a filing status."""
    tax = Decimal(0)
    lower = 0
    for upper, rate_pct in _BRACKETS[filing_status]:
        ceiling = taxable if upper is None else min(taxable, Decimal(upper))
        span = ceiling - lower
        if span > 0:
            tax += span * Decimal(rate_pct) / Decimal(100)
        if upper is not None and taxable <= upper:
            break
        lower = upper
    return tax


def net_pay(gross_cents, filing_status="single", retirement_pct=0,
            garnishment_cents=0):
    """Net pay in integer cents.

    Order of operations (load-bearing): gross -> pre-tax retirement deduction
    -> taxable income -> progressive tax (change3: per filing status) ->
    post-tax garnishment (change2) -> net. The retirement deduction is pre-tax;
    the garnishment is post-tax and must NOT reduce taxable income.
    """
    if gross_cents < 0:
        raise ValueError("gross_cents must be non-negative")
    if filing_status not in _BRACKETS:
        raise ValueError(f"unknown filing status: {filing_status!r}")
    if not (0 <= retirement_pct <= 100):
        raise ValueError("retirement_pct must be between 0 and 100")
    if garnishment_cents < 0:
        raise ValueError("garnishment_cents must be non-negative")

    pretax = Decimal(gross_cents) * Decimal(retirement_pct) / Decimal(100)
    taxable = Decimal(gross_cents) - pretax
    tax = _tax(taxable, filing_status)
    net = Decimal(gross_cents) - pretax - tax - Decimal(garnishment_cents)
    return _round_cents(net)


def gross_from_hours(hours, hourly_rate_cents):
    """Gross pay in integer cents from hours worked at an hourly rate.

    Hours beyond _OVERTIME_THRESHOLD_HOURS (40) are paid at 1.5x (change1).
    """
    if hours < 0:
        raise ValueError("hours must be non-negative")
    if hourly_rate_cents < 0:
        raise ValueError("hourly_rate_cents must be non-negative")
    regular = min(Decimal(hours), Decimal(_OVERTIME_THRESHOLD_HOURS))
    overtime = max(Decimal(hours) - Decimal(_OVERTIME_THRESHOLD_HOURS), Decimal(0))
    gross = (regular * Decimal(hourly_rate_cents)
             + overtime * Decimal(hourly_rate_cents) * _OVERTIME_MULTIPLIER)
    return _round_cents(gross)
