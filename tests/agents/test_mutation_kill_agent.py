"""Contract for the mutation-kill agent (epic #443, issue #461).

An autonomous survivor-reduction loop: scoped tool -> survivors -> generate
tests -> verify -> commit -> repeat, gated on hard kills only.

Ported from tests/agents/mutation_kill_agent_tests.bats (issue #675:
bats -> pytest).

Baseline-reuse doc tests moved to ``test_mutation_kill_baseline_reuse_doc.py``
(#1545) and pre-loop feasibility-gate doc tests moved to
``test_mutation_kill_feasibility_gate_doc.py`` (#1543/#1564) — both split out
of this file once it grew past the project's 500-line guideline.
"""

from __future__ import annotations

import re

import pytest
from skill_doc_helpers import section

from _repo_root import REPO_ROOT

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
    # Budget bumped by 1 (#1284): every agent's frontmatter grew a `model:`
    # line when the native model:/effort: contract replaced the retired
    # effort: <band> scheme. Bumped by 1 more (#1334): every agent's
    # frontmatter grew a `color:` line under the new fleet-wide convention.
    # Bumped by 1 more (#1335): this agent (file-mutating) gained a
    # `memory: project` line under the same fleet-wide convention.
    # Bumped by 3 more (#1357): Python/mutmut support added — a
    # mutation_kill_loop_python.py row in the scripted-mechanics table, a
    # Python row in the per-language translation table, and a Python prompt
    # rule.
    # Bumped by 23 more (#1369): a new "Accepted survivors: raw vs adjusted
    # score" subsection documenting per-mutant status: "accepted" deferrals
    # alongside the existing file-level EXCLUDED convention.
    # Bumped by 12 more (#1543): split the single `degrade` bullet in the
    # "Pre-loop feasibility gate" section into the unconditional
    # shim-decline/capture-failure degrade and the new `ask-operator`
    # budget-only outcome, with its confirmation-prompt content, echo-back
    # rule, off-script re-ask rule, and non-interactive default-to-degrade
    # fallback.
    # Bumped by 63 more (#1545): added a new "Baseline reuse for Round 1
    # (--concurrency 1 only)" section documenting the canonical baseline and
    # tracking-file paths, the per-file resolve-before/mark-consumed-after
    # procedure, the capture-commit lifetime, the no-baseline fallback, the
    # three-counter run-summary line, and the --concurrency 1-only scope.
    # Bumped by 1 more (#1545 review): added a mutation_baseline_reuse.py row
    # to the scripted-mechanics table (arch-review finding).
    # Bumped by 2 more (#1561/#1562): mutation_kill_loop.py split into three
    # files — added mutation_kill_insert.py and mutation_kill_headless.py
    # rows to the scripted-mechanics table.
    # Bumped by 7 more (#1598/#1584 review): documented the corrected
    # commit-failure revert (unstage + restore, not a plain checkout) and
    # the fatal-on-failed-revert contract in the "Verify + revert" bullet.
    # Bumped by 5 more (#1580/#1583 review): added mutation_kill_shared.py
    # and mutation_kill_insert_python.py rows to the scripted-mechanics
    # table, and added run_claude_headless to the reused-helpers list.
    # Bumped by 1 more (#1925/#1926): added a mutation_kill_retry.py row to
    # the scripted-mechanics table (net of merging the two Parallelism
    # sections into one).
    # Bumped by 14 more (#1920): widened the "Baseline reuse for Round 1"
    # section's scope statement to all --concurrency values and added
    # absolute-path/concurrent-write-safety invocation guidance.
    assert len(text.splitlines()) < 636


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


# --- Issue #1369: per-mutant accepted-survivor deferral + raw/adjusted score


def test_defines_accepted_survivors_subsection(text: str) -> None:
    assert re.search(r"^### Accepted survivors", text, re.MULTILINE)


def test_accepted_survivors_section_defines_raw_and_adjusted_score(text: str) -> None:
    assert re.search(
        r"adjusted_score\s*=\s*Killed\s*/\s*\(Killed\s*\+\s*\(Survived\s*-\s*Accepted\)"
        r"\s*\+\s*NoCoverage\)",
        text,
    )
    assert "raw_score" in text


def test_accepted_survivors_section_requires_a_reason_and_never_replaces_file_level_excluded(
    text: str,
) -> None:
    assert re.search(r"reason", text, re.IGNORECASE)
    assert "EXCLUDED" in text
    assert re.search(r"per-mutant", text, re.IGNORECASE)


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
        r"^## Parallelism|^### Sub-agent fan-out",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    assert re.search(r"Agent tool", text, re.IGNORECASE)
    # bash `grep -E '3.4'` treats `.` as any-char (matches the en-dash "3–4").
    assert re.search(r"3.4", text) or re.search(r"3-4", text)
    assert re.search(r"1.2", text) or re.search(r"1-2", text)


def test_parallel_and_concurrency_interaction_rule_specified(text: str) -> None:
    parallel_section = section(
        text,
        r"^## Parallelism",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )
    assert parallel_section, "Parallelism section not found"
    assert re.search(r"concurrency", parallel_section, re.IGNORECASE)


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


def test_tiered_mutation_level_basic_baseline_and_standard_escalation(
    text: str, flat: str
) -> None:
    """Slice 4, Step 4.1 (#683)."""
    # Baseline --all scan runs at mutation-level Basic.
    assert re.search(r"mutation-level Basic", text)
    # Fully-Basic-converged files skip the Standard pass.
    assert re.search(
        r"survivors *== *0.*(done|no Standard)|"
        r"(done|no Standard).*survivors *== *0",
        flat,
        re.IGNORECASE,
    )
    assert re.search(
        r"no Standard.?level pass|does not receive a Standard", text, re.IGNORECASE
    )
    # Escalation condition: Basic rounds stop (no-improvement/--max-rounds)
    # with survivors remaining.
    assert re.search(r"no-improvement|--max-rounds", text)
    assert re.search(
        r"ESCALATING <file> — Standard pass: N survivors remaining after Basic",
        text,
    )
    # One additional Standard-level pass scoped to that file only.
    assert re.search(r"mutation-level Standard", text)
    assert re.search(
        r"scoped.*(via --mutate)?.*to (just )?that file", flat, re.IGNORECASE
    )
    # A Standard pass that itself still ends with survivors gets no
    # convergence-history entry and is re-attempted from Basic next --all.
    assert re.search(
        r"no *(\*\*)?convergence.history(\*\*)? entry", flat, re.IGNORECASE
    )
    assert re.search(r"re-attempted.*(from )?Basic", flat, re.IGNORECASE)


def test_tiered_mutation_level_compile_error_trap_and_concurrency_crossref(
    text: str, flat: str
) -> None:
    """Slice 4, Step 4.2 (#683)."""
    # Cross-references the existing CompileError trap; drop-to-Basic-only +
    # EXCLUDED log, not a retry loop.
    assert re.search(r"CompileError", text)
    assert re.search(
        r"drops? back to Basic.only.*EXCLUDED|EXCLUDED.*drops? back to Basic.only",
        flat,
        re.IGNORECASE,
    )
    assert re.search(r"not a retry", flat, re.IGNORECASE)
    # Cross-references the wrapper's --stryker-concurrency cores-2 default,
    # naming it distinctly from mutation-kill's own --concurrency.
    assert re.search(r"--stryker-concurrency", text)
    assert re.search(r"cores.{0,10}2|cpu_count.{0,10}2", flat, re.IGNORECASE)
    assert re.search(r"--concurrency", text)
    assert re.search(
        r"different dial|worktree fan.?out|unrelated and unchanged",
        flat,
        re.IGNORECASE,
    )


def test_registered_in_agent_registry() -> None:
    registry_text = REGISTRY.read_text(encoding="utf-8")
    assert "agents/mutation-kill.md" in registry_text


# --- Slice 6 (#1136): the agent delegates mechanics to the shipped scripts and
# retains only the two genuinely-LLM steps (generation + exclusion judgment). --


def test_delegates_deterministic_mechanics_to_the_named_scripts(text: str) -> None:
    # The five migrated scripts + the reused wrapper must all be named, so the
    # agent points at them rather than re-describing their mechanics.
    for script in (
        "mutation_report.py",
        "mutation_kill_loop.py",
        "stryker_shard_setup.py",
        "stryker_shard_pipeline.py",
        "stryker_timeout_retry.py",
        "csharp_stryker_net_wrapper.py",
    ):
        assert script in text, f"agent must name the delegated script: {script}"


def test_report_parsing_and_scoring_delegated_to_mutation_report(
    text: str, flat: str
) -> None:
    # Report parsing + honest/reported scoring are computed by the script; the
    # agent gates on the honest score rather than re-deriving it.
    assert re.search(
        r"mutation_report\.py[^.]*?(compute|parse|scor|survivor)",
        flat,
        re.IGNORECASE,
    )


def test_loop_mechanics_delegated_to_mutation_kill_loop(text: str, flat: str) -> None:
    # Insertion, build/test, commit, and revert are the loop script's job —
    # the agent invokes the loop, it does not hand-run those steps.
    assert "mutation_kill_loop" in text
    assert re.search(r"run_for_file|per-file loop", text, re.IGNORECASE)
    assert re.search(r"invoke.*loop|loop.*(scripted|invoke)", flat, re.IGNORECASE)


def test_generation_is_agent_driven_by_default_with_headless_documented(
    text: str, flat: str
) -> None:
    # Generation stays with the agent: agent-driven by default, --headless as
    # the CI mode, and forced-headless in the shard pipeline.
    assert re.search(r"agent-driven", text, re.IGNORECASE)
    assert re.search(r"--headless", text)
    assert re.search(r"default", text, re.IGNORECASE)
    assert re.search(
        r"forces? .*--headless|--headless.*forced|forced.*headless",
        flat,
        re.IGNORECASE,
    )
    # The forcing is because a script-spawned round has no live agent turn.
    assert re.search(r"no (live )?agent turn|unattended", flat, re.IGNORECASE)


def test_retains_generation_and_exclusion_as_the_llm_only_responsibilities(
    text: str, flat: str
) -> None:
    # The agent must state that generation and exclusion judgment are the two
    # steps it owns — with the exclusion decision criteria kept (not merely
    # named): the numeric signals and the structural patterns.
    assert re.search(r"exclusion judg", flat, re.IGNORECASE)
    assert re.search(r"generat", text, re.IGNORECASE)
    # Exclusion criteria retained, not merely named.
    assert re.search(r"15%", text) and re.search(r"50%", text)

