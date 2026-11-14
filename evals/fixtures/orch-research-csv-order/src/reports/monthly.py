from .export import export_csv


def monthly_sales_csv(rows: list[dict], columns: list[str] | None = None) -> str:
    return export_csv(rows, columns)
