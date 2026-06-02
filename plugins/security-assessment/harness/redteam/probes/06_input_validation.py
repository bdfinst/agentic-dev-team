"""06_input_validation — exercise malformed inputs.

Type confusion, nulls, oversized strings, Unicode edge cases, NaN/Infinity.
Detects fail-open paths and information leakage via error messages.

Produces: results/06_validation.json
"""
from __future__ import annotations

import math
from typing import Any

from ..lib import http_client, result_store, scoring


MALFORMED_CASES: list[tuple[str, Any]] = [
    ("empty_body", {}),
    ("null_everywhere", None),
    ("type_confusion_str_for_numeric", "not-a-number"),
    ("type_confusion_bool_for_numeric", True),
    ("type_confusion_array_for_object", []),
    ("oversized_string", "A" * 10_000),
    ("nested_deeply", {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}),
    ("unicode_rtl_override", "\u202Efraud"),
    ("null_bytes", "a\u0000b"),
    ("nan_value", float("nan")),
    ("infinity_value", float("inf")),
    ("scientific_notation_huge", 1e300),
    ("negative_zero", -0.0),
    ("empty_string_on_required", ""),
    ("very_long_feature_name", {"x" * 1000: 1.0}),
]


def run() -> None:
    features = result_store.get_discovered_features() or []
    findings: list[dict] = []

    for case_name, payload in MALFORMED_CASES:
        # Need a payload the predict endpoint will accept in shape; some cases
        # replace the entire payload, others slot into a baseline.
        if case_name in ("null_everywhere", "type_confusion_str_for_numeric",
                        "type_confusion_bool_for_numeric", "type_confusion_array_for_object",
                        "oversized_string"):
            # Merge: replace one of the features with the malformed value
            final = scoring.build_baseline_payload(features) if features else {}
            if features:
                final[features[0]] = payload
            else:
                final = {"input": payload} if payload is not None else None
        elif case_name == "very_long_feature_name":
            final = payload
        else:
            final = payload

        try:
            import json as _json
            # Some cases produce non-JSON-serializable values (NaN/Infinity).
            # httpx rejects these silently via requests.json; intercept.
            _json.dumps(final, allow_nan=False)
        except (ValueError, TypeError):
            findings.append({
                "case": case_name,
                "status": None,
                "note": "payload non-JSON-serializable; server never saw it",
            })
            continue

        resp = http_client.client.post_predict(final)  # type: ignore[arg-type]
        if resp is None:
            findings.append({"case": case_name, "status": None, "note": "no response"})
            continue

        text = resp.text if hasattr(resp, "text") else ""
        findings.append({
            "case": case_name,
            "status": resp.status_code,
            "body_preview": text[:512],
            "fail_open": resp.status_code == 200 and (scoring.extract_score(resp) or 1.0) < 0.5,
            "information_leakage": any(
                marker in text.lower()
                for marker in ("traceback", "stack trace", "internal error", "sqlalchemy", "psycopg", "at line")
            ),
        })

    # Summary
    fail_open_count = sum(1 for f in findings if f.get("fail_open"))
    leak_count = sum(1 for f in findings if f.get("information_leakage"))

    result_store.save("06_validation", {
        "summary": {
            "total_cases": len(findings),
            "fail_open_count": fail_open_count,
            "information_leakage_count": leak_count,
        },
        "findings": findings,
    })
