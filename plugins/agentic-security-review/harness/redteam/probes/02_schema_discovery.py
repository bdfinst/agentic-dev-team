"""02_schema_discovery — discover the model's input feature list.

Four-strategy cascade per the opus_repo_scan_test reference:
  1. OpenAPI directly (fetch /openapi.json, parse schema)
  2. /payload endpoint (some ML services expose the expected shape)
  3. Error-message mining (POST empty body; harvest field names from errors)
  4. Brute force against lib.feature_dict (try each feature individually)

Records which strategy succeeded so probe 03 knows whether it is working from
an authoritative schema or a best-effort reconstruction.

Produces: results/02_schema.json  (shape: {features: [...], strategy_used: "..."})
"""
from __future__ import annotations

import json
import re
from typing import Any

from .. import config
from ..lib import http_client, result_store, feature_dict


def _try_openapi() -> list[str]:
    """Strategy 1: fetch OpenAPI spec and parse the predict endpoint's schema."""
    for path in ("/openapi.json", "/swagger.json", "/v3/api-docs"):
        url = config.TARGET_URL + path
        resp = http_client.client.get(url)
        if resp is None or resp.status_code != 200:
            continue
        try:
            spec = resp.json()
        except json.JSONDecodeError:
            continue
        # Look for the predict path's request body schema
        paths = spec.get("paths", {})
        for path_key, ops in paths.items():
            if config.MODEL_ENDPOINT.rstrip("/") in path_key:
                for _method, op in ops.items():
                    if not isinstance(op, dict):
                        continue
                    rb = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
                    if rb.get("type") == "object":
                        return list((rb.get("properties") or {}).keys())
    return []


def _try_payload_endpoint() -> list[str]:
    """Strategy 2: GET /payload or /payload-sample, harvest keys."""
    for path in (config.PAYLOAD_URL, config.TARGET_URL + "/payload-sample", config.TARGET_URL + "/sample"):
        if not path:
            continue
        resp = http_client.client.get(path)
        if resp is None or resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return list(data.keys())
    return []


FIELD_NAME_PATTERN = re.compile(
    r"(?:missing|required|unknown|not found|invalid)\b[^'\"]*['\"]?([a-z][a-zA-Z0-9_]{1,60})"
)


def _try_error_mining() -> list[str]:
    """Strategy 3: POST an empty body; parse error-response field names."""
    resp = http_client.client.post_predict({})
    if resp is None:
        return []
    text = resp.text if hasattr(resp, "text") else ""
    # Look for field names mentioned in error messages
    matches = FIELD_NAME_PATTERN.findall(text)
    unique = []
    seen: set[str] = set()
    for m in matches:
        lower = m.lower()
        if lower not in seen and lower not in {"true", "false", "null", "body", "request", "required", "missing"}:
            seen.add(lower)
            unique.append(m)
    return unique


def _try_brute_force() -> list[str]:
    """Strategy 4: brute-force against the feature_dict. Try each feature
    individually; retain features that change the response vs. an empty body.

    Budget-conscious: limit to top 30 features from the dict; skip the rest.
    """
    baseline = http_client.client.post_predict({})
    if baseline is None:
        return []
    baseline_body = baseline.text if hasattr(baseline, "text") else ""

    retained: list[str] = []
    candidates = feature_dict.all_features()[:30]
    for feat in candidates:
        resp = http_client.client.post_predict({feat: 0.5})
        if resp is None:
            continue
        body = resp.text if hasattr(resp, "text") else ""
        if resp.status_code != baseline.status_code or body != baseline_body:
            retained.append(feat)
    return retained


def run() -> None:
    result: dict[str, Any] = {"features": [], "strategy_used": None}

    for strategy_name, fn in (
        ("openapi", _try_openapi),
        ("payload_endpoint", _try_payload_endpoint),
        ("error_mining", _try_error_mining),
        ("brute_force", _try_brute_force),
    ):
        features = fn()
        if features:
            result["features"] = features
            result["strategy_used"] = strategy_name
            break

    # Categorize discovered features using feature_dict
    if result["features"]:
        by_category: dict[str, list[str]] = {}
        for f in result["features"]:
            cat = feature_dict.category_for(f) or "unknown"
            by_category.setdefault(cat, []).append(f)
        result["by_category"] = by_category

    result_store.save("02_schema", result)
