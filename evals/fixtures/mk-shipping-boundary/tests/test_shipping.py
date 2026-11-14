from shop.shipping import shipping_fee


def test_small_order_pays_flat_fee():
    assert shipping_fee(10, 1) == 5


def test_large_order_ships_free():
    assert shipping_fee(100, 1) == 0
