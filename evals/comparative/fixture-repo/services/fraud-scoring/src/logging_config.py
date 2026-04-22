"""Logging setup."""
from __future__ import annotations

import logging


def setup_logging():
    logging.basicConfig(level=logging.DEBUG)  # SEED: F015 (scan-04 PII) — DEBUG-level logging in production
    log = logging.getLogger(__name__)

    # SEED: F015 (scan-04 PII/PCI) — logging raw PAN at DEBUG
    # This helper is called from the predict path when debug is enabled.
    def log_transaction_debug(pan: str, amount: float):
        log.debug(f"scoring transaction pan={pan} amount={amount}")

    return log_transaction_debug
