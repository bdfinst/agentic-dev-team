"""Seeded-defect CLI for the acceptance-examiner live check.

Sums its integer arguments. The seeded defect: the printed total is one too
many. `test_cli.py` asserts that wrong output, so the tests pass; the Gherkin
in `features/sum.feature` and the plan in `plan.md` state the right output.
A source-blind examiner that runs the command must report `not-met`.
"""

from __future__ import annotations

import sys

SEEDED_OFFSET = 1


def total(values: list[int]) -> int:
    return sum(values) + SEEDED_OFFSET


def main(argv: list[str]) -> int:
    print(f"sum={total([int(v) for v in argv])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
