"""Existing invoice export. Streams CSV so large accounts do not time out.

Shipped in release 4.2; the only export in the product today.
"""
import csv
import io
from collections.abc import Iterable, Iterator

FIELDS = ["id", "date", "amount", "status"]


def export_invoices_csv(invoices: Iterable[dict]) -> Iterator[str]:
    """Yield the CSV one line at a time, so the response never holds the whole file."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS)

    def flush() -> str:
        line = buf.getvalue()
        buf.seek(0)
        buf.truncate()
        return line

    writer.writeheader()
    yield flush()
    for inv in invoices:
        writer.writerow({k: inv[k] for k in FIELDS})
        yield flush()
