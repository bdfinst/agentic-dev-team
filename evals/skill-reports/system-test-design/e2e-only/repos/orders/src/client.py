import requests

BILLING = 'http://billing'
INVENTORY = 'http://inventory'


def bill(order):
    # call billing
    # call billing
    # call billing
    # call billing
    return requests.post(BILLING + '/invoices', json=order)
