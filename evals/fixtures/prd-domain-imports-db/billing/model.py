"""Invoice entity (abridged)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class Invoice:
    id: str
    customer_id: str
    due_date: date
    balance: Decimal
    late_fee_applied: bool = False

    def add_fee(self, amount: Decimal) -> None:
        self.balance += amount
        self.late_fee_applied = True

    @classmethod
    def from_row(cls, row) -> Invoice:
        return cls(row["id"], row["customer_id"], row["due_date"], row["balance"], row["late_fee_applied"])
