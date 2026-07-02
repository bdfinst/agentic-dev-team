"""Doc-shape contract for issue #561 (first-class slicing + configurable
slice-level parallelism for Stryker.NET).

Pattern mirrors tests/skills/test_mutation_kill_slice_loop_refinements.py —
grep guards against csharp-stryker-net.md's new "Slice runner" section. The
prose (and the shipped script it documents) are the deliverable; these
guards regress when the contract drifts.
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


def _slice_runner_section() -> str:
    return section(
        _text(),
        r"^## Slice runner",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


def test_documents_the_shipped_slice_runner_script():
    s = _slice_runner_section()
    assert grep(r"csharp_stryker_net_slice_runner\.py", s)


def test_documents_slice_cli_flags():
    s = _slice_runner_section()
    assert grep(r"--slice\s+<name>", s)
    assert grep(r"--slice\s+all", s)


def test_documents_slices_config_block_with_required_and_reserved_fields():
    s = _slice_runner_section()
    assert grep(r"\bname\b", s)
    assert grep(r"\bmutate\b", s)
    # Reserved fields for #667 — accepted, not yet acted on.
    assert grep(r"\bkind\b", s)
    assert grep(r"mutation-level", s)
    assert grep(r"exclude-converged", s)
    assert grep(r"#667", s)


def test_documents_per_slice_output_and_aggregate_rollup():
    s = _slice_runner_section()
    assert grep(r"slice-<name>", s)
    assert grep(r"mutation-report\.json", s)
    assert grep(r"aggregate", s, ignore_case=True)


def test_documents_resume_and_force_override():
    s = _slice_runner_section()
    assert grep(r"--force", s)
    assert grep(r"resum", s, ignore_case=True)


def test_documents_total_workers_flag_and_auto_formula():
    s = _slice_runner_section()
    assert grep(r"--total-workers", s)
    assert grep(r"auto", s, ignore_case=True)
    assert grep(r"max\(2,\s*cores\s*/\s*2\)", s) or grep(r"max\(2, cores", s)


def test_documents_parallel_slices_and_per_slice_concurrency_hints():
    s = _slice_runner_section()
    assert grep(r"--parallel-slices", s)
    assert grep(r"--per-slice-concurrency", s)
    assert grep(r"cores\s*-\s*1|cores\s*−\s*1", s)


def test_documents_sln_hide_restore_once_per_fleet_not_per_slice():
    s = _slice_runner_section()
    assert grep(r"\.sln", s)
    assert grep(r"once", s, ignore_case=True)
    assert grep(r"fleet", s, ignore_case=True)


def test_documents_rolled_up_progress_reporting():
    s = _slice_runner_section()
    assert grep(r"slice \d/\d", s) or grep(r"queued|running|done", s)
