"""The `tests_pass` grader: after a write-capable agent's trial, do the fixture's tests pass?

For `software-engineer` and `mutation-kill`. The harness runs the spec's
`testCommands` in the trial's sandbox copy once the agent has finished, after
restoring the grader-owned paths (`protectedPaths`) from the pristine fixture, so
an agent cannot pass by editing the tests that judge it. This grader reads those
recorded exit codes; the rules are the `integration` grader's.

Recorded ``actual`` shape::

    {"results": [{"command": "...", "exit_code": 0, "stderr_first_line": ""}]}
"""

from __future__ import annotations

from .integration import grade_integration


def grade_tests_pass(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    return grade_integration(spec, actual, label="tests_pass")
