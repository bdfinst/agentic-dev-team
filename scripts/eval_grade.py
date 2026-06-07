#!/usr/bin/env python3
"""Deterministic eval grader — the reusable core behind the CI agent-eval gate.

This is the scriptable extraction of the grading rules described in
`plugins/dev-team/skills/agent-eval/SKILL.md` (Step 4). The /agent-eval skill
*dispatches* agents (which requires a model); this grader takes the agents'
recorded outputs ("actuals") and grades them against `evals/expected/*.json`
exactly, with no judgment. Keeping grading deterministic and model-free is what
lets it run as a CI gate (issue #99) and lets #101/#103/#108/#110 reuse it.

Inputs
------
--expected-dir DIR   Directory of expected/*.json (default: evals/expected).
--actuals FILE       JSON mapping fixture stem -> recorded outputs:
                       {
                         "<stem>": {
                           "agents": {
                             "<agent>": {"status": "...",
                                          "issues": [{"severity": "...",
                                                      "message": "..."}],
                                          "summary": "..."}
                           },
                           "skills": {
                             "<skill>": {"report": "full text",
                                          "gates": ["A"], "layers": ["unit"]}
                           }
                         }
                       }
--baseline FILE      Optional JSON: {"passing": ["<stem>::<agent>", ...]}.
                     Any pair listed there that now FAILS is a regression and
                     forces a non-zero exit. Missing baseline => any failure
                     fails the run.

Modes
-----
--check-corpus       Structural mode (no actuals needed): assert every
                     expected/*.json is schema-valid and pairs with a fixture.
                     This is the model-free gate that always runs in CI.

Exit codes
----------
0  all graded pairs pass (or, with baseline, no baseline-passing pair regressed)
1  a regression / failure was detected (readable diff on stdout)
2  usage / corpus-integrity error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - io
        raise SystemExit(f"error: cannot read {path}: {exc}")


def _in_range(n: int, rng: dict) -> bool:
    lo = rng.get("min", 0)
    hi = rng.get("max", float("inf"))
    return lo <= n <= hi


def _mentions(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


# --------------------------------------------------------------------------
# Grading — mirrors SKILL.md Step 4, deterministically.
# --------------------------------------------------------------------------

def grade_agent(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []

    exp_status = spec.get("expectedStatus")
    got_status = actual.get("status")
    if exp_status is not None and got_status != exp_status:
        fails.append(f"status: expected {exp_status!r}, got {got_status!r}")

    issues = actual.get("issues", []) or []
    if "issueCount" in spec and not _in_range(len(issues), spec["issueCount"]):
        rng = spec["issueCount"]
        fails.append(
            f"issueCount: expected {rng.get('min', 0)}-{rng.get('max', '∞')}, "
            f"got {len(issues)}"
        )

    for sev, rng in spec.get("severities", {}).items():
        count = sum(1 for i in issues if i.get("severity") == sev)
        if not _in_range(count, rng):
            fails.append(
                f"severities.{sev}: expected {rng.get('min', 0)}-"
                f"{rng.get('max', '∞')}, got {count}"
            )

    text = " ".join(str(i.get("message", "")) for i in issues)
    text += " " + str(actual.get("summary", ""))
    for kw in spec.get("mustMention", []):
        if not _mentions(text, kw):
            fails.append(f"mustMention: missing {kw!r}")
    for kw in spec.get("mustNotMention", []):
        if _mentions(text, kw):
            fails.append(f"mustNotMention: found forbidden {kw!r}")

    return fails


def grade_skill(spec: dict, actual: dict) -> list[str]:
    fails: list[str] = []
    got_gates = set(actual.get("gates", []) or [])
    for g in spec.get("expectedGates", []):
        if g not in got_gates:
            fails.append(f"gate: expected gate {g!r} to fire")
    got_layers = set(actual.get("layers", []) or [])
    for layer in spec.get("expectedLayers", []):
        if layer not in got_layers:
            fails.append(f"layer: expected layer {layer!r}")

    report = str(actual.get("report", ""))
    for kw in spec.get("mustMention", []):
        if not _mentions(report, kw):
            fails.append(f"mustMention: missing {kw!r}")
    for kw in spec.get("mustNotMention", []):
        if _mentions(report, kw):
            fails.append(f"mustNotMention: found forbidden {kw!r}")
    return fails


# --------------------------------------------------------------------------
# Corpus integrity (model-free CI gate).
# --------------------------------------------------------------------------

def check_corpus(expected_dir: Path, fixtures_dir: Path):
    """Return (fatal_problems, warnings).

    Fatal = a contract the grader cannot tolerate (invalid JSON, missing
    'fixture' key, no applicable* target, agents-block/applicableAgents
    drift). Warnings = a missing fixture FILE for an expected JSON — flagged
    but non-fatal so a pre-existing corpus gap does not red-line the gate.
    """
    problems: list[str] = []
    warnings: list[str] = []
    expected_files = sorted(expected_dir.glob("*.json"))
    if not expected_files:
        problems.append(f"no expected/*.json found in {expected_dir}")

    # Pairing is by stem (SKILL.md Step 2: "Match the fixture stem — filename
    # without extension — to its expected JSON; for directory fixtures the
    # directory name is the stem"). Python's .stem strips one extension, which
    # matches the corpus convention expected = fixture-with-final-ext→.json
    # (e.g. fixture sv-x.svelte.ts -> expected sv-x.svelte.json).
    fixture_stems = set()
    if fixtures_dir.is_dir():
        for p in fixtures_dir.iterdir():
            fixture_stems.add(p.name if p.is_dir() else p.stem)

    for ef in expected_files:
        try:
            spec = json.loads(ef.read_text())
        except json.JSONDecodeError as exc:
            problems.append(f"{ef.name}: invalid JSON ({exc})")
            continue

        stem = ef.stem  # canonical stem == expected filename without .json
        if not spec.get("fixture"):
            problems.append(f"{ef.name}: missing 'fixture' key")
        has_agents = "applicableAgents" in spec or "agents" in spec
        has_skills = "applicableSkills" in spec or "skills" in spec
        if not (has_agents or has_skills):
            problems.append(
                f"{ef.name}: declares neither applicableAgents nor "
                f"applicableSkills"
            )
        # Cross-check: agents block keys should match applicableAgents.
        for agent in spec.get("agents", {}):
            if agent not in spec.get("applicableAgents", []):
                problems.append(
                    f"{ef.name}: agents block has {agent!r} not in "
                    f"applicableAgents"
                )
        if fixture_stems and stem not in fixture_stems:
            warnings.append(
                f"{ef.name}: no fixture file/dir with stem {stem!r} in "
                f"{fixtures_dir}"
            )
    return problems, warnings


# --------------------------------------------------------------------------
# Run grading against actuals.
# --------------------------------------------------------------------------

def run_grading(expected_dir: Path, actuals: dict, baseline: dict | None,
                only: set | None = None):
    baseline_pass = set(baseline.get("passing", [])) if baseline else None
    results = []  # (pair, passed, fails)
    for ef in sorted(expected_dir.glob("*.json")):
        spec = json.loads(ef.read_text())
        stem = ef.stem  # canonical stem (matches --check-corpus pairing)
        actual_entry = actuals.get(stem, {})

        for agent, aspec in spec.get("agents", {}).items():
            if only and agent not in only:
                continue  # diff-scoped run: this agent did not change
            pair = f"{stem}::{agent}"
            got = actual_entry.get("agents", {}).get(agent)
            if got is None:
                # No recorded output. Only a failure if baseline expected it.
                if baseline_pass is None or pair in baseline_pass:
                    results.append((pair, False, ["no actual output recorded"]))
                continue
            fails = grade_agent(aspec, got)
            results.append((pair, not fails, fails))

        for skill, sspec in spec.get("skills", {}).items():
            if only and skill not in only:
                continue  # diff-scoped run: this skill did not change
            pair = f"{stem}::{skill}"
            got = actual_entry.get("skills", {}).get(skill)
            if got is None:
                if baseline_pass is None or pair in baseline_pass:
                    results.append((pair, False, ["no actual output recorded"]))
                continue
            fails = grade_skill(sspec, got)
            results.append((pair, not fails, fails))

    return results, baseline_pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected-dir", default="evals/expected")
    ap.add_argument("--fixtures-dir", default="evals/fixtures")
    ap.add_argument("--actuals")
    ap.add_argument("--baseline")
    ap.add_argument("--quarantine",
                    help="quarantine.json (#231): flaky pairs that fail but must "
                         "not block — informs, does not gate")
    ap.add_argument("--only", default="",
                    help="comma-separated agent/skill names to grade "
                         "(diff-scoped run); empty means all")
    ap.add_argument("--write-baseline", metavar="PATH",
                    help="write a baseline.json of all currently-passing pairs "
                         "to PATH (use with --actuals; records the pass set)")
    ap.add_argument("--check-corpus", action="store_true")
    args = ap.parse_args(argv)

    expected_dir = Path(args.expected_dir)
    if not expected_dir.is_dir():
        print(f"error: expected dir not found: {expected_dir}", file=sys.stderr)
        return 2

    if args.check_corpus:
        problems, warnings = check_corpus(expected_dir, Path(args.fixtures_dir))
        for w in warnings:
            print(f"  ⚠ {w}")
        if problems:
            print("Eval corpus integrity FAILED:")
            for p in problems:
                print(f"  ✗ {p}")
            return 2
        n = len(list(expected_dir.glob("*.json")))
        print(
            f"Eval corpus OK: {n} expected fixtures valid"
            f"{f' ({len(warnings)} missing-fixture warning(s))' if warnings else ''}."
        )
        return 0

    if not args.actuals:
        print("error: --actuals required unless --check-corpus", file=sys.stderr)
        return 2

    actuals = _load_json(Path(args.actuals))
    baseline = _load_json(Path(args.baseline)) if args.baseline else None
    quarantined: set = set()
    if args.quarantine and Path(args.quarantine).exists():
        q = _load_json(Path(args.quarantine))
        quarantined = set(q.get("quarantine", []) if isinstance(q, dict) else q)

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    results, baseline_pass = run_grading(expected_dir, actuals, baseline, only)
    if only:
        print(f"(diff-scoped to: {', '.join(sorted(only))})\n")

    if args.write_baseline:
        target = Path(args.write_baseline)
        # Merge into an existing baseline so a diff-scoped run tops up rather
        # than clobbers. Pairs graded this run are updated (passing added,
        # failing removed); pairs outside this run's scope are left untouched.
        existing = set()
        if target.exists():
            try:
                existing = set(json.loads(target.read_text()).get("passing", []))
            except (OSError, json.JSONDecodeError):
                existing = set()
        graded_pass = {p for p, ok, _ in results if ok}
        graded_fail = {p for p, ok, _ in results if not ok}
        merged = (existing | graded_pass) - graded_fail
        from datetime import datetime, timezone
        target.write_text(json.dumps({
            "_comment": "Regression baseline for the agent-eval CI gate (#99). "
                        "Pairs listed here must not regress. Update with "
                        "eval_grade.py --actuals <f> --write-baseline (merges "
                        "into this file: passing pairs added, pairs tested-but-"
                        "failing removed, untested pairs kept).",
            # Stamped 'measured' because this baseline came from grading a real
            # actuals.json run, distinguishing it from a hand-authored seed (#133).
            "provenance": "measured",
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "passing": sorted(merged),
        }, indent=2) + "\n")
        added = sorted(graded_pass - existing)
        removed = sorted(existing & graded_fail)
        print(f"Baseline merged → {target}: {len(merged)} total "
              f"(+{len(added)} added, -{len(removed)} removed)")
        if added:
            print("  added:   " + ", ".join(added))
        if removed:
            print("  removed: " + ", ".join(removed))
        return 0

    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]

    print(f"# Eval grade — {len(passed)}/{len(results)} pairs passed\n")
    if failed:
        print("## Failures")
        for pair, _, fails in failed:
            regressed = baseline_pass is not None and pair in baseline_pass
            if regressed and pair in quarantined:
                tag = " [QUARANTINED]"
            elif regressed:
                tag = " [REGRESSION]"
            else:
                tag = ""
            print(f"  ✗ {pair}{tag}")
            for f in fails:
                print(f"      - {f}")

    # Determine exit: with a baseline, only baseline-passing regressions block —
    # and a quarantined (flaky) pair informs but never blocks (#231).
    if baseline_pass is not None:
        regressions = [p for p, ok, _ in results
                       if not ok and p in baseline_pass and p not in quarantined]
        ignored = [p for p, ok, _ in results
                   if not ok and p in baseline_pass and p in quarantined]
        if ignored:
            print(f"\n{len(ignored)} baseline pair(s) failed but are quarantined "
                  f"(flaky) — not blocking.")
        if regressions:
            print(f"\n{len(regressions)} regression(s) against baseline.")
            return 1
        print("\nNo regressions against baseline.")
        return 0

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
