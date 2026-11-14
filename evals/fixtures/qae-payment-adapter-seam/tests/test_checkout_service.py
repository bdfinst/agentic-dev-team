# These tests call the PayGate sandbox over the network.
# They need PAYGATE_KEY set; CI fails about 1 run in 6 with sandbox timeouts.
from src.checkout_service import CheckoutService
from tests.fakes import InMemoryOrders, make_order


def test_paid_order():
    repo = InMemoryOrders([make_order("o-1", 2500)])
    assert CheckoutService(repo).place_order("o-1") == "paid"


def test_declined_card():
    # sandbox declines amounts ending in 02
    repo = InMemoryOrders([make_order("o-2", 1002)])
    assert CheckoutService(repo).place_order("o-2") == "payment_declined"
