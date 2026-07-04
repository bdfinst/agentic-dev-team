"""Regression coverage for the workflow-audit fixes in issue #531:
  - plugin-tests.yml renamed from "Tests" to "Plugin tests"
  - agent-eval.yml renamed from "Eval" to "Agent eval" AND its
    structural-gate job delegates two commands through
    `bash scripts/ci-local.sh --only=chk_eval_corpus,chk_citation_lint`
    rather than invoking them directly
  - link-check.yml documents the intentional local/CI split for
    chk_nav_integrity

These assertions guard against a silent revert of the rename or a
refactor that reintroduces the drift between ci-local.sh and the CI job.

Ported from tests/repo/workflow-audit-531.bats (issue #672).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_TESTS = REPO_ROOT / ".github" / "workflows" / "plugin-tests.yml"
AGENT_EVAL = REPO_ROOT / ".github" / "workflows" / "agent-eval.yml"
LINK_CHECK = REPO_ROOT / ".github" / "workflows" / "link-check.yml"


# ---------------------------------------------------------------------------
# Slice 1 — plugin-tests.yml workflow name
# ---------------------------------------------------------------------------


def test_531_1_1a_plugin_tests_yml_declares_name_plugin_tests() -> None:
    text = PLUGIN_TESTS.read_text()
    assert len(re.findall(r"^name: Plugin tests$", text, flags=re.MULTILINE)) == 1


def test_531_1_1b_plugin_tests_yml_no_longer_declares_name_tests() -> None:
    text = PLUGIN_TESTS.read_text()
    assert len(re.findall(r"^name: Tests$", text, flags=re.MULTILINE)) == 0


# ---------------------------------------------------------------------------
# Slice 2 — agent-eval.yml workflow name + structural-gate delegation
# ---------------------------------------------------------------------------


def _structural_gate_block() -> str:
    """Extract the `structural-gate:` job block only. Range starts at the job
    heading and ends just before the next `  <name>:` job heading at the same
    indent level. Used to scope assertions so they don't accidentally match on
    other jobs in the same file.

    Boundary regex tolerates lowercase, uppercase, digits, underscore, and
    dash so a future job like `slice2-gate:` or `structural_gate_v2:` still
    terminates the range correctly. Assumes canonical 2-space YAML indent.

    Callers must invoke `_assert_gate_block_present(block)` before running
    negative assertions on the output — an empty block (job renamed away)
    would trivially satisfy any zero-match check and silently mask a
    regression.
    """
    lines = AGENT_EVAL.read_text().splitlines()
    collected: list[str] = []
    in_block = False
    heading = re.compile(r"^  [A-Za-z0-9_-]+:\s*(#.*)?$")
    for line in lines:
        if line.startswith("  structural-gate:"):
            in_block = True
            continue
        if in_block and heading.match(line):
            in_block = False
        if in_block:
            collected.append(line)
    return "\n".join(collected)


def _assert_gate_block_present(block: str) -> None:
    assert block, "structural-gate: block not found in agent-eval.yml — job renamed?"


def test_531_2_1a_agent_eval_yml_declares_name_agent_eval() -> None:
    text = AGENT_EVAL.read_text()
    assert len(re.findall(r"^name: Agent eval$", text, flags=re.MULTILINE)) == 1


def test_531_2_1b_agent_eval_yml_no_longer_declares_name_eval() -> None:
    text = AGENT_EVAL.read_text()
    assert len(re.findall(r"^name: Eval$", text, flags=re.MULTILINE)) == 0


def test_531_2_1c_structural_gate_has_exactly_one_only_chk_eval_corpus_step() -> None:
    block = _structural_gate_block()
    _assert_gate_block_present(block)
    assert block.count("--only=chk_eval_corpus") == 1


def test_531_2_1d_structural_gate_has_exactly_one_only_chk_citation_lint_step() -> None:
    block = _structural_gate_block()
    _assert_gate_block_present(block)
    assert block.count("--only=chk_citation_lint") == 1


def test_531_2_1e_structural_gate_no_longer_invokes_eval_grade_py_check_corpus_directly() -> (
    None
):
    block = _structural_gate_block()
    _assert_gate_block_present(block)
    assert block.count("scripts/eval_grade.py --check-corpus") == 0


def test_531_2_1f_structural_gate_no_longer_invokes_citation_lint_py_all_directly() -> (
    None
):
    block = _structural_gate_block()
    _assert_gate_block_present(block)
    assert block.count("scripts/citation_lint.py --all") == 0


def test_531_2_1g_structural_gate_preserves_the_pytest_step_running_test_eval_grader_py() -> (
    None
):
    block = _structural_gate_block()
    _assert_gate_block_present(block)
    assert block.count("test_eval_grader.py") >= 1


# ---------------------------------------------------------------------------
# Slice 3 — link-check.yml documents its intentional local/CI split
# ---------------------------------------------------------------------------


def test_531_3_1a_link_check_yml_references_chk_nav_integrity_the_local_counterpart() -> (
    None
):
    text = LINK_CHECK.read_text()
    assert text.count("chk_nav_integrity") >= 1


def test_531_3_1b_link_check_yml_names_mkdocs_as_a_ci_only_tool() -> None:
    text = LINK_CHECK.read_text().lower()
    assert text.count("mkdocs") >= 1


def test_531_3_1c_link_check_yml_names_lychee_as_a_ci_only_tool() -> None:
    text = LINK_CHECK.read_text().lower()
    assert text.count("lychee") >= 1


def test_531_3_1d_link_check_yml_has_a_relationship_to_the_local_gate_block() -> None:
    # Guards the doctrine itself: the previous three assertions could pass on
    # inline mentions alone. This one requires the header block that names
    # chk_nav_integrity as the LOCAL counterpart and mkdocs/lychee as the
    # CI-only additions. Deleting the top-of-file comment (the review flagged
    # this as a vacuous-test risk) fails HERE, not silently.
    text = LINK_CHECK.read_text()
    assert re.search(r"^# Relationship to the local gate", text, flags=re.MULTILINE)
    assert "chk_nav_integrity" in text
    assert "CI-only" in text
