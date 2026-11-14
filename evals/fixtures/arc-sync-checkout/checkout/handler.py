from checkout import clients


def post_checkout(cart, customer):
    # All three calls run in the request path, in order.
    reservation = clients.inventory.reserve(cart.items, timeout=0.5)
    price = clients.pricing.quote(cart.items, customer.tier, timeout=0.3)
    order = save_order(cart, customer, price, reservation)
    clients.notify.send_confirmation_email(customer.email, order.id, timeout=2.0)
    return {"order_id": order.id, "total": price.total}


def save_order(cart, customer, price, reservation):
    ...
