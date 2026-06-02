"""08_report_generator — compile probe outputs into adversarial-report.md.

The report is consumed by prompt adversarial-05-report (the red-team-report-
generator Claude agent) for refinement into executive form. This script
produces the raw, machine-friendly content; interpretation happens downstream.

Produces: results/08_report.json  AND  results/adversarial-report.md
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import config
from ..lib import result_store


def _load_or_empty(name: str) -> dict:
    try:
        return result_store.load(name)
    except FileNotFoundError:
        return {"_missing": True, "_probe": name}


def _format_recon(recon: dict) -> str:
    lines = ["## Probe 01 — API Recon\n"]
    lines.append(f"- **Target**: `{recon.get('target', 'unknown')}`")
    lines.append(f"- **Inferred framework**: {recon.get('inferred_framework')}")
    visible_doc = [p for p in recon.get("doc_paths", []) if p.get("status") == 200]
    lines.append(f"- **Documentation paths exposed**: {len(visible_doc)}")
    for p in visible_doc[:5]:
        lines.append(f"  - `{p['path']}` ({p.get('content_type', 'unknown')})")
    if recon.get("method_matrix"):
        accepted_verbs = [m for m, d in recon["method_matrix"].items() if d.get("status", 500) < 400]
        lines.append(f"- **HTTP verbs accepted on predict endpoint**: {', '.join(accepted_verbs) or 'none'}")
    return "\n".join(lines) + "\n"


def _format_schema(schema: dict) -> str:
    lines = ["## Probe 02 — Schema Discovery\n"]
    lines.append(f"- **Discovery strategy**: {schema.get('strategy_used', 'none succeeded')}")
    feats = schema.get("features", [])
    lines.append(f"- **Features discovered**: {len(feats)}")
    for category, group in (schema.get("by_category") or {}).items():
        lines.append(f"  - **{category}**: {', '.join(group)}")
    return "\n".join(lines) + "\n"


def _format_sensitivity(sens: dict) -> str:
    lines = ["## Probe 03 — Feature Sensitivity\n"]
    lines.append(f"- **Baseline score**: {sens.get('baseline_score')}")
    lines.append("- **Top 5 most-influential features**:")
    for r in (sens.get("rankings") or [])[:5]:
        lines.append(f"  - `{r['feature']}` (sensitivity {r['sensitivity']:.3f})")
    return "\n".join(lines) + "\n"


def _format_boundaries(boundaries: dict) -> str:
    lines = ["## Probe 04 — Boundary Mapping\n"]
    for b in boundaries.get("boundaries", []):
        if b.get("boundary") is not None:
            lines.append(f"- `{b['feature']}`: boundary at {b['boundary']:.3f}")
        else:
            lines.append(f"- `{b['feature']}`: no boundary ({b.get('reason')})")
    return "\n".join(lines) + "\n"


def _format_evasion(evasion: dict) -> str:
    lines = ["## Probe 05 — Evasion\n"]
    lines.append(f"- **Score target**: < {evasion.get('score_target', 0.4)}")
    results = evasion.get("results") or []
    methods_used = sorted({r.get("method") for r in results})
    lines.append(f"- **Methods that found adversarials**: {', '.join(m for m in methods_used if m) or 'none'}")
    lines.append(f"- **Lowest score achieved**: "
                 f"{min((r['score'] for r in results if isinstance(r.get('score'), (int, float))), default='n/a')}")
    return "\n".join(lines) + "\n"


def _format_validation(validation: dict) -> str:
    lines = ["## Probe 06 — Input Validation\n"]
    summary = validation.get("summary") or {}
    lines.append(f"- **Cases tested**: {summary.get('total_cases', 0)}")
    lines.append(f"- **Fail-open cases**: {summary.get('fail_open_count', 0)}")
    lines.append(f"- **Information-leakage cases**: {summary.get('information_leakage_count', 0)}")
    return "\n".join(lines) + "\n"


def _format_extraction(extraction: dict) -> str:
    lines = ["## Probe 07 — Model Extraction\n"]
    lines.append(f"- **Samples collected**: {extraction.get('n_samples', 0)}")
    lines.append(f"- **Best R²**: {extraction.get('best_r2', 0.0):.3f}")
    lines.append(f"- **Fidelity**: {extraction.get('fidelity', 'unknown')}")
    surrogates = extraction.get("surrogates") or {}
    for name, stats in surrogates.items():
        if isinstance(stats, dict) and "r2" in stats:
            lines.append(f"  - {name}: R² = {stats['r2']:.3f}")
    return "\n".join(lines) + "\n"


def run() -> None:
    recon = _load_or_empty("01_recon")
    schema = _load_or_empty("02_schema")
    sens = _load_or_empty("03_sensitivity")
    boundaries = _load_or_empty("04_boundaries")
    evasion = _load_or_empty("05_evasion")
    validation = _load_or_empty("06_validation")
    extraction = _load_or_empty("07_extraction")

    # JSON artifact (machine-friendly; consumed by adversarial-05-report prompt)
    report = {
        "target": config.TARGET_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "probes": {
            "01_recon": recon,
            "02_schema": schema,
            "03_sensitivity": sens,
            "04_boundaries": boundaries,
            "05_evasion": evasion,
            "06_validation": validation,
            "07_extraction": extraction,
        },
    }
    result_store.save("08_report", report)

    # Markdown report (human-readable; refined in place by the analyst agent)
    md_lines = [
        f"# Adversarial ML Red-Team Report",
        "",
        f"**Target**: `{config.TARGET_URL}`  ",
        f"**Generated**: {report['generated_at']}",
        "",
        "> This report is the machine-generated output of the red-team harness.",
        "> The `red-team-report-generator` agent (prompt adversarial-05) refines",
        "> this file in place into the final executive-ready form.",
        "",
    ]
    md_lines.append(_format_recon(recon))
    md_lines.append(_format_schema(schema))
    md_lines.append(_format_sensitivity(sens))
    md_lines.append(_format_boundaries(boundaries))
    md_lines.append(_format_evasion(evasion))
    md_lines.append(_format_validation(validation))
    md_lines.append(_format_extraction(extraction))

    md_path = config.RESULTS_DIR / "adversarial-report.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with md_path.open("w") as f:
        f.write("\n".join(md_lines))
