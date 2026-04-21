"""Negative fixture — should produce zero matches."""


def score_transaction(request, model, velocity_lookup):
    # Fail-closed: error path returns an error shape, not allow
    try:
        score = model.predict(request.features)
    except Exception as e:
        return {"decision": "error", "error": str(e)}

    return {"decision": "deny" if score > 0.7 else "allow", "score": score}


def build_features(request, velocity_lookup):
    # velocity computed server-side, not from request
    return {
        "velocity_24h": velocity_lookup.get(request.card_id, "24h"),
        "amount": request.body.amount,   # OK: amount is not an aggregate
    }
