#!/usr/bin/env python3
"""validate_agent_contract.py — validate agent frontmatter against the
official Claude Code sub-agent contract (knowledge/agent-contract.json).

Self-contained and stdlib-only so marketplace-dev stays installable on its
own, with no dependency on dev-team's tooling or PyYAML. Frontmatter in this
repo's agent files is flat scalars/comma-lists (never nested YAML mappings),
so a small line-based parser is enough — no real YAML parser needed.

Checks (schema-driven from agent-contract.json, not hardcoded, so a contract
update can't silently drift out of sync with this script):
  - required fields (name, description) present and non-empty
  - name matches the contract's name pattern
  - every top-level frontmatter key is a known contract field (unknown/
    misspelled keys are warned on — the contract notes they are silently
    ignored, never erroring, so this script never fails on them)
  - enum-valued fields (model, effort, permissionMode, memory, isolation,
    color) validated against the contract's enum when present; `model` also
    accepts a full `claude-*` ID or the literal alias set
  - boolean/integer-typed fields (background, maxTurns) type-checked
  - hooks/mcpServers/permissionMode on a plugins/*/agents/*.md file warn —
    the contract states plugin-supplied subagents ignore all three

Exit codes (matches this repo's other structural-check scripts):
  0 = pass, 1 = fail (errors present), 2 = warn (warnings only)

CLI usage:
  python3 validate_agent_contract.py <agent.md> [<agent.md> ...]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_CONTRACT = _SCRIPT_DIR / ".." / "knowledge" / "agent-contract.json"

_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")
_FULL_MODEL_ID_RE = re.compile(r"^claude-[a-z0-9-]+$")
_PLUGIN_AGENT_PATH_RE = re.compile(r"plugins/[^/]+/agents/[^/]+\.md$")


def _contract_path() -> Path:
    return Path(os.environ.get("AGENT_CONTRACT_JSON", str(_DEFAULT_CONTRACT)))


def load_contract(path: Optional[Path] = None) -> Optional[dict]:
    path = path or _contract_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _strip_value(raw: str) -> str:
    return raw.strip().strip("'\"")


def parse_frontmatter(text: str) -> Dict[str, str]:
    """Return {top-level key: raw scalar value} from a markdown file's
    frontmatter. Indented continuation/list lines are ignored — this script
    only validates scalar fields, and every field it checks is a scalar in
    this repo's convention."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith((" ", "\t")):
            continue
        m = _TOP_LEVEL_KEY_RE.match(line)
        if m:
            fields[m.group(1)] = _strip_value(m.group(2))
    return fields


def make_issue(severity: str, file: str, message: str, field: str = "") -> dict:
    issue = {"severity": severity, "file": file, "message": message}
    if field:
        issue["field"] = field
    return issue


def _check_required_and_pattern(
    fields: Dict[str, str], contract: dict, file: str
) -> List[dict]:
    issues: List[dict] = []
    for name, spec in contract.get("fields", {}).items():
        if not spec.get("required"):
            continue
        value = fields.get(name)
        if not value:
            issues.append(
                make_issue(
                    "error",
                    file,
                    f"Missing required frontmatter field '{name}'",
                    field=name,
                )
            )
    name_spec = contract.get("fields", {}).get("name", {})
    pattern = name_spec.get("pattern")
    if pattern and fields.get("name") and not re.match(pattern, fields["name"]):
        issues.append(
            make_issue(
                "error",
                file,
                f"name '{fields['name']}' does not match required pattern '{pattern}'",
                field="name",
            )
        )
    return issues


def _check_unknown_keys(fields: Dict[str, str], contract: dict, file: str) -> List[dict]:
    known = set(contract.get("fields", {}).keys())
    issues = []
    for key in fields:
        if key not in known:
            issues.append(
                make_issue(
                    "warning",
                    file,
                    f"Unknown frontmatter key '{key}' — per the contract, unrecognized "
                    "keys are silently ignored (no error) and take no effect.",
                    field=key,
                )
            )
    return issues


def _model_is_valid(value: str, enum: List[str]) -> bool:
    return value in enum or bool(_FULL_MODEL_ID_RE.match(value))


def _check_enum_and_type_fields(
    fields: Dict[str, str], contract: dict, file: str
) -> List[dict]:
    issues: List[dict] = []
    for name, spec in contract.get("fields", {}).items():
        if name not in fields:
            continue
        value = fields[name]
        enum = spec.get("enum")
        field_type = spec.get("type")
        if name == "model" and enum:
            if not _model_is_valid(value, enum):
                issues.append(
                    make_issue(
                        "error",
                        file,
                        f"model '{value}' is not one of {enum} and does not look like "
                        "a full claude-* model ID",
                        field=name,
                    )
                )
        elif enum:
            if value not in [str(v) for v in enum]:
                issues.append(
                    make_issue(
                        "error",
                        file,
                        f"{name} '{value}' must be one of {enum}",
                        field=name,
                    )
                )
        elif field_type == "boolean" and value not in ("true", "false"):
            issues.append(
                make_issue(
                    "error",
                    file,
                    f"{name} '{value}' must be a boolean (true/false)",
                    field=name,
                )
            )
        elif field_type == "integer" and not value.lstrip("-").isdigit():
            issues.append(
                make_issue(
                    "error",
                    file,
                    f"{name} '{value}' must be an integer",
                    field=name,
                )
            )
    return issues


def _check_plugin_ignored_fields(fields: Dict[str, str], file: str) -> List[dict]:
    if not _PLUGIN_AGENT_PATH_RE.search(file.replace(os.sep, "/")):
        return []
    issues = []
    for name in ("hooks", "mcpServers", "permissionMode"):
        if name in fields:
            issues.append(
                make_issue(
                    "warning",
                    file,
                    f"'{name}' is ignored for plugin-supplied sub-agents per the "
                    "contract — this field has no effect here.",
                    field=name,
                )
            )
    return issues


def validate_file(path: Path, contract: dict) -> List[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [make_issue("error", str(path), f"Could not read file: {exc}")]

    fields = parse_frontmatter(text)
    file = str(path)
    if not fields:
        return [make_issue("error", file, "Could not find or parse YAML frontmatter")]

    issues: List[dict] = []
    issues += _check_required_and_pattern(fields, contract, file)
    issues += _check_unknown_keys(fields, contract, file)
    issues += _check_enum_and_type_fields(fields, contract, file)
    issues += _check_plugin_ignored_fields(fields, file)
    return issues


def build_result(issues: List[dict]) -> dict:
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    if errors:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"
    return {"status": status, "issues": issues, "summary": ""}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate agent frontmatter against the official contract."
    )
    parser.add_argument("files", nargs="+", help="Agent markdown file(s) to validate")
    args = parser.parse_args(argv)

    contract = load_contract()
    if contract is None:
        sys.stderr.write(f"Contract file not found or invalid: {_contract_path()}\n")
        return 1

    all_issues: List[dict] = []
    for file_arg in args.files:
        all_issues += validate_file(Path(file_arg), contract)

    result = build_result(all_issues)
    print(json.dumps(result))
    if result["status"] == "fail":
        return 1
    if result["status"] == "warn":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
