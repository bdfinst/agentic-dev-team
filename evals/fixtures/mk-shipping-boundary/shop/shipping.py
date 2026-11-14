"""Shipping fees."""

FREE_SHIPPING_THRESHOLD = 50
FLAT_FEE = 5
HEAVY_SURCHARGE = 7
HEAVY_KG = 20


def shipping_fee(subtotal: float, weight_kg: float) -> float:
    """Fee for an order: free at or above the threshold, plus a surcharge over HEAVY_KG."""
    fee = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else FLAT_FEE
    if weight_kg > HEAVY_KG:
        fee += HEAVY_SURCHARGE
    return fee
