#!/usr/bin/env python3
"""validator for plugins/agentic-dev-team/tools/{entropy-check,model-hash-verify}.py

For each custom script, runs it against its fixture directory and asserts:
  1. Exit code 0 (graceful completion regardless of findings)
  2. Output is valid JSON that looks like SARIF 2.1.0
  3. Expected rule_ids appear in the findings set
  4. Every emitted result passes through evals/static-analysis-tools/validate.py's
     SARIF-to-unified-finding parser AND validates against unified-finding-v1

Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO / "plugins/agentic-dev-team/tools"
FIXTURE_DIR = REPO / "evals/custom-tools"
SCHEMA_PATH = REPO / "plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json"

# Import the SARIF parser from the sibling static-analysis-tools validator.
sys.path.insert(0, str(REPO / "evals/static-analysis-tools"))
from validate import parse_sarif, load_schema_registry  # type: ignore
from jsonschema import Draft202012Validator


def run_tool(script: Path, target: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(script), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{script.name} exited {proc.returncode}: {proc.stderr}")
    return json.loads(proc.stdout)


def assert_sarif_shape(sarif: dict, tool_name: str) -> None:
    assert sarif.get("version") == "2.1.0", f"{tool_name}: missing or wrong SARIF version"
    assert "runs" in sarif and isinstance(sarif["runs"], list), f"{tool_name}: missing runs[]"
    for run in sarif["runs"]:
        driver = run.get("tool", {}).get("driver", {})
        assert driver.get("name") == tool_name, f"{tool_name}: driver.name mismatch"
        assert isinstance(driver.get("rules"), list), f"{tool_name}: missing rules[]"


def assert_rule_ids(sarif: dict, expected: set[str]) -> None:
    actual = {r["ruleId"] for run in sarif["runs"] for r in run["results"]}
    missing = expected - actual
    if missing:
        raise AssertionError(f"expected rule_ids missing: {missing}; actual: {actual}")


def parse_and_validate(sarif: dict, validator: Draft202012Validator) -> int:
    """Normalize via the shared SARIF parser + schema-validate each finding."""
    unified = parse_sarif(sarif)
    errs = 0
    for f in unified:
        for e in validator.iter_errors(f):
            print(f"  schema error: {e.message} @ {list(e.absolute_path)}")
            errs += 1
    return errs


def main() -> int:
    schema, registry = load_schema_registry()
    validator = Draft202012Validator(schema, registry=registry)

    fail = 0

    # entropy-check
    print("[entropy-check]")
    sarif = run_tool(TOOLS_DIR / "entropy-check.py", FIXTURE_DIR / "entropy-check/fixture")
    assert_sarif_shape(sarif, "entropy-check")
    try:
        assert_rule_ids(sarif, {"short-secret", "low-entropy-secret", "weak-placeholder", "cross-env-reuse"})
        print(f"  [OK] all 4 expected rule_ids fired on fixture")
    except AssertionError as e:
        print(f"  [FAIL] {e}")
        fail += 1
    errs = parse_and_validate(sarif, validator)
    if errs:
        print(f"  [FAIL] {errs} unified-finding schema error(s)")
        fail += 1
    else:
        count = sum(len(r["results"]) for r in sarif["runs"])
        print(f"  [OK] {count} finding(s) normalized + validated")

    # model-hash-verify
    print("\n[model-hash-verify]")
    sarif = run_tool(TOOLS_DIR / "model-hash-verify.py", FIXTURE_DIR / "model-hash-verify/fixture")
    assert_sarif_shape(sarif, "model-hash-verify")
    try:
        assert_rule_ids(sarif, {"integrity-failure", "no-provenance"})
        print(f"  [OK] both expected rule_ids fired on fixture")
    except AssertionError as e:
        print(f"  [FAIL] {e}")
        fail += 1
    errs = parse_and_validate(sarif, validator)
    if errs:
        print(f"  [FAIL] {errs} unified-finding schema error(s)")
        fail += 1
    else:
        count = sum(len(r["results"]) for r in sarif["runs"])
        print(f"  [OK] {count} finding(s) normalized + validated")

    if fail:
        print(f"\nFAIL: {fail} check(s) failed")
        return 1
    print("\nOK: custom scripts emit valid SARIF that the shared parser consumes cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
