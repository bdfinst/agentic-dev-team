"""Contract for the mutation-kill agent (epic #443, issue #461).

An autonomous survivor-reduction loop: scoped tool -> survivors -> generate
tests -> verify -> commit -> repeat, gated on hard kills only.

Ported from tests/agents/mutation_kill_agent_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "mutation-kill.md"
REGISTRY = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "agent-registry.md"


@pytest.fixture(scope="module")
def text() -> str:
    return AGENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def flat(text: str) -> str:
    return text.replace("\n", " ")


def test_mutation_kill_md_exists() -> None:
    assert AGENT.is_file()


def test_declares_required_frontmatter(text: str) -> None:
    fm_lines = []
    for i, line in enumerate(text.splitlines()):
        if i > 0 and line.strip() == "---":
            break
        fm_lines.append(line)
    fm = "\n".join(fm_lines)
    assert re.search(r"^name: *mutation-kill", fm, re.MULTILINE)
    assert re.search(r"^description:", fm, re.MULTILINE)
    assert re.search(r"^tools:", fm, re.MULTILINE)
    assert re.search(r"^effort: *(low|medium|high)", fm, re.MULTILINE)


def test_agent_body_stays_under_500_line_limit(text: str) -> None:
    assert len(text.splitlines()) < 500


def test_defines_honest_score_formula(text: str) -> None:
    assert re.search(r"honest", text, re.IGNORECASE)
    assert re.search(r"Killed */ *\(Killed \+ Survived \+ NoCoverage\)", text)
    assert re.search(r"timeout", text, re.IGNORECASE)
    # Retired formula must be gone, not just supplemented.
    assert not re.search(r"Killed */ *\(Total *- *Ignored", text)


def test_reports_timeout_count_separately_and_never_gates_on_it(text: str) -> None:
    assert re.search(
        r"timeout.*separate|report.*timeout|never.*timeout|"
        r"timeout.*not.*(count|gate)",
        text,
        re.IGNORECASE,
    )


def test_no_coverage_is_first_class_prioritized_signal(text: str) -> None:
    assert text.count("NoCoverage") >= 3
    assert re.search(
        r"prioritize NoCoverage|NoCoverage.*before.*Survived|NoCoverage.*first",
        text,
        re.IGNORECASE,
    )


def test_loop_starts_with_fresh_build_prohibits_no_build(text: str, flat: str) -> None:
    assert re.search(r"dotnet build", text)
    assert re.search(
        r"never.*--no-build|do not use.*--no-build|not.*--no-build",
        flat,
        re.IGNORECASE,
    )


def test_parallel_flag_documented_as_invocation_flag_with_agent_tool_fanout(
    text: str,
) -> None:
    assert re.search(r"--parallel", text)
    assert re.search(
        r"^## Parallel execution|^### Parallel execution",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    assert re.search(r"Agent tool", text, re.IGNORECASE)
    # bash `grep -E '3.4'` treats `.` as any-char (matches the en-dash "3–4").
    assert re.search(r"3.4", text) or re.search(r"3-4", text)
    assert re.search(r"1.2", text) or re.search(r"1-2", text)


def test_parallel_and_concurrency_interaction_rule_specified(text: str) -> None:
    lines = text.splitlines()
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if start is None and re.match(r"^## Parallel execution", line):
            start = i + 1
            continue
        if start is not None and re.match(r"^## [^P]", line):
            end = i
            break
    assert start is not None, "Parallel execution section not found"
    section = "\n".join(lines[start:end])
    assert re.search(r"concurrency", section, re.IGNORECASE)


def test_infrastructure_exclusion_thresholds_patterns_and_log_format(
    text: str,
) -> None:
    assert re.search(r"15%", text)
    assert re.search(r"50%", text)
    assert re.search(r"Startup\.cs", text)
    assert re.search(r"Program\.cs", text)
    assert re.search(r"\*Filter\.cs", text)
    assert re.search(r"\*Middleware\.cs", text)
    assert re.search(r"\*Logger\*\.cs", text)
    assert re.search(r"\*HealthCheck\*\.cs", text)
    assert re.search(r"\*\.Designer\.cs", text)
    assert re.search(r"EXCLUDED", text, re.IGNORECASE)


def test_infrastructure_exclusion_di_wiring_filename_patterns_catch_by_signal_alone(
    text: str, flat: str
) -> None:
    # Five new DI/wiring filename patterns must be present in the allowlist
    # (#680).
    assert re.search(r"\*Module\.cs", text)
    assert re.search(r"\*Container\.cs", text)
    assert re.search(r"\*Registration\.cs", text)
    assert re.search(r"\*Bootstrap\*\.cs", text)
    assert re.search(r"\*DependencyInjection\*\.cs", text)
    # The two numeric signals alone (no filename match required) must be
    # stated as sufficient to trigger the batched confirmation.
    assert re.search(
        r"signal(s)? alone|alone.*(is|are).*sufficient|no filename match required",
        flat,
        re.IGNORECASE,
    )
    # Explicit negative case: failing either numeric signal alone must never
    # trigger the question.
    assert re.search(
        r"failing either.*signal.*alone.*never trigger|"
        r"never trigger.*failing either",
        flat,
        re.IGNORECASE,
    )
    # The batched confirmation must itemize each flagged file with its
    # specific trigger reason (named convention vs signal-only).
    assert re.search(r"named convention", text, re.IGNORECASE)
    assert re.search(r"signal.?only", text, re.IGNORECASE)


def test_warns_shard_and_full_run_scores_not_comparable(text: str) -> None:
    assert re.search(r"shard", text, re.IGNORECASE)
    assert re.search(
        r"not comparable|never (mix|compare)|prohibit.*compar", text, re.IGNORECASE
    )


def test_requires_specific_value_assertion(text: str) -> None:
    assert re.search(r"status.?code", text, re.IGNORECASE)
    assert re.search(
        r"specific value|value assertion|assert.*value", text, re.IGNORECASE
    )


def test_has_mutation_type_priority_order_table(text: str) -> None:
    assert re.search(r"priority", text, re.IGNORECASE)
    assert re.search(r"String", text)
    assert re.search(r"ObjectInit", text)
    assert re.search(r"Equality", text, re.IGNORECASE)
    assert re.search(r"Statement", text, re.IGNORECASE)


def test_statement_block_needs_missing_code_path(text: str) -> None:
    assert re.search(r"Statement|Block", text, re.IGNORECASE)
    assert re.search(
        r"missing code path|new (test|code path)|not.*stronger assertion|"
        r"not.*existing",
        text,
        re.IGNORECASE,
    )


def test_per_language_translation_table(text: str) -> None:
    assert re.search(r"Stryker", text, re.IGNORECASE)
    assert re.search(r"pitest", text, re.IGNORECASE)
    assert re.search(r"Stryker\.NET", text, re.IGNORECASE)
    assert re.search(r"go-mutesting", text, re.IGNORECASE)


def test_duplicate_method_detection_stops_cleanly(text: str) -> None:
    assert re.search(r"duplicate", text, re.IGNORECASE)
    assert re.search(r"stop", text, re.IGNORECASE)


def test_build_and_test_verification_gates_insertion_reverts_on_failure(
    text: str,
) -> None:
    assert re.search(r"revert|git checkout --", text, re.IGNORECASE)
    assert re.search(r"build", text, re.IGNORECASE)


def test_documents_no_improvement_exit_condition(text: str) -> None:
    assert re.search(
        r"no.improvement|survivors >= prev|>= prev_survivors|stop.*no.*decreas",
        text,
        re.IGNORECASE,
    )


def test_concurrency_flag_defaults_to_2(text: str) -> None:
    assert re.search(r"--concurrency", text)
    assert re.search(r"default.*2|2 per", text, re.IGNORECASE)


def test_documents_structurally_unkillable_file_exclusion_with_reason(
    text: str,
) -> None:
    assert re.search(r"unkillable|structural guard|exclude", text, re.IGNORECASE)
    assert re.search(r"reason|document the exclusion", text, re.IGNORECASE)


def test_catalogs_three_structurally_untestable_patterns(text: str) -> None:
    assert re.search(r"#if DEBUG|#if RELEASE", text)
    assert re.search(r"HttpContext\.RequestServices", text)
    assert re.search(r"service.?locator", text, re.IGNORECASE)
    assert re.search(
        r"services\.AddX|builder\.Services\.AddX|services\.Add[A-Za-z]|AddX\(\)",
        text,
    )
    assert re.search(
        r"DI registration|test.?startup|TestStartup|TestServer", text, re.IGNORECASE
    )


def test_go_runs_advisory_logs_does_not_commit(text: str) -> None:
    assert re.search(r"advisory", text, re.IGNORECASE)
    assert re.search(
        r"does not commit|not commit|operator applies", text, re.IGNORECASE
    )


def test_convergence_history_persisted_entry_shape_and_write_triggers(
    text: str, flat: str
) -> None:
    """Slice 3, Step 3.1 (#682)."""
    # Persisted file path.
    assert re.search(r"mutation-kill-convergence\.json", text)
    # Entry shape fields.
    assert '"file"' in text
    assert '"status"' in text
    assert '"reason"' in text
    assert '"commit"' in text
    # Both write triggers: converged (survivors == 0) and excluded.
    assert re.search(
        r"survivors *== *0.*(write|record|entry)|"
        r"(write|record|entry).*survivors *== *0",
        flat,
        re.IGNORECASE,
    )
    assert re.search(
        r"excluded.*(write|record|entry)|(write|record|entry).*excluded",
        flat,
        re.IGNORECASE,
    )


def test_convergence_history_staleness_check_and_glob_shrinking_read_path(
    text: str, flat: str
) -> None:
    """Slice 3, Step 3.2 (#682)."""
    # Reads the convergence file before the baseline scan.
    assert re.search(r"before the baseline scan", flat, re.IGNORECASE)
    # Commit-SHA staleness check.
    assert re.search(r"commit-SHA|last-commit SHA|git log -1", text, re.IGNORECASE)
    assert re.search(r"stale", text, re.IGNORECASE)
    # Glob-shrinking negation for both converged and excluded entries.
    assert "!<file>" in text
    assert re.search(
        r"both.*converged.*excluded|converged.*and.*excluded.*shrink|"
        r"regardless of.*status",
        flat,
        re.IGNORECASE,
    )
    # The SKIPPED log-line pair.
    assert "SKIPPED <file> — already converged at" in text
    assert "SKIPPED <file> — excluded:" in text
    # Run-level summary line.
    assert re.search(r"convergence: skipped", text, re.IGNORECASE)
    # --since differentiation sentence.
    assert re.search(r"--since", text)
    assert re.search(r"complementary", flat, re.IGNORECASE)


def test_registered_in_agent_registry() -> None:
    registry_text = REGISTRY.read_text(encoding="utf-8")
    assert "agents/mutation-kill.md" in registry_text
