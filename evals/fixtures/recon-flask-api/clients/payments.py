import os

import requests

BASE_URL = os.getenv("PAYMENTS_URL", "https://payments.example.com")


def charge(order_id, amount_cents):
    resp = requests.post(f"{BASE_URL}/charges",
                         json={"order": order_id, "amount": amount_cents},
                         timeout=5)
    resp.raise_for_status()
    return resp.json()
