#!/usr/bin/env python3
"""Tier-1 SARIF-parser validator for the static-analysis-integration skill.

Reads each tier1-mocks/<tool>/mock.sarif, runs it through the shared SARIF
parser, and asserts the output:
  1) equals the fixture's expected-findings.json
  2) validates against unified-finding-v1 JSON Schema

Exits non-zero on any failure. Designed to run in CI and locally.

Requires: jsonschema, referencing (both ship together with `pip install jsonschema`).

Usage:
    python3 evals/static-analysis-tools/validate.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json"
MOCKS_DIR = REPO / "evals/static-analysis-tools/tier1-mocks"

# Tool-driver (lowercased) → capability-tier segment used when the raw SARIF
# ruleId is flat (no dots). See references/sarif-parser.md for the policy.
TOOL_TIER_MAP: dict[str, str] = {
    "semgrep": "sast",
    "gitleaks": "secrets",
    "trivy": "iac",
    "hadolint": "dockerfile",
    "actionlint": "workflows",
}

SEVERITY_MAP: dict[str, str] = {
    "error": "error",
    "warning": "warning",
    "note": "suggestion",
    "none": "info",
}


def kebab(s: str) -> str:
    """Lowercase; replace any run of non-[a-z0-9] with a single hyphen; trim."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build_rule_id(driver_name: str, raw_rule_id: str, tier_override: str | None = None) -> str:
    """Apply the rule-id prefix rules from references/sarif-parser.md."""
    driver_l = driver_name.lower().strip()
    if "." in raw_rule_id:
        # Structured rule id (e.g. semgrep's python.django.audit.sql-injection).
        # Preserve dot structure; kebab-case each segment independently.
        parts = [kebab(p) for p in raw_rule_id.split(".") if p]
        return f"{driver_l}." + ".".join(parts)
    tier = tier_override or TOOL_TIER_MAP.get(driver_l, "generic")
    return f"{driver_l}.{tier}.{kebab(raw_rule_id)}"


def trivy_tier_for_rule(raw_rule_id: str) -> str:
    """Trivy scans multiple surfaces; infer tier from rule id shape."""
    if raw_rule_id.upper().startswith("CVE-"):
        return "cve"
    # DS* / AVD* / KSV* / etc. are iac checks
    return "iac"


def parse_result(driver_name: str, result: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Map a single SARIF result to a unified finding dict. Returns None for
    results that are missing required SARIF fields (logged by caller)."""
    raw_rule_id = result.get("ruleId")
    if not raw_rule_id:
        return None

    locations = result.get("locations") or []
    if not locations:
        return None
    first = locations[0]
    physical = first.get("physicalLocation") or {}
    artifact = physical.get("artifactLocation") or {}
    region = physical.get("region") or {}
    uri = artifact.get("uri")
    if not uri or "startLine" not in region:
        return None

    message = (result.get("message") or {}).get("text")
    if not message:
        return None

    # File path normalization
    file_path = uri
    if file_path.startswith("file://"):
        file_path = file_path[7:]

    level = result.get("level", "warning")
    severity = SEVERITY_MAP.get(level, "info")

    # rule_id — trivy-specific tier override
    tier_override = None
    if driver_name.lower() == "trivy":
        tier_override = trivy_tier_for_rule(raw_rule_id)
    rule_id = build_rule_id(driver_name, raw_rule_id, tier_override)

    unified: dict[str, Any] = {
        "rule_id": rule_id,
        "file": file_path,
        "line": int(region["startLine"]),
        "severity": severity,
        "message": (message[:500] if len(message) > 500 else message),
        "metadata": {
            "source": driver_name.lower(),
            "confidence": (result.get("properties") or {}).get("confidence", "medium"),
        },
    }

    if "startColumn" in region:
        unified["column"] = int(region["startColumn"])
    if "endLine" in region:
        unified["end_line"] = int(region["endLine"])
    if "endColumn" in region:
        unified["end_column"] = int(region["endColumn"])

    # CWE / OWASP — from rule properties, looked up by ruleIndex if present
    rule_index = result.get("ruleIndex")
    rule_obj = rules[rule_index] if (rule_index is not None and 0 <= rule_index < len(rules)) else None
    if rule_obj:
        props = rule_obj.get("properties") or {}
        if "cwe" in props:
            cwe_raw = props["cwe"]
            if isinstance(cwe_raw, (str, int)):
                cwe_str = str(cwe_raw)
                if not cwe_str.upper().startswith("CWE-"):
                    cwe_str = f"CWE-{cwe_str}"
                unified["cwe"] = [cwe_str.upper()]
            elif isinstance(cwe_raw, list):
                unified["cwe"] = [str(c).upper() if str(c).upper().startswith("CWE-") else f"CWE-{c}" for c in cwe_raw]
        if "owasp" in props:
            owasp_raw = props["owasp"]
            unified["owasp"] = [owasp_raw] if isinstance(owasp_raw, str) else list(owasp_raw)

    exploit = (result.get("properties") or {}).get("exploitability")
    if exploit:
        unified["metadata"]["exploitability"] = exploit

    return unified


def parse_sarif(sarif_doc: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for run in sarif_doc.get("runs", []):
        tool = run.get("tool", {})
        driver = tool.get("driver", {})
        driver_name = driver.get("name")
        rules = driver.get("rules") or []
        if not driver_name:
            raise ValueError(f"SARIF run missing tool.driver.name (run: {run!r:.200})")
        for result in run.get("results", []):
            unified = parse_result(driver_name, result, rules)
            if unified:
                findings.append(unified)
    return findings


def load_schema_registry() -> tuple[dict[str, Any], Registry]:
    with SCHEMA_PATH.open() as f:
        schema = json.load(f)
    resource = Resource(contents=schema, specification=DRAFT202012)
    registry = Registry().with_resources([(SCHEMA_PATH.name, resource)])
    return schema, registry


INSTALL_HINT_PATTERN = re.compile(
    r"^`?(?P<tool>[a-z0-9-]+)`?\s+—\s+(?P<tier>[^.]+)\.\s+install:\s+(?P<cmd>\S.*)$"
)
TOOL_CONFIGS_PATH = REPO / "plugins/agentic-dev-team/skills/static-analysis-integration/references/tool-configs.md"


def check_install_hints() -> int:
    """Assert every Tier-1 tool has an install-hint line in the canonical shape:
        <tool> — <capability tier>. install: <pkg-mgr> install <name>
    """
    if not TOOL_CONFIGS_PATH.exists():
        print(f"[FAIL] install-hint check: tool-configs.md missing at {TOOL_CONFIGS_PATH}")
        return 1

    text = TOOL_CONFIGS_PATH.read_text()
    needed = {"semgrep", "gitleaks", "trivy", "hadolint", "actionlint"}
    found: dict[str, str] = {}

    for line in text.splitlines():
        if "**Install hint**:" not in line:
            continue
        # install-hint lines look like:
        #   - **Install hint**: `semgrep — SAST. install: pip install semgrep`
        after_label = line.split("**Install hint**:", 1)[-1].strip()
        after_label = after_label.strip().strip("`").strip()
        m = INSTALL_HINT_PATTERN.match(after_label)
        if not m:
            continue
        found[m.group("tool").lower()] = after_label

    missing = needed - set(found)
    if missing:
        print(f"[FAIL] install-hint check: missing hints for {sorted(missing)}")
        return 1

    print(f"[OK]   install-hint check: all 5 tier-1 tools present with canonical format")
    for t in sorted(found):
        print(f"         {found[t]}")
    return 0


def run() -> int:
    schema, registry = load_schema_registry()
    validator = Draft202012Validator(schema, registry=registry)

    tools = sorted(p.name for p in MOCKS_DIR.iterdir() if p.is_dir())
    if not tools:
        print(f"no tier-1 mock fixtures found under {MOCKS_DIR}", file=sys.stderr)
        return 2

    fail = 0
    for tool in tools:
        fixture_dir = MOCKS_DIR / tool
        mock_sarif = fixture_dir / "mock.sarif"
        expected_file = fixture_dir / "expected-findings.json"
        if not mock_sarif.exists() or not expected_file.exists():
            print(f"[SKIP] {tool}: incomplete fixture (need mock.sarif + expected-findings.json)")
            continue

        with mock_sarif.open() as f:
            sarif = json.load(f)
        with expected_file.open() as f:
            expected = json.load(f)

        try:
            actual = parse_sarif(sarif)
        except Exception as e:
            fail += 1
            print(f"[FAIL] {tool}: parser raised: {e}")
            continue

        # Schema validation of each emitted finding
        schema_errors = []
        for i, finding in enumerate(actual):
            errs = list(validator.iter_errors(finding))
            if errs:
                schema_errors.append((i, errs))
        if schema_errors:
            fail += 1
            print(f"[FAIL] {tool}: {len(schema_errors)} finding(s) violate unified-finding-v1 schema")
            for i, errs in schema_errors[:3]:
                for e in errs[:2]:
                    print(f"   finding[{i}]: {e.message} @ {list(e.absolute_path)}")
            continue

        # Equality check (order-sensitive, dict-equality)
        if actual != expected:
            fail += 1
            print(f"[FAIL] {tool}: parser output differs from expected")
            print(f"   actual:   {json.dumps(actual, indent=2)}")
            print(f"   expected: {json.dumps(expected, indent=2)}")
            continue

        print(f"[OK]   {tool}: {len(actual)} finding(s) — valid + match")

    # Install-hint consistency check across tier-1 tools
    print()
    fail += check_install_hints()

    if fail:
        print(f"\nFAIL: {fail} check(s) failed")
        return 1
    print("\nOK: all tier-1 SARIF fixtures parse correctly + install hints consistent")
    return 0


if __name__ == "__main__":
    sys.exit(run())
