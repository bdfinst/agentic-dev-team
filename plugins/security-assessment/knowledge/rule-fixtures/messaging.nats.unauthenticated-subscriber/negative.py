def register(nc):
    authenticate(ctx)
    nc.subscribe("payment.txn.scored", cb)
