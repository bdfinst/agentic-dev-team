"""Postgres adapter for InvoiceRepository."""
from __future__ import annotations

from datetime import date

import psycopg
from billing.model import Invoice


class PgInvoiceRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def overdue_as_of(self, day: date) -> list[Invoice]:
        rows = self._conn.execute(
            "SELECT * FROM invoices WHERE due_date < %s AND balance > 0", (day,)
        ).fetchall()
        return [Invoice.from_row(r) for r in rows]

    def save(self, invoice: Invoice) -> None:
        self._conn.execute(
            "UPDATE invoices SET balance = %s, late_fee_applied = %s WHERE id = %s",
            (invoice.balance, invoice.late_fee_applied, invoice.id),
        )
