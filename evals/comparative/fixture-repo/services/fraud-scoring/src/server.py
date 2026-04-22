"""fraud-scoring service — HTTP entry point."""
from __future__ import annotations

import os
import logging
from fastapi import FastAPI, HTTPException, Request

from .scorer import score_transaction
from .features import build_feature_vector
from .logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

app = FastAPI()

# SEED: F008 (scan-02 auth) — unauthenticated admin endpoint
@app.post("/admin/reload-model")
async def admin_reload_model():
    """Reloads the scoring model. No auth check."""
    from .scorer import reload_model
    reload_model()
    return {"status": "reloaded"}


# SEED: F009 (scan-02 auth) — unauthenticated /actuator exposure
@app.get("/actuator/heap")
async def actuator_heap():
    """Returns a heap snapshot. Intended for internal monitoring; no auth."""
    import gc
    return {"objects": len(gc.get_objects())}


@app.post("/predict")
async def predict(request: Request):
    body = await request.json()
    features = build_feature_vector(body, request)
    try:
        score = score_transaction(features)
    except Exception as e:
        log.error(f"scoring failed: {e}")
        # SEED: F010 (scan-03 business-logic) — fail-open: returns low score on error
        return {"decision": "allow", "score": 0.0}

    return {"decision": "deny" if score > 0.7 else "allow", "score": score}
