#!/usr/bin/env python3
"""make_toy_repo.py — scaffold the throwaway toy repo used by /harness-e2e-check's
Step 3/4 (a real `/build` run against a real plan, not a description of one).

Recreates the exact fixture first hand-built for issue #907's `/build` smoke
test: a two-slice plan (subtract, then multiply) where slice 1's own
IMPLEMENT instruction seeds a deliberate first-attempt bug, so the resulting
`/build` run genuinely exercises the repair loop (failure-class routing +
dead-end-non-fire) rather than asserting it exists.

By construction this fixture also reproduces three known, still-open SKILL.md
gaps (see references/watchlist.md): no branch is ever created (issue #916),
the module lives under `src/` with no `__init__.py` (issue #917), and slice 2
declares Invariants so the checkbox-ordering question (issue #915) is live.
Do not "fix" those properties out of the fixture — they are the bait.

Usage:
    python3 make_toy_repo.py --target /path/to/scratch/toy-repo
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

PLAN = """# Plan: Add subtract and multiply to calc.py

**Created**: {date}
**Branch**: build-smoke-test
**Status**: approved
**Gherkin persistence**: plan-file-only
**Scope enforcement**: freeze

## Goal

Add `subtract` and `multiply` functions to `src/calc.py`, exercising the full
`/build` per-behavior cycle including a deliberate repair iteration and slice-level
Invariants/Rollback point/Files.

## Acceptance Criteria

- [ ] `subtract(a, b)` returns `a - b`
- [ ] `multiply(a, b)` returns `a * b`

## Slices

### Slice 1: subtract

**Depends-on:** none
**Files:** `src/calc.py`, `tests/test_calc.py`

**Behavior:**

```gherkin
Feature: Subtraction

  Scenario: Subtract two positive integers
    Given the calculator module
    When subtract(5, 3) is called
    Then the result is 2

  Scenario: Subtract resulting in a negative number
    Given the calculator module
    When subtract(3, 5) is called
    Then the result is -2
```

**Steps:**

#### Step 1.1: Implement subtract with a deliberate first-attempt bug

**Complexity**: standard
**IMPLEMENT**: Add `subtract(a, b)` to `src/calc.py`. On your FIRST attempt,
deliberately implement it backwards as `return b - a` (a realistic off-by-one/
sign-inversion mistake) — this is intentional: the point of this smoke-test step
is to exercise the real repair loop, not to write correct code on the first try.
**TEST**: Write `tests/test_calc.py` covering both Gherkin scenarios above. Run
the full suite. The backwards implementation will fail the first scenario
(`subtract(5, 3)` returns -2, not 2). When it fails: classify the failure via
`${{CLAUDE_PLUGIN_ROOT}}/knowledge/failure-routing.md` (expect `behavioral-test`
class, inline-fix route), compute the failure signature, then fix the
implementation to `return a - b` and re-run. This second attempt should pass —
confirm the failure signature changed between iteration 1 and 2 (dead-end
detection must NOT fire here; it only fires on two *identical* consecutive
signatures). Paste the passing output before proceeding.
**REFACTOR**: Add a short docstring to `subtract` explaining the sign
convention (real cleanup, not a no-op — state in one line what you changed).
**Files**: `src/calc.py`, `tests/test_calc.py`
**Commit**: `feat: add subtract to calc module`

### Slice 2: multiply

**Depends-on:** 1
**Files:** `src/calc.py`, `tests/test_calc.py`
**Invariants:** `python3 -m pytest tests/ -q`
**Rollback point:** slice-start

**Behavior:**

```gherkin
Feature: Multiplication

  Scenario: Multiply two positive integers
    Given the calculator module
    When multiply(4, 3) is called
    Then the result is 12

  Scenario: Multiply by zero
    Given the calculator module
    When multiply(4, 0) is called
    Then the result is 0
```

**Steps:**

#### Step 2.1: Implement multiply

**Complexity**: standard
**IMPLEMENT**: Add `multiply(a, b)` to `src/calc.py`, implemented correctly on
the first attempt (no deliberate bug this time — this step exercises the plain
happy path so the run has both a repair-loop slice and a clean slice).
**TEST**: Write test covering both scenarios above. Run the full suite; paste
passing output.
**REFACTOR**: State in one line whether anything is worth cleaning up (a
no-op refactor is valid here — the mandate is the check, not a diff).
**Files**: `src/calc.py`, `tests/test_calc.py`
**Commit**: `feat: add multiply to calc module`

## Parallelization

```mermaid
graph TD
  S1[Slice 1] --> S2[Slice 2]
```

| Wave | Slices (parallel) |
|------|-------------------|
| 1 | 1 |
| 2 | 2 |

## Complexity Classification

Both steps are `standard`.

## Pre-PR Quality Gate

- [ ] All tests pass
- [ ] `/code-review` passes

## Risks & Open Questions

- None — this is a throwaway smoke-test plan for `/harness-e2e-check`, not a
  real feature.

## Build Progress

### Slices (grouped by wave)

#### Wave 1
- [ ] Slice 1: subtract
  - [ ] Step 1.1: Implement subtract with a deliberate first-attempt bug

#### Wave 2
- [ ] Slice 2: multiply
  - [ ] Step 2.1: Implement multiply
"""

CALC_PY = '''"""A tiny calculator module for the /harness-e2e-check smoke test."""


def add(a, b):
    return a + b
'''


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def scaffold(target: Path, date: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "src").mkdir(exist_ok=True)
    (target / "tests").mkdir(exist_ok=True)
    (target / "plans").mkdir(exist_ok=True)

    (target / "src" / "calc.py").write_text(CALC_PY, encoding="utf-8")
    (target / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (target / "plans" / "calc-ops.md").write_text(PLAN.format(date=date), encoding="utf-8")

    _run(["git", "init", "-q"], target)
    _run(["git", "config", "user.email", "harness-e2e-check@example.invalid"], target)
    _run(["git", "config", "user.name", "harness-e2e-check"], target)
    _run(["git", "add", "-A"], target)
    _run(["git", "commit", "-q", "-m", "chore: initial toy repo for /harness-e2e-check smoke test"], target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path, help="Directory to scaffold into (created if missing)")
    parser.add_argument("--date", default="1970-01-01", help="Date string stamped into the plan header (cosmetic only)")
    args = parser.parse_args()

    scaffold(args.target, args.date)
    print(f"Scaffolded toy repo at {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
