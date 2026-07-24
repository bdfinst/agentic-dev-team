"""#252 — GETTING-STARTED.md must list /specs as a workflow command and
position the primary lifecycle commands ahead of the "Invoke a skill
directly" section. Documentation gate.

Ported from tests/docs/getting_started_workflow_commands_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import pytest

from _repo_root import REPO_ROOT

DOC = REPO_ROOT / "GETTING-STARTED.md"


@pytest.fixture(scope="module")
def lines() -> list[str]:
    return DOC.read_text(encoding="utf-8").splitlines()


def test_workflow_commands_block_lists_specs_as_lifecycle_entry_point(
    lines: list[str],
) -> None:
    # The /specs line must live inside the workflow-commands fenced block,
    # not only in the skill-invocation examples.
    in_section = False
    found = False
    for line in lines:
        if line.startswith("### Use the workflow commands"):
            in_section = True
            continue
        if in_section and line.startswith("### Invoke a skill directly"):
            in_section = False
        if in_section and line.startswith("/specs"):
            found = True
    assert found


def test_workflow_commands_section_appears_before_invoke_skill_directly(
    lines: list[str],
) -> None:
    workflow_line = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith("### Use the workflow commands")
        ),
        None,
    )
    invoke_line = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith("### Invoke a skill directly")
        ),
        None,
    )
    assert workflow_line is not None
    assert invoke_line is not None
    assert workflow_line < invoke_line


def test_primary_lifecycle_commands_remain_documented() -> None:
    text = DOC.read_text(encoding="utf-8")
    for cmd in ("/specs", "/plan", "/build", "/pr", "/code-review", "/triage"):
        assert cmd in text, f"missing: {cmd}"
