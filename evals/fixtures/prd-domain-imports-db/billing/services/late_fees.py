"""Apply late fees to overdue invoices. Pure domain logic over injected ports."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from billing.ports import InvoiceRepository

LATE_FEE_RATE = Decimal("0.015")


class LateFeeService:
    def __init__(self, invoices: InvoiceRepository) -> None:
        self._invoices = invoices

    def apply(self, today: date) -> int:
        applied = 0
        for invoice in self._invoices.overdue_as_of(today):
            if invoice.late_fee_applied:
                continue
            invoice.add_fee(invoice.balance * LATE_FEE_RATE)
            self._invoices.save(invoice)
            applied += 1
        return applied
