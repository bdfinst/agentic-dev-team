def register(nc):
    nc.subscribe("payment.txn.scored", cb)
