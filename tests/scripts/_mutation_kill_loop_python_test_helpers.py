"""Shared fixture helpers for ``test_mutation_kill_loop_python*.py`` (#1604).

``test_mutation_kill_loop_python.py`` grew past the project's 500-line
guideline and was split into four scenario-focused files, mirroring the C#
loop's own #1564 split: mutmut invocation mechanics (kept in
``test_mutation_kill_loop_python.py``), ``run_for_file`` orchestration
(``test_mutation_kill_loop_python_orchestration.py``), verify/commit
subprocess wiring (``test_mutation_kill_loop_python_verify.py``), and CLI
dispatch (``test_mutation_kill_loop_python_cli.py``). ``_ctx``/``_junit``/
``_survived``/``_killed`` are used across more than one of those files, so
they are centralized here rather than duplicated — mirrors
``_mutation_kill_loop_test_helpers.py``'s own rationale for the C# split.

Named with a leading underscore (not ``conftest``) to match this directory's
existing convention for cross-file test helpers — see
``_mutation_test_helpers.py``'s own docstring for the rationale. This module
is a plain importable module, not a pytest plugin.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _mutation_test_helpers import SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_loop_python as loop  # noqa: E402


def _ctx(test_file: Path, source_file: Path, *, log=print, **overrides) -> "loop.RunContext":
    """Build a RunContext for these tests — a thin local convenience since
    the vast majority of tests here only vary test_file/source_file/log."""
    fields = {
        "test_file": test_file,
        "source_path": source_file,
        "test_command": "pytest",
        "log": log,
    }
    fields.update(overrides)
    return loop.RunContext(**fields)


def _junit(*testcases: str, failures: int = 0) -> str:
    body = "\n".join(testcases)
    return (
        '<?xml version="1.0" ?>\n'
        f'<testsuites errors="0" failures="{failures}" tests="{len(testcases)}">\n'
        f'<testsuite errors="0" failures="{failures}" name="mutmut" tests="{len(testcases)}">\n'
        f"{body}\n</testsuite></testsuites>\n"
    )


def _survived(name: str, file: str, line: int) -> str:
    return (
        f'<testcase name="{name}" file="{file}" line="{line}">'
        '<failure type="failure" message="bad_survived">diff</failure></testcase>'
    )


def _killed(name: str, file: str, line: int) -> str:
    return f'<testcase name="{name}" file="{file}" line="{line}"><system-out>x</system-out></testcase>'
