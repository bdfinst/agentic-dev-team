"""Reference solution for the `cart` task — FINAL state (after change1-3).

Used only to validate the hidden acceptance suites. Never given to an agent.
"""
from decimal import Decimal, ROUND_HALF_UP

_BULK_QTY_THRESHOLD = 10        # qty >= this earns the bulk discount
_BULK_DISCOUNT_PCT = 10         # percent off a qualifying line's gross
_TAX_PCT = Decimal("8")         # sales tax percent on the taxed subtotal
_CATEGORY_DISCOUNT_CAP = {      # change2: max discount cents per category
    "electronics": 2000,
    "apparel": 500,
}
_TAX_EXEMPT = {"groceries", "books"}  # change3: categories that are not taxed


def _round_cents(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def checkout(items, coupon_pct=0):
    """Order total in integer cents.

    Order of operations (change2/change3 make this load-bearing): for each line,
    gross -> bulk discount -> order coupon -> per-category discount cap, then the
    line's net joins the taxed or the tax-exempt subtotal by its category, and
    only the taxed subtotal is taxed.
    """
    if coupon_pct < 0 or coupon_pct > 100:
        raise ValueError("coupon_pct must be between 0 and 100")

    taxed_net = Decimal(0)
    untaxed_net = Decimal(0)
    for item in items:
        price = item["price_cents"]
        qty = item["qty"]
        if price < 0:
            raise ValueError("price_cents must be non-negative")
        if qty < 0:
            raise ValueError("qty must be non-negative")

        gross = Decimal(price) * Decimal(qty)
        category = item.get("category")

        discount = Decimal(0)
        if qty >= _BULK_QTY_THRESHOLD:
            discount += gross * Decimal(_BULK_DISCOUNT_PCT) / Decimal(100)
        # change1: order coupon, after bulk discount, on what remains of the line
        discount += (gross - discount) * Decimal(coupon_pct) / Decimal(100)

        # change2: the combined discount per category cannot exceed its cap
        cap = _CATEGORY_DISCOUNT_CAP.get(category)
        if cap is not None and discount > cap:
            discount = Decimal(cap)

        net = gross - discount
        # change3: tax-exempt categories never enter the taxed subtotal
        if category in _TAX_EXEMPT:
            untaxed_net += net
        else:
            taxed_net += net

    tax = taxed_net * _TAX_PCT / Decimal(100)
    return _round_cents(taxed_net + untaxed_net + tax)
