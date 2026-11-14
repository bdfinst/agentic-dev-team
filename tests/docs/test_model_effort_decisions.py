"""Tests for the docs/model-effort-decisions.md gate.

The rules live in ``_model_effort_gate.py``. They run once against the real
log, its agent frontmatter and its committed run artifacts, and again against
synthetic rows and artifacts that each break one rule.
"""

from __future__ import annotations

import pytest
from _model_effort_gate import (
    COLUMNS,
    DECISION_DOWNGRADE,
    DECISION_KEEP,
    DECISION_LOG_PATH,
    DECISION_UPGRADE,
    DECISIONS,
    DIRECTION_UNCHANGED,
    EVIDENCE_COLUMN,
    KEEP_REASONS,
    MIN_FIXTURES,
    NOT_APPLICABLE,
    OPUS,
    REASON_BLANK,
    REASON_DIRECTORY_FIXTURES_ONLY,
    REASON_FAILED_EVAL,
    REASON_HARNESS_GAP,
    REASON_INSUFFICIENT_FIXTURES,
    REASON_NO_FIXTURE,
    REASON_NOT_SELECTED,
    REASON_OPUS_NOT_RUN,
    REASON_TOOLS_WITHHELD,
    RECALL_GAP_SENTENCE,
    RUN_STATUS_COMPLETE,
    SAVING_COLUMN,
    check_log,
    check_row,
    cost_matches,
    expected_sources,
    load_repo_artifact,
    load_repo_frontmatter,
    parse_log,
    tier_direction,
)

# --- real repository ---------------------------------------------------------


def test_log_passes_gate():
    errors = check_log(
        DECISION_LOG_PATH.read_text(encoding="utf-8"),
        load_repo_frontmatter,
        load_repo_artifact,
    )
    assert errors == []


def test_log_covers_every_agent_and_effort_setting_skill():
    _, rows, parse_errors = parse_log(DECISION_LOG_PATH.read_text(encoding="utf-8"))
    assert parse_errors == []
    actual = {r["Source"] for r in rows}
    expected = expected_sources()
    assert expected
    assert actual
    assert (expected - actual, actual - expected) == (set(), set())


# --- synthetic fixtures ------------------------------------------------------

GOOD_RUN_ID = "run-1"
UPGRADE_RUN_ID = "run-up"
SKILL_RUN_ID = "run-skill"
GOOD_EVIDENCE = (
    f"eval:{GOOD_RUN_ID}; model:claude-haiku-5-5; effort:medium; "
    f"fixtures:{MIN_FIXTURES}; trials:3; delta:0; cost:0.40->0.02"
)
UPGRADE_EVIDENCE = (
    f"eval:{UPGRADE_RUN_ID}; model:claude-haiku-5-5; effort:medium; "
    f"fixtures:{MIN_FIXTURES}; trials:3; delta:0; cost:0.02->0.40"
)
SKILL_EVIDENCE = GOOD_EVIDENCE.replace(f"eval:{GOOD_RUN_ID}", f"eval:{SKILL_RUN_ID}")
# Baseline arm cost minus final arm cost in the GOOD_RUN_ID artifact.
GOOD_SAVING = "0.380"
FRONTMATTER_BY_SOURCE = {
    "a.md": "model: sonnet\neffort: high",
    "b.md": "model: haiku\neffort: medium",
    "b-low.md": "model: haiku\neffort: low",
    "o.md": "model: opus\neffort: high",
    "s.md": "effort: medium",
}
FIELD_BY_COLUMN = {
    "Agent": "agent",
    "Source": "source",
    "Baseline model": "baseline_model",
    "Baseline effort": "baseline_effort",
    "Final model": "final_model",
    "Final effort": "final_effort",
    "Decision": "decision",
    "Fixtures": "fixtures",
    EVIDENCE_COLUMN: "evidence",
    SAVING_COLUMN: "saving",
}
FIXTURES_AT_MINIMUM = str(MIN_FIXTURES)
FIXTURES_BELOW_MINIMUM = str(MIN_FIXTURES - 1)
FIXTURES_ABOVE_MINIMUM = str(MIN_FIXTURES + 1)
NO_CANDIDATES = "0"
ONE_CANDIDATE = "1"


def make_arm(label, model, effort, cost_usd, fixtures=MIN_FIXTURES, trials=3):
    """One arm in the shape scripts/model_effort_ab.py writes; only gate-read fields."""
    return {
        "label": label,
        "model": model,
        "model_id": f"claude-{model}-5-5",
        "effort": effort,
        "trials_per_fixture": trials,
        "fixtures": [{"stem": f"f{i}"} for i in range(fixtures)],
        "totals": {"actual_cost_usd": cost_usd},
    }


def make_artifact(run_id, agent, arms, status=RUN_STATUS_COMPLETE):
    return {"run_id": run_id, "status": status, "agent": agent, "arms": arms}


ARTIFACTS_BY_RUN_ID = {
    GOOD_RUN_ID: make_artifact(
        GOOD_RUN_ID,
        "b",
        [
            make_arm("baseline", "sonnet", "high", 0.4012),
            make_arm("candidate", "haiku", "medium", 0.0212),
        ],
    ),
    UPGRADE_RUN_ID: make_artifact(
        UPGRADE_RUN_ID,
        "b",
        [
            make_arm("baseline", "haiku", "low", 0.02),
            make_arm("candidate", "haiku", "medium", 0.40),
        ],
    ),
    SKILL_RUN_ID: make_artifact(
        SKILL_RUN_ID,
        "s",
        [
            make_arm("baseline", "haiku", "high", 0.4012),
            make_arm("candidate", "haiku", "medium", 0.0212),
        ],
    ),
}


def fake_frontmatter_for_source(source):
    return FRONTMATTER_BY_SOURCE.get(source)


def fake_artifact_for_run(run_id):
    return ARTIFACTS_BY_RUN_ID.get(run_id)


def make_log(
    rows,
    candidates,
    include_recall_gap=True,
    alias="claude-haiku-5-5",
    effort_variable="yes",
):
    head = f"- Candidates evaluated: {candidates}\n"
    head += f"- Alias resolved: {alias}\n- Effort variable: {effort_variable}\n"
    head += (RECALL_GAP_SENTENCE + "\n") if include_recall_gap else ""
    table = "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n"
    return (
        head
        + table
        + "".join("| " + " | ".join(r[c] for c in COLUMNS) + " |\n" for r in rows)
    )


def make_row(**overrides):
    row = {
        "agent": "b",
        "source": "b.md",
        "baseline_model": "haiku",
        "baseline_effort": "medium",
        "final_model": "haiku",
        "final_effort": "medium",
        "decision": DECISION_KEEP,
        "evidence": REASON_BLANK,
        "fixtures": FIXTURES_BELOW_MINIMUM,
        "saving": "",
        **overrides,
    }
    return {column: row[field] for column, field in FIELD_BY_COLUMN.items()}


def make_tier_change_row(**overrides):
    defaults = {
        "baseline_model": "sonnet",
        "baseline_effort": "high",
        "decision": DECISION_DOWNGRADE,
        "evidence": GOOD_EVIDENCE,
        "saving": GOOD_SAVING,
        "fixtures": FIXTURES_AT_MINIMUM,
    }
    return make_row(**{**defaults, **overrides})


def make_upgrade_row(**overrides):
    defaults = {
        "baseline_model": "haiku",
        "baseline_effort": "low",
        "decision": DECISION_UPGRADE,
        "evidence": UPGRADE_EVIDENCE,
        "saving": "",
    }
    return make_tier_change_row(**{**defaults, **overrides})


def make_skill_row(**overrides):
    defaults = {
        "agent": "s",
        "source": "s.md",
        "baseline_model": NOT_APPLICABLE,
        "final_model": NOT_APPLICABLE,
    }
    return make_row(**{**defaults, **overrides})


def make_skill_tier_change_row(**overrides):
    defaults = {
        "baseline_effort": "high",
        "decision": DECISION_DOWNGRADE,
        "evidence": SKILL_EVIDENCE,
        "saving": GOOD_SAVING,
        "fixtures": FIXTURES_AT_MINIMUM,
    }
    return make_skill_row(**{**defaults, **overrides})


def errors_for(row, artifact_for_run=fake_artifact_for_run):
    return check_row(row, fake_frontmatter_for_source, artifact_for_run)


def errors_with_good_artifact(row, **artifact_overrides):
    """errors_for, with GOOD_RUN_ID resolving to its artifact plus the overrides."""
    artifact = {**ARTIFACTS_BY_RUN_ID[GOOD_RUN_ID], **artifact_overrides}
    return errors_for(row, {GOOD_RUN_ID: artifact}.get)


def check_synthetic_log(text):
    return check_log(text, fake_frontmatter_for_source, fake_artifact_for_run)


def test_valid_log_passes():
    rows = [
        make_row(
            agent="a",
            source="a.md",
            baseline_model="sonnet",
            baseline_effort="high",
            final_model="sonnet",
            final_effort="high",
        ),
        make_row(),
        make_skill_row(),
    ]
    assert check_synthetic_log(make_log(rows, NO_CANDIDATES)) == []


def test_valid_downgrade_log_passes():
    assert check_synthetic_log(make_log([make_tier_change_row()], ONE_CANDIDATE)) == []


def test_final_model_drift_from_frontmatter_fails():
    row = make_row(baseline_model="sonnet", final_model="sonnet")
    assert errors_for(row) == ["b: Final model differs from frontmatter"]


def test_skill_row_effort_drift_fails():
    row = make_skill_row(baseline_effort="high", final_effort="high")
    assert errors_for(row) == ["s: Final effort differs from frontmatter"]


def test_keep_decision_with_moved_tier_fails():
    assert errors_for(make_tier_change_row(decision=DECISION_KEEP)) == [
        f"b: decision '{DECISION_KEEP}' contradicts the {DECISION_DOWNGRADE} movement"
    ]


@pytest.mark.parametrize(
    "evidence",
    [
        "",
        "  ",
        "TBD",
        "baseline",
        NOT_APPLICABLE,
        "ran it, fine",
        GOOD_EVIDENCE.replace("model:claude-haiku-5-5", "model:haiku"),
        GOOD_EVIDENCE.replace(f"eval:{GOOD_RUN_ID}", "eval:../run-1"),
    ],
)
def test_malformed_downgrade_evidence_fails(evidence):
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        "b: evidence missing or malformed"
    ]


def test_unversioned_model_family_in_evidence_is_rejected():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-haiku")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        "b: evidence names a model family, not a concrete model ID"
    ]


def test_evidence_effort_must_match_final_effort():
    evidence = GOOD_EVIDENCE.replace("effort:medium", "effort:high")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        "b: evidence effort differs from Final effort"
    ]


def test_evidence_model_must_match_final_model():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-sonnet-5-5")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        "b: evidence model differs from Final model"
    ]


def test_evidence_fixtures_must_equal_fixtures_column():
    assert errors_for(make_tier_change_row(fixtures=FIXTURES_ABOVE_MINIMUM)) == [
        f"b: evidence fixtures must equal Fixtures and be >= {MIN_FIXTURES}"
    ]


def test_evidence_fixtures_below_minimum_fails():
    thin = GOOD_EVIDENCE.replace(
        f"fixtures:{MIN_FIXTURES}", f"fixtures:{FIXTURES_BELOW_MINIMUM}"
    )
    row = make_tier_change_row(evidence=thin, fixtures=FIXTURES_BELOW_MINIMUM)
    assert errors_for(row) == [
        f"b: evidence fixtures must equal Fixtures and be >= {MIN_FIXTURES}"
    ]


def test_candidate_not_cheaper_fails():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.40->0.40")
    assert errors_for(make_tier_change_row(evidence=evidence, saving="0")) == [
        "b: candidate cost is not lower than baseline"
    ]


def test_decision_must_match_movement_direction():
    row = make_tier_change_row(baseline_model="haiku", baseline_effort="low")
    assert errors_for(row) == [
        f"b: decision '{DECISION_DOWNGRADE}' contradicts the {DECISION_UPGRADE} movement"
    ]


def test_mixed_movement_is_rejected():
    row = make_tier_change_row(baseline_model="sonnet", baseline_effort="low")
    assert errors_for(row) == [
        f"b: decision '{DECISION_DOWNGRADE}' contradicts the mixed movement"
    ]


def test_upgrade_with_evidence_passes_without_lower_cost():
    assert errors_for(make_upgrade_row()) == []


def test_upgrade_without_evidence_fails():
    assert errors_for(make_upgrade_row(evidence="")) == [
        "b: evidence missing or malformed"
    ]


# An upgrade costs more, so a saving on it is either a sign error or a
# mislabelled row; the gate rejects it rather than check its value.
def test_upgrade_reporting_a_saving_is_rejected():
    assert errors_for(make_upgrade_row(saving=GOOD_SAVING)) == [
        "b: upgrade row must not report a cost saving"
    ]


@pytest.mark.parametrize("column", ["baseline_model", "final_model"])
def test_model_outside_allowed_set_is_rejected(column):
    assert errors_for(make_row(**{column: "gpt"})) == [
        "b: model outside the allowed set"
    ]


# --- skill rows: no model, effort only ---------------------------------------


def test_skill_row_effort_change_backed_by_an_artifact_passes():
    assert errors_for(make_skill_tier_change_row()) == []


def test_skill_row_without_a_baseline_effort_arm_is_rejected():
    row = make_skill_tier_change_row(baseline_effort="xhigh")
    assert errors_for(row) == [
        f"s: artifact {SKILL_RUN_ID} has no arm at the Baseline model and effort"
    ]


# --- saving agrees with the artifact -----------------------------------------


@pytest.mark.parametrize("saving", ["0.3809", "0.3791"])
def test_saving_within_tolerance_of_the_artifact_passes(saving):
    assert errors_for(make_tier_change_row(saving=saving)) == []


@pytest.mark.parametrize("saving", ["0.3811", "0.3789"])
def test_saving_just_outside_tolerance_of_the_artifact_fails(saving):
    assert errors_for(make_tier_change_row(saving=saving)) == [
        (
            f"b: saving {saving} differs from artifact {GOOD_RUN_ID} "
            "baseline minus final cost (0.3800)"
        )
    ]


def test_coarse_written_costs_cannot_hide_a_wrong_saving():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.4->0.0")
    assert errors_for(make_tier_change_row(evidence=evidence, saving="0.4")) == [
        (
            f"b: saving 0.4 differs from artifact {GOOD_RUN_ID} "
            "baseline minus final cost (0.3800)"
        )
    ]


@pytest.mark.parametrize("saving", ["", "TBD"])
def test_downgrade_without_a_numeric_saving_fails(saving):
    assert errors_for(make_tier_change_row(saving=saving)) == [
        "b: downgrade row must report a numeric cost saving"
    ]


# --- evidence resolves to a committed run artifact ---------------------------


def test_evidence_run_without_an_artifact_is_rejected():
    evidence = GOOD_EVIDENCE.replace(f"eval:{GOOD_RUN_ID}", "eval:run-uncommitted")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        "b: evidence run run-uncommitted has no committed artifact"
    ]


def test_artifact_recording_another_run_id_is_rejected():
    assert errors_with_good_artifact(make_tier_change_row(), run_id="run-other") == [
        f"b: artifact for {GOOD_RUN_ID} records run_id 'run-other'"
    ]


def test_incomplete_artifact_is_rejected():
    assert errors_with_good_artifact(make_tier_change_row(), status="incomplete") == [
        f"b: artifact {GOOD_RUN_ID} status is 'incomplete', not '{RUN_STATUS_COMPLETE}'"
    ]


def test_evidence_run_for_another_agent_is_rejected():
    row = make_tier_change_row(agent="other")
    assert errors_for(row) == [
        f"other: artifact {GOOD_RUN_ID} ran agent 'b', not this row's"
    ]


def test_evidence_model_absent_from_the_artifact_is_rejected():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-haiku-9-9")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        f"b: artifact {GOOD_RUN_ID} has no arm with model claude-haiku-9-9"
    ]


def test_evidence_effort_absent_from_the_artifact_is_rejected():
    row = make_tier_change_row(
        source="b-low.md",
        final_effort="low",
        evidence=GOOD_EVIDENCE.replace("effort:medium", "effort:low"),
    )
    assert errors_for(row) == [
        f"b: artifact {GOOD_RUN_ID} has no claude-haiku-5-5 arm at effort low"
    ]


def test_baseline_tier_absent_from_the_artifact_is_rejected():
    row = make_tier_change_row(baseline_effort="xhigh")
    assert errors_for(row) == [
        f"b: artifact {GOOD_RUN_ID} has no arm at the Baseline model and effort"
    ]


def test_evidence_fixtures_differing_from_the_artifact_are_rejected():
    evidence = GOOD_EVIDENCE.replace(
        f"fixtures:{MIN_FIXTURES}", f"fixtures:{FIXTURES_ABOVE_MINIMUM}"
    )
    row = make_tier_change_row(evidence=evidence, fixtures=FIXTURES_ABOVE_MINIMUM)
    assert errors_for(row) == [
        f"b: evidence fixtures differ from artifact {GOOD_RUN_ID} high arm (3)",
        f"b: evidence fixtures differ from artifact {GOOD_RUN_ID} medium arm (3)",
    ]


def test_evidence_trials_differing_from_the_artifact_are_rejected():
    evidence = GOOD_EVIDENCE.replace("trials:3", "trials:5")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        f"b: evidence trials differ from artifact {GOOD_RUN_ID} high arm (3)",
        f"b: evidence trials differ from artifact {GOOD_RUN_ID} medium arm (3)",
    ]


def test_evidence_baseline_cost_differing_from_the_artifact_is_rejected():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.41->0.02")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        f"b: evidence baseline cost 0.41 differs from artifact {GOOD_RUN_ID} (0.4012)"
    ]


def test_evidence_candidate_cost_differing_from_the_artifact_is_rejected():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.40->0.03")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        f"b: evidence candidate cost 0.03 differs from artifact {GOOD_RUN_ID} (0.0212)"
    ]


def test_artifact_arms_are_matched_by_tier_not_label():
    reversed_labels = make_artifact(
        GOOD_RUN_ID,
        "b",
        [
            make_arm("baseline", "haiku", "medium", 0.0212),
            make_arm("candidate", "sonnet", "high", 0.4012),
        ],
    )
    assert errors_for(make_tier_change_row(), {GOOD_RUN_ID: reversed_labels}.get) == []


@pytest.mark.parametrize(
    ("written", "reported", "matches"),
    [
        ("0.146", 0.14634233, True),
        ("0.15", 0.14634233, True),
        ("0.147", 0.14634233, False),
    ],
)
def test_cost_matches_at_the_written_precision(written, reported, matches):
    assert cost_matches(written, reported) is matches


# --- log structure and header ------------------------------------------------


def test_duplicate_source_is_rejected():
    text = make_log([make_row(), make_row()], NO_CANDIDATES)
    assert check_synthetic_log(text) == ["b.md: listed more than once"]


def test_row_for_missing_source_is_rejected():
    assert errors_for(make_row(agent="ghost", source="ghost.md")) == [
        "ghost: no frontmatter source at ghost.md"
    ]


def test_table_missing_column_is_rejected():
    text = "| Agent | Source |\n|---|---|\n| a | a.md |\n"
    assert parse_log(text)[2] == [f"table missing column(s): {', '.join(COLUMNS[2:])}"]


def test_short_row_is_a_named_parse_error():
    short = "| b | b.md | haiku |"
    text = make_log([make_row()], NO_CANDIDATES) + short + "\n"
    assert check_synthetic_log(text) == [
        f"row has 3 cells, expected {len(COLUMNS)}: {short}"
    ]


def test_unknown_decision_is_rejected():
    assert errors_for(make_row(decision="maybe")) == [
        f"b: decision 'maybe' not in {sorted(DECISIONS)}"
    ]


@pytest.mark.parametrize("column", ["baseline_effort", "final_effort"])
@pytest.mark.parametrize("effort", ["ultra", ""])
def test_effort_outside_allowed_set_is_rejected(column, effort):
    assert errors_for(make_row(**{column: effort})) == [
        "b: effort outside the allowed set"
    ]


@pytest.mark.parametrize(
    "alias",
    [
        "haiku",
        "claude-haiku",
        "claude-haiku-5-5 (resolved via headless run)",
        "Claude-Haiku-5-5",
        "",
    ],
)
def test_alias_resolved_must_be_a_concrete_model_id(alias):
    errors = check_synthetic_log(make_log([make_row()], NO_CANDIDATES, alias=alias))
    assert errors == [f"Alias resolved must be a concrete model ID, got '{alias}'"]


@pytest.mark.parametrize("value", ["maybe", "yes (low and high)", "Yes", ""])
def test_effort_variable_must_be_yes_or_no(value):
    errors = check_synthetic_log(
        make_log([make_row()], NO_CANDIDATES, effort_variable=value)
    )
    assert errors == [f"Effort variable must be yes or no, got '{value}'"]


@pytest.mark.parametrize("value", ["yes", "no"])
def test_effort_variable_accepts_yes_and_no(value):
    text = make_log([make_row()], NO_CANDIDATES, effort_variable=value)
    assert check_synthetic_log(text) == []


def test_missing_header_fields_are_reported():
    text = (
        make_log([make_row()], NO_CANDIDATES)
        .replace("- Alias resolved: claude-haiku-5-5\n", "")
        .replace("- Effort variable: yes\n", "")
    )
    assert check_synthetic_log(text) == [
        "Alias resolved must be a concrete model ID, got ''",
        "Effort variable must be yes or no, got ''",
    ]


def test_recall_gap_sentence_is_required():
    text = make_log([make_row()], NO_CANDIDATES, include_recall_gap=False)
    assert check_synthetic_log(text) == ["recall-gap sentence missing from header"]


def test_candidates_evaluated_counts_tier_changes_and_failed_evals_only():
    rows = [
        make_tier_change_row(),
        make_row(
            agent="a",
            source="a.md",
            baseline_model="sonnet",
            baseline_effort="high",
            final_model="sonnet",
            final_effort="high",
            evidence=REASON_FAILED_EVAL,
            fixtures=FIXTURES_AT_MINIMUM,
        ),
        make_skill_row(fixtures="0"),
    ]
    assert check_synthetic_log(make_log(rows, "2")) == []
    assert check_synthetic_log(make_log(rows, "3")) == [
        "Candidates evaluated is '3', rows show 2"
    ]


def test_candidates_evaluated_must_match_rows():
    text = make_log([make_row()], "9")
    assert check_synthetic_log(text) == ["Candidates evaluated is '9', rows show 0"]


# --- keep rows ---------------------------------------------------------------

# A valid Fixtures value for each keep reason; a new reason fails the parametrized test until added.
KEEP_REASON_FIXTURES = {
    REASON_BLANK: FIXTURES_BELOW_MINIMUM,
    REASON_NO_FIXTURE: "0",
    REASON_INSUFFICIENT_FIXTURES: FIXTURES_BELOW_MINIMUM,
    REASON_DIRECTORY_FIXTURES_ONLY: FIXTURES_AT_MINIMUM,
    REASON_FAILED_EVAL: FIXTURES_AT_MINIMUM,
    REASON_TOOLS_WITHHELD: FIXTURES_AT_MINIMUM,
    REASON_NOT_SELECTED: FIXTURES_AT_MINIMUM,
    REASON_OPUS_NOT_RUN: FIXTURES_AT_MINIMUM,
    REASON_HARNESS_GAP: FIXTURES_AT_MINIMUM,
}


OPUS_ROW = {
    "agent": "o",
    "source": "o.md",
    "baseline_model": OPUS,
    "baseline_effort": "high",
    "final_model": OPUS,
    "final_effort": "high",
}
# Reasons that name a property of the row's tier need a row that has it.
KEEP_REASON_ROW_FIELDS = {REASON_OPUS_NOT_RUN: OPUS_ROW}


@pytest.mark.parametrize("reason", sorted(KEEP_REASONS))
def test_known_keep_reasons_are_accepted(reason):
    row = make_row(
        evidence=reason,
        fixtures=KEEP_REASON_FIXTURES[reason],
        **KEEP_REASON_ROW_FIELDS.get(reason, {}),
    )
    assert errors_for(row) == []


def test_unknown_keep_reason_is_rejected():
    assert errors_for(make_row(evidence="TBD")) == [
        "b: keep-row evidence must be one of the known reasons"
    ]


def test_no_fixture_reason_requires_zero_fixtures():
    row = make_row(evidence=REASON_NO_FIXTURE, fixtures=FIXTURES_AT_MINIMUM)
    assert errors_for(row) == [f"b: '{REASON_NO_FIXTURE}' requires Fixtures of 0"]


def test_insufficient_fixtures_reason_requires_fewer_than_the_minimum():
    row = make_row(evidence=REASON_INSUFFICIENT_FIXTURES, fixtures=FIXTURES_AT_MINIMUM)
    assert errors_for(row) == [
        f"b: '{REASON_INSUFFICIENT_FIXTURES}' requires Fixtures below {MIN_FIXTURES}"
    ]


def test_not_selected_reason_requires_the_minimum_fixtures():
    row = make_row(evidence=REASON_NOT_SELECTED, fixtures=FIXTURES_BELOW_MINIMUM)
    assert errors_for(row) == [
        f"b: '{REASON_NOT_SELECTED}' requires Fixtures of at least {MIN_FIXTURES}"
    ]


@pytest.mark.parametrize("fixtures", [FIXTURES_AT_MINIMUM, "TBD", ""])
def test_blank_reason_is_rejected_unless_fixtures_are_below_minimum(fixtures):
    row = make_row(evidence=REASON_BLANK, fixtures=fixtures)
    assert errors_for(row) == [
        f"b: a blank reason requires Fixtures below {MIN_FIXTURES}"
    ]


def test_opus_not_run_reason_requires_an_opus_final_model():
    row = make_row(evidence=REASON_OPUS_NOT_RUN, fixtures=FIXTURES_AT_MINIMUM)
    assert errors_for(row) == [
        f"b: '{REASON_OPUS_NOT_RUN}' requires Final model {OPUS}"
    ]


def test_skill_row_with_a_baseline_model_is_rejected():
    assert errors_for(make_skill_row(baseline_model="haiku")) == [
        f"s: Baseline model must be {NOT_APPLICABLE} when Final model is {NOT_APPLICABLE}"
    ]


def test_unmoved_tier_routes_to_the_keep_row_checks():
    row = make_row(decision=DECISION_DOWNGRADE)
    assert tier_direction(row) == DIRECTION_UNCHANGED
    assert errors_for(row) == ["b: decision contradicts the baseline-to-final movement"]


def test_keep_row_with_saving_is_rejected():
    assert errors_for(make_row(saving="0.2")) == [
        "b: keep row must not report a cost saving"
    ]


def test_keep_row_cannot_carry_an_eval_record():
    assert errors_for(make_row(evidence=GOOD_EVIDENCE)) == [
        "b: keep-row evidence must be one of the known reasons"
    ]
