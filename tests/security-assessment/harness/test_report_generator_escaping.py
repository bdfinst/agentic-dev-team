"""Regression test for HTML/Markdown injection in
probes/08_report_generator.py.

`_format_*()` interpolate fields from probe result dicts — which ultimately
originate from the probed model's own HTTP responses (an attacker-controlled
service under test) — directly into the generated `adversarial-report.md`.
That Markdown is later rendered to HTML/PDF (see
plugins/security-assessment/commands/export-pdf.md, python-markdown +
weasyprint), and python-markdown passes raw embedded HTML through
unmodified. A malicious model response value (e.g. an inferred-framework
string, a feature name, a doc path) can therefore inject arbitrary HTML/
script markup into the rendered report — a plausible HTML injection -> SSRF
vector, since weasyprint fetches remote resources referenced in rendered
HTML/CSS by default.

This test proves a crafted probed-model response value can no longer break
out of the Markdown/HTML context unescaped.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS = REPO_ROOT / "plugins" / "security-assessment" / "harness"

os.environ.setdefault("TARGET_URL", "http://127.0.0.1:8000")
sys.path.insert(0, str(HARNESS))

from redteam import orchestrator  # noqa: E402  (path set above)

report_generator = orchestrator._import_agent("08_report_generator.py")

PAYLOAD = '"><script>alert(document.cookie)</script>'


def _assert_escaped(rendered: str) -> None:
    assert "<script>alert(document.cookie)</script>" not in rendered
    assert "&lt;script&gt;alert(document.cookie)&lt;/script&gt;" in rendered


def test_recon_target_and_framework_are_escaped():
    recon = {
        "target": PAYLOAD,
        "inferred_framework": PAYLOAD,
        "doc_paths": [{"status": 200, "path": PAYLOAD, "content_type": PAYLOAD}],
        "method_matrix": {PAYLOAD: {"status": 200}},
    }
    _assert_escaped(report_generator._format_recon(recon))


def test_schema_categories_and_features_are_escaped():
    schema = {
        "strategy_used": PAYLOAD,
        "features": [PAYLOAD],
        "by_category": {PAYLOAD: [PAYLOAD]},
    }
    _assert_escaped(report_generator._format_schema(schema))


def test_sensitivity_feature_names_are_escaped():
    sens = {
        "baseline_score": 0.5,
        "rankings": [{"feature": PAYLOAD, "sensitivity": 0.123}],
    }
    _assert_escaped(report_generator._format_sensitivity(sens))


def test_boundaries_feature_and_reason_are_escaped():
    boundaries = {
        "boundaries": [
            {"feature": PAYLOAD, "boundary": None, "reason": PAYLOAD},
        ]
    }
    _assert_escaped(report_generator._format_boundaries(boundaries))


def test_evasion_methods_are_escaped():
    evasion = {
        "score_target": 0.4,
        "results": [{"method": PAYLOAD, "score": 0.1}],
    }
    _assert_escaped(report_generator._format_evasion(evasion))


def test_extraction_surrogate_names_and_fidelity_are_escaped():
    extraction = {
        "n_samples": 10,
        "best_r2": 0.9,
        "fidelity": PAYLOAD,
        "surrogates": {PAYLOAD: {"r2": 0.5}},
    }
    _assert_escaped(report_generator._format_extraction(extraction))
