#!/usr/bin/env python3
"""Conformance validator for the security primitives contract v1.0.0.

Usage:
    python3 evals/primitives-contract/validate.py
    python3 evals/primitives-contract/validate.py --mutate

With --mutate, the script also runs mutation tests: each fixture is altered in
a specific way and the script asserts that validation FAILS. This guards
against silent schema loosening.

Exits non-zero on any validation or mutation-test failure. Designed to run in
CI and locally.

Requires: jsonschema >= 4.18, referencing (both ship together on recent pip
installs).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "plugins/agentic-dev-team/knowledge/schemas"
FIXTURE_DIR = REPO / "evals/primitives-contract/fixtures"

SCHEMA_NAMES = [
    "unified-finding-v1.json",
    "recon-envelope-v1.json",
    "disposition-register-v1.json",
]

FIXTURES = [
    ("recon-envelope", "recon-envelope-v1.json", "recon-envelope-valid.json"),
    ("unified-finding", "unified-finding-v1.json", "unified-finding-valid.json"),
    ("disposition-register", "disposition-register-v1.json", "disposition-register-valid.json"),
]


def build_registry() -> Registry:
    resources = []
    for name in SCHEMA_NAMES:
        with (SCHEMA_DIR / name).open() as f:
            doc = json.load(f)
        resources.append((name, Resource(contents=doc, specification=DRAFT202012)))
    return Registry().with_resources(resources)


def validate(schema_name: str, data: dict, registry: Registry) -> list[str]:
    with (SCHEMA_DIR / schema_name).open() as f:
        schema = json.load(f)
    v = Draft202012Validator(schema, registry=registry)
    return [f"{e.message} @ {list(e.absolute_path)}" for e in v.iter_errors(data)]


def check_positive_fixtures(registry: Registry) -> int:
    failures = 0
    for label, schema_name, fixture_name in FIXTURES:
        with (FIXTURE_DIR / fixture_name).open() as f:
            data = json.load(f)
        errors = validate(schema_name, data, registry)
        if errors:
            failures += 1
            print(f"[FAIL] positive fixture '{label}':")
            for e in errors[:5]:
                print(f"   {e}")
        else:
            print(f"[OK]   positive fixture '{label}': valid")
    return failures


def check_mutations(registry: Registry) -> int:
    """Each mutation breaks a specific schema constraint. Validation MUST fail."""
    mutations = [
        (
            "unified-finding: missing required 'rule_id'",
            "unified-finding-v1.json",
            lambda d: {k: v for k, v in d.items() if k != "rule_id"},
            "unified-finding-valid.json",
        ),
        (
            "unified-finding: bad severity enum",
            "unified-finding-v1.json",
            lambda d: {**d, "severity": "catastrophic"},
            "unified-finding-valid.json",
        ),
        (
            "recon: schema_version mismatch",
            "recon-envelope-v1.json",
            lambda d: {**d, "schema_version": "0.9"},
            "recon-envelope-valid.json",
        ),
        (
            "disposition: reachability without rationale",
            "disposition-register-v1.json",
            lambda d: {**d, "entries": [
                {**d["entries"][0], "reachability": {"reachable": True, "rationale": ""}}
            ]},
            "disposition-register-valid.json",
        ),
    ]

    failures = 0
    for label, schema_name, mutate_fn, base_fixture in mutations:
        with (FIXTURE_DIR / base_fixture).open() as f:
            base = json.load(f)
        mutated = mutate_fn(base)
        errors = validate(schema_name, mutated, registry)
        if not errors:
            failures += 1
            print(f"[FAIL] mutation '{label}' was accepted (should have failed)")
        else:
            print(f"[OK]   mutation '{label}' rejected: {errors[0]}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutate", action="store_true", help="Also run mutation tests")
    args = parser.parse_args()

    registry = build_registry()
    failures = check_positive_fixtures(registry)
    if args.mutate:
        failures += check_mutations(registry)

    if failures:
        print(f"\nFAIL: {failures} check(s) failed")
        return 1
    print("\nOK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
