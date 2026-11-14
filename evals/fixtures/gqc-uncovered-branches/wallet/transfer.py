"""Move money between two wallets owned by the same customer."""
from __future__ import annotations

from decimal import Decimal

from wallet.model import Wallet


class TransferError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def transfer(source: Wallet, target: Wallet, amount: Decimal) -> None:
    if amount <= 0:
        raise TransferError("AMOUNT_NOT_POSITIVE")
    if source.id == target.id:
        raise TransferError("SAME_WALLET")
    if source.currency != target.currency:
        raise TransferError("CURRENCY_MISMATCH")
    if source.balance < amount:
        raise TransferError("INSUFFICIENT_FUNDS")
    source.balance -= amount
    target.balance += amount
