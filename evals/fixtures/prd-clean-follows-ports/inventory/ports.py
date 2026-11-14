"""Ports the inventory domain depends on."""
from __future__ import annotations

from typing import Protocol

from inventory.model import StockItem


class StockRepository(Protocol):
    def get(self, sku: str) -> StockItem | None: ...
    def save(self, item: StockItem) -> None: ...
