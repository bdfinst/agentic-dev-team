"""Shipped docs must invoke Python scripts with python3, not bash (issue #777).

ADR 0014/0015 ported every shipped `plugins/dev-team/` script from bash to
Python (epic #572). A handful of skill/agent docs still instruct the reader
to run the resulting `.py` file with a `bash` prefix — bash then executes
the module docstring as shell, failing immediately. This is a doc-drift
sensor sibling to `tests/repo/test_bash_removal_stale_sh_refs.py` (which
guards stale `.sh` *filenames* in prose): this test guards the *interpreter
prefix* used to invoke a `.py` file, with a generic regex scan rather than
an itemized table, so any future occurrence is caught by construction
instead of only hand-listed ones.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

BASH_INVOKES_PY = re.compile(r"\bbash\s+\S*\.py\b")


def _find_violations(paths: list[Path]) -> list[str]:
    violations = []
    for path in paths:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if BASH_INVOKES_PY.search(line):
                violations.append(f"{path}:{lineno}: {line.strip()}")
    return violations


def _shipped_doc_paths() -> list[Path]:
    return sorted(PLUGIN_ROOT.glob("skills/**/SKILL.md")) + sorted(
        PLUGIN_ROOT.glob("agents/**/*.md")
    )


def test_no_bash_invokes_python_in_shipped_docs() -> None:
    violations = _find_violations(_shipped_doc_paths())
    assert not violations, "bash-invokes-python found in shipped docs:\n" + "\n".join(
        violations
    )


def test_correctly_invoked_scripts_are_not_flagged(tmp_path: Path) -> None:
    fixture = tmp_path / "clean.md"
    fixture.write_text(
        "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_waves.py <plan-file>\n"
        "bash ${CLAUDE_PLUGIN_ROOT}/install.sh\n"
    )
    assert _find_violations([fixture]) == []


def test_scanner_detects_a_synthetic_violation(tmp_path: Path) -> None:
    fixture = tmp_path / "dirty.md"
    fixture.write_text("bash ${CLAUDE_PLUGIN_ROOT}/scripts/whatever.py\n")
    violations = _find_violations([fixture])
    assert violations == [
        f"{fixture}:1: bash ${{CLAUDE_PLUGIN_ROOT}}/scripts/whatever.py"
    ]


def test_scanner_aggregates_across_multiple_lines_and_files(tmp_path: Path) -> None:
    first = tmp_path / "a.md"
    first.write_text("intro\nbash ${CLAUDE_PLUGIN_ROOT}/scripts/one.py\n")
    second = tmp_path / "b.md"
    second.write_text("bash ${CLAUDE_PLUGIN_ROOT}/scripts/two.py\n")
    violations = _find_violations([first, second])
    assert violations == [
        f"{first}:2: bash ${{CLAUDE_PLUGIN_ROOT}}/scripts/one.py",
        f"{second}:1: bash ${{CLAUDE_PLUGIN_ROOT}}/scripts/two.py",
    ]


def test_scanner_does_not_match_pyc_or_embedded_py_substrings(tmp_path: Path) -> None:
    fixture = tmp_path / "near_miss.md"
    fixture.write_text(
        "bash ${CLAUDE_PLUGIN_ROOT}/scripts/whatever.pyc\n"
        "notbash ${CLAUDE_PLUGIN_ROOT}/scripts/whatever.py\n"
    )
    assert _find_violations([fixture]) == []
