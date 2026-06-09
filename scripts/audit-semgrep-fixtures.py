#!/usr/bin/env python3
"""audit-semgrep-fixtures.py — measure the 36 custom semgrep rules (#124).

#118 made the rules-vs-prompts boundary structural at the CLASS level and shipped
a manifest audit that checks fixture *presence* but never runs semgrep. This
closes that gap for the security-assessment plugin's 36 custom rules: it ships a
positive + negative fixture per rule and MEASURES real behaviour by running
semgrep over them.

For every rule it determines:
  * WORKING      — semgrep compiles the rule AND the positive fixture fires.
  * PARSE-ERROR  — semgrep cannot compile the rule (e.g. a Python-only pattern
                   declared for `javascript`); the rule fires on nothing.
  * NO-FIRE      — the rule compiles but the positive does not fire (e.g. an
                   over-literal string-ellipsis pattern).
And the measured false-positive rate: fp_rate = (negative fixtures that fired) /
(negative fixtures), recorded in each rule's YAML `metadata.fp_rate`.

Gate (exit 1) on:
  * a rule missing a positive or negative fixture;
  * a WORKING rule whose measured fp_rate exceeds the policy's 0.10 ceiling
    (a negative fired) — the demotion trigger;
  * a rule that fires on nothing (PARSE-ERROR / NO-FIRE) and is NOT already
    recorded in known-broken-rules.txt — i.e. a regression, or a brand-new
    rule that was shipped broken;
  * a rule listed in known-broken-rules.txt that now WORKS — a stale entry that
    must be removed (so the list never hides a fixed rule).

The known-broken list pins the rules the measurement found already firing on
nothing (cross-language parse errors / unsupported string-ellipsis). Fixing
their grammar changes detection semantics, so it is tracked separately (#124
follow-up); the list keeps the gate honest in the meantime — every other rule's
positive MUST fire.

Usage: audit-semgrep-fixtures.py [--write] [--json]
  --write   stamp `fp_rate:` into each rule's metadata block (in place).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# This audit lives in the repo-root scripts/ (it is build/test tooling, not
# shipped with the plugin); the fixtures it measures live in the plugin tree.
ROOT = Path(__file__).resolve().parent.parent / "plugins" / "security-assessment"
RULES_DIR = ROOT / "knowledge" / "semgrep-rules"
FIX_DIR = ROOT / "knowledge" / "rule-fixtures"
KNOWN_BROKEN = FIX_DIR / "known-broken-rules.txt"
FP_CEILING = 0.10


def _load_known_broken() -> set[str]:
    if not KNOWN_BROKEN.is_file():
        return set()
    out = set()
    for line in KNOWN_BROKEN.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out
_ERR_RE = re.compile(r"Rule parse error in rule \S*?\.?([a-z0-9._-]+):", re.I)


def _run_semgrep(ruleset: Path):
    out = subprocess.run(
        ["semgrep", "--config", str(ruleset), "--json", "--quiet",
         "--no-git-ignore", "--disable-version-check", str(FIX_DIR)],
        capture_output=True, text=True)
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return set(), set()
    fired = set()           # (rule_id_suffix, path)
    for r in data.get("results", []):
        fired.add((r["check_id"].split(".")[-1] if "." in r["check_id"]
                   else r["check_id"], r["path"]))
        fired.add((r["check_id"], r["path"]))
    errored = set()         # rule-id suffixes that failed to compile
    for e in data.get("errors", []):
        m = _ERR_RE.search(e.get("message", ""))
        if m:
            errored.add(m.group(1))
    return fired, errored


def audit():
    rows = []
    fatal = []
    known_broken = _load_known_broken()
    seen_broken = set()
    for ruleset in sorted(RULES_DIR.glob("*.yaml")):
        fired, errored = _run_semgrep(ruleset)
        spec = yaml.safe_load(ruleset.read_text())
        for rule in spec.get("rules", []) or []:
            rid = rule["id"]
            d = FIX_DIR / rid
            pos = sorted(d.glob("positive.*")) if d.is_dir() else []
            neg = sorted(d.glob("negative.*")) if d.is_dir() else []
            if not pos or not neg:
                fatal.append(f"{rid}: missing fixtures (pos={len(pos)} neg={len(neg)})")
                rows.append({"rule": rid, "status": "MISSING-FIXTURE",
                             "fp_rate": None})
                continue

            def _fired(p):
                return (rid, str(p)) in fired or any(
                    cid.endswith(rid) and path == str(p) for cid, path in fired)

            pos_fires = any(_fired(p) for p in pos)
            neg_fired = [p for p in neg if _fired(p)]
            fp_rate = round(len(neg_fired) / len(neg), 4)

            # rid namespaced suffix match for parse errors
            parse_error = any(rid.endswith(e) or e.endswith(rid) for e in errored)
            if parse_error:
                status = "PARSE-ERROR"
            elif not pos_fires:
                status = "NO-FIRE"
            else:
                status = "WORKING"

            if status == "WORKING" and fp_rate > FP_CEILING:
                fatal.append(f"{rid}: measured fp_rate {fp_rate} exceeds "
                             f"{FP_CEILING} (negative fired) — demote candidate")
            if status in ("PARSE-ERROR", "NO-FIRE"):
                seen_broken.add(rid)
                if rid not in known_broken:
                    fatal.append(f"{rid}: positive fires on nothing ({status}) and "
                                 f"is not in known-broken-rules.txt — fix the rule "
                                 f"or record it as known-broken with justification")
            elif rid in known_broken:
                fatal.append(f"{rid}: listed in known-broken-rules.txt but now "
                             f"WORKS — remove it from the list")
            rows.append({"rule": rid, "status": status,
                         "fp_rate": fp_rate if status == "WORKING" else None})

    stale = known_broken - seen_broken - {r["rule"] for r in rows
                                          if r["status"] == "MISSING-FIXTURE"}
    for rid in sorted(stale):
        fatal.append(f"{rid}: in known-broken-rules.txt but not found among rules")
    return rows, fatal


def _stamp(rows):
    """Insert/update `fp_rate:` under each rule's metadata block (text-level so
    comments survive). fp_rate is only stamped for WORKING rules; broken rules
    get a `semgrep_status:` marker instead."""
    by_id = {r["rule"]: r for r in rows}
    for ruleset in sorted(RULES_DIR.glob("*.yaml")):
        lines = ruleset.read_text().splitlines()
        out = []
        cur = None
        for i, line in enumerate(lines):
            m = re.match(r"\s*- id:\s*(\S+)", line)
            if m:
                cur = m.group(1)
            out.append(line)
            # stamp right after the `metadata:` line for the current rule
            if re.match(r"\s*metadata:\s*$", line) and cur in by_id:
                indent = " " * (len(line) - len(line.lstrip()) + 2)
                r = by_id[cur]
                # skip if next lines already contain fp_rate (idempotent)
                follow = "\n".join(lines[i + 1:i + 12])
                if r["fp_rate"] is not None:
                    if "fp_rate:" not in follow:
                        # quoted string — semgrep's metadata schema rejects bare floats
                        out.append(f'{indent}fp_rate: "{r["fp_rate"]}"')
                else:
                    if "semgrep_status:" not in follow:
                        out.append(f'{indent}semgrep_status: "{r["status"].lower()}"')
        ruleset.write_text("\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rows, fatal = audit()
    if args.write:
        _stamp(rows)

    if args.json:
        print(json.dumps({"rules": rows, "fatal": fatal}, indent=2))
    else:
        print(f"{'STATUS':<14} {'FP':<6} RULE")
        for r in sorted(rows, key=lambda x: (x["status"], x["rule"])):
            fp = "-" if r["fp_rate"] is None else f"{r['fp_rate']}"
            print(f"{r['status']:<14} {fp:<6} {r['rule']}")
        broken = [r for r in rows if r["status"] in ("PARSE-ERROR", "NO-FIRE")]
        if broken:
            print(f"\n⚠ {len(broken)} rule(s) fire on nothing (fix candidates — "
                  "see #124): " + ", ".join(r["rule"] for r in broken))
        working = [r for r in rows if r["status"] == "WORKING"]
        print(f"\n{len(working)} working, {len(broken)} broken, "
              f"{len(rows)} total.")

    if fatal:
        print("\nFAIL:", file=sys.stderr)
        for f in fatal:
            print("  - " + f, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
