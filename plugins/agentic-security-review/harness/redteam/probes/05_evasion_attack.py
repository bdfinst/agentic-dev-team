"""05_evasion_attack — search for adversarial inputs that receive low fraud
scores despite looking like fraud.

Three methods in order of cost:
  1. Random search        (fast, wide coverage)
  2. Greedy perturbation  (cheap, local; uses probe 03's feature ranking)
  3. Differential evolution (expensive; only if 1 + 2 did not find a good result)

Each method's results are tagged with `method` in the output so analysts can
reason about which attack class succeeded. Uses scipy's differential_evolution
when available; falls back to skipping method 3 if scipy is missing.

Produces: results/05_evasion.json
"""
from __future__ import annotations

import random
from typing import Any

from ..lib import http_client, result_store, scoring


SCORE_TARGET = 0.4   # low-fraud score we are trying to achieve
RANDOM_SEARCH_ITERATIONS = 30
GREEDY_ITERATIONS = 20


def _score(features: list[str], payload: dict) -> float | None:
    resp = http_client.client.post_predict(payload)
    return scoring.extract_score(resp)


def _random_search(features: list[str]) -> list[dict]:
    found: list[dict] = []
    rng = random.Random(42)
    for _ in range(RANDOM_SEARCH_ITERATIONS):
        payload = {f: rng.random() for f in features}
        score = _score(features, payload)
        if score is not None and score < SCORE_TARGET:
            found.append({"method": "random", "payload": payload, "score": score})
    return sorted(found, key=lambda x: x["score"])[:5]


def _greedy(features: list[str], ranked: list[str]) -> list[dict]:
    """Starting from baseline, iteratively move the most-sensitive feature toward
    whichever value produces a lower score."""
    payload = scoring.build_baseline_payload(features)
    baseline = _score(features, payload) or 1.0
    found: list[dict] = []

    for feat in ranked[:GREEDY_ITERATIONS]:
        best_for_feat = (payload[feat], baseline)
        for v in (0.0, 0.1, 0.3, 0.7, 0.9, 1.0):
            trial = dict(payload)
            trial[feat] = v
            score = _score(features, trial)
            if score is not None and score < best_for_feat[1]:
                best_for_feat = (v, score)
        payload[feat] = best_for_feat[0]
        if best_for_feat[1] < SCORE_TARGET:
            found.append({"method": "greedy", "payload": dict(payload), "score": best_for_feat[1]})
    return found[:5]


def _differential_evolution(features: list[str]) -> list[dict]:
    try:
        from scipy.optimize import differential_evolution  # type: ignore
    except ImportError:
        return []

    def objective(x: Any) -> float:
        payload = {f: float(x[i]) for i, f in enumerate(features)}
        score = _score(features, payload)
        if score is None:
            return 1.0
        return score  # minimize score

    bounds = [(0.0, 1.0)] * len(features)
    try:
        result = differential_evolution(
            objective,
            bounds,
            maxiter=3,            # keep query count low
            popsize=5,
            seed=42,
            polish=False,
        )
    except Exception as e:  # scipy raises various exceptions
        return [{"method": "differential_evolution", "error": f"{type(e).__name__}: {e}"}]
    payload = {f: float(result.x[i]) for i, f in enumerate(features)}
    return [{
        "method": "differential_evolution",
        "payload": payload,
        "score": float(result.fun),
        "iterations": int(result.nit),
    }]


def run() -> None:
    features = result_store.get_discovered_features()
    sensitivity = result_store.get_sensitivity_data()
    if not features:
        result_store.save("05_evasion", {"error": "no features from probe 02"})
        return

    all_results: list[dict] = []

    # Method 1: random
    all_results.extend(_random_search(features))

    # Method 2: greedy (uses probe 03's ranking)
    ranked = [r["feature"] for r in (sensitivity.get("rankings") or [])]
    if ranked:
        all_results.extend(_greedy(features, ranked))

    # Method 3: differential evolution only if earlier methods did not find anything
    lowest = min((r["score"] for r in all_results if "score" in r), default=1.0)
    if lowest >= SCORE_TARGET:
        all_results.extend(_differential_evolution(features))

    result_store.save("05_evasion", {
        "score_target": SCORE_TARGET,
        "results": all_results,
    })
