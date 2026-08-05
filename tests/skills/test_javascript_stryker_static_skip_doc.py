"""Doc-content contract for the Stryker-side mechanics of the mutation-kill
agent's opt-in ``--skip-static-mutants`` flag (#1907, Slice 2, Step 2.2 of
plans/mutation-kill-batch-hardening-1906-1910.md).

Sibling to ``tests/agents/test_mutation_kill_skip_static_doc.py`` (Step 2.1),
which covers only the flag's bare presence/default/scope/link in
``mutation-kill.md``'s Invocation bullet. This file covers everything else
— mechanism, the corrected trade-off, the unfiltered-scoring invariant, the
absent-field fallback, and the non-JS/TS/``--headless``/``--parallel`` scope
notes — all of which now live in ``javascript-stryker.md``'s dedicated
"### Static-mutant skip" subsection rather than the whole "## Run (scoped)"
section (test-review + correctness-review finding, build round 1,
addressed: assertions are windowed to that subsection specifically, not the
enclosing section, mirroring ``test_mutation_testing_skill_doc.py``'s
``_emitting_adapters_window()``/``_line_clustering_window()`` precedent).

Pure text assertions over shipped skill-reference prose, no state-mutating
filesystem/git operations — same convention as
``tests/skills/test_mutation_testing_scoping.py``.
"""

from __future__ import annotations

import re

import pytest
from skill_doc_helpers import PLUGIN_ROOT, collapsed, section

JS_STRYKER = (
    PLUGIN_ROOT
    / "skills"
    / "mutation-testing"
    / "references"
    / "languages"
    / "javascript-stryker.md"
)


@pytest.fixture(scope="module")
def text() -> str:
    return JS_STRYKER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def static_skip_section(text: str) -> str:
    result = section(
        text,
        r"^### Static-mutant skip",
        boundary_pattern=r"^#{2,3} ",
        include_start_line=False,
    )
    assert result, "Static-mutant skip subsection not found"
    return result


@pytest.fixture(scope="module")
def static_skip_flat(static_skip_section: str) -> str:
    return collapsed(static_skip_section)


def test_flag_is_named_in_the_static_skip_subsection(static_skip_section: str) -> None:
    assert "--skip-static-mutants" in static_skip_section


def test_subsection_links_back_to_mutation_kill_invocation(static_skip_flat: str) -> None:
    assert "agents/mutation-kill.md#invocation" in static_skip_flat


def test_mechanism_filters_the_native_report_not_the_normalized_shape(
    static_skip_flat: str,
) -> None:
    assert re.search(r'`?"static"?:\s*true`?', static_skip_flat)
    assert re.search(r"native.{0,60}mutation\.json", static_skip_flat)
    assert "survivors[]" in static_skip_flat
    assert re.search(r"does.{0,15}not.{0,10}carry", static_skip_flat)


def test_mechanism_explains_why_a_static_mutant_forces_a_full_suite_rerun(
    static_skip_flat: str,
) -> None:
    assert re.search(r"module-initialization time", static_skip_flat)
    assert re.search(r'coverageAnalysis:\s*"perTest"', static_skip_flat)
    assert re.search(r"forcing a full-suite re-run", static_skip_flat)


def test_trade_off_does_not_claim_stryker_runs_faster(static_skip_flat: str) -> None:
    """correctness-review finding, build round 1: the prior wording claimed
    'trades a smaller wall-clock (no full-suite re-run per static mutant)',
    which the post-run filter cannot deliver — Stryker has already paid
    that cost by the time the report exists. Pin the corrected framing."""
    assert re.search(
        r"cannot make Stryker'?s own run faster", static_skip_flat
    )
    assert re.search(r"saves is the generation-and-verify.{0,10}rounds", static_skip_flat)
    assert re.search(r"small, documented survivor over-count", static_skip_flat)


def test_scoring_and_convergence_stay_unfiltered(static_skip_flat: str) -> None:
    """correctness-review finding, build round 1: without this statement, a
    file whose only remaining survivors are static could have its filtered
    (empty) list feed the survivors == 0 convergence exit, getting written
    as status: "converged" and permanently glob-shrunk out of future --all
    runs — contradicting the doc's own "stays counted as an unaddressed
    survivor" promise."""
    assert re.search(r"convergence.{0,20}stay unfiltered", static_skip_flat)
    assert re.search(r"survivors == 0", static_skip_flat)
    assert re.search(r'never be written as `?status: "converged"`?', static_skip_flat)


def test_absent_static_field_has_a_stated_fallback(static_skip_flat: str) -> None:
    assert re.search(r"[Ff]allback when the field is absent", static_skip_flat)
    assert re.search(r"skip is inapplicable", static_skip_flat)


def test_scope_is_interactive_agent_path_only(static_skip_flat: str) -> None:
    assert re.search(r"agent-parsed prose, not an argparse flag", static_skip_flat)
    assert re.search(r"unrecognized arguments", static_skip_flat)


def test_parallel_fan_out_does_not_auto_propagate_the_flag(static_skip_flat: str) -> None:
    assert re.search(r"--all --parallel", static_skip_flat)
    assert re.search(r"does not propagate automatically", static_skip_flat)
