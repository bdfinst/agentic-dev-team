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


def test_batch_verdict_distinguishes_batch_blocked_from_plain_in_flight():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"distinct case", section_text)
    assert grep(r"single-issue \"in-flight; MONITOR\" verdict", section_text)


def test_probe_1_queries_the_batch_branch():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"gh pr list --state all --head issues-<n1>-<n2>-", section_text)


def test_monitor_exemption_requires_same_repository():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"not cross-repository", section_text)
    assert grep(r"isCrossRepository", section_text)


def test_monitor_exemption_excludes_cross_repo_branch_name_spoofing():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"a cross-repository PR merely sharing the branch name",
        section_text,
    )


def test_batch_verdict_documents_posting_comment_naming_the_in_flight_member():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"post a comment on", section_text, ignore_case=True)
    assert grep(r"naming which one", section_text, ignore_case=True)


def test_batch_verdict_halts_dispatch_this_round():
    assert grep(r"halt dispatch of the", _resume_guard_section())


def test_batch_verdict_scopes_the_halt_to_the_whole_batch():
    assert grep(r"\*\*whole batch\*\*", _resume_guard_section())


def test_batch_verdict_states_branches_evaluated_in_order_first_match_wins():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"evaluated in the order", section_text, ignore_case=True)
    assert grep(r"first whose condition holds wins", section_text, ignore_case=True)


# --- 2b. Fix 2 — idempotent comment + own-PR MONITOR path --------------------


def test_batch_verdict_documents_idempotent_comment_no_repost_on_refire():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"only if an equivalent /ship halt comment does not already exist",
        section_text,
    )
    assert grep(r"must not re-post", section_text, ignore_case=True)


def test_batch_verdict_documents_monitor_treatment_when_head_branch_matches_batchs_own():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"batch's own conventional branch", section_text)
    assert grep(r"gh pr checks <pr>", section_text)
    assert grep(r"issues-<n1>-<n2>-\.\.\.", section_text)


def test_batch_verdict_monitor_exemption_is_head_branch_match_only():
    # CRITICAL fix (security-review, correctness-review; issue #1701
    # follow-up): the MONITOR exemption must trigger ONLY on a head-branch
    # match — the retired `Closes #<N>` disjunct was identical to the halt
    # trigger's own condition (every halt-triggering PR would also exempt
    # itself), and a PR body is third-party-controllable text, so keeping it
    # let any outsider's PR silently suppress the batch's safety halt.
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"one whose body happens to carry `Closes #<N>` for a member",
        section_text,
    )
    assert grep(r"neither alone", section_text, ignore_case=True)
    # The old exemption wording checked the PR's OWN body for `Closes #<N>`
    # as a way into MONITOR — that phrasing must be gone entirely now.
    assert not grep(
        r"its body already carries `Closes #<N>` for a batch member",
        section_text,
    )


# --- 2c. Fix 3 — tightened Closes-#<N>-or-matching-branch trigger ------------


def test_batch_verdict_trigger_requires_closes_line_or_matching_branch():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"open PR whose body carries `Closes #<N>` or whose head "
        r"branch matches that member's conventional branch",
        section_text,
    )


def test_batch_verdict_trigger_excludes_bare_number_mention():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"not merely one whose title/body mentions the number in passing",
        section_text,
    )


# --- 3. Fully-shipped branch covers same-or-different merged PRs ------------


def test_batch_verdict_names_fully_shipped_case():
    assert grep(r"fully shipped", _resume_guard_section(), ignore_case=True)


def test_batch_verdict_fully_shipped_branch_covers_different_merged_prs():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"whether by the same PR/path or different ones",
        section_text,
    )


def test_batch_verdict_closure_branches_use_broadened_closed_wording():
    # correctness-review residual: "closed ... by [a/the] merged PR" only
    # covered closure-via-merged-PR; a member closed as not-planned or
    # manually satisfied neither branch's old qualifier. Both the
    # fully-shipped and malformed-batch branches must use the broadened
    # "closed (by a merged PR or otherwise)" wording so any closed state is
    # caught, and the human is told which path a member closed via.
    section_text = collapsed(_resume_guard_section())
    assert grep(r"closed \(by a merged PR or otherwise\)", section_text)
    assert grep(
        r"the merged PR when there is one, or otherwise how it closed",
        section_text,
    )
    assert grep(r"how each closed \(merged PR, or otherwise\)", section_text)


# --- 4. Fix 1 — malformed/partially-shipped (mixed shipped state) branch ----


def test_batch_verdict_names_malformed_partially_shipped_branch():
    section_text = collapsed(_resume_guard_section())
    assert grep(r"malformed/partially-shipped batch", section_text, ignore_case=True)
    assert grep(r"mixed shipped state", section_text, ignore_case=True)


def test_batch_verdict_malformed_branch_offers_askuserquestion_to_reform_or_halt():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"AskUserQuestion.*re-form the batch from only the still-open members",
        section_text,
    )


def test_batch_verdict_malformed_branch_falls_through_to_monitor_for_own_pr():
    # correctness-review ordering/shadowing fix: the batch's own PR shipping
    # incrementally (one member merged, another still open under the
    # batch's own PR) must not be shadowed by the malformed-batch branch —
    # it falls through to the batch-blocked branch's MONITOR treatment
    # instead of halting.
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"unless the still-open members are covered by the batch's own open PR",
        section_text,
    )
    assert grep(
        r"normal incremental progress: fall through to the batch-blocked "
        r"branch's MONITOR treatment instead of halting",
        section_text,
    )


# --- 5. Otherwise branch's now-clarified, whole-set criterion ---------------


def test_batch_verdict_otherwise_branch_names_first_run_and_resume_logic():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"Otherwise → proceed as today's \"genuine first run\" / "
        r"\"partially in-flight; RESUME\" logic",
        section_text,
    )


def test_batch_verdict_otherwise_branch_evaluated_across_whole_issue_set():
    section_text = collapsed(_resume_guard_section())
    assert grep(
        r"evaluated across the whole issue set rather than a single issue",
        section_text,
    )


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


def test_resume_guard_still_labels_pr_probe_verbatim():
    assert grep(r"\*\*PR\*\* — `gh pr list", _resume_guard_section())


def test_resume_guard_still_labels_spec_sub_issues_probe_verbatim():
    assert grep(
        r"\*\*Spec / sub-issues\*\* — an existing spec epic",
        _resume_guard_section(),
    )


def test_resume_guard_still_labels_plan_probe_verbatim():
    assert grep(
        r"\*\*Plan\*\* — an approved/implemented plan",
        _resume_guard_section(),
    )


def test_resume_guard_still_states_merged_pr_already_shipped_verbatim():
    assert grep(
        r"Merged PR closing the issue → already shipped\.",
        _resume_guard_section(),
    )


def test_resume_guard_still_states_open_pr_in_flight_monitor_verbatim():
    assert grep(
        r"Open PR for the issue → in-flight; MONITOR\.",
        _resume_guard_section(),
    )


def test_resume_guard_still_states_partially_in_flight_resume_verbatim():
    # The pre-existing single-issue term this diff must NOT touch — distinct
    # from the renamed batch term "batch-blocked" (was "partial-in-flight").
    assert grep(r"partially in-flight;\s*RESUME\.", _resume_guard_section())
