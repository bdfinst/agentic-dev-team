"""Doc-content contract for the mutation-kill agent's survivor
line-clustering guidance (#1906, Slice 1, Step 1.1 of
plans/mutation-kill-batch-hardening-1906-1910.md).

Mirrors the grep-on-section pattern already used in
``test_mutation_kill_feasibility_gate_doc.py`` and
``test_mutation_kill_baseline_reuse_doc.py`` — pure text assertions over
shipped agent prose, no state-mutating filesystem/git operations. Reuses
``skill_doc_helpers.section()`` for section-scoped extraction rather than
hand-rolling a new one, per this repo's established DRY convention.
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
def priority_section(text: str) -> str:
    return required_section(
        text,
        r"^## Target mutation types in priority order",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Target mutation types in priority order",
    )


@pytest.fixture(scope="module")
def priority_flat(priority_section: str) -> str:
    return collapsed(priority_section)


def test_clustering_happens_before_the_priority_order(priority_flat: str) -> None:
    assert re.search(
        r"[Cc]luster survivors by source line before applying the priority order",
        priority_flat,
    )


def test_clustering_groups_by_source_line_and_adjacent_expression_lines(
    priority_flat: str,
) -> None:
    assert re.search(r"[Gg]roup survivors by source line", priority_flat)
    assert re.search(
        r"adjacent lines that\s+share one expression", priority_flat
    )


def test_clusters_sorted_by_survivors_per_line_descending(priority_flat: str) -> None:
    assert re.search(r"survivors-per-line descending", priority_flat)
    # Not total mutants-per-line — see the fix commit for the ranking-signal
    # rationale (a heavily-mutated-but-mostly-killed line must not outrank a
    # smaller line whose mutants all survived).
    assert re.search(r"not total mutants-per-line", priority_flat)


def test_one_test_per_cluster_preferred_over_one_test_per_mutant(
    priority_flat: str,
) -> None:
    assert re.search(
        r"one test per cluster where\s+feasible", priority_flat
    )
    assert re.search(
        r"rather than defaulting to one test per mutant", priority_flat
    )


def test_unclusterable_survivors_have_a_stated_fallback(priority_flat: str) -> None:
    assert re.search(r"no resolvable source line", priority_flat)
    assert re.search(r"forms? no cluster", priority_flat)


@pytest.fixture(scope="module")
def parallel_execution_section(text: str) -> str:
    return required_section(
        text,
        r"^## Parallelism",
        boundary_pattern=r"^## ",
        include_start_line=False,
        name="Parallelism",
    )


def test_parallel_execution_propagates_clustering_before_priority_order(
    parallel_execution_section: str,
) -> None:
    """Correctness-review finding (build, Slice 1): the --all --parallel
    fan-out path used to restate the mutation-type priority order with no
    clustering-first step, bypassing the rule this file states above for
    the sequential --all path. Guard the ordering itself, not just that
    the word "cluster" appears somewhere in this section — a second,
    unrelated "clusters" mention later in the same step would otherwise
    keep a bare substring check green even if the clustering-first step
    were removed (round-2 review finding)."""
    flat = collapsed(parallel_execution_section)
    assert re.search(
        r"clusters them by\s+source line.*targets mutation types in the priority order",
        flat,
    )
