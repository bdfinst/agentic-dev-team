#!/usr/bin/env python3
"""security-review agent output -> unified-finding envelope adapter.

Reads the security-review agent's JSON output (see
plugins/agentic-dev-team/agents/security-review.md for the agent-output
schema) and emits one unified-finding envelope v1 (JSONL) per issue.

Rule_id lookup is driven by the canonical mapping at
plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml. This
adapter contains NO inline rule_id literals beyond the
``security-review.`` namespace prefix constant used for the
fallback path; the single-source-of-truth invariant is enforced by an
AST-level test in evals/security-review-adapter/tests/.

Contract, error semantics, and failure modes are documented in
plugins/agentic-dev-team/docs/specs/agent-rule-id-adapter.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

# Namespace prefix used when a well-formed category is not in the mapping YAML.
# This is the ONLY rule_id-shaped literal permitted in this source file;
# every other rule_id travels in from security-review-rule-map.yaml.
_FALLBACK_NAMESPACE = "security-review."

# Default mapping path resolved relative to this file, so the adapter works
# from any cwd. The repo-relative path is also named in --help for operators.
_THIS_FILE = os.path.abspath(__file__)
_ADAPTER_DIR = os.path.dirname(_THIS_FILE)
# /plugins/agentic-dev-team/skills/static-analysis-integration/adapters -> /plugins/agentic-dev-team
_PLUGIN_ROOT = os.path.abspath(os.path.join(_ADAPTER_DIR, "..", "..", ".."))
_DEFAULT_MAPPING_ABS = os.path.join(
    _PLUGIN_ROOT, "knowledge", "security-review-rule-map.yaml"
)
_DEFAULT_MAPPING_REL = (
    "plugins/agentic-dev-team/knowledge/security-review-rule-map.yaml"
)


def _load_mapping(path: str) -> Dict[str, str]:
    """Load the YAML mapping."""
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {str(k): str(v) for k, v in data["mappings"].items()}


def _build_finding(issue: Dict[str, Any], rule_id: str) -> Dict[str, Any]:
    """Map an agent issue to a unified-finding envelope."""
    return {
        "rule_id": rule_id,
        "file": issue["file"],
        "line": issue["line"],
        "severity": issue["severity"],
        "message": issue["message"],
        "metadata": {
            "source": "security-review",
            "confidence": issue.get("confidence", "none"),
            "source_ref": issue,
        },
    }


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="security-review-adapter.py",
        description=(
            "Normalize security-review agent JSON into unified-finding-v1 JSONL. "
            f"Default mapping: {_DEFAULT_MAPPING_REL}."
        ),
    )
    parser.add_argument("--input", required=True, help="Agent-output JSON file.")
    parser.add_argument(
        "--output",
        required=True,
        help="Destination JSONL path (one unified finding per line).",
    )
    parser.add_argument(
        "--mapping",
        default=_DEFAULT_MAPPING_ABS,
        help=f"Mapping YAML path. Default: {_DEFAULT_MAPPING_REL}",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    with open(args.input, "r", encoding="utf-8") as fh:
        agent = json.load(fh)

    mapping = _load_mapping(args.mapping)
    issues = agent.get("issues", []) or []

    with open(args.output, "w", encoding="utf-8") as out:
        for issue in issues:
            rule_id = mapping[issue["category"]]
            finding = _build_finding(issue, rule_id)
            out.write(json.dumps(finding, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
