"""scoring — score extraction and baseline payload construction.

Centralizes response-shape knowledge so probes do not hardcode key paths.
Supports the shapes observed in the opus_repo_scan_test reference plus the
common ML-serving patterns.
"""
from __future__ import annotations

from typing import Any

import httpx


def extract_score(response: httpx.Response | dict | None) -> float | None:
    """Return a single float score from a model response across known shapes.

    Shapes handled (in order of preference):
        1. top-level float or int
        2. top-level dict with 'score', 'fraud_score', 'probability', 'risk_score'
        3. nested 'result.probas.B' (legacy ACI shape)
        4. 'predictions[0].score' (TF-serving / SageMaker shape)
        5. 'output.confidence' (some Hugging Face wrappers)

    Returns None when no shape matches.
    """
    if response is None:
        return None

    if isinstance(response, httpx.Response):
        try:
            data: Any = response.json()
        except (ValueError, httpx.ResponseNotRead):
            return None
    else:
        data = response

    # Shape 1: raw numeric
    if isinstance(data, (int, float)):
        return float(data)

    # Shape 2: top-level score-like keys
    if isinstance(data, dict):
        for key in ("score", "fraud_score", "probability", "risk_score"):
            if key in data and isinstance(data[key], (int, float)):
                return float(data[key])

        # Shape 3: nested result.probas.B
        result = data.get("result")
        if isinstance(result, dict):
            probas = result.get("probas")
            if isinstance(probas, dict):
                b = probas.get("B")
                if isinstance(b, (int, float)):
                    return float(b)

        # Shape 4: predictions[0].score
        preds = data.get("predictions")
        if isinstance(preds, list) and preds:
            first = preds[0]
            if isinstance(first, dict) and isinstance(first.get("score"), (int, float)):
                return float(first["score"])

        # Shape 5: output.confidence
        output = data.get("output")
        if isinstance(output, dict):
            conf = output.get("confidence")
            if isinstance(conf, (int, float)):
                return float(conf)

    return None


def build_baseline_payload(features: list[str], values: dict[str, Any] | None = None) -> dict:
    """Construct a mid-range payload for sensitivity / boundary analysis.

    Each feature is defaulted to a numeric mid-value (0.5) unless overridden in
    `values`. Non-numeric features default to None; probes that care about
    non-numeric types should pass their own defaults via `values`.
    """
    payload: dict[str, Any] = {}
    for feat in features:
        if values and feat in values:
            payload[feat] = values[feat]
        else:
            payload[feat] = 0.5
    return payload
