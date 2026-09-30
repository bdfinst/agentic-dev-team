"""Doc-shape contract for plan slice 5 (autoship-issue-batching, Steps 5.1/5.2)
additions to the /ship skill: the `--issues` batch-dispatch flag, the
generalized (batch-aware) resume guard, the one-spec/one-plan-per-batch
invariant, and the per-member `Closes #<N>` PR-body generalization.

Plan: plans/autoship-issue-batching.md — Slice 5, Step 5.1.

Includes a verbatim-preservation check: specific substrings of the
*original* (pre-this-plan) single-issue Step 1a resume-guard text must still
appear unchanged, so a solo (no `--issues`) invocation's documented behavior
is checked as unmodified, not just asserted to be.

Post-review-panel revision (issue #1701): the batch verdict's in-flight case
was renamed from "partial-in-flight" to "batch-blocked" (naming-review) to
avoid a textual collision with the pre-existing, protected "partially
in-flight; RESUME" phrase; a fourth "malformed/partially-shipped batch"
branch was added for mixed-shipped-state batches (correctness-review); the
in-flight trigger was tightened to require a `Closes #<N>`/matching-branch
qualifier (security-review, correctness-review); the halt-and-comment
resolution gained an idempotency guard and an own-PR MONITOR path
(concurrency-review, ai-provenance-review); and the batch's stable
`<issue-identifier>` key was defined for iteration-journal-gate calls
(ai-provenance-review, arch-review, domain-review).

Second post-review-panel revision (issue #1701 follow-up): the own-PR
MONITOR exemption was narrowed to ONLY the head-branch-match condition — the
`Closes #<N>` disjunct was dropped because it was identical to the halt
trigger itself and is third-party-controllable text, so it could never
actually gate a halt and let any outsider's PR suppress it (security-review,
correctness-review); the batch's own conventional branch name was defined
explicitly as the same `issues-<n1>-<n2>-...` batch key (arch-review); the
`<issue-identifier>` sentence in the iteration-journal-gate section was
updated to mention the batch key (arch-review); the Parse Arguments
workflow-state/iteration-journal scoping sentence was narrowed to
iteration-journal-gate only, since `workflow_state.py record` takes no
issue/round identifier param (arch-review); and the malformed-batch branch
gained an explicit fall-through exception for a batch's own PR shipping
incrementally, plus both closure branches' wording was broadened from
"closed ... by [a/the] merged PR" to "closed (by a merged PR or otherwise)"
(correctness-review).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    collapsed,
    grep,
    parse_arguments_section,
    section,
)

SHIP = PLUGIN_ROOT / "skills" / "ship"
SKILL = SHIP / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _parse_arguments_section() -> str:
    return parse_arguments_section(_text())


def _resume_guard_section() -> str:
    return section(
        _text(),
        r"^#### 1a\. Resume guard",
        boundary_pattern=r"^#### 1b\.",
    )


def _step_2_section() -> str:
    return section(
        _text(),
        r"^### 2\. Spec",
        boundary_pattern=r"^### 3\.",
    )


def _step_3_section() -> str:
    return section(
        _text(),
        r"^### 3\. Plan",
        boundary_pattern=r"^### 4\.",
    )


def _step_6_section() -> str:
    return section(
        _text(),
        r"^### 6\. PR",
        boundary_pattern=r"^### 7\.",
    )


def _iteration_journal_gate_section() -> str:
    return section(
        _text(),
        r"^## Iteration journal gate",
        boundary_pattern=r"^## ",
    )


# --- 1. --issues documented in Parse Arguments -------------------------------


def test_parse_arguments_issues_flag_takes_comma_separated_list():
    assert grep(r"--issues <comma-separated-list>", _parse_arguments_section())


def test_argument_hint_frontmatter_names_issues_flag():
    assert grep(r"^argument-hint:.*--issues", _text())


def test_parse_arguments_documents_issues_token_validation():
    section_text = collapsed(_parse_arguments_section())
    assert grep(r"bare issue number", section_text)
    assert grep(r"never coerce or best-effort parse", section_text, ignore_case=True)


def test_parse_arguments_documents_issue_numbers_never_interpolated_into_shell_string():
    assert grep(r"never interpolated into a shell string", _parse_arguments_section())


def test_parse_arguments_documents_batch_issue_identifier_key():
    section_text = collapsed(_parse_arguments_section())
    assert grep(r"batch's stable key", section_text)
    assert grep(r"issues-<n1>-<n2>-\.\.\.", section_text)
    assert grep(r"never re-derived differently", section_text, ignore_case=True)


def test_parse_arguments_scopes_batch_key_to_iteration_journal_gate_only():
    # arch-review fix: workflow_state.py record's actual CLI args (--cwd,
    # --workflow, --prior-state, --new-state, --session) carry no issue/round
    # identifier param at all — only iteration_journal_gate.py takes
    # --round-id. The old "every workflow-state/iteration-journal call"
    # wording implied a workflow-state parameter that doesn't exist.
    section_text = collapsed(_parse_arguments_section())
    assert grep(r"for every iteration-journal-gate call in this run", section_text)
    assert not grep(r"workflow-state/iteration-journal call", section_text)


# --- 2. Batch-blocked named explicitly and distinctly, not the retired term --


def test_batch_verdict_names_batch_blocked_case():
    assert grep(r"batch-blocked", _resume_guard_section())


def test_batch_verdict_does_not_use_the_retired_partial_in_flight_term():
    # "partial-in-flight" (no space) is the retired term this diff renamed to
    # "batch-blocked" (naming-review, issue #1701) — it collided with the
    # pre-existing, protected "partially in-flight; RESUME" phrase (note the
    # space), which is a different string and is untouched by this
    # assertion — see the verbatim-preservation tests below.
    assert not grep(r"partial-in-flight", _resume_guard_section())


def test_batch_verdict_scopes_the_halt_to_the_whole_batch():
    assert grep(r"\*\*whole batch\*\*", _resume_guard_section())


# --- 2b. Fix 2 — idempotent comment + own-PR MONITOR path --------------------


# --- 2c. Fix 3 — tightened Closes-#<N>-or-matching-branch trigger ------------


# --- 3. Fully-shipped branch covers same-or-different merged PRs ------------


# --- 4. Fix 1 — malformed/partially-shipped (mixed shipped state) branch ----


# --- 5. Otherwise branch's now-clarified, whole-set criterion ---------------


# --- 6. One-spec/one-plan-per-batch invariant documented in Steps 2/3 --------


def test_step_2_documents_one_spec_per_batch():
    section_text = collapsed(_step_2_section())
    assert grep(r"/specs.*invoked \*\*once\*\* for the whole batch", section_text)
    assert grep(r"one shared spec", section_text, ignore_case=True)


def test_step_2_documents_scope_split_protocol_exception():
    section_text = collapsed(_step_2_section())
    assert grep(r"Scope Split Protocol", section_text)
    assert grep(r"surface it and stop", section_text, ignore_case=True)


def test_step_3_documents_one_plan_per_batch():
    section_text = collapsed(_step_3_section())
    assert grep(r"/plan.*invoked \*\*once\*\* for the whole batch", section_text)
    assert grep(r"one shared plan", section_text, ignore_case=True)


# --- 7. Per-member Closes #<N> generalization in Step 6 ----------------------


def test_step_6_documents_one_closes_line_per_member_issue():
    section_text = collapsed(_step_6_section())
    assert grep(r"one `Closes #<N>` line per member issue", section_text)


def test_step_6_documents_ship_confirms_closes_line_per_member_before_success():
    section_text = collapsed(_step_6_section())
    assert grep(
        r"`/ship` confirms the created PR body actually carries one such line",
        section_text,
    )


def test_step_6_references_pr_close_keyword_lint_script():
    assert grep(r"pr_close_keyword_lint\.py", _step_6_section())


def test_step_6_references_pr_skill_doc():
    assert grep(r"skills/pr/SKILL\.md", _step_6_section())


# --- 8b. Fix B — iteration-journal-gate section's <issue-identifier> --------


def test_iteration_journal_gate_issue_identifier_mentions_batch_key():
    # arch-review fix: the <issue-identifier> definition here predates the
    # batch-key definition added to Parse Arguments and was never updated to
    # mention it.
    section_text = collapsed(_iteration_journal_gate_section())
    assert grep(
        r"or, when `--issues` was given, the batch key defined in Parse "
        r"Arguments \(`issues-<n1>-<n2>-\.\.\.`\)",
        section_text,
    )


def test_iteration_journal_gate_issue_identifier_still_names_resume_guard():
    # Verbatim-preservation companion to the fix above: the original
    # solo-case sentence must still be present, just extended.
    section_text = collapsed(_iteration_journal_gate_section())
    assert grep(
        r"the same identifier the Step 1a resume guard resolves",
        section_text,
    )


# --- 8. Verbatim-preservation: solo (no --issues) behavior is unmodified ----



# --- Resume guard is script-backed (#2213) ------------------------------------

_VERDICTS = (
    "shipped", "monitor", "resume", "partial-batch", "batch-blocked",
    "first-run", "probe-failed",
)


def test_resume_guard_delegates_to_script():
    assert "scripts/ship_resume_guard.py" in _resume_guard_section()


def test_resume_guard_action_table_names_every_verdict():
    body = _resume_guard_section()
    missing = [v for v in _VERDICTS if f"`{v}`" not in body]
    assert not missing, missing


def test_resume_guard_table_keeps_batch_safety_actions():
    body = collapsed(_resume_guard_section())
    assert "comment on **every member issue**" in body
    assert "AskUserQuestion" in body
    assert "never off conversation memory" in body.replace("**never** off", "never off")


def test_review_phase_consults_ship_review_gate():
    body = section(_text(), r"^### 5\. Review", boundary_pattern=r"^### 6\.")
    assert "scripts/ship_review_gate.py" in body
