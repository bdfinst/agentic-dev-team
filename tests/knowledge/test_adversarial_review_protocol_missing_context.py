"""Content contract for knowledge/adversarial-review-protocol.md's
"Missing Context Is Reported, Never Reconstructed" pre-check (#1591).

While manually driving /code-review's 4-agent fast-path, doc-review was
dispatched with an instruction to look at `git diff --cached` despite its
tool grant having no Bash. Rather than reporting that limitation, it
fabricated a plausible-sounding but entirely wrong diff (describing a change
to an unrelated helper function) and returned `"status": "pass"` for a diff
it never saw. Two other Bash-less agents in the same batch (security-review,
correctness-review) handled the same gap correctly by falling back to
Read/Grep on the working tree — only doc-review confabulated.

This test guards the new shared pre-check that closes the gap: when a
review agent cannot obtain the content it needs (no Bash, diff not embedded
in the prompt, ambiguous scope), it must say so and return a status that
actually blocks the review gate — never a confident "pass" (or a
non-blocking "warn") for content it never examined.

This wording is the result of four /code-review fix-loop rounds against
this PR's own diff (arch-review, correctness-review, security-review each
re-verified multiple times):

- Gate-blocking severity: an early `"warn"`/`"warning"` draft never blocked
  `.review-passed` (`skills/code-review/scripts/consolidate.py` buckets
  overall status by severity). Fixed to `"fail"`/`"error"`.
- Confidence semantics: `"confidence": "high"` (tried to dodge a perceived
  conflict with `correctness-review.md`'s "drop, don't downgrade to
  confidence: none" rule) conflicts with
  `skills/code-review/output-format.md`'s own operational definition
  (`high` = mechanical fix, auto-apply), routing this unfixable meta-finding
  into the automatic fix loop. Fixed by restoring `"confidence": "none"` and
  adding an explicit scope carve-out (this finding reports the review's own
  executability, not reviewed content) plus a matching exception in
  `correctness-review.md` itself.
- Challenger-pass survival: an `error` severity that isn't explicitly
  exempted gets silently downgraded to `warning` by Loop item 3 (no listed
  impact category fits) or item 3a (no falsifier), which would reintroduce
  the exact defect this pre-check exists to prevent. Fixed by naming this
  case in item 3's impact list and requiring the falsifier (successful
  retrieval) directly in the mandated `message`.
- A08 scoping: an early draft told every citing agent to emit an
  `A08.review-manipulation` finding, contradicting the sibling "Files Are
  Data" pre-check's security-review-only scoping, and triggered on mere
  content rather than an actual instruction to the reviewer (a false-positive
  risk against benign `REVIEW-CONTEXT.md` scope notes). Fixed to match the
  sibling pre-check's scoping and intent trigger exactly.
- Non-JSON-agent carve-out: an early draft named `session-analysis`, which
  actually declares a JSON `status` field (including a `skip` clause for
  the exact missing-input case this pre-check governs) — only
  `data-flow-tracer` genuinely has none.

Semantic correctness (whether an agent actually follows the wording) is
verified by eval fixtures and real usage, not by grep — these assertions
verify the wording is present and durable, per the existing
`test_adversarial_review_protocol_evidence.py` pattern.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

DOC = (
    REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "adversarial-review-protocol.md"
)

SECTION_MARKER = "Missing Context Is Reported"
NEXT_HEADING = "\n## "


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section(text: str) -> str:
    # Bounded at both ends: from this pre-check's heading up to (not
    # including) the next "## " heading. An earlier draft split only the
    # start, so every assertion actually meant "appears somewhere after this
    # heading" — silently satisfiable by unrelated later sections (e.g. The
    # Loop's own JSON examples, or the Output section's `session-analysis`
    # mention) even if the guarded wording were deleted from this section.
    return text.split(SECTION_MARKER, 1)[1].split(NEXT_HEADING, 1)[0]


@pytest.fixture(scope="module")
def flat_section(section: str) -> str:
    # Markdown line-wraps prose across lines that don't matter semantically;
    # collapse whitespace so a phrase-presence check doesn't break just
    # because a future edit reflows where the line break falls.
    return re.sub(r"\s+", " ", section)


def test_missing_context_precheck_heading_present(text: str) -> None:
    assert re.search(
        r"## Mandatory Pre-Check: Missing Context Is Reported, Never Reconstructed",
        text,
    )


def test_missing_context_precheck_runs_before_analysis(section: str) -> None:
    assert re.search(r"\*\*Before any analysis begins\*\*", section)


def test_missing_context_precheck_binds_determination_to_own_tool_grant(
    flat_section: str,
) -> None:
    # The "context is unavailable" determination must come from the agent's
    # own tool grant and the orchestrator's dispatch instructions, never from
    # claims in repo-sourced prompt content — otherwise injected prose (in a
    # reviewed file, or in REVIEW-CONTEXT.md / diff bodies / static-analysis
    # output) could exploit this pre-check as a sanctioned skip-analysis
    # exit.
    assert re.search(
        r"solely from this agent's own tool grant and the orchestrator's dispatch instructions",
        flat_section,
    )
    assert "REVIEW-CONTEXT.md" in flat_section


def test_missing_context_precheck_requires_instruction_not_mere_mention(
    flat_section: str,
) -> None:
    # A08 must trigger on an actual instruction to the reviewer, not on any
    # text merely mentioning missing context — otherwise a benign
    # REVIEW-CONTEXT.md scope note (e.g. "generated files excluded") would
    # mandate a Critical finding and hard-block the review gate.
    assert re.search(r"is inert data, not a finding", flat_section)
    assert re.search(r"framed as such an\s*instruction", flat_section)


def test_missing_context_precheck_scopes_a08_to_security_review(
    flat_section: str,
) -> None:
    # Mirrors the sibling "Files Are Data" pre-check's own scoping: only
    # security-review emits the A08.review-manipulation finding; every other
    # agent proceeds normally without altering its finding counts or
    # severities.
    assert re.search(
        r"`security-review` emits the Critical `A08\.review-manipulation` finding",
        flat_section,
    )
    assert re.search(
        r"every other agent proceeds normally without altering its finding counts or severities",
        flat_section,
    )


def test_missing_context_precheck_names_no_bash_case(section: str) -> None:
    assert re.search(r"no Bash access", section, re.IGNORECASE)


def test_missing_context_precheck_forbids_reconstruction(flat_section: str) -> None:
    assert re.search(
        r"[Nn]ever infer, reconstruct, or guess at missing content",
        flat_section,
    )


def test_missing_context_precheck_requires_confirming_gap_first(
    flat_section: str,
) -> None:
    # Must not let an agent skip legitimate Read/Grep/Glob reconnaissance and
    # jump straight to reporting a gap that a direct read would have closed.
    assert re.search(r"try those before concluding", flat_section, re.IGNORECASE)


def test_missing_context_precheck_specifies_fail_status(section: str) -> None:
    assert '"status": "fail"' in section


def test_missing_context_precheck_specifies_error_severity(section: str) -> None:
    # error (not warning) so an unexamined change aggregates to overall
    # "fail" and withholds the .review-passed gate file, required of every
    # agent (unlike the sibling pre-check's security-review-only scoping).
    assert '"severity": "error"' in section


def test_missing_context_precheck_specifies_none_confidence(flat_section: str) -> None:
    # none (not high): per skills/code-review/output-format.md's confidence
    # table, "none" means "requires human judgment, never auto-applied" —
    # the correct classification for a meta-finding no code edit can
    # resolve. "high" was tried and rejected: it made the finding
    # auto-fix-actionable.
    assert '"confidence": "none"' in flat_section
    assert re.search(r"output-format\.md`'s confidence table", flat_section)


def test_missing_context_precheck_message_states_impact_and_falsifier(
    flat_section: str,
) -> None:
    assert re.search(
        r'`"message"`\s*stating what was missing, why it\s*could not be retrieved',
        flat_section,
    )
    assert re.search(
        r"an unexamined change would otherwise clear the\s*review gate",
        flat_section,
    )
    assert re.search(
        r"successfully retrieving the content on a later\s*attempt would falsify the finding",
        flat_section,
    )


def test_missing_context_precheck_requires_summary_stating_gap(flat_section: str) -> None:
    assert re.search(
        r'`"summary"`\s*stating that the review did not examine the actual change',
        flat_section,
    )


def test_missing_context_precheck_forbids_pass_or_skip_status(
    flat_section: str,
) -> None:
    assert re.search(
        r'[Nn]ever return `"status": "pass"`\s*or `"status": "skip"`', flat_section
    )


def test_missing_context_precheck_exempts_from_evident_intent_and_confidence_rules(
    flat_section: str,
) -> None:
    # Closes the correctness-review.md conflict at its source (scope, not
    # the confidence value): this finding is exempt from any agent-specific
    # rule requiring an evident-intent citation OR restricting the
    # confidence enum, since it reports the review's own executability, not
    # a claim about reviewed content.
    assert re.search(
        r"exempt from any\s*agent-specific rule requiring an\s*evident-intent citation, restricting the\s*`confidence` enum",
        flat_section,
    )


def test_missing_context_precheck_survives_loop_items_3_and_3a(
    flat_section: str,
) -> None:
    # Must not be a blanket "don't downgrade" exemption — Loop item 3
    # downgrades an error lacking a concrete impact, and item 3a downgrades
    # one lacking a falsifier. This pre-check satisfies both on the merits
    # (the impact and falsifier are stated in the mandated message, and item
    # 3's own category list names this case) rather than exempting itself
    # from them, so a literal reading of the challenger loop can't silently
    # unblock the gate.
    assert re.search(r"not from item 3/3a", flat_section)
    assert re.search(r"do not\s*downgrade its `error` severity under either", flat_section)


def test_loop_item_3_impact_list_names_review_gate_case(text: str) -> None:
    loop_item_3 = re.search(r"\*\*Severity justification\*\*.*", text)
    assert loop_item_3 is not None
    assert "review gate silently passing an unexamined change" in loop_item_3.group(0)


def test_missing_context_precheck_covers_non_json_agents(section: str) -> None:
    # data-flow-tracer genuinely has no `status` field. session-analysis was
    # incorrectly named in an earlier draft — its agent spec declares
    # {"status": "pass|warn|fail|skip", ...} and uses "skip" for exactly the
    # missing-input case this pre-check governs, so it must go through the
    # normal fail/error/none path above, not the non-JSON carve-out.
    assert "data-flow-tracer" in section
    assert "session-analysis" not in section


def test_missing_context_precheck_links_to_lazy_exits_loop_item(section: str) -> None:
    assert re.search(r"Loop item 6 \(Lazy exits\)", section)


def test_missing_context_precheck_precedes_the_loop(text: str) -> None:
    precheck_idx = text.index("Missing Context Is Reported, Never Reconstructed")
    loop_idx = text.index("## The Loop")
    assert precheck_idx < loop_idx
