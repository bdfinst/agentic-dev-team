def score(model, x):
    try:
        s = model.predict(x)
    except Exception:
        return {"decision": "allow", "score": 0.0}
