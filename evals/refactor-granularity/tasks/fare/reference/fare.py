"""Reference solution for the `fare` task — FINAL state (after change1-3).

Used only to validate the hidden acceptance suites. Never given to an agent.
"""
from decimal import Decimal, ROUND_HALF_UP

# (upper_inclusive_km, base_cents); distances above the last bound use _BASE_ABOVE.
_BANDS = ((5, 200), (10, 350))
_BASE_ABOVE = 500
_DISCOUNT_PCT = {"adult": 0, "child": 50, "senior": 30}
_PEAK_MULT = Decimal("1.5")
_ZONE_SURCHARGE = 100  # cents per zone beyond the first
_DAILY_CAP = 1000      # cents
_TRANSFER_WINDOW = 90  # minutes


def _round_cents(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fare(distance_km, passenger="adult", peak=False, zones=1):
    """Single-ride fare in integer cents.

    Order of operations (change3 makes this load-bearing): base band ->
    + zone surcharge -> x peak multiplier -> x passenger discount.
    """
    if distance_km < 0:
        raise ValueError("distance_km must be non-negative")
    if passenger not in _DISCOUNT_PCT:
        raise ValueError(f"unknown passenger type: {passenger!r}")
    if zones < 1:
        raise ValueError("zones must be >= 1")

    base = _BASE_ABOVE
    for upper, band_cents in _BANDS:
        if distance_km <= upper:
            base = band_cents
            break

    amount = Decimal(base + (zones - 1) * _ZONE_SURCHARGE)
    if peak:
        amount *= _PEAK_MULT
    amount *= Decimal(100 - _DISCOUNT_PCT[passenger]) / Decimal(100)
    return _round_cents(amount)


def day_total(rides, daily_cap_cents=_DAILY_CAP):
    """Total cents for a day of rides, applying transfer discounts then a cap.

    Each ride is a dict of fare() kwargs, optionally with 'start_min' (minutes
    since midnight). A ride whose start is within _TRANSFER_WINDOW minutes after
    the previous ride's start is charged at half (transfer discount, change2),
    computed before the running daily cap (change1) is applied.
    """
    total = 0
    prev_start = None
    for ride in rides:
        start = ride.get("start_min")
        kwargs = {k: v for k, v in ride.items() if k != "start_min"}
        charge = fare(**kwargs)
        if (prev_start is not None and start is not None
                and 0 <= start - prev_start <= _TRANSFER_WINDOW):
            charge = _round_cents(Decimal(charge) / 2)
        if total + charge > daily_cap_cents:
            charge = daily_cap_cents - total
        total += charge
        if start is not None:
            prev_start = start
    return total
