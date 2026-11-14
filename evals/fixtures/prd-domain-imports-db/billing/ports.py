"""Ports the billing domain depends on. Adapters implement them."""
from __future__ import annotations

from datetime import date
from typing import Protocol

from billing.model import Invoice


class InvoiceRepository(Protocol):
    def overdue_as_of(self, day: date) -> list[Invoice]: ...
    def save(self, invoice: Invoice) -> None: ...


class Notifier(Protocol):
    def send(self, customer_id: str, template: str, context: dict) -> None: ...
