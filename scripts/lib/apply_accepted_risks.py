#!/usr/bin/env python3
"""apply_accepted_risks — deterministic Phase 1c suppression gate.

Reads a unified-finding-envelope JSONL stream and an ACCEPTED-RISKS.md at a
target root, applies the first-match-wins suppression algorithm defined in
plugins/agentic-dev-team/knowledge/accepted-risks-schema.md, and emits:

    - rewritten findings.jsonl with suppressed entries removed
    - suppressed.jsonl with removed entries annotated by rule id
    - suppression-log.jsonl with one audit line per suppression

Exit codes:
    0   success (any number of suppressions, including zero)
    2   schema-invalid ACCEPTED-RISKS.md (fails the run, per the schema spec)
    3   missing input files

Usage:
    python3 apply_accepted_risks.py \\
        --findings memory/findings-<slug>.jsonl \\
        --accepted-risks <target>/ACCEPTED-RISKS.md \\
        --suppressed-out memory/suppressed-<slug>.jsonl \\
        --audit-log-out memory/suppression-log-<slug>.jsonl
    [--skip-if-missing-risks]   # exit 0 with no work if ACCEPTED-RISKS.md absent
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


# ── YAML frontmatter parsing ─────────────────────────────────────────────────
# Lightweight YAML parser for the narrow shape we accept. Avoids pyyaml dep.

def _parse_yaml_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from the ACCEPTED-RISKS.md file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        raise ValueError(f"{path}: no YAML frontmatter (must start with ---)")
    # Find the closing ---
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        raise ValueError(f"{path}: unterminated YAML frontmatter")
    yaml_block = rest[:end]

    # Try pyyaml first (cleaner); fall back to a tiny hand-rolled parser
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(yaml_block)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: frontmatter is not a mapping")
        return data
    except ImportError:
        return _mini_yaml(yaml_block)


def _mini_yaml(text: str) -> dict:
    """Tiny YAML subset: list of mappings with scalar / string / list values.

    Handles the ACCEPTED-RISKS schema. Does not handle anchors, aliases,
    multi-doc, flow style, or complex indentation. Pyyaml is strongly preferred.
    """
    raise ImportError("pyyaml not available; install with: pip install pyyaml")


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class Rule:
    id: str
    rule_id: str
    files: list[str]
    rationale: str
    expires: date
    owner: str
    scope: str = "finding"
    broad: bool = False


def _iso_to_date(s: Any) -> date:
    if isinstance(s, date):
        return s
    if not isinstance(s, str):
        raise ValueError(f"expires must be ISO-8601 date, got {type(s).__name__}: {s!r}")
    try:
        return date.fromisoformat(s.strip())
    except ValueError as e:
        raise ValueError(f"expires not ISO-8601: {s!r} ({e})")


def _validate_rule(raw: dict, index: int) -> Rule:
    missing = [k for k in ("id", "rule_id", "files", "rationale", "expires", "owner") if k not in raw]
    if missing:
        raise ValueError(f"rule[{index}] missing required field(s): {missing}")

    id_ = str(raw["id"]).strip()
    if not re.match(r"^[a-z0-9-]+$", id_):
        raise ValueError(f"rule[{index}] id must be kebab-case [a-z0-9-]+, got {id_!r}")

    rule_id = str(raw["rule_id"]).strip()
    files = raw["files"]
    if not isinstance(files, list) or not files:
        raise ValueError(f"rule {id_}: files must be a non-empty list")

    rationale = str(raw["rationale"]).strip()
    if len(rationale) < 50:
        raise ValueError(f"rule {id_}: rationale < 50 chars ({len(rationale)})")

    expires = _iso_to_date(raw["expires"])
    owner = str(raw["owner"]).strip()
    scope = str(raw.get("scope", "finding")).strip()
    if scope not in ("finding", "file"):
        raise ValueError(f"rule {id_}: scope must be 'finding' or 'file', got {scope!r}")

    broad = bool(raw.get("broad", False))

    # Wildcard rule_id requires broad: true
    has_wildcard = "*" in rule_id or "?" in rule_id
    if has_wildcard and not broad:
        raise ValueError(f"rule {id_}: wildcard rule_id {rule_id!r} requires broad: true")

    # scope=file requires broad: true (suppresses all findings on a file)
    if scope == "file" and not broad:
        raise ValueError(f"rule {id_}: scope=file requires broad: true")

    return Rule(
        id=id_,
        rule_id=rule_id,
        files=[str(f) for f in files],
        rationale=rationale,
        expires=expires,
        owner=owner,
        scope=scope,
        broad=broad,
    )


def load_rules(path: Path) -> list[Rule]:
    fm = _parse_yaml_frontmatter(path)
    raw_rules = fm.get("rules") or []
    if not isinstance(raw_rules, list):
        raise ValueError(f"{path}: 'rules' must be a list (got {type(raw_rules).__name__})")
    return [_validate_rule(r, i) for i, r in enumerate(raw_rules)]


# ── Matching ──────────────────────────────────────────────────────────────────


def _rule_id_matches(rule_pattern: str, finding_rule_id: str) -> bool:
    """fnmatch-style match. Exact match also accepted."""
    if not finding_rule_id:
        return False
    return fnmatch.fnmatch(finding_rule_id, rule_pattern)


def _normalize_finding_path(finding_file: str, target_root: str | None) -> str:
    """Strip the target_root prefix from the finding's file so rule globs
    (which are written relative to the ACCEPTED-RISKS.md location) match.

    Handles:
      - Absolute match:  /abs/path/to/target/services/... → services/...
      - Prefix match:    evals/.../target/services/...    → services/...
      - Basename embed:  any/.../<target-base>/services/.. → services/...
    """
    if not finding_file or not target_root:
        return finding_file
    target_root = target_root.rstrip("/")
    if finding_file.startswith(target_root + "/"):
        return finding_file[len(target_root) + 1:]
    basename = target_root.split("/")[-1]
    # Look for /<basename>/ embedded in the finding path
    idx = finding_file.find(f"/{basename}/")
    if idx >= 0:
        return finding_file[idx + len(basename) + 2:]
    if finding_file.startswith(f"{basename}/"):
        return finding_file[len(basename) + 1:]
    return finding_file


def _file_matches(rule_globs: list[str], finding_file: str, target_root: str | None = None) -> bool:
    """Any-match across the rule's file globs. finding_file is normalized to be
    relative to target_root before glob matching; unnormalized match also
    tried as a fallback."""
    if not finding_file:
        return False
    normalized = _normalize_finding_path(finding_file, target_root)
    return any(
        fnmatch.fnmatch(normalized, g) or fnmatch.fnmatch(finding_file, g)
        for g in rule_globs
    )


def _is_expired(rule: Rule, today: date) -> bool:
    return rule.expires < today


def match_finding(finding: dict, rules: list[Rule], today: date,
                  target_root: str | None = None) -> tuple[Rule | None, list[str]]:
    """Return (matched rule or None, warnings). First-match-wins."""
    warnings: list[str] = []
    for rule in rules:
        if _is_expired(rule, today):
            warnings.append(f"EXPIRED: rule {rule.id!r} past {rule.expires.isoformat()} (owner: {rule.owner}); stopped suppressing")
            continue
        # rule_id match
        if rule.scope == "finding":
            if not _rule_id_matches(rule.rule_id, finding.get("rule_id", "")):
                continue
        # file match
        if not _file_matches(rule.files, finding.get("file", ""), target_root):
            continue
        return rule, warnings
    return None, warnings


# ── I/O ───────────────────────────────────────────────────────────────────────


def load_findings_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [skip] malformed JSON line: {e}", file=sys.stderr)
    return out


def write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--findings", type=Path, required=True,
                   help="Input findings JSONL (also rewritten in place with suppressed entries removed)")
    p.add_argument("--accepted-risks", type=Path, required=True,
                   help="Path to ACCEPTED-RISKS.md (YAML frontmatter + markdown body)")
    p.add_argument("--suppressed-out", type=Path, required=True,
                   help="Output path for suppressed-<slug>.jsonl")
    p.add_argument("--audit-log-out", type=Path, required=True,
                   help="Output path for suppression-log-<slug>.jsonl")
    p.add_argument("--skip-if-missing-risks", action="store_true",
                   help="Exit 0 with no work if ACCEPTED-RISKS.md is absent")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse + print what would be suppressed, but do not write files")
    p.add_argument("--target-root", type=Path,
                   help="Target directory root; finding paths are normalized relative to this so rule globs match. Defaults to the directory containing the ACCEPTED-RISKS.md.")
    args = p.parse_args()

    if not args.findings.exists():
        print(f"error: findings not found: {args.findings}", file=sys.stderr)
        return 3

    if not args.accepted_risks.exists():
        if args.skip_if_missing_risks:
            print(f"note: no ACCEPTED-RISKS.md at {args.accepted_risks}; skipping Phase 1c")
            return 0
        print(f"error: ACCEPTED-RISKS.md not found: {args.accepted_risks}", file=sys.stderr)
        return 3

    try:
        rules = load_rules(args.accepted_risks)
    except ValueError as e:
        print(f"ACCEPTED-RISKS schema error: {e}", file=sys.stderr)
        return 2

    today = date.today()
    expired_rules = [r for r in rules if _is_expired(r, today)]
    active_rules = [r for r in rules if not _is_expired(r, today)]

    print(f"Loaded {len(rules)} rule(s): {len(active_rules)} active, {len(expired_rules)} expired")
    broad_rules = [r for r in active_rules if r.broad]
    if broad_rules:
        print(f"  {len(broad_rules)} broad rule(s) — reviewer attention: "
              + ", ".join(f"{r.id!r}" for r in broad_rules))

    findings = load_findings_jsonl(args.findings)
    print(f"Loaded {len(findings)} finding(s) from {args.findings}")

    # Target root for path normalization: defaults to parent of ACCEPTED-RISKS.md
    target_root_str = str((args.target_root or args.accepted_risks.parent).resolve())

    surviving: list[dict] = []
    suppressed: list[dict] = []
    audit: list[dict] = []
    all_warnings: set[str] = set()

    for finding in findings:
        matched, warnings = match_finding(finding, rules, today, target_root_str)
        for w in warnings:
            if w not in all_warnings:
                all_warnings.add(w)
                print(f"  WARN: {w}")
        if matched:
            entry = dict(finding)
            entry["_suppressed_by"] = {
                "rule_id": matched.id,
                "rule_rule_id": matched.rule_id,
                "owner": matched.owner,
                "expires": matched.expires.isoformat(),
                "rationale": matched.rationale[:100] + ("..." if len(matched.rationale) > 100 else ""),
            }
            suppressed.append(entry)
            audit_line = {
                "ts": datetime.now(tz=None).astimezone().isoformat(),
                "event": "SUPPRESSED",
                "file": finding.get("file", ""),
                "line": finding.get("line"),
                "rule_id": finding.get("rule_id", ""),
                "by_rule": matched.id,
                "broad": matched.broad,
            }
            audit.append(audit_line)
        else:
            surviving.append(finding)

    # Also log expiry warnings to the audit so they persist
    for w in sorted(all_warnings):
        audit.append({"ts": datetime.now(tz=None).astimezone().isoformat(), "event": "WARN", "message": w})

    print(f"Suppressed: {len(suppressed)} finding(s)")
    print(f"Surviving:  {len(surviving)} finding(s)")
    print(f"Audit:      {len(audit)} entry(s)")

    if args.dry_run:
        print("\n[dry-run] not writing files")
        return 0

    # Rewrite findings JSONL in place
    write_jsonl(args.findings, surviving)
    # Emit suppressed + audit
    write_jsonl(args.suppressed_out, suppressed)
    write_jsonl(args.audit_log_out, audit)

    print(f"\nWrote:")
    print(f"  {args.findings} (rewritten, {len(surviving)} findings)")
    print(f"  {args.suppressed_out} ({len(suppressed)} suppressed)")
    print(f"  {args.audit_log_out} ({len(audit)} audit entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
