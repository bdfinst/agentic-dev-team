"""Pure scoring rules; no I/O."""


def score(model, features):
    raw = model.predict_proba([features])[0][1]
    return round(float(raw), 4)


def band(risk):
    if risk >= 0.8:
        return "high"
    return "medium" if risk >= 0.4 else "low"
