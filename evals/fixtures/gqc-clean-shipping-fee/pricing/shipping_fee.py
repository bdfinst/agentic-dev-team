"""Flat-rate shipping fee by destination country, free above a threshold."""
from __future__ import annotations

from decimal import Decimal

FREE_SHIPPING_THRESHOLD = Decimal("50.00")
RATES = {"DE": Decimal("4.90"), "FR": Decimal("5.90"), "NL": Decimal("4.50")}


class UnsupportedCountry(Exception):
    pass


def shipping_fee(subtotal: Decimal, country: str) -> Decimal:
    if subtotal < 0:
        raise ValueError("subtotal must not be negative")
    if country not in RATES:
        raise UnsupportedCountry(country)
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return Decimal("0.00")
    return RATES[country]
