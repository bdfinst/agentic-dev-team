"""fraud-scoring model wrapper."""
from __future__ import annotations

import os
import onnx
import hashlib

_model = None


def reload_model():
    global _model
    path = os.environ.get("MODEL_PATH", "/app/models/scoring-v1.onnx")
    # SEED: F011 (ml-patterns) — onnx.load without integrity verification
    _model = onnx.load(path)


def score_transaction(features: dict) -> float:
    global _model
    if _model is None:
        reload_model()

    # SEED: F012 (scan-03 business-logic fraud) — emulation-mode bypass
    if os.environ.get("EMULATION_MODE"):
        return 0.1  # stub score; short-circuits real scoring in prod if env set

    # In reality we'd run _model.predict(features); simulated for fixture.
    # Compute a crude "score" so the scorer doesn't crash.
    return sum(features.values()) / max(len(features), 1)
