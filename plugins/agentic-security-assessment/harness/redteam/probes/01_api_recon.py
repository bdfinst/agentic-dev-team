"""01_api_recon — probe documentation paths, HTTP methods, content types, server headers.

Captures what the API leaks before any knowledge of the schema. Output is
consumed by probe 02 (schema discovery) to pick the right feature-discovery
strategy, and by prompt adversarial-01-recon for interpretation.

Produces: results/01_recon.json
"""
from __future__ import annotations

from .. import config
from ..lib import http_client, result_store


DOC_PATHS = [
    "/openapi.json", "/openapi.yaml", "/swagger.json", "/swagger-ui.html",
    "/docs", "/redoc", "/api-docs", "/v2/api-docs", "/v3/api-docs",
]
STANDARD_PATHS = [
    "/metrics", "/version", "/info", "/health", "/status",
    "/actuator", "/actuator/info", "/actuator/metrics",
]
METHOD_PROBES = ["GET", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"]


def _probe_path(path: str) -> dict:
    url = config.TARGET_URL + path
    resp = http_client.client.get(url)
    if resp is None:
        return {"path": path, "status": None, "note": "no-response"}
    ct = resp.headers.get("content-type", "")
    # Cap body preview at 2KB
    body_preview = (resp.text or "")[:2048] if ct.startswith("application/json") or ct.startswith("text/") else ""
    return {
        "path": path,
        "status": resp.status_code,
        "content_type": ct,
        "headers": {k: v for k, v in resp.headers.items() if k.lower() in {"server", "x-powered-by", "x-frame-options", "strict-transport-security", "content-security-policy"}},
        "body_preview": body_preview,
    }


def run() -> None:
    findings: dict = {
        "target": config.TARGET_URL,
        "doc_paths": [_probe_path(p) for p in DOC_PATHS],
        "standard_paths": [_probe_path(p) for p in STANDARD_PATHS],
        "method_matrix": {},
        "inferred_framework": None,
    }

    # Method matrix on the predict endpoint — what verbs does the server accept?
    predict_path = config.MODEL_ENDPOINT
    for method in METHOD_PROBES:
        url = config.TARGET_URL + predict_path
        resp = http_client.client.probe(url, method=method)
        findings["method_matrix"][method] = {
            "status": resp.status_code if resp else None,
            "allow_header": resp.headers.get("allow") if resp else None,
        }

    # Crude framework inference from server header or body markers
    for doc in findings["doc_paths"]:
        body = (doc.get("body_preview") or "").lower()
        if "openapi" in body and "paths" in body:
            findings["inferred_framework"] = "openapi-exposed"
            break
        if "swagger" in body:
            findings["inferred_framework"] = "swagger-exposed"
            break
    if not findings["inferred_framework"]:
        servers = {(p.get("headers") or {}).get("server", "") for p in findings["doc_paths"] + findings["standard_paths"]}
        servers.discard("")
        if servers:
            findings["inferred_framework"] = f"server-header: {sorted(servers)[0]}"

    result_store.save("01_recon", findings)
