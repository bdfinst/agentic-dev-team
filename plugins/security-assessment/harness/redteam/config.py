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
    SELF_CERTIFY_OWNED Path to a self-cert authorization    (internal use)
                       artifact. Required by validate() when
                       TARGET_URL does not resolve to a
                       self-owned CIDR (see lib/scope_check.py).

Derived URLs:
    PREDICT_URL = TARGET_URL + MODEL_ENDPOINT
    PAYLOAD_URL = TARGET_URL + "/payload"
    VERSION_URL = TARGET_URL + "/version"

Paths:
    BASE_DIR      resolves to this file's directory
    RESULTS_DIR   BASE_DIR / "results"
    AUDIT_LOG     RESULTS_DIR / "audit_log.jsonl"

Scope enforcement:
    validate() is the harness's single config-validation entrypoint, and
    orchestrator.py's main() calls it before running any probe against
    TARGET_URL. validate() calls lib.scope_check.is_self_owned(TARGET_URL)
    and refuses (raises ValueError) unless the target resolves to a
    self-owned CIDR OR SELF_CERTIFY_OWNED points at a readable artifact —
    this is the actual safety boundary; REDTEAM_AUTHORIZED alone is not
    sufficient to reach a live probe run.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .lib import scope_check

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


def _log_self_cert(target_url: str, artifact_path: str, artifact_sha256: str) -> None:
    """Append the self-cert audit trail entry documented in
    knowledge/redteam-authorization.md. Best-effort: a logging failure must
    not be the reason a legitimate, already-authorized run is blocked."""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": "self_cert",
        "target": target_url,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
    }
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _enforce_scope() -> None:
    """Refuse to proceed unless TARGET_URL is self-owned or a verified
    self-cert artifact is present. This is the harness's actual safety
    boundary — see the module docstring's "Scope enforcement" section."""
    accepted, reason = scope_check.is_self_owned(TARGET_URL)
    if accepted:
        return

    cert_path = os.environ.get("SELF_CERTIFY_OWNED", "").strip()
    if not cert_path:
        raise ValueError(scope_check.refusal_message(TARGET_URL, reason))

    try:
        artifact_sha256 = scope_check.hash_artifact(cert_path)
    except FileNotFoundError as e:
        raise ValueError(str(e)) from e

    _log_self_cert(TARGET_URL, cert_path, artifact_sha256)


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
    _enforce_scope()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
