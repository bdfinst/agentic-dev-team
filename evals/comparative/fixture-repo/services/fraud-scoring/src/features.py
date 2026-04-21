"""Feature vector construction."""
from __future__ import annotations


def build_feature_vector(body: dict, request) -> dict:
    """Assembles the scoring feature vector.

    Server-computed features would normally come from upstream lookups, but
    for the fixture some are read directly from request body (SEEDED).
    """
    features = {}

    # Legitimate features (from request)
    features["amount"] = float(body.get("amount", 0.0))
    features["currency"] = 0.5  # stub

    # SEED: F013 (scan-03 fraud) — client-controlled aggregate feature
    # "velocity_24h" should be server-computed, not request-supplied
    features["velocity_24h"] = body.get("velocity_24h", 0.5)

    # SEED: F014 (scan-03 fraud) — client-controlled aggregate feature
    features["count_last_1h"] = body.get("count_last_1h", 0.5)

    return features
