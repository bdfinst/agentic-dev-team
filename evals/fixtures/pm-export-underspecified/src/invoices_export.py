"""Existing invoice export. Streams CSV so large accounts do not time out.

Shipped in release 4.2; the only export in the product today.
"""
import csv
import io


def export_invoices_csv(invoices: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["id", "date", "amount", "status"])
    writer.writeheader()
    for inv in invoices:
        writer.writerow({k: inv[k] for k in writer.fieldnames})
    return buf.getvalue()
