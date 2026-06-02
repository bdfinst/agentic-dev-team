"""07_model_extraction — train surrogate models against captured scores.

Latin-Hypercube sampling + three surrogate models (decision tree, random
forest, linear regression). R² on a held-out 20% sample is the extraction
fidelity metric. R² > 0.85 suggests substantial reproduction; > 0.95 is
effectively IP theft.

Produces: results/07_extraction.json
"""
from __future__ import annotations

from ..lib import http_client, result_store, scoring


N_SAMPLES_DEFAULT = 200   # keep query count modest; budget-bounded
HOLDOUT_FRACTION = 0.2


def _collect_samples(features: list[str], n: int) -> list[dict]:
    """Latin-Hypercube sampling over [0,1]^len(features). Returns
    [{payload, score}, ...] with score=None for queries that returned nothing."""
    try:
        from scipy.stats import qmc  # type: ignore
        sampler = qmc.LatinHypercube(d=len(features), seed=42)
        raw_samples = sampler.random(n=n)
    except ImportError:
        # Deterministic uniform fallback — not as space-filling but works
        import random
        rng = random.Random(42)
        raw_samples = [[rng.random() for _ in features] for _ in range(n)]

    out: list[dict] = []
    for row in raw_samples:
        payload = {f: float(row[i]) for i, f in enumerate(features)}
        resp = http_client.client.post_predict(payload)
        out.append({
            "payload": payload,
            "score": scoring.extract_score(resp),
        })
    return out


def _train_surrogates(samples: list[dict], features: list[str]) -> dict:
    try:
        import numpy as np
        from sklearn.tree import DecisionTreeRegressor
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import r2_score
    except ImportError as e:
        return {"error": f"sklearn unavailable: {e}"}

    X = np.array([[s["payload"][f] for f in features] for s in samples if s["score"] is not None])
    y = np.array([s["score"] for s in samples if s["score"] is not None])
    if len(y) < 20:
        return {"error": f"too few valid samples for surrogate training: {len(y)}"}

    split = int(len(y) * (1 - HOLDOUT_FRACTION))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    out: dict = {}

    tree = DecisionTreeRegressor(max_depth=8, random_state=42)
    tree.fit(X_train, y_train)
    out["decision_tree"] = {"r2": float(r2_score(y_test, tree.predict(X_test))),
                            "max_depth": 8,
                            "n_train": int(len(y_train))}

    forest = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=1)
    forest.fit(X_train, y_train)
    out["random_forest"] = {"r2": float(r2_score(y_test, forest.predict(X_test))),
                            "n_estimators": 100,
                            "n_train": int(len(y_train))}

    linreg = LinearRegression()
    linreg.fit(X_train, y_train)
    out["linear_regression"] = {"r2": float(r2_score(y_test, linreg.predict(X_test))),
                                "n_train": int(len(y_train))}
    return out


def run() -> None:
    features = result_store.get_discovered_features()
    if not features:
        result_store.save("07_extraction", {"error": "no features from probe 02"})
        return

    n = N_SAMPLES_DEFAULT
    samples = _collect_samples(features, n)
    surrogates = _train_surrogates(samples, features)

    best_r2 = max(
        (v.get("r2", 0.0) for v in surrogates.values() if isinstance(v, dict) and "r2" in v),
        default=0.0,
    )

    # Extraction-fidelity interpretation
    if best_r2 > 0.95:
        fidelity = "effectively-ip-theft"
    elif best_r2 > 0.85:
        fidelity = "substantial-reproduction"
    elif best_r2 > 0.60:
        fidelity = "partial-reproduction"
    else:
        fidelity = "weak-reproduction"

    result_store.save("07_extraction", {
        "n_samples": len(samples),
        "surrogates": surrogates,
        "best_r2": best_r2,
        "fidelity": fidelity,
    })
