"""Positive fixture for fraud-domain rules."""
import os


def score_transaction(request, model):
    # Expected match: fraud-domain.fail-open-scoring (ERROR)
    try:
        score = model.predict(request.features)
    except Exception:
        return {"decision": "allow", "score": 0.0}

    # Expected match: fraud-domain.emulation-mode-bypass (WARNING)
    if os.environ.get("EMULATION_MODE"):
        return {"decision": "allow", "score": 0.0}

    return {"decision": "deny" if score > 0.7 else "allow", "score": score}


def build_features(request):
    features = {}
    # Expected match: fraud-domain.client-controlled-aggregate-feature (ERROR)
    features["velocity_24h"] = request.body.velocity_24h
    return features
