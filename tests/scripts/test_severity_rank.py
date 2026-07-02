"""scripts/lib/normalize_findings.py and scripts/lib/skeleton_report.py each
hand-rolled their own severity-rank ordering (a dict in one, a list in the
other) for the same concept: error > warning > suggestion > info. Both must
now share a single canonical ordering from scripts/lib/severity_rank.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIB = REPO_ROOT / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import severity_rank  # noqa: E402


def test_severity_order_is_highest_first() -> None:
    assert severity_rank.SEVERITY_ORDER == ["error", "warning", "suggestion", "info"]


def test_rank_orders_error_above_warning_above_suggestion_above_info() -> None:
    ranks = [severity_rank.rank(s) for s in severity_rank.SEVERITY_ORDER]
    assert ranks == sorted(ranks, reverse=True)


def test_rank_unknown_severity_is_lowest() -> None:
    assert severity_rank.rank("bogus") < severity_rank.rank("info")


def test_sort_index_orders_error_first() -> None:
    indices = [severity_rank.sort_index(s) for s in severity_rank.SEVERITY_ORDER]
    assert indices == sorted(indices)


def test_sort_index_unknown_severity_sorts_last() -> None:
    assert severity_rank.sort_index("bogus") > severity_rank.sort_index("info")


def _module_source(name: str) -> str:
    return (LIB / name).read_text(encoding="utf-8")


def test_normalize_findings_does_not_duplicate_the_rank_table() -> None:
    src = _module_source("normalize_findings.py")
    assert "severity_rank" in src
    assert '"error": 4' not in src, (
        "normalize_findings.py should import the shared rank table, not "
        "redefine it inline"
    )


def test_skeleton_report_does_not_duplicate_the_order_list() -> None:
    src = _module_source("skeleton_report.py")
    assert "severity_rank" in src
    assert 'SEVERITY_ORDER = ["error", "warning", "suggestion", "info"]' not in src, (
        "skeleton_report.py should import the shared SEVERITY_ORDER, not "
        "redefine it inline"
    )
