#!/usr/bin/env python3
"""apply_severity_floors — deterministic Phase 2b severity calibration.

Reads a disposition register produced by fp-reduction, applies domain-class
severity floors to each entry based on rule_id pattern matching, rewrites
the register with updated exploitability.score (floor-applied if higher than
mechanical) and exploitability.rationale (annotated with the floor class).

Handles both the schema-conformant nested shape (entry.finding.rule_id) and
the flat shape (entry.rule_id) defensively. Never downgrades — final
exploitability is max(mechanical, floor).

Also records every floor application to an audit log for maintainability.

Usage:
    python3 apply_severity_floors.py \\
        --disposition memory/disposition-<slug>.json \\
        [--audit-log-out memory/severity-floors-log-<slug>.jsonl]
        [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FloorRule:
    """A rule_id → severity floor mapping with optional path gating."""
    pattern: re.Pattern[str]              # rule_id regex
    floor: int                            # 0..10
    class_name: str                       # e.g. "pii-class", "weak-crypto"
    rationale: str                        # cited when floor applied
    path_gate: re.Pattern[str] | None = None   # optional: only apply if file path matches


# ── Floor rules ──────────────────────────────────────────────────────────────
#
# Tuned against the comparative-testing fixture data. Each regex matches the
# FULL rule_id (after unified-finding normalization). Ordered by specificity
# — path-gated / narrow rules before broad ones.
#
FLOOR_RULES: list[FloorRule] = [
    # PII in logs / responses — compliance-grade CRITICAL by presence
    FloorRule(
        pattern=re.compile(r"^(?:.+[.])?(?:pii[_.-]?log|pan[_.-]?at[_.-]?log|pii[_.-]?in[_.-]?response|pii[_.-]?(?:general|flow))\b", re.IGNORECASE),
        floor=7,
        class_name="pii-class",
        rationale="PCI-DSS §3.4 / §10.2 and GDPR Art 32 violations by mere presence",
    ),
    # TLS disabled — MITM-enabling
    FloorRule(
        pattern=re.compile(r"(?:tls[_.-]?disabled|node[_.-]?tls[_.-]?reject[_.-]?unauthorized|(?:python[_.-]?)?verify[_.-]?false|insecure[_.-]?tls)", re.IGNORECASE),
        floor=7,
        class_name="tls-disabled",
        rationale="MITM-enabling class; cascades to credential theft and request tampering",
    ),
    # Non-AEAD cipher / weak hash / weak cipher / deprecated crypto
    FloorRule(
        pattern=re.compile(r"(?:non[_.-]?aead[_.-]?cipher|weak[_.-]?hash|md5[_.-]?for[_.-]?integrity|weak[_.-]?cipher|deprecated[_.-]?crypto|insecure[_.-]?hash[_.-]?algorithm|crypto[_.-]?mode[_.-]?without[_.-]?authentication)", re.IGNORECASE),
        floor=6,
        class_name="weak-crypto",
        rationale="Broken or deprecated cryptographic primitives enable padding-oracle, collision, downgrade attacks",
    ),
    # Shared credentials / cross-env reuse — immediate cred exposure
    FloorRule(
        pattern=re.compile(r"(?:shared[_.-]?cred|shared[_.-]?credential|cross[_.-]?env[_.-]?reuse|cred[_.-]?reuse)", re.IGNORECASE),
        floor=7,
        class_name="shared-credential",
        rationale="Direct credential exposure with cross-repo / cross-env cascade",
    ),
    # Hardcoded / committed credentials
    FloorRule(
        pattern=re.compile(r"(?:hardcoded|gitleaks[.]secrets[.]|entropy[_.-]?check[.]secrets[.])", re.IGNORECASE),
        floor=7,
        class_name="hardcoded-cred",
        rationale="Direct credential exposure; immediate attacker utility",
    ),
    # Fail-open scoring — direct fraud bypass
    FloorRule(
        pattern=re.compile(r"(?:fail[_.-]?open|fraud[.].*fail[_.-]?open)", re.IGNORECASE),
        floor=8,
        class_name="fail-open-fraud",
        rationale="Direct fraud bypass — the finding IS the exploit primitive",
    ),
    # Tokenization skip — direct PCI §3.4 violation
    FloorRule(
        pattern=re.compile(r"(?:tokenization[_.-]?skip|pan[_.-]?bypass)", re.IGNORECASE),
        floor=8,
        class_name="tokenization-skip",
        rationale="Tokenization / PII-masking disabled — direct PCI-DSS §3.4 violation",
    ),
    # Emulation-mode bypass — production short-circuit
    FloorRule(
        pattern=re.compile(r"(?:emulation[_.-]?mode|fraud[.].*emulation)", re.IGNORECASE),
        floor=7,
        class_name="emulation-bypass",
        rationale="Production short-circuit of fraud scoring via env var / header",
    ),
    # Feature poisoning / client-controlled aggregates
    FloorRule(
        pattern=re.compile(r"(?:client[_.-]?controlled[_.-]?aggregate|feature[_.-]?poisoning)", re.IGNORECASE),
        floor=7,
        class_name="feature-poisoning",
        rationale="Attacker controls features the model trusts — direct scoring manipulation",
    ),
    # Unauthenticated ADMIN / privileged endpoints (path-gated to avoid over-calling info-leak actuators)
    FloorRule(
        pattern=re.compile(r"(?:unauth(?:enticated)?[_.-]?(?:admin|endpoint)|missing[_.-]?auth|unauth[_.-]?admin[_.-]?endpoint)", re.IGNORECASE),
        floor=7,
        class_name="unauth-admin-endpoint",
        rationale="Auth bypass on privileged or decision-making surface",
        path_gate=re.compile(r"/(?:admin|internal|predict|score|token|model|reload|reset|delete)", re.IGNORECASE),
    ),
    # Unauthenticated INFO-LEAK endpoints (actuator/metrics/etc.) — floor 5, not 7
    FloorRule(
        pattern=re.compile(r"(?:unauth(?:enticated)?[_.-]?(?:actuator|metric|info|debug|management)|unauth[_.-]?actuator[_.-]?endpoint)", re.IGNORECASE),
        floor=5,
        class_name="unauth-info-leak-endpoint",
        rationale="Info-disclosure via unauth diagnostic endpoint — MEDIUM; actionable only with additional chain",
    ),
    # Pip trusted-host wildcard — TLS bypass at install time
    FloorRule(
        pattern=re.compile(r"pip[_.-]?trusted[_.-]?host|trusted[_.-]?host[_.-]?wildcard", re.IGNORECASE),
        floor=6,
        class_name="pip-trusted-host",
        rationale="pip --trusted-host * disables PyPI TLS verification; supply-chain attack surface",
    ),
]


# ── Entry access (nested + flat defensive) ──────────────────────────────────


def _get_rule_id(entry: dict) -> str:
    """Read rule_id from nested or flat shape."""
    nested = entry.get("finding")
    if isinstance(nested, dict):
        v = nested.get("rule_id")
        if v:
            return str(v)
    return str(entry.get("rule_id", ""))


def _get_file(entry: dict) -> str:
    nested = entry.get("finding")
    if isinstance(nested, dict):
        v = nested.get("file")
        if v:
            return str(v)
    return str(entry.get("file", ""))


# ── Core ────────────────────────────────────────────────────────────────────


def find_floor(rule_id: str, file_path: str) -> FloorRule | None:
    """Return the first matching FloorRule, or None."""
    for rule in FLOOR_RULES:
        if not rule.pattern.search(rule_id):
            continue
        if rule.path_gate and not rule.path_gate.search(file_path):
            continue
        return rule
    return None


def apply_floor_to_entry(entry: dict, audit: list[dict]) -> bool:
    """Mutate entry in-place if a floor applies. Return True if changed."""
    rule_id = _get_rule_id(entry)
    file_path = _get_file(entry)
    floor_rule = find_floor(rule_id, file_path)
    if floor_rule is None:
        return False

    exploit = entry.setdefault("exploitability", {})
    mechanical = exploit.get("score", 0)
    if not isinstance(mechanical, (int, float)):
        mechanical = 0
    mechanical = int(mechanical)

    if mechanical >= floor_rule.floor:
        # Floor doesn't apply (mechanical already meets or exceeds)
        return False

    # Apply the floor
    exploit["score"] = floor_rule.floor
    original_rationale = exploit.get("rationale", "")
    new_rationale = (
        f"Floor applied (class: {floor_rule.class_name}, reason: {floor_rule.rationale}); "
        f"mechanical: {mechanical}; final: {floor_rule.floor}. "
        f"Original rationale: {original_rationale}"
    )[:500]
    exploit["rationale"] = new_rationale

    audit.append({
        "ts": datetime.now().astimezone().isoformat(),
        "event": "FLOOR_APPLIED",
        "rule_id": rule_id,
        "file": file_path,
        "class": floor_rule.class_name,
        "mechanical": mechanical,
        "floor": floor_rule.floor,
    })
    return True


def process_register(register: dict) -> tuple[dict, list[dict]]:
    """Return (updated register, audit list)."""
    audit: list[dict] = []
    if "entries" not in register or not isinstance(register["entries"], list):
        return register, audit
    for entry in register["entries"]:
        apply_floor_to_entry(entry, audit)
    return register, audit


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--disposition", type=Path, required=True,
                   help="Path to disposition-<slug>.json; rewritten in place unless --dry-run")
    p.add_argument("--audit-log-out", type=Path,
                   help="Optional audit log of floor applications (severity-floors-log-<slug>.jsonl)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print summary; do not rewrite the disposition file")
    args = p.parse_args()

    if not args.disposition.exists():
        print(f"error: disposition not found: {args.disposition}", file=sys.stderr)
        return 3

    with args.disposition.open() as f:
        register = json.load(f)

    entries_before = len(register.get("entries", []))
    updated, audit = process_register(register)
    applied = len(audit)

    # Summary
    by_class: dict[str, int] = {}
    for a in audit:
        by_class[a["class"]] = by_class.get(a["class"], 0) + 1

    print(f"Processed {entries_before} entries from {args.disposition}")
    print(f"Applied floor to: {applied} entries")
    if by_class:
        for cls, count in sorted(by_class.items()):
            print(f"  {cls}: {count}")

    if args.dry_run:
        print("\n[dry-run] not writing files")
        return 0

    # Rewrite register
    tmp = args.disposition.with_suffix(args.disposition.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(updated, f, indent=2)
    tmp.rename(args.disposition)
    print(f"\nRewrote {args.disposition}")

    # Audit log
    if args.audit_log_out and audit:
        args.audit_log_out.parent.mkdir(parents=True, exist_ok=True)
        with args.audit_log_out.open("w") as f:
            for a in audit:
                f.write(json.dumps(a) + "\n")
        print(f"Wrote {args.audit_log_out} ({applied} entries)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
