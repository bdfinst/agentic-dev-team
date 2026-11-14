"""Every benefit metric states a checked baseline status.

The rules live in ``_benefit_baseline_rules.py``. Each one runs once against the real pre-registration
(``test_real_pre_registration_passes_rule``) and again against synthetic cases that break it, so a rule that
cannot fail would show here. The record and private-path rules are tested in
``test_benefit_baseline_records.py``.
"""

from __future__ import annotations

import functools

import pytest
from _benefit_baseline_builders import (
    CELL_CHECKS,
    GUARD_FP,
    RECORD_CHECKS,
    assert_clean,
    assert_rejected,
    ctx_for,
    good_baseline,
    good_doc,
    good_entries,
    table_doc,
    with_baseline,
)
from _benefit_baseline_rules import (
    ALLOWED_TOKENS,
    ISSUE_CITES,
    PBT,
    PINNED_STATUS,
    PINNED_THRESHOLDS,
    REASONS,
    THRESHOLD_FIELDS,
    TR_TP,
    Context,
    check_baseline_cells,
    check_issue_cites,
    check_no_private_paths,
    check_status_table,
    check_thresholds,
    check_unmeasurable_matches_handling,
    check_verdict_order,
    current_usernames,
    run_checks,
)
from _benefit_eval_support import REAL_PREREG, real_entries

from _repo_root import REPO_ROOT

# --- literals the rules must equal -----------------------------------------------------------------------
# The helper holds the values the rules use. These copies are the deliberate pin: changing a value in the
# helper alone turns the equality tests below red, so a change has to be made, and read, in both places.

PINNED_TOKENS = (
    "by-definition",
    "measured",
    "forward-captured",
    "no-reference",
    "unmeasurable",
)

PINNED_STATUS_MAP = {
    "skip-rate": "by-definition",
    "findings-parity": "by-definition",
    "injection-overhead": "by-definition",
    "guard-false-positive": "by-definition",
    "pbt-mutants-killed": "measured",
    "test-review-tp-change": "no-reference",
    "injection-uptake": "forward-captured",
    "test-review-token-delta": "forward-captured",
    "abort-yield": "no-reference",
    "guard-divergence": "no-reference",
    "contradicted-rate": "no-reference",
    "expand-rate": "no-reference",
    "report-size-cut": "unmeasurable",
}

PINNED_ISSUE_CITES = {
    "skip-rate": 2306,
    "abort-yield": 2306,
    "expand-rate": 2307,
    "report-size-cut": 2308,
}

# keep, tune, retire and minimum_n as merged in docs/benefit-eval/preregistration.md at commit 02201d4d.
MERGED_THRESHOLDS = {
    "skip-rate": (">= 10", "< 10", "< 3", 10),
    "findings-parity": ("<= 0", "<= 2", ">= 3", 3),
    "abort-yield": ("<= 25", "> 25", "> 60", 10),
    "test-review-tp-change": (">= 0", "< 0", "< -10", 10),
    "test-review-token-delta": ("<= -15", "> -15", "> 0", 10),
    "expand-rate": ("<= 20", "> 20", "> 50", 10),
    "report-size-cut": (">= 40", "< 40", "< 15", 10),
    "injection-overhead": ("<= 400", "> 400", "> 1200", 10),
    "injection-uptake": (">= 50", "< 50", "< 10", 10),
    "guard-divergence": (">= 2", "< 2", "< 0.5", 10),
    "guard-false-positive": ("<= 5", "> 5", "> 30", 10),
    "contradicted-rate": (">= 0.2", "< 0.2", "< 0.05", 10),
    "pbt-mutants-killed": (">= 1", "< 1", "<= 0", 10),
}

#: A number no pinned follow-up issue uses.
OTHER_ISSUE = max(PINNED_ISSUE_CITES.values()) + 1


def test_rules_use_the_pinned_allowed_tokens():
    assert ALLOWED_TOKENS == PINNED_TOKENS


def test_rules_use_the_pinned_status_of_each_metric():
    assert PINNED_STATUS == PINNED_STATUS_MAP


def test_rules_use_the_pinned_follow_up_issue_of_each_cell():
    assert ISSUE_CITES == PINNED_ISSUE_CITES


def test_rules_use_the_merged_thresholds():
    assert PINNED_THRESHOLDS == MERGED_THRESHOLDS


# --- the real pre-registration ---------------------------------------------------------------------------


@functools.cache
def real_ctx() -> Context:
    text = REAL_PREREG.read_text()
    return Context(real_entries(), text, REPO_ROOT, tuple(current_usernames()))


REAL_CHECKS = (
    *CELL_CHECKS,
    check_status_table,
    check_verdict_order,
    *RECORD_CHECKS,
    check_no_private_paths,
    check_thresholds,
)


@pytest.mark.parametrize("check", REAL_CHECKS, ids=lambda check: check.__name__)
def test_real_pre_registration_passes_rule(check):
    findings = run_checks(real_ctx(), check)
    assert not findings.problems, findings.report()
    if findings.skips:
        pytest.skip("; ".join(findings.skips))


def test_every_pinned_status_is_an_allowed_token():
    assert set(PINNED_STATUS_MAP.values()) <= set(PINNED_TOKENS)


# --- baseline cells --------------------------------------------------------------------------------------


def test_synthetic_baseline_is_accepted():
    assert_clean(ctx_for(), *CELL_CHECKS, check_status_table, check_verdict_order)


@pytest.mark.parametrize(
    ("cell", "reason"),
    [
        ("invented: text", "unknown token"),
        ("Measured: text", "unknown token"),
        ("by-definition, measured: text", "unknown token"),
        ("by-definition: measured: text", "two status tokens"),
        ("by-definition: ", "empty text"),
        ("no text token at all", "no '<token>: <text>' form"),
        ("none: first measurement", "'none' or 'TBD'"),
        ("TBD: later", "'none' or 'TBD'"),
    ],
    ids=[
        "unknown-token",
        "wrong-case-token",
        "two-tokens-before-colon",
        "two-tokens-chained",
        "empty-text",
        "no-token",
        "none-prefix",
        "tbd-prefix",
    ],
)
def test_baseline_cell_with_a_bad_token_form_is_rejected_naming_metric_and_allowed_tokens(
    cell, reason
):
    assert_rejected(
        with_baseline(GUARD_FP, cell),
        check_baseline_cells,
        starts=f"{GUARD_FP}.baseline:",
        has=(reason, *ALLOWED_TOKENS),
    )


def test_baseline_text_after_the_token_can_be_reworded():
    assert_clean(
        with_baseline(GUARD_FP, "by-definition: a different sentence entirely"),
        check_baseline_cells,
    )


def test_baseline_status_that_differs_from_the_pinned_map_is_rejected():
    assert_rejected(
        with_baseline(GUARD_FP, "forward-captured: text"),
        check_baseline_cells,
        starts=f"{GUARD_FP}.baseline:",
        has=("'by-definition'",),
    )


def test_a_pinned_metric_missing_from_the_pre_registration_is_rejected():
    entries = good_entries()
    del entries["skip-rate"]
    assert_rejected(ctx_for(entries), check_baseline_cells, starts="skip-rate:")


def test_a_registered_metric_with_no_pinned_status_is_rejected():
    entries = good_entries()
    entries["new-metric"] = {**entries["skip-rate"], "id": "new-metric"}
    assert_rejected(ctx_for(entries), check_baseline_cells, starts="new-metric:")


def test_not_yet_run_is_accepted_for_a_measured_pin():
    assert_clean(
        with_baseline(PBT, "no-reference: not-yet-run; text"), check_baseline_cells
    )


def test_a_reason_other_than_not_yet_run_is_rejected_for_a_measured_pin():
    assert_rejected(
        with_baseline(PBT, "no-reference: cost-declined; text"),
        check_baseline_cells,
        starts=f"{PBT}.baseline:",
        has=("only 'not-yet-run'",),
    )


def test_a_downgrade_reason_outside_the_enum_is_rejected():
    assert_rejected(
        with_baseline(TR_TP, "no-reference: gave-up; text"),
        check_baseline_cells,
        starts=f"{TR_TP}.baseline:",
        has=REASONS,
    )


def test_a_no_reference_cell_without_a_reason_is_rejected_for_a_record_capable_metric():
    assert_rejected(
        with_baseline(PBT, "no-reference: text with no reason separator"),
        check_baseline_cells,
        starts=f"{PBT}.baseline:",
        has=("reason '' is not one of",),
    )


def test_a_downgraded_metric_accepts_any_enum_reason_once_the_pin_follows():
    pinned = {**PINNED_STATUS, PBT: "no-reference"}
    assert_clean(
        with_baseline(PBT, "no-reference: cost-declined; text", pinned=pinned),
        check_baseline_cells,
    )


def test_a_no_reference_cell_on_a_record_capable_metric_pinned_to_another_status_is_rejected():
    ctx = with_baseline(
        PBT,
        "no-reference: cost-declined; text",
        pinned={**PINNED_STATUS, PBT: "by-definition"},
    )
    assert_rejected(
        ctx,
        check_baseline_cells,
        starts=f"{PBT}.baseline:",
        has=("does not match pinned",),
    )


@pytest.mark.parametrize(
    ("metric_id", "cell"),
    [
        ("report-size-cut", "by-definition: counted by hand"),
        ("skip-rate", f"unmeasurable: no instrument (#{ISSUE_CITES['skip-rate']})"),
    ],
    ids=[
        "unmeasurable-handling-without-the-status",
        "unmeasurable-status-without-the-handling",
    ],
)
def test_unmeasurable_status_that_disagrees_with_id_less_handling_is_rejected(
    metric_id, cell
):
    assert_rejected(
        with_baseline(metric_id, cell),
        check_unmeasurable_matches_handling,
        starts=f"{metric_id}.baseline:",
    )


@pytest.mark.parametrize(
    ("metric_id", "number"), sorted(ISSUE_CITES.items()), ids=sorted(ISSUE_CITES)
)
def test_a_cell_missing_its_follow_up_issue_number_is_rejected_naming_the_metric(
    metric_id, number
):
    ctx = with_baseline(
        metric_id, good_baseline(metric_id).replace(f"#{number}", f"#{OTHER_ISSUE}")
    )
    assert_rejected(
        ctx, check_issue_cites, starts=f"{metric_id}.baseline:", has=(f"#{number}",)
    )


def test_an_issue_number_can_follow_the_reason_text():
    cell = f"unmeasurable: nothing is counted; follow-up #{ISSUE_CITES['expand-rate']}"
    assert_clean(with_baseline("expand-rate", cell), check_issue_cites)


def test_an_issue_number_that_only_prefixes_the_cited_one_is_rejected():
    cited = ISSUE_CITES["expand-rate"]
    ctx = with_baseline(
        "expand-rate", f"unmeasurable: nothing is counted; follow-up #{cited}1"
    )
    assert_rejected(
        ctx, check_issue_cites, starts="expand-rate.baseline:", has=(f"#{cited}",)
    )


def test_an_unmeasurable_cell_for_a_metric_with_no_pinned_issue_must_still_cite_an_issue():
    assert_rejected(
        with_baseline("contradicted-rate", "unmeasurable: no instrument exists"),
        check_issue_cites,
        starts="contradicted-rate.baseline:",
        has=("#<number>",),
    )


def test_an_unmeasurable_cell_for_a_metric_with_no_pinned_issue_accepts_any_cited_issue():
    assert_clean(
        with_baseline(
            "contradicted-rate",
            f"unmeasurable: no instrument exists (#{OTHER_ISSUE})",
        ),
        check_issue_cites,
    )


# --- document text ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc",
    [
        table_doc(ALLOWED_TOKENS[:-1]),
        table_doc((*ALLOWED_TOKENS, "estimated")),
        table_doc((*ALLOWED_TOKENS, "measured")),
        "## Rules\n\ntext\n",
    ],
    ids=["token-missing", "token-added", "token-duplicated", "no-table"],
)
def test_status_table_that_differs_from_the_pinned_enum_is_rejected(doc):
    assert_rejected(ctx_for(doc_text=doc), check_status_table, starts="status table:")


def test_verdict_order_that_omits_a_no_reference_metric_is_rejected_naming_it():
    entries = good_entries()
    ctx = ctx_for(entries, doc_text=good_doc(entries).replace("`abort-yield`, ", ""))
    assert_rejected(
        ctx,
        check_verdict_order,
        starts="verdict order:",
        has=("missing ['abort-yield']",),
    )


def test_verdict_order_that_names_a_metric_with_a_reference_is_rejected_naming_it():
    entries = good_entries()
    ctx = ctx_for(
        entries,
        doc_text=good_doc(entries).replace(
            "verdict is posted for: ", "verdict is posted for: `skip-rate`, "
        ),
    )
    assert_rejected(
        ctx, check_verdict_order, starts="verdict order:", has=("extra ['skip-rate']",)
    )


def test_verdict_order_follows_a_downgraded_metric_automatically():
    measured = "measured: .dev-team-reports/baselines/benefit-pbt-mutants-killed.json"
    stale_doc = good_doc(with_baseline(PBT, measured).entries)
    downgraded = with_baseline(PBT, "no-reference: cost-declined; text")
    assert_rejected(
        Context(downgraded.entries, stale_doc),
        check_verdict_order,
        starts="verdict order:",
        has=(f"missing ['{PBT}']",),
    )
    assert_clean(downgraded, check_verdict_order)


def test_verdict_order_without_the_no_verdict_statement_is_rejected():
    entries = good_entries()
    doc = good_doc(entries).replace(
        "No keep, tune, or retire verdict is posted for", "Metrics"
    )
    assert_rejected(
        ctx_for(entries, doc_text=doc),
        check_verdict_order,
        starts="verdict order:",
        has=("no keep, tune, or retire verdict",),
    )


def test_verdict_order_can_be_reworded_around_the_id_list():
    entries = good_entries()
    doc = good_doc(entries).replace(
        "is posted for:", "is ever posted for these metrics:"
    )
    assert_clean(ctx_for(entries, doc_text=doc), check_verdict_order)


def test_a_verdict_order_paragraph_in_a_later_section_is_not_the_one_under_rules():
    entries = good_entries()
    section = good_doc(entries).split("## Rules\n\n", 1)[1]
    doc = "## Rules\n\n**Other.** text\n\n## Later section\n\n" + section
    assert_rejected(
        ctx_for(entries, doc_text=doc), check_verdict_order, starts="verdict order: no"
    )


def test_a_document_without_a_verdict_order_paragraph_is_rejected():
    assert_rejected(
        ctx_for(doc_text="## Rules\n\n**Other.** text\n"),
        check_verdict_order,
        starts="verdict order: no",
    )


# --- thresholds ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("field_name", THRESHOLD_FIELDS)
def test_a_moved_threshold_is_rejected_naming_metric_and_field(field_name):
    entries = good_entries()
    entries["skip-rate"][field_name] = 99 if field_name == "minimum_n" else "> 99"
    assert_rejected(
        ctx_for(entries), check_thresholds, starts=f"skip-rate.{field_name}: is "
    )


def test_a_rationale_can_be_reworded_without_moving_a_threshold():
    entries = good_entries()
    entries["skip-rate"]["rationale"] = "A different explanation."
    assert_clean(ctx_for(entries), check_thresholds)


def test_a_metric_missing_from_the_pre_registration_is_reported_by_the_threshold_check():
    entries = good_entries()
    del entries["skip-rate"]
    assert_rejected(ctx_for(entries), check_thresholds, starts="skip-rate:")
