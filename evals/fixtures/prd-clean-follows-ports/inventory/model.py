from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StockItem:
    sku: str
    on_hand: int
    reorder_point: int

    def reserve(self, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.on_hand:
            raise InsufficientStock(self.sku, qty, self.on_hand)
        self.on_hand -= qty


class InsufficientStock(Exception):
    def __init__(self, sku: str, wanted: int, available: int) -> None:
        super().__init__(f"{sku}: wanted {wanted}, available {available}")
        self.sku, self.wanted, self.available = sku, wanted, available
