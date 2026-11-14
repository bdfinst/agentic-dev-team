"""Build the order list shown on a customer's account page."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

LOOKUP_SQL = (Path(__file__).parent / "order_lookup.sql").read_text()


@dataclass(frozen=True)
class OrderLine:
    order_id: int
    status: str


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def orders_for(connection: sqlite3.Connection, customer_id: int) -> list[OrderLine]:
    rows = connection.execute(LOOKUP_SQL, {"customer_id": customer_id}).fetchall()
    return [OrderLine(order_id=row["id"], status=row["status"]) for row in rows]
