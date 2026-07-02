#!/usr/bin/env python3
"""severity_rank — canonical unified-finding severity ordering.

Single source of truth for the error > warning > suggestion > info ordering
shared by scripts/lib/normalize_findings.py (dedup: keep the higher-severity
duplicate) and scripts/lib/skeleton_report.py (sort findings tables by
severity). Both previously hand-rolled their own copy of this ordering.
"""

from __future__ import annotations

# Highest severity first.
SEVERITY_ORDER = ["error", "warning", "suggestion", "info"]


def rank(severity: str) -> int:
    """Numeric rank where a higher value is more severe. Unknown/missing
    severities rank below every known severity (0)."""
    try:
        return len(SEVERITY_ORDER) - SEVERITY_ORDER.index(severity)
    except ValueError:
        return 0


def sort_index(severity: str) -> int:
    """Sort key where a lower value sorts first (most severe first). Unknown
    severities sort after every known severity."""
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)
