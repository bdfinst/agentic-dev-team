import time

import requests


def test_checkout_through_staging():
    time.sleep(5)
    response = requests.post("https://staging.example.com/checkout", json={"items": []})
    assert response.status_code == 200
