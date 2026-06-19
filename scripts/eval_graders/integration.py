"""The `integration` grader (issue #313).

Every other grader scores a *single agent's output in isolation* — unit-level
verification ("did the reviewer flag the right thing?"). The integration grader
answers the *validation* question instead: does a plan from our orchestrator
yield code that actually compiles and whose tests pass?

The model-dependent work — dispatching the orchestrator in an ephemeral git
worktree built from the fixture's golden-repo snapshot, running the fixture's
test commands, capturing exit codes — is the runner's job
(``scripts/run-integration-eval.sh``). This grader stays deterministic and
model-free, like every other registered grader: it grades the *recorded* command
results against the fixture's ``testCommands`` manifest.

Verdict: every declared command must have a recorded result that exited 0. Any
non-zero exit (or a command with no recorded result) is a FAIL, reported with
the command, its exit code, and the first line of its stderr.

Recorded ``actual`` shape::

    {
      "results": [
        {"command": "npm test", "exit_code": 0, "stderr_first_line": ""},
        ...
      ]
    }
"""

from __future__ import annotations


def grade_integration(spec: dict, actual: dict) -> list[str]:
    """Return a list of check-failure strings; empty list == PASS."""
    fails: list[str] = []

    expected_cmds = spec.get("testCommands", []) or []
    if not expected_cmds:
        fails.append("integration: fixture declares no testCommands")
        return fails

    results = {}
    for r in actual.get("results", []) or []:
        if isinstance(r, dict) and "command" in r:
            results[r["command"]] = r

    for cmd in expected_cmds:
        r = results.get(cmd)
        if r is None:
            fails.append(f"integration: no result recorded for command {cmd!r}")
            continue
        code = r.get("exit_code")
        if code != 0:
            stderr = str(r.get("stderr_first_line", "")).strip()
            tail = f" — {stderr}" if stderr else ""
            fails.append(f"integration: command {cmd!r} exited {code}{tail}")

    return fails
