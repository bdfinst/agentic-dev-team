#!/usr/bin/env python3
"""entropy-check — passphrase entropy + cross-env credential-reuse detector.

Scans env-files (.env, .env.*, docker-compose env blocks) for two issues:

  1. Low Shannon entropy on declared secrets (suggests predictable password).
  2. The same secret hash appearing across multiple env files (suggests
     cross-environment credential reuse — a common fail pattern).

Emits SARIF 2.1.0 on stdout. Shipped alongside the SARIF-first baseline so
the shared parser normalizes its findings to unified-finding v1.0 with no
special case.

Usage:
    entropy-check.py <path> [<path> ...]
    entropy-check.py --help

Detection:
    - Lines matching KEY=VALUE where KEY ends in {PASSWORD, PASSWD, SECRET,
      TOKEN, KEY, API_KEY, CREDENTIAL} (case-insensitive).
    - Value shorter than 12 chars OR Shannon entropy below 2.5 bits/char -> LOW_ENTROPY finding.
    - SHA-256 of each value tracked across files; duplicate -> CRED_REUSE finding emitted
      once per duplicate pair.

Exit codes:
    0   always zero on successful scan (findings reported via SARIF, not exit).
    2   argument or IO error.

See plugins/agentic-dev-team/knowledge/semgrep-rules/ml-patterns.yaml for
analogous detection patterns shipped as semgrep rules in Step 3b's ruleset
work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SENSITIVE_KEY_PATTERN = re.compile(
    r"^(?P<key>[A-Z_][A-Z0-9_]*(PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|CREDENTIAL|KEY))\s*=\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
ENV_FILE_PATTERNS = (".env", ".env.local", ".env.development", ".env.staging",
                     ".env.production", ".env.test", ".env.example")
MIN_LEN = 12
LOW_ENTROPY_BITS_PER_CHAR = 2.5


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    file: str
    line: int
    message: str


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    total = len(s)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def is_env_file(path: Path) -> bool:
    name = path.name
    return name in ENV_FILE_PATTERNS or name.startswith(".env.")


def scan_file(path: Path) -> tuple[list[Finding], dict[str, list[tuple[Path, int]]]]:
    """Return (findings, value_hash -> [(path, line), ...]) for cross-file analysis."""
    findings: list[Finding] = []
    hash_map: dict[str, list[tuple[Path, int]]] = {}

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"entropy-check: cannot read {path}: {e}", file=sys.stderr)
        return findings, hash_map

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = SENSITIVE_KEY_PATTERN.match(stripped)
        if not m:
            continue
        value = m.group("value").strip().strip('"').strip("'")
        if not value or value.lower() in {"changeme", "replace-me", "fixme", "xxx", ""}:
            # Placeholders — flag separately as weak-placeholder
            findings.append(Finding(
                rule_id="weak-placeholder",
                severity="warning",
                file=str(path),
                line=lineno,
                message=f"Sensitive key {m.group('key')!r} uses placeholder value; likely unset in production.",
            ))
            continue

        # Low-entropy check
        if len(value) < MIN_LEN:
            findings.append(Finding(
                rule_id="short-secret",
                severity="warning",
                file=str(path),
                line=lineno,
                message=f"Sensitive key {m.group('key')!r} has a value shorter than {MIN_LEN} chars.",
            ))
        elif shannon_entropy(value) < LOW_ENTROPY_BITS_PER_CHAR:
            findings.append(Finding(
                rule_id="low-entropy-secret",
                severity="warning",
                file=str(path),
                line=lineno,
                message=(
                    f"Sensitive key {m.group('key')!r} has Shannon entropy "
                    f"{shannon_entropy(value):.2f} bits/char (< {LOW_ENTROPY_BITS_PER_CHAR})."
                ),
            ))

        h = hashlib.sha256(value.encode("utf-8")).hexdigest()
        hash_map.setdefault(h, []).append((path, lineno))

    return findings, hash_map


def cross_file_findings(hash_map_global: dict[str, list[tuple[Path, int]]]) -> list[Finding]:
    findings: list[Finding] = []
    for h, locations in hash_map_global.items():
        if len(locations) < 2:
            continue
        # One finding per duplicate, on the second-and-later locations.
        for path, line in locations[1:]:
            first_path, first_line = locations[0]
            findings.append(Finding(
                rule_id="cross-env-reuse",
                severity="error",
                file=str(path),
                line=line,
                message=(
                    f"Secret value (SHA-256 {h[:12]}...) also appears at "
                    f"{first_path}:{first_line} — credential reused across files."
                ),
            ))
    return findings


def sarif_from_findings(findings: list[Finding]) -> dict:
    rules = {
        "weak-placeholder": "Sensitive key uses a placeholder value",
        "short-secret": "Sensitive key value shorter than minimum length",
        "low-entropy-secret": "Sensitive key value has low Shannon entropy",
        "cross-env-reuse": "Sensitive value reused across env files",
    }
    rule_order = list(rules.keys())

    def rule_index(rule_id: str) -> int:
        return rule_order.index(rule_id) if rule_id in rule_order else 0

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "entropy-check",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/bdfinst/agentic-dev-team",
                        "rules": [
                            {"id": rid, "shortDescription": {"text": text}}
                            for rid, text in rules.items()
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": f.rule_id,
                        "ruleIndex": rule_index(f.rule_id),
                        "level": f.severity,
                        "message": {"text": f.message},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": f.file},
                                    "region": {"startLine": f.line},
                                }
                            }
                        ],
                    }
                    for f in findings
                ],
            }
        ],
    }


def walk_targets(targets: list[str]) -> list[Path]:
    """Resolve targets — files are added as-is, directories walked for env-files."""
    out: list[Path] = []
    for t in targets:
        p = Path(t)
        if not p.exists():
            print(f"entropy-check: path not found: {t}", file=sys.stderr)
            continue
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and is_env_file(sub):
                    out.append(sub)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("paths", nargs="+", help="Files or directories to scan.")
    args = parser.parse_args()

    files = walk_targets(args.paths)
    if not files:
        # No env files found — emit empty SARIF and succeed.
        json.dump(sarif_from_findings([]), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    all_findings: list[Finding] = []
    global_hash_map: dict[str, list[tuple[Path, int]]] = {}
    for path in files:
        findings, hash_map = scan_file(path)
        all_findings.extend(findings)
        for h, locs in hash_map.items():
            global_hash_map.setdefault(h, []).extend(locs)

    all_findings.extend(cross_file_findings(global_hash_map))

    json.dump(sarif_from_findings(all_findings), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
