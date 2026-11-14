"""Reserve stock for an order line. Domain logic over the injected port."""
from __future__ import annotations

from inventory.model import StockItem
from inventory.ports import StockRepository


class UnknownSku(Exception):
    pass


class ReservationService:
    def __init__(self, stock: StockRepository) -> None:
        self._stock = stock

    def reserve(self, sku: str, qty: int) -> StockItem:
        item = self._stock.get(sku)
        if item is None:
            raise UnknownSku(sku)
        item.reserve(qty)
        self._stock.save(item)
        return item
