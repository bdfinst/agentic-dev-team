"""Content checks for stryker-xunit-v2-shim/SKILL.md.

Covers the read-before-edit preamble and converged-state check (#1773), the
canonical bash invocations that exist to cut command-retry churn (#1777), and
the operator remediation gate (#1791).
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

SKILL = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "skills"
    / "stryker-xunit-v2-shim"
    / "SKILL.md"
)


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_read_before_edit_list_names_all_three_artifacts_together() -> None:
    text = _text()
    for phrase in ("mutant-survivors report", "shim config", "step files"):
        assert phrase in text, f"read-before-edit list is missing {phrase!r}"

    idx1 = text.index("mutant-survivors report")
    idx2 = text.index("shim config")
    idx3 = text.index("step files")
    span_start = min(idx1, idx2, idx3)
    span_end = max(idx1, idx2, idx3)
    assert span_end - span_start < 500, (
        "the three read-before-edit items should be co-located in one list, "
        "not scattered across the file"
    )


def test_converged_state_skip_instruction_present() -> None:
    text = _text().lower()
    assert "converged-state" in text or "converged state" in text, (
        "missing a converged-state check instruction"
    )
    assert "skip re-editing" in text, (
        "missing the instruction to skip re-editing a file already at its target state"
    )


# --- canonical bash invocations (#1777) -------------------------------------
#
# The churn this cuts was measured, not guessed: 25 retried bash commands and 26
# Bash tool errors against this skill's workflow, with zero repeated verify runs
# ruling out a test-retry loop. The value is entirely in the commands being
# present, correct, and pasteable, so each of those three is pinned.


def _bash_blocks() -> list[str]:
    return re.findall(r"```bash\n(.*?)```", _text(), re.DOTALL)


def test_canonical_invocations_section_exists() -> None:
    assert "## Canonical invocations" in _text(), (
        "the copy-pasteable invocation section (#1777) is gone"
    )


def test_the_one_correct_mutation_run_is_spelled_out() -> None:
    blocks = "\n".join(_bash_blocks())
    assert "cd tests/<TestProject>.Mutation" in blocks, (
        "the shim-directory cd — the single most retried step — is missing"
    )
    assert "dotnet-stryker" in blocks


def test_the_no_shim_floor_command_is_given() -> None:
    blocks = "\n".join(_bash_blocks())
    assert "dotnet-stryker -t mtp" in blocks


def test_coverage_analysis_is_never_offered_as_a_cli_flag() -> None:
    # It is config-file-only in Stryker.NET; presenting it as a flag manufactures
    # exactly the failed-command-then-retry cycle #1777 measured. It may appear
    # only inside the don't-do-this table.
    for block in _bash_blocks():
        assert "--coverage-analysis" not in block, (
            "a runnable example offers --coverage-analysis, which does not exist"
        )
    assert "config-file-only" in _text()


def test_the_wrong_forms_table_names_the_root_run_and_the_solution_trap() -> None:
    text = _text()
    assert "solution mode" in text
    assert "--solution" in text
    assert "SolutionPath trap" in text


# --- operator remediation gate (#1791) --------------------------------------


def test_operator_gate_step_is_documented() -> None:
    assert "Step 1a" in _text(), "the always-ask operator gate step is missing"


@pytest.mark.parametrize("choice", ["port", "exclude", "skip", "degrade"])
def test_all_four_remediation_options_are_documented(choice: str) -> None:
    assert f"`{choice}`" in _text(), f"remediation option {choice!r} is undocumented"


def test_the_gate_is_described_as_enforced_not_advisory() -> None:
    text = _text()
    assert "recorded" in text, (
        "the gate's enforcement mechanism (a recorded choice) is undocumented, "
        "leaving it as prose an agent can skip"
    )
    assert "blocks" in text


def test_the_skill_no_longer_tells_the_agent_to_decide_alone() -> None:
    # The pre-#1791 text said to "say so and stop rather than forcing it" on a
    # heavy AutoFixture suite — i.e. the agent silently picking one of the four
    # options. That instruction must not come back.
    text = _text()
    assert "stop rather than forcing it" not in text
    assert "it is theirs to pick" in text or "operator" in text
