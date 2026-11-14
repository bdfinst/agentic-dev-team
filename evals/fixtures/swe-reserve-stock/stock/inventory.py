"""In-memory inventory with reservations."""


class InsufficientStock(Exception):
    """A reservation asked for more units than are available."""


class Inventory:
    def __init__(self, on_hand: dict[str, int]):
        self._on_hand = dict(on_hand)
        self._reserved = {sku: 0 for sku in on_hand}

    def on_hand(self, sku: str) -> int:
        return self._on_hand[sku]

    def available(self, sku: str) -> int:
        return self._on_hand[sku] - self._reserved[sku]

    def receive(self, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self._on_hand[sku] = self._on_hand.get(sku, 0) + quantity
        self._reserved.setdefault(sku, 0)

    def release(self, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self._reserved[sku] -= min(quantity, self._reserved[sku])
