from src.cart import validate


def test_rejects_empty_cart():
    assert validate([]) == 'cart is empty'
