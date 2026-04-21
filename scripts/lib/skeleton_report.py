#!/usr/bin/env python3
"""skeleton_report — assemble a markdown assessment report from deterministic artifacts.

Reads the recon JSON, findings JSONL, and optional service-comm Mermaid
diagram produced by scripts/run-assessment-local.sh, then writes a
report.md with severity-sorted finding tables and an appendix.

This is a *skeleton* — it has no narrative prose, no LLM-generated exec
summary, no compliance mapping, and no FP reduction. It provides the
structural frame that the full /security-assessment pipeline's
exec-report-generator agent would fill in.

Usage:
    python3 scripts/lib/skeleton_report.py \\
        --recon <recon.json> \\
        --findings <findings.jsonl> \\
        [--service-comm <mermaid-file>] \\
        [--shared-creds <sarif>] \\
        --output <report.md>
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


SEVERITY_ORDER = ["error", "warning", "suggestion", "info"]
PRESENTATIONAL_MAP = {
    "error": "HIGH",       # skeleton default — real pipeline maps with exploitability
    "warning": "MEDIUM",
    "suggestion": "LOW",
    "info": "LOW",
}


def load_findings(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_recon(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def render_report(
    recon: dict,
    findings: list[dict],
    service_comm_path: Path | None,
    shared_creds_path: Path | None,
) -> str:
    target_name = recon.get("repo", {}).get("name", "target")
    generated_at = recon.get("generated_at", "unknown")

    lines: list[str] = []
    lines.append(f"# Security Assessment — {target_name}")
    lines.append("")
    lines.append(f"**Generated**: {generated_at}")
    lines.append("")
    lines.append("> This is a **deterministic-only skeleton report** produced by")
    lines.append("> `scripts/run-assessment-local.sh`. The full `/security-assessment`")
    lines.append("> pipeline adds LLM-driven sections (exec summary narrative, FP reduction,")
    lines.append("> compliance mapping, business-logic analysis, remediation prose). Those")
    lines.append("> sections are marked `[LLM-SKIPPED]` below.")
    lines.append("")
    lines.append("> This compliance mapping is informational and derived from pattern matching.")
    lines.append("> It does not constitute a certified audit and should not be used as a")
    lines.append("> substitute for formal compliance review.")
    lines.append("")

    # ── Section 0 — Executive Summary ──────────────────────────────────────
    lines.append("## Section 0 — Executive Summary")
    lines.append("")
    by_pres = defaultdict(int)
    for f in findings:
        pres = PRESENTATIONAL_MAP.get(f.get("severity", "warning"), "MEDIUM")
        by_pres[pres] += 1
    lines.append(f"- **Findings summary**: CRITICAL: 0  HIGH: {by_pres['HIGH']}  MEDIUM: {by_pres['MEDIUM']}  LOW: {by_pres['LOW']}")
    lines.append(f"- **Languages detected**: " + ", ".join(l.get("name", "?") for l in recon.get("languages", [])[:5]) or "none")
    ep_count = len(recon.get("entry_points", []))
    lines.append(f"- **Entry points identified**: {ep_count}")
    lines.append("")
    lines.append("**Top 3 Actions**: [LLM-SKIPPED — requires exec-report-generator agent]")
    lines.append("")

    # ── Section 1 — Findings Dashboard ────────────────────────────────────
    lines.append("## Section 1 — Findings Dashboard")
    lines.append("")
    if not findings:
        lines.append("_No findings emitted. Either the target is clean or deterministic tools were unavailable._")
        lines.append("")
    else:
        lines.append("| ID | Rule | File | Line | Severity | Presentational | Source |")
        lines.append("|---|---|---|---|---|---|---|")
        # Sort by severity then by rule_id
        sorted_findings = sorted(
            findings,
            key=lambda f: (SEVERITY_ORDER.index(f.get("severity", "warning"))
                           if f.get("severity") in SEVERITY_ORDER else 99,
                           f.get("rule_id", "")),
        )
        for i, f in enumerate(sorted_findings, start=1):
            rule = f.get("rule_id", "?")
            file_ = f.get("file", "?")
            line = f.get("line", "?")
            sev = f.get("severity", "?")
            pres = PRESENTATIONAL_MAP.get(sev, "?")
            source = f.get("metadata", {}).get("source", "?")
            lines.append(f"| F{i:03d} | `{rule}` | `{file_}` | {line} | {sev} | {pres} | {source} |")
        lines.append("")

    # ── Section 2 — Critical & High Findings (detailed) ───────────────────
    lines.append("## Section 2 — Critical & High Findings")
    lines.append("")
    high_findings = [f for f in findings if PRESENTATIONAL_MAP.get(f.get("severity", ""), "") in ("CRITICAL", "HIGH")]
    if not high_findings:
        lines.append("_No findings at HIGH or CRITICAL severity._")
        lines.append("")
    else:
        for i, f in enumerate(high_findings, start=1):
            lines.append(f"### F{i:03d} — {f.get('rule_id', 'unnamed')}")
            lines.append("")
            lines.append(f"- **Location**: `{f.get('file', '?')}:{f.get('line', '?')}`")
            lines.append(f"- **Severity**: {f.get('severity', '?')} → {PRESENTATIONAL_MAP.get(f.get('severity', ''), '?')} presentational")
            lines.append(f"- **Source**: {f.get('metadata', {}).get('source', '?')}")
            if f.get("cwe"):
                lines.append(f"- **CWE**: {', '.join(f['cwe'])}")
            if f.get("owasp"):
                lines.append(f"- **OWASP**: {', '.join(f['owasp'])}")
            lines.append(f"- **Message**: {f.get('message', '(none)')}")
            lines.append(f"- **Attack scenario**: [LLM-SKIPPED]")
            lines.append(f"- **Remediation**: [LLM-SKIPPED]")
            lines.append("")

    # ── Section 3 — Medium & Low Findings (condensed) ─────────────────────
    lines.append("## Section 3 — Medium & Low Findings")
    lines.append("")
    low_findings = [f for f in findings if PRESENTATIONAL_MAP.get(f.get("severity", ""), "") in ("MEDIUM", "LOW")]
    if not low_findings:
        lines.append("_No findings at MEDIUM or LOW severity._")
        lines.append("")
    else:
        for f in low_findings:
            sev = PRESENTATIONAL_MAP.get(f.get("severity", ""), "?")
            lines.append(f"- **[{sev}]** `{f.get('rule_id', '?')}` at `{f.get('file', '?')}:{f.get('line', '?')}` — {f.get('message', '')[:120]}")
        lines.append("")

    # ── Section 4 — Service Communication Diagram ─────────────────────────
    lines.append("## Section 4 — Service Communication")
    lines.append("")
    if service_comm_path and service_comm_path.exists():
        lines.append(service_comm_path.read_text().rstrip())
        lines.append("")
    else:
        lines.append("_Service-communication diagram not generated (single-target run, or tool absent)._")
        lines.append("")

    # ── Section 5 — Cross-repo findings (if any) ──────────────────────────
    lines.append("## Section 5 — Cross-Repository Findings")
    lines.append("")
    if shared_creds_path and shared_creds_path.exists():
        try:
            with shared_creds_path.open() as f:
                doc = json.load(f)
            results = sum(len(r.get("results", [])) for r in doc.get("runs", []))
            lines.append(f"- **Shared credentials detected**: {results} occurrence(s) across repos (see `{shared_creds_path}` for SARIF)")
        except (json.JSONDecodeError, OSError):
            lines.append("_Shared-credentials SARIF unparseable._")
    else:
        lines.append("_Not applicable — single-target run or cross-cred script skipped._")
    lines.append("")
    lines.append("_Attack chains and systemic patterns: [LLM-SKIPPED — requires cross-repo-synthesizer agent]_")
    lines.append("")

    # ── Section 6 — Methodology & Scope ───────────────────────────────────
    lines.append("## Section 6 — Methodology & Scope")
    lines.append("")
    lines.append("**Deterministic-only skeleton pipeline:**")
    lines.append("")
    lines.append("- Codebase reconnaissance via `scripts/lib/deterministic_recon.py` (grep-based)")
    lines.append("- Custom SARIF-emitting scripts: `entropy-check`, `model-hash-verify`")
    lines.append("- Custom semgrep rulesets: `ml-patterns`, `llm-safety`, `fraud-domain`, `crypto-anti-patterns`")
    lines.append("- Community bundles: `p/security-audit`, `p/secrets`, `p/owasp-top-ten`")
    lines.append("- Tier-1 tools (where installed): semgrep, gitleaks, trivy, hadolint, actionlint")
    lines.append("- Custom cross-repo scripts: `service-comm-parser`, `shared-cred-hash-match`")
    lines.append("")
    lines.append("**Skipped (needs full `/security-assessment` or plugin install):**")
    lines.append("")
    lines.append("- LLM judgment agents: `security-review`, `business-logic-domain-review`, `tool-finding-narrative-annotator`, `compliance-edge-annotator`")
    lines.append("- 5-stage FP reduction")
    lines.append("- Compliance mapping with edge-case LLM annotation")
    lines.append("- Executive summary narrative, attack scenarios, and remediation prose")
    lines.append("")

    # ── Appendices ─────────────────────────────────────────────────────────
    lines.append("## Section 7 — Appendices")
    lines.append("")
    lines.append("### Appendix A — RECON artifact summary")
    lines.append("")
    lines.append(f"- **Package manager**: {recon.get('repo', {}).get('package_manager', '?')}")
    lines.append(f"- **Monorepo**: {recon.get('repo', {}).get('monorepo', False)}")
    lines.append(f"- **Workspaces**: {recon.get('repo', {}).get('workspaces', [])}")
    lines.append(f"- **Entry points**: {len(recon.get('entry_points', []))}")
    sec = recon.get("security_surface", {})
    lines.append(f"- **Auth paths**: {len(sec.get('auth_paths', []))}")
    lines.append(f"- **Network egress callers**: {len(sec.get('network_egress', []))}")
    lines.append(f"- **Secret references**: {len(sec.get('secrets_referenced', []))}")
    lines.append(f"- **Crypto calls**: {len(sec.get('crypto_calls', []))}")
    lines.append(f"- **ML models loaded**: {len(sec.get('ml_models_loaded', []))}")
    lines.append("")
    lines.append("Full RECON JSON available as companion artifact.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recon", type=Path, required=True)
    p.add_argument("--findings", type=Path, required=True)
    p.add_argument("--service-comm", type=Path)
    p.add_argument("--shared-creds", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    if not args.recon.exists():
        print(f"error: recon not found: {args.recon}", file=sys.stderr)
        return 2
    if not args.findings.exists():
        print(f"error: findings not found: {args.findings}", file=sys.stderr)
        return 2

    recon = load_recon(args.recon)
    findings = load_findings(args.findings)

    report = render_report(recon, findings, args.service_comm, args.shared_creds)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
