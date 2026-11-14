from .registry import REPORT_TYPES


def render(report_type: str, rows: list[dict]) -> dict:
    """Return the on-screen table for a report. Rows are capped at 500 for display."""
    if report_type not in REPORT_TYPES:
        raise KeyError(report_type)
    return {"title": REPORT_TYPES[report_type], "rows": rows[:500]}
