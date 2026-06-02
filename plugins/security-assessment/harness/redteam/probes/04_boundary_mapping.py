"""04_boundary_mapping — binary-search per-feature decision boundaries.

For each sensitive feature (from probe 03's rankings), find the exact value at
which the fraud score flips between fraud and not-fraud. Assumes the score is
roughly monotonic in each feature (fails gracefully otherwise).

Produces: results/04_boundaries.json
"""
from __future__ import annotations

from ..lib import http_client, result_store, scoring


THRESHOLD = 0.5     # fraud / not-fraud boundary
MAX_ITERATIONS = 12


def _score_with(features: list[str], overrides: dict) -> float | None:
    payload = scoring.build_baseline_payload(features, overrides)
    resp = http_client.client.post_predict(payload)
    return scoring.extract_score(resp)


def _binary_search(features: list[str], feat: str, low: float, high: float) -> dict:
    """Find the value of `feat` in [low, high] where the score crosses THRESHOLD."""
    low_score = _score_with(features, {feat: low})
    high_score = _score_with(features, {feat: high})
    if low_score is None or high_score is None:
        return {"feature": feat, "boundary": None, "reason": "score extraction failed"}

    # Require that low and high straddle the threshold
    if (low_score - THRESHOLD) * (high_score - THRESHOLD) > 0:
        return {"feature": feat, "boundary": None,
                "reason": "range does not cross threshold",
                "low_score": low_score, "high_score": high_score}

    for _ in range(MAX_ITERATIONS):
        mid = (low + high) / 2.0
        mid_score = _score_with(features, {feat: mid})
        if mid_score is None:
            return {"feature": feat, "boundary": None, "reason": "mid-score failed"}
        if (mid_score - THRESHOLD) * (low_score - THRESHOLD) <= 0:
            high, high_score = mid, mid_score
        else:
            low, low_score = mid, mid_score

    return {
        "feature": feat,
        "boundary": (low + high) / 2.0,
        "iterations_used": MAX_ITERATIONS,
        "low_score": low_score,
        "high_score": high_score,
    }


def run() -> None:
    features = result_store.get_discovered_features()
    sensitivity = result_store.get_sensitivity_data()
    if not features or not sensitivity.get("rankings"):
        result_store.save("04_boundaries", {"error": "missing features or sensitivity rankings"})
        return

    # Probe the top-10 most-sensitive features
    top = [r["feature"] for r in sensitivity["rankings"][:10]]
    results: list[dict] = []
    for feat in top:
        results.append(_binary_search(features, feat, 0.0, 1.0))

    result_store.save("04_boundaries", {"boundaries": results})
