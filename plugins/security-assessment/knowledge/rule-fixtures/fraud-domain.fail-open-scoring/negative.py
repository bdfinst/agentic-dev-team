def score(model, x):
    try:
        s = model.predict(x)
    except Exception:
        return {"decision": "deny", "score": 1.0}
