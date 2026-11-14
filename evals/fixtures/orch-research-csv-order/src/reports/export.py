import csv
import io

DEFAULT_COLUMNS = ["month", "region", "units", "revenue"]


def export_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    """Render report rows as CSV in DEFAULT_COLUMNS order."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=DEFAULT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
