from app.db import conn

TAX_RATE = 0.2


def issue_invoice(order_id, customer_id, net):
    with conn() as c:
        return c.insert("invoices", order_id=order_id, customer_id=customer_id,
                        amount=round(net * (1 + TAX_RATE), 2), status="open")


def record_payment(invoice_id, amount):
    with conn() as c:
        inv = c.get("invoices", id=invoice_id)
        status = "paid" if amount >= inv["amount"] else "partial"
        c.update("invoices", {"status": status}, id=invoice_id)
