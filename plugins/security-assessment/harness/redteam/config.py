"""config — red-team harness runtime configuration.

All settings can be overridden via environment variables. Names match the
opus_repo_scan_test reference for operator muscle memory.

Required:
    TARGET_URL         Base URL of the model service (no trailing slash)

Optional:
    MODEL_ENDPOINT     Path appended to TARGET_URL          default: /1_0/predict
    RATE_LIMIT         Max requests per second              default: 5
    REQUEST_TIMEOUT    Per-request timeout (seconds)        default: 30
    QUERY_BUDGET       Total cross-probe budget             default: 10000
    MAX_RETRIES        Retries on 5xx/timeout/conn-error    default: 3
    REDTEAM_AUTHORIZED Set to "1" by the /redteam-model     (internal use)
                       wrapper after scope/consent checks.
                       Harness refuses to run if unset.

Derived URLs:
    PREDICT_URL = TARGET_URL + MODEL_ENDPOINT
    PAYLOAD_URL = TARGET_URL + "/payload"
    VERSION_URL = TARGET_URL + "/version"

Paths:
    BASE_DIR      resolves to this file's directory
    RESULTS_DIR   BASE_DIR / "results"
    AUDIT_LOG     RESULTS_DIR / "audit_log.jsonl"
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Environment variables ─────────────────────────────────────────────────────

TARGET_URL: str = os.environ.get("TARGET_URL", "").rstrip("/")
MODEL_ENDPOINT: str = os.environ.get("MODEL_ENDPOINT", "/1_0/predict")
RATE_LIMIT: float = float(os.environ.get("RATE_LIMIT", "5"))
REQUEST_TIMEOUT: float = float(os.environ.get("REQUEST_TIMEOUT", "30"))
QUERY_BUDGET: int = int(os.environ.get("QUERY_BUDGET", "10000"))
MAX_RETRIES: int = int(os.environ.get("MAX_RETRIES", "3"))

# ── Derived URLs ──────────────────────────────────────────────────────────────

def _join(base: str, path: str) -> str:
    if not base:
        return ""
    return base + (path if path.startswith("/") else "/" + path)


PREDICT_URL: str = _join(TARGET_URL, MODEL_ENDPOINT)
PAYLOAD_URL: str = _join(TARGET_URL, "/payload")
VERSION_URL: str = _join(TARGET_URL, "/version")

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR: Path = Path(__file__).resolve().parent
RESULTS_DIR: Path = BASE_DIR / "results"
AUDIT_LOG: Path = RESULTS_DIR / "audit_log.jsonl"
PROGRESS_MANIFEST: Path = RESULTS_DIR / "progress-manifest.json"


def validate() -> None:
    """Raise ValueError with a specific message if the config is unusable."""
    if not TARGET_URL:
        raise ValueError(
            "TARGET_URL is not set. Export TARGET_URL before running the harness."
        )
    if RATE_LIMIT <= 0:
        raise ValueError(f"RATE_LIMIT must be positive (got {RATE_LIMIT}).")
    if QUERY_BUDGET <= 0:
        raise ValueError(f"QUERY_BUDGET must be positive (got {QUERY_BUDGET}).")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
