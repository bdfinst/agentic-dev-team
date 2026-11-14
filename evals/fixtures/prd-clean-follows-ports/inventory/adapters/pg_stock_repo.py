"""Postgres adapter for StockRepository."""
from __future__ import annotations

import psycopg
from inventory.model import StockItem


class PgStockRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get(self, sku: str) -> StockItem | None:
        row = self._conn.execute(
            "SELECT sku, on_hand, reorder_point FROM stock WHERE sku = %s", (sku,)
        ).fetchone()
        return StockItem(*row) if row else None

    def save(self, item: StockItem) -> None:
        self._conn.execute(
            "UPDATE stock SET on_hand = %s WHERE sku = %s", (item.on_hand, item.sku)
        )
