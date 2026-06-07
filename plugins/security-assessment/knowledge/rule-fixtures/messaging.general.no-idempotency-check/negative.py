def handle_message(msg):
    seen = cache.get(idempotency_key)
    if seen:
        return
    db.insert(msg)
