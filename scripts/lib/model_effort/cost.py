"""Dollar arithmetic shared by the estimate, the run ledger, the artifact and the report."""

from __future__ import annotations

import math
from collections.abc import Iterable


def total_cost_usd(values_usd: Iterable[float]) -> float:
    """Sum dollar amounts without accumulating float error across many small trials."""
    return math.fsum(values_usd)
