import os

import requests

PAYGATE_URL = "https://sandbox.paygate.example.com/v2/charges"


class CheckoutService:
    def __init__(self, orders_repo):
        self.orders = orders_repo

    def place_order(self, order_id: str) -> str:
        order = self.orders.get(order_id)
        if order.total_cents <= 0:
            raise ValueError("empty order")
        resp = requests.post(
            PAYGATE_URL,
            json={"amount": order.total_cents, "currency": "USD", "ref": order_id},
            headers={"Authorization": f"Bearer {os.environ['PAYGATE_KEY']}"},
            timeout=10,
        )
        if resp.status_code == 402:
            order.status = "payment_declined"
        elif resp.status_code >= 500:
            order.status = "payment_pending_retry"
        else:
            order.status = "paid"
        self.orders.save(order)
        return order.status
