"""Doc-content contract for the mutation-kill agent's opt-in
``--skip-static-mutants`` flag (#1907, Slice 2, Step 2.1 of
plans/mutation-kill-batch-hardening-1906-1910.md).

Mirrors the grep-on-section pattern already used in
``test_mutation_kill_line_clustering_doc.py`` and
``test_mutation_kill_feasibility_gate_doc.py`` — pure text assertions over
shipped agent prose, no state-mutating filesystem/git operations. Reuses
``skill_doc_helpers.collapsed()`` for whitespace-reflow-proof flattening
rather than a hand-rolled ``.replace("\\n", " ")`` (correctness-review
finding, build round 1, addressed).

Architecture note (see the plan file): this flag is agent-parsed prose, not
an argparse CLI flag — there is no scripted JS/TS loop to unit-test against.
Runtime honoring (actually excluding static mutants; actually emitting the
ignored-flag notice) is agent-behavior verified by one-time manual
verification recorded in the PR description, not by this test file.

Scope note (correctness-review finding, build round 1, addressed): most of
the mechanism/trade-off/non-JS-TS-notice detail was moved out of
mutation-kill.md's Invocation bullet (a hard 620-line-ceiling file with no
budget headroom) into javascript-stryker.md's dedicated subsection — this
file only guards what actually still lives in mutation-kill.md: the flag's
presence in the synopsis, its default/scope one-liner, the agent-parsed/
no-argparse note, and the pointer link. The mechanism/trade-off/notice
assertions moved to test_javascript_stryker_static_skip_doc.py alongside
the prose they now guard.
"""

from __future__ import annotations

import re

import pytest
from _mutation_kill_agent_doc_helpers import agent_text, required_section
from skill_doc_helpers import collapsed


@pytest.fixture(scope="module")
def text() -> str:
    return agent_text()


@pytest.fixture(scope="module")
def invocation_section(text: str) -> str:
    return required_section(
        text,
        r"^## Invocation",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Invocation",
    )


@pytest.fixture(scope="module")
def invocation_synopsis(invocation_section: str) -> str:
    """The fenced usage-synopsis block specifically — NOT the whole
    Invocation section (correctness-review finding, build round 1: the
    prior version of this fixture returned the whole section, so a test
    named "appears in the usage synopsis" could not fail even if the flag
    were deleted from the fence, since the bullet list below it also names
    the flag). Scoped to the first ``` ... ``` fence in the section."""
    match = re.search(r"```\n(.*?)\n```", invocation_section, re.DOTALL)
    assert match, "Fenced usage synopsis not found in Invocation section"
    return match.group(1)


@pytest.fixture(scope="module")
def invocation_flat(invocation_section: str) -> str:
    return collapsed(invocation_section)


def test_flag_appears_in_the_usage_synopsis(invocation_synopsis: str) -> None:
    assert "--skip-static-mutants" in invocation_synopsis


def test_flag_bullet_states_default_off_and_scope(invocation_flat: str) -> None:
    assert re.search(r"--skip-static-mutants.{0,40}opt-in, default OFF", invocation_flat)
    assert re.search(
        r"--skip-static-mutants.{0,80}JS/TS \(Stryker\) path only", invocation_flat
    )


def test_flag_bullet_states_agent_parsed_not_argparse(invocation_flat: str) -> None:
    """Corrected wording (round-3 pre-merge review, #1937): the OLD claim
    ("agent-parsed ... no argparse CLI for JS/TS") was stale — this branch's
    own mutation_report_cli.py IS a real, shipped argparse-flag CLI for
    JS/TS. Pin the narrower, corrected claim instead: the *invocation* flag
    has no argparse CLI on the JS/TS loop scripts; the underlying filter
    *computation* it drives does have one, on mutation_report_cli.py."""
    assert re.search(
        r"invocation flag itself remains agent-parsed prose.{0,10}no argparse "
        r"CLI on the JS/TS loop scripts",
        invocation_flat,
    )
    assert re.search(
        r"filter computation it drives is a real,? shipped argparse flag on"
        r".{0,5}mutation_report_cli\.py",
        invocation_flat,
    )


def test_flag_bullet_links_to_javascript_stryker_mechanics(invocation_flat: str) -> None:
    assert "javascript-stryker.md#static-mutant-skip-skip-static-mutants" in invocation_flat


@pytest.fixture(scope="module")
def convergence_section(text: str) -> str:
    return required_section(
        text,
        r"^## Convergence history across --all invocations",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Convergence history across --all invocations",
    )


def test_converged_write_trigger_caveats_static_mutant_skip(
    convergence_section: str,
) -> None:
    """domain-review finding (build round 1, closing pass): the
    scoring/convergence-stays-unfiltered invariant was stated only in
    javascript-stryker.md, but the component that actually writes
    `status: "converged"` — this section — carried no caveat, and JS/TS
    has no scripted loop to structurally separate the filtered generation
    input from the unfiltered convergence count. Guard the caveat at its
    actual point of use, not only at the cross-referenced doc."""
    flat = collapsed(convergence_section)
    assert re.search(r"--skip-static-mutants.{0,40}unfiltered report count", flat)
