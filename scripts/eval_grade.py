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

# Make the grader registry importable whether this module is run as a script
# (sys.path[0] is scripts/) or imported by a sibling (eval_variance/eval_ablation
# already insert scripts/ first, but this keeps the import robust either way).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_graders import (  # noqa: E402
    DEFAULT_GRADERS,
    get_grader,
    is_registered,
    registered_graders,
)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - io
        raise SystemExit(f"error: cannot read {path}: {exc}")


# --------------------------------------------------------------------------
# Grading — dispatched through the pluggable grader registry (issue #309).
# The `verdict` grader carries the original agent-verdict rules; `skill_gate`
# carries the advisory-skill (tlg-*) rules. New genres register a module in
# scripts/eval_graders/ — no edits here. See eval_graders/__init__.py.
# --------------------------------------------------------------------------


def _entry_grader(block: str, espec: dict) -> str:
    """Resolve the grader name for one expected entry.

    An explicit ``grader`` field wins; otherwise fall back to the block default
    (agents -> verdict, skills -> skill_gate) so pre-registry fixtures are
    unchanged.
    """
    return espec.get("grader", DEFAULT_GRADERS.get(block, "verdict"))


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
        has_integration = "integration" in spec
        if not (has_agents or has_skills or has_integration):
            problems.append(
                f"{ef.name}: declares neither applicableAgents, "
                f"applicableSkills, nor an integration block"
            )
        # Integration fixture manifests (#313): each integration entry must name
        # a frozen spec, a golden-repo snapshot, and a non-empty test-command
        # list — the runner needs all three to build and grade the worktree.
        for name, ispec in spec.get("integration", {}).items():
            if not isinstance(ispec, dict):
                problems.append(
                    f"{ef.name}: integration.{name} is not an object")
                continue
            for field in ("spec", "goldenRepo"):
                if not ispec.get(field):
                    problems.append(
                        f"{ef.name}: integration.{name} missing {field!r}")
            cmds = ispec.get("testCommands")
            if not isinstance(cmds, list) or not cmds:
                problems.append(
                    f"{ef.name}: integration.{name} needs a non-empty "
                    f"testCommands list")
        # Cross-check: agents block keys should match applicableAgents.
        for agent in spec.get("agents", {}):
            if agent not in spec.get("applicableAgents", []):
                problems.append(
                    f"{ef.name}: agents block has {agent!r} not in "
                    f"applicableAgents"
                )
        # Registry contract (#309): any explicit `grader` must be registered.
        for block in ("agents", "skills"):
            for name, espec in spec.get(block, {}).items():
                if not isinstance(espec, dict):
                    continue
                g = espec.get("grader")
                if g is not None and not is_registered(g):
                    problems.append(
                        f"{ef.name}: {block}.{name} declares unknown grader "
                        f"{g!r} (known: {', '.join(registered_graders())})"
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

        # Grade each block in registry order (agents, skills, integration).
        # Each entry's grader is resolved from the registry; an explicit
        # `grader` field overrides the per-block default. Adding a block type is
        # a DEFAULT_GRADERS entry — no new branch here.
        for block in DEFAULT_GRADERS:
            for name, espec in spec.get(block, {}).items():
                if only and name not in only:
                    continue  # diff-scoped run: this target did not change
                pair = f"{stem}::{name}"
                got = actual_entry.get(block, {}).get(name)
                if got is None:
                    # No recorded output. Only a failure if baseline expected it.
                    if baseline_pass is None or pair in baseline_pass:
                        results.append(
                            (pair, False, ["no actual output recorded"]))
                    continue
                grader_name = _entry_grader(block, espec)
                grader = get_grader(grader_name)
                if grader is None:
                    results.append(
                        (pair, False,
                         [f"unknown grader {grader_name!r} (known: "
                          f"{', '.join(registered_graders())})"]))
                    continue
                fails = grader(espec, got)
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
