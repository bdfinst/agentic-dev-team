"""03_feature_sensitivity — sweep each discovered feature across a value range,
measure how the fraud score responds, rank features by influence.

Produces: results/03_sensitivity.json
"""
from __future__ import annotations

from ..lib import http_client, result_store, scoring


SWEEP_VALUES = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]


def _score_for(features: list[str], overrides: dict) -> float | None:
    payload = scoring.build_baseline_payload(features, overrides)
    resp = http_client.client.post_predict(payload)
    return scoring.extract_score(resp)


def run() -> None:
    features = result_store.get_discovered_features()
    if not features:
        result_store.save("03_sensitivity", {"error": "no features from probe 02"})
        return

    baseline = _score_for(features, {})
    rankings: list[dict] = []

    for feat in features:
        sweep_scores = []
        for v in SWEEP_VALUES:
            score = _score_for(features, {feat: v})
            sweep_scores.append({"value": v, "score": score})
        valid = [s["score"] for s in sweep_scores if s["score"] is not None]
        if len(valid) < 2:
            sensitivity = 0.0
        else:
            sensitivity = max(valid) - min(valid)
        rankings.append({
            "feature": feat,
            "sensitivity": sensitivity,
            "sweep": sweep_scores,
        })

    rankings.sort(key=lambda r: r["sensitivity"], reverse=True)
    result_store.save("03_sensitivity", {
        "baseline_score": baseline,
        "rankings": rankings,
    })
