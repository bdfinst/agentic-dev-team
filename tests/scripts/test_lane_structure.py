"""Source-text pins for the lane scripts.

These tests read the source of `lane*.py` and the PR hook, not behavior: what
the scripts may import, which function may touch the hook's private names, and
that the lane has wording for every rule the hook can log. They break on a
structural change, so they live apart from the behavior suites.
"""

from __future__ import annotations

import ast
import sys

import pytest
from lane_fixtures import LANE_SOURCES
from lane_fixtures_integrate import GATE_RELATIVE_PATH, PR_HOOK_PATH, load_pr_hook

from _repo_root import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lane


def private_attribute_users(source: str, receiver: str) -> dict[str, set[str]]:
    """Function name -> private attributes it reads off a variable named `receiver`."""
    users: dict[str, set[str]] = {}
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == receiver
                and node.attr.startswith("_")
            ):
                users.setdefault(function.name, set()).add(node.attr)
    return users


def test_there_are_lane_sources_to_scan():
    assert {path.name for path in LANE_SOURCES} >= {"lane.py", "lane_core.py"}


def test_the_hooks_private_names_are_used_in_one_function_only():
    users: dict[str, set[str]] = {}
    for path in LANE_SOURCES:
        users |= private_attribute_users(path.read_text(encoding="utf-8"), "hook")

    assert users == {"_review_gate_refusal": {"_evaluate_gate", "_GATE_FILE_NAME"}}


def gate_verdict_rules(source: str) -> set[str]:
    """The `matched_rule` literal of every rejecting `GateVerdict(...)` call.

    Fails on a call whose rule is not a string constant: a rule given by
    keyword, by variable, or left out (two positional arguments) would escape
    the wording table unseen. The one-argument accepting form
    `GateVerdict(True)` is the only call without a rule.
    """
    rules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "GateVerdict"
        ):
            continue
        accepting = (
            len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value is True
        )
        if accepting:
            continue
        rule = node.args[2] if len(node.args) >= 3 else None
        assert (
            rule is not None
            and not node.keywords
            and isinstance(rule, ast.Constant)
            and isinstance(rule.value, str)
        ), f"GateVerdict rule is not a string constant: {ast.unparse(node)}"
        rules.add(rule.value)
    return rules


@pytest.mark.parametrize(
    "call",
    [
        'GateVerdict(False, "m", rule)',
        'GateVerdict(False, "m", matched_rule="r")',
        'GateVerdict(False, "m")',
        "GateVerdict(passed=False)",
        "GateVerdict(False)",
    ],
)
def test_the_rule_scan_rejects_a_verdict_whose_rule_is_not_a_constant(call):
    with pytest.raises(AssertionError, match="not a string constant"):
        gate_verdict_rules(call)


def test_every_rule_the_hook_can_log_has_lane_wording():
    rules = gate_verdict_rules(PR_HOOK_PATH.read_text(encoding="utf-8"))

    assert rules == {
        "pre-pr-review",
        "gate-setup-failure-empty-digest",
        "registry-read-failure",
        "dispatch-failure-veto",
        "dispatch-ledger-read-failure",
        "dispatch-evidence-insufficient",
        "dispatch-evidence-stale",
        "dispatch-evidence-different-content",
        "dispatch-evidence-missing",
    }
    assert rules <= set(lane.GATE_RULE_WORDING)


@pytest.mark.parametrize(
    "name",
    [lane.GATE_FILE_NAME, GATE_RELATIVE_PATH.name],
    ids=["lane.GATE_FILE_NAME", "the fixtures' gate path"],
)
def test_the_gate_file_name_is_the_hooks(name):
    assert name == load_pr_hook()._GATE_FILE_NAME
