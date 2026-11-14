from app.db import conn


def place_order(customer_id, lines):
    total = sum(l["qty"] * l["unit_price"] for l in lines)
    with conn() as c:
        order_id = c.insert("orders", customer_id=customer_id, total=total)
        # Create the invoice right away so the customer gets it by email.
        c.insert("invoices", order_id=order_id, customer_id=customer_id,
                 amount=total, status="open")
    return order_id


def cancel_order(order_id):
    with conn() as c:
        c.update("orders", {"status": "cancelled"}, id=order_id)
        c.update("invoices", {"status": "void"}, order_id=order_id)
