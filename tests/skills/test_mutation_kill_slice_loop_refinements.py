"""Doc-shape contract for issue #667 / #681 (plan: Slice 2 — Concurrency
default fix): plans/mutation-kill-slice-loop-refinements.md.

Pattern mirrors tests/skills/test_mutation_testing_skill_doc.py — grep
guards against csharp-stryker-net.md's "Shipped wrapper" section. The
prose is the deliverable; these guards regress when the contract drifts.

This file is the shared home for all four slices of the plan
(mutation-kill-slice-loop-refinements). Slice 2 (this PR) adds only the
concurrency-default doc-content test below; later slices append their own
tests here as those slices land.

Ported from tests/skills/mutation_kill_slice_loop_refinements_tests.bats
(issue #700).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

CSHARP = (
    PLUGIN_ROOT
    / "skills"
    / "mutation-testing"
    / "references"
    / "languages"
    / "csharp-stryker-net.md"
)


def _text() -> str:
    return CSHARP.read_text()


def _shipped_wrapper_section() -> str:
    return section(
        _text(),
        r"^## Shipped wrapper",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


def _infra_exclusion_section() -> str:
    return section(
        _text(),
        r"^## Infrastructure exclusion `mutate` glob template",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


# --- Slice 2 · AC-5: concurrency default documented in the C# reference ----


def test_csharp_stryker_net_md_documents_the_wrappers_concurrency_default():
    s = _shipped_wrapper_section()

    # Wording near the CLI-flag table naming cores / cpu_count.
    assert grep(r"cores|cpu_count", s)

    # The flag name itself.
    assert "--stryker-concurrency" in s

    # The env-var equivalent.
    assert "STRYKER_MUTANT_CONCURRENCY" in s

    # A sentence distinguishing it from mutation-kill's own --concurrency
    # (worktree fan-out).
    assert "--concurrency" in s
    assert grep(r"worktree fan-out", s, ignore_case=True)

    # The CI/cgroup caveat for os.cpu_count().
    assert grep(r"cgroup", s, ignore_case=True)


# --- Slice 3 · convergence-derived glob negation example (#682) ------------


def test_csharp_stryker_net_md_infra_exclusion_glob_template_shows_a_convergence_derived_negation_example():
    s = _infra_exclusion_section()

    # A convergence-derived negation example, distinguished from the
    # permanent infra-exclusion negations already in the template.
    assert grep(r"convergence", s, ignore_case=True)
    assert "!" in s
    assert grep(r"re-checked|drop out|permanent", s, ignore_case=True)


# --- Slice 4 · tiered mutation-level example commands (#683) ----------------


def test_csharp_stryker_net_md_shows_both_a_basic_baseline_and_a_standard_escalation_example_command():
    content = _text()

    # Basic baseline command.
    assert "--mutation-level Basic" in content

    # Standard escalation command, scoped via --mutate to one file.
    assert "--mutation-level Standard" in content
    assert "--mutate" in content
