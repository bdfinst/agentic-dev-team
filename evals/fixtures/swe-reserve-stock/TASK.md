# Task: reserve stock for an order

Add `Inventory.reserve(sku: str, quantity: int) -> None` to `stock/inventory.py`.
A reservation holds units for an order: reserved units stay on hand but can no
longer be reserved again, and `available(sku)` drops by the reserved amount.

Acceptance criteria:

1. Reserving decreases `available(sku)` by `quantity`; `on_hand(sku)` is unchanged.
2. Reserving exactly the available amount succeeds and leaves 0 available.
3. Reserving more than is available raises `InsufficientStock` and changes nothing.
4. A quantity of zero or less raises `ValueError` and changes nothing.
5. An unknown SKU raises `KeyError`.
6. `release(sku, quantity)` (already present) must keep working: it returns
   reserved units to `available`, never more than were reserved.

`tests/test_acceptance.py` encodes these criteria and must pass unchanged; the
existing tests must keep passing. Note the existing `release` keeps its own
bookkeeping in `_reserved`; reuse it. Run:

    python3 -m unittest discover -s tests -t .
