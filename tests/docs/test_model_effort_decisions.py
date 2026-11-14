"""Gate for docs/model-effort-decisions.md.

The log records the per-agent model/effort decision and its eval evidence.
Agent frontmatter stays authoritative; this gate checks that the log's Final
columns equal it, that every tier change carries well-formed evidence tied to
the row, and that each evidence run ID resolves to a committed run artifact
whose model, effort, fixtures, trials and cost agree with the row.
Baseline is historical text: nothing here reads git.
"""

from __future__ import annotations

import json
import re

import pytest
from _plugin_dirs import frontmatter_block, frontmatter_field

from _repo_root import REPO_ROOT

DECISION_LOG_PATH = REPO_ROOT / "docs" / "model-effort-decisions.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
SKILLS_DIR = REPO_ROOT / "plugins" / "dev-team" / "skills"
RUNS_DIR = REPO_ROOT / "evals" / "model-effort" / "runs"

EVIDENCE_COLUMN = "Evidence or reason"
COLUMNS = [
    "Agent",
    "Source",
    "Baseline model",
    "Baseline effort",
    "Final model",
    "Final effort",
    "Decision",
    "Fixtures",
    EVIDENCE_COLUMN,
    "Eval cost saving (USD)",
]
MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
NOT_APPLICABLE = "n/a"
DECISION_KEEP = "keep"
DECISION_DOWNGRADE = "downgrade"
DECISION_UPGRADE = "upgrade"
DECISIONS = {DECISION_KEEP, DECISION_DOWNGRADE, DECISION_UPGRADE}
DIRECTION_MIXED = "mixed"
DIRECTION_UNCHANGED = "unchanged"
OPUS = "opus"
MIN_FIXTURES = 3
SAVING_TOLERANCE = 0.001
HEADER_AND_SEPARATOR_LINES = 2
ERROR_EXCERPT_WIDTH = 60
UNVERSIONED_MODEL_IDS = {"claude-haiku", "claude-sonnet", "claude-opus"}
REASON_BLANK = ""
REASON_NO_FIXTURE = "no fixture"
REASON_INSUFFICIENT_FIXTURES = "insufficient fixtures"
REASON_DIRECTORY_FIXTURES_ONLY = "directory fixtures only"
REASON_NOT_SELECTED = "not selected"
REASON_OPUS_NOT_RUN = "opus: not run"
REASON_HARNESS_GAP = "harness gap: Phase 0 not reproduced"
REASON_FAILED_EVAL = "failed eval"
REASON_TOOLS_WITHHELD = "weak evidence: tools withheld"
# Keep-row reasons that mean the agent was evaluated and not changed.
# Other reasons ("not selected" included) mean no evaluation ran.
EVALUATED_KEEP_REASONS = {REASON_FAILED_EVAL, REASON_TOOLS_WITHHELD}
KEEP_REASONS = {
    REASON_BLANK,
    REASON_NO_FIXTURE,
    REASON_INSUFFICIENT_FIXTURES,
    REASON_DIRECTORY_FIXTURES_ONLY,
    REASON_NOT_SELECTED,
    REASON_OPUS_NOT_RUN,
    REASON_HARNESS_GAP,
} | EVALUATED_KEEP_REASONS
RECALL_GAP_SENTENCE = (
    "correctness-review recall gap is known and unfixed; "
    "its results are excluded from evidence."
)
# The downgrade rule is relative to the current tier: recall equal or better,
# no clean-fixture false-positive increase, 100% parse. delta:0 means the
# proposed tier lost no recall relative to the current tier; it does not mean
# every trial passed.
EVIDENCE_RE = re.compile(
    r"^eval:(?P<run_id>[A-Za-z0-9][A-Za-z0-9-]*); "
    r"model:(?P<model>claude-[a-z0-9-]+); "
    r"effort:(?P<effort>low|medium|high|xhigh|max); fixtures:(?P<fixtures>\d+); "
    r"trials:(?P<trials>\d+); delta:0; "
    r"cost:(?P<baseline_cost>\d+(?:\.\d+)?)->(?P<candidate_cost>\d+(?:\.\d+)?)$"
)
CONCRETE_MODEL_ID_RE = re.compile(r"^claude-[a-z0-9-]+$")
EFFORT_VARIABLE_VALUES = {"yes", "no"}
HEADER_FIELD_RE = re.compile(
    r"^- (Candidates evaluated|Alias resolved|Effort variable): (.+)$", re.MULTILINE
)


def violations_for(name: str, message: str) -> list[str]:
    return [f"{name}: {message}"]


def load_repo_artifact(run_id: str):
    """The committed run artifact for run_id, or None when no file exists."""
    path = RUNS_DIR / f"{run_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def parse_log(text: str) -> tuple[dict[str, str], list[dict[str, str]], list[str]]:
    """Return (header fields, table rows, parse errors)."""
    headers = {k: v.strip() for k, v in HEADER_FIELD_RE.findall(text)}
    lines = [ln for ln in text.splitlines() if ln.startswith("|")]
    if not lines:
        return headers, [], ["decision table not found"]
    cells = [c.strip() for c in lines[0].strip("|").split("|")]
    missing = [c for c in COLUMNS if c not in cells]
    if missing:
        return headers, [], [f"table missing column(s): {', '.join(missing)}"]
    rows, errors = [], []
    for line in lines[HEADER_AND_SEPARATOR_LINES:]:
        values = [c.strip() for c in line.strip("|").split("|")]
        if len(values) != len(cells):
            errors.append(
                f"row has {len(values)} cells, expected {len(cells)}: {line[:ERROR_EXCERPT_WIDTH]}"
            )
            continue
        rows.append(dict(zip(cells, values)))
    return headers, rows, errors


def check_log(
    text: str, frontmatter_for_source, artifact_for_run=load_repo_artifact
) -> list[str]:
    """Return one error string per violation; empty means the log passes."""
    headers, rows, errors = parse_log(text)
    if RECALL_GAP_SENTENCE not in text:
        errors.append("recall-gap sentence missing from header")
    errors += check_header_fields(headers)
    sources = [r["Source"] for r in rows]
    for dup in sorted({s for s in sources if sources.count(s) > 1}):
        errors.append(f"{dup}: listed more than once")
    for row in rows:
        errors += check_row(row, frontmatter_for_source, artifact_for_run)
    evaluated = sum(1 for r in rows if is_evaluated(r))
    if headers.get("Candidates evaluated") != str(evaluated):
        errors.append(
            f"Candidates evaluated is '{headers.get('Candidates evaluated')}', "
            f"rows show {evaluated}"
        )
    return errors


def is_evaluated(row: dict[str, str]) -> bool:
    """True when the agent was A/B evaluated: its tier changed or it failed the eval."""
    return (
        row["Decision"] != DECISION_KEEP
        or row[EVIDENCE_COLUMN] in EVALUATED_KEEP_REASONS
    )


def check_header_fields(headers: dict[str, str]) -> list[str]:
    errors = []
    alias = headers.get("Alias resolved", "")
    if not CONCRETE_MODEL_ID_RE.match(alias) or alias in UNVERSIONED_MODEL_IDS:
        errors.append(f"Alias resolved must be a concrete model ID, got '{alias}'")
    effort_variable = headers.get("Effort variable", "")
    if effort_variable not in EFFORT_VARIABLE_VALUES:
        errors.append(f"Effort variable must be yes or no, got '{effort_variable}'")
    return errors


def check_row(
    row: dict[str, str], frontmatter_for_source, artifact_for_run=load_repo_artifact
) -> list[str]:
    name = row["Agent"]
    frontmatter = frontmatter_for_source(row["Source"])
    if frontmatter is None:
        return violations_for(name, f"no frontmatter source at {row['Source']}")
    final_model, final_effort = row["Final model"], row["Final effort"]
    if row["Decision"] not in DECISIONS:
        return violations_for(
            name, f"decision '{row['Decision']}' not in {sorted(DECISIONS)}"
        )
    if final_effort not in EFFORT_RANK or row["Baseline effort"] not in EFFORT_RANK:
        return violations_for(name, "effort outside the allowed set")
    is_skill = final_model == NOT_APPLICABLE
    if is_skill and row["Baseline model"] != NOT_APPLICABLE:
        return violations_for(
            name, "Baseline model must be n/a when Final model is n/a"
        )
    if not is_skill and (
        final_model not in MODEL_RANK or row["Baseline model"] not in MODEL_RANK
    ):
        return violations_for(name, "model outside the allowed set")
    problems = []
    if frontmatter_field(frontmatter, "model") != ("" if is_skill else final_model):
        problems += violations_for(name, "Final model differs from frontmatter")
    if frontmatter_field(frontmatter, "effort") != final_effort:
        problems += violations_for(name, "Final effort differs from frontmatter")
    direction = tier_direction(row)
    if direction == DIRECTION_UNCHANGED:
        problems += check_keep_row(name, row)
    else:
        problems += check_tier_change(name, row, direction, artifact_for_run)
    return problems


def has_minimum_fixtures(row: dict[str, str]) -> bool:
    return row["Fixtures"].isdigit() and int(row["Fixtures"]) >= MIN_FIXTURES


def check_keep_row(name: str, row: dict[str, str]) -> list[str]:
    reason = row[EVIDENCE_COLUMN]
    if row["Decision"] != DECISION_KEEP:
        return violations_for(
            name, "decision contradicts the baseline-to-final movement"
        )
    if row["Eval cost saving (USD)"]:
        return violations_for(name, "keep row must not report a cost saving")
    if reason == REASON_NO_FIXTURE and row["Fixtures"] != "0":
        return violations_for(name, f"'{REASON_NO_FIXTURE}' requires Fixtures of 0")
    if reason == REASON_INSUFFICIENT_FIXTURES and (
        not row["Fixtures"].isdigit() or has_minimum_fixtures(row)
    ):
        return violations_for(
            name,
            f"'{REASON_INSUFFICIENT_FIXTURES}' requires Fixtures below {MIN_FIXTURES}",
        )
    if reason == REASON_NOT_SELECTED and not has_minimum_fixtures(row):
        return violations_for(
            name,
            f"'{REASON_NOT_SELECTED}' requires Fixtures of at least {MIN_FIXTURES}",
        )
    if reason == REASON_BLANK and (
        not row["Fixtures"].isdigit() or has_minimum_fixtures(row)
    ):
        return violations_for(
            name, f"a blank reason requires Fixtures below {MIN_FIXTURES}"
        )
    if reason == REASON_OPUS_NOT_RUN and row["Final model"] != OPUS:
        return violations_for(
            name, f"'{REASON_OPUS_NOT_RUN}' requires Final model {OPUS}"
        )
    if reason not in KEEP_REASONS:
        return violations_for(
            name, "keep-row evidence must be one of the known reasons"
        )
    return []


def tier_direction(row: dict[str, str]) -> str:
    """A DECISION_* direction, DIRECTION_MIXED, or DIRECTION_UNCHANGED when no ranked pair moved."""
    pairs = [(EFFORT_RANK[row["Baseline effort"]], EFFORT_RANK[row["Final effort"]])]
    if row["Final model"] != NOT_APPLICABLE:
        pairs.append(
            (MODEL_RANK[row["Baseline model"]], MODEL_RANK[row["Final model"]])
        )
    if any(f > b for b, f in pairs) and any(f < b for b, f in pairs):
        return DIRECTION_MIXED
    if any(f > b for b, f in pairs):
        return DECISION_UPGRADE
    return DECISION_DOWNGRADE if any(f < b for b, f in pairs) else DIRECTION_UNCHANGED


def check_tier_change(
    name: str, row: dict[str, str], direction: str, artifact_for_run
) -> list[str]:
    """Direction, then evidence format, tie to the row, cost, and run artifact."""
    if row["Decision"] != direction:
        return violations_for(
            name, f"decision '{row['Decision']}' contradicts the {direction} movement"
        )
    match = EVIDENCE_RE.match(row[EVIDENCE_COLUMN])
    if not match:
        return violations_for(name, "evidence missing or malformed")
    if match["model"] in UNVERSIONED_MODEL_IDS:
        return violations_for(
            name, "evidence names a model family, not a concrete model ID"
        )
    if match["effort"] != row["Final effort"]:
        return violations_for(name, "evidence effort differs from Final effort")
    if row["Final model"] != NOT_APPLICABLE and not match["model"].startswith(
        f"claude-{row['Final model']}-"
    ):
        return violations_for(name, "evidence model differs from Final model")
    if int(match["fixtures"]) < MIN_FIXTURES or match["fixtures"] != row["Fixtures"]:
        return violations_for(
            name, f"evidence fixtures must equal Fixtures and be >= {MIN_FIXTURES}"
        )
    if direction == DECISION_DOWNGRADE:
        problems = check_saving(name, row, match)
        if problems:
            return problems
    return check_artifact(name, row, match, artifact_for_run)


def check_saving(name: str, row: dict[str, str], match: re.Match) -> list[str]:
    baseline, candidate = float(match["baseline_cost"]), float(match["candidate_cost"])
    if not candidate < baseline:
        return violations_for(name, "candidate cost is not lower than baseline")
    saving = row["Eval cost saving (USD)"]
    if not saving or abs(float(saving) - (baseline - candidate)) > SAVING_TOLERANCE:
        return violations_for(name, "saving differs from baseline minus candidate cost")
    return []


def arm_at_baseline_tier(arm: dict, row: dict[str, str]) -> bool:
    """True when the arm ran the row's Baseline tier; a skill row has no model to match."""
    return arm["effort"] == row["Baseline effort"] and (
        row["Baseline model"] == NOT_APPLICABLE or arm["model"] == row["Baseline model"]
    )


def cost_matches(written: str, reported_usd: float) -> bool:
    """True when the CLI-reported cost rounds to the evidence cost at its written precision."""
    decimals = len(written.partition(".")[2])
    return f"{reported_usd:.{decimals}f}" == written


def check_artifact(
    name: str, row: dict[str, str], match: re.Match, artifact_for_run
) -> list[str]:
    """The evidence run resolves to an artifact that ran this agent at both tiers with the row's numbers.

    Arms are matched by tier, not by label: a re-run may record the proposed
    tier as its baseline arm.
    """
    run_id = match["run_id"]
    artifact = artifact_for_run(run_id)
    if artifact is None:
        return violations_for(name, f"evidence run {run_id} has no committed artifact")
    if artifact["agent"] != name:
        return violations_for(
            name, f"artifact {run_id} ran agent '{artifact['agent']}', not this row's"
        )
    arms = artifact["arms"]
    model_arms = [a for a in arms if a["model_id"] == match["model"]]
    if not model_arms:
        return violations_for(
            name, f"artifact {run_id} has no arm with model {match['model']}"
        )
    final_arm = next((a for a in model_arms if a["effort"] == match["effort"]), None)
    if final_arm is None:
        return violations_for(
            name,
            f"artifact {run_id} has no {match['model']} arm at effort {match['effort']}",
        )
    baseline_arm = next(
        (a for a in arms if a is not final_arm and arm_at_baseline_tier(a, row)), None
    )
    if baseline_arm is None:
        return violations_for(
            name, f"artifact {run_id} has no arm at the Baseline model and effort"
        )
    problems = []
    for arm in (baseline_arm, final_arm):
        if len(arm["fixtures"]) != int(match["fixtures"]):
            problems += violations_for(
                name,
                f"evidence fixtures differ from artifact {run_id} "
                f"{arm['effort']} arm ({len(arm['fixtures'])})",
            )
        if arm["trials_per_fixture"] != int(match["trials"]):
            problems += violations_for(
                name,
                f"evidence trials differ from artifact {run_id} "
                f"{arm['effort']} arm ({arm['trials_per_fixture']})",
            )
    for column, arm in (("baseline", baseline_arm), ("candidate", final_arm)):
        reported = arm["totals"]["actual_cost_usd"]
        if not cost_matches(match[f"{column}_cost"], reported):
            problems += violations_for(
                name,
                f"evidence {column} cost {match[f'{column}_cost']} differs from "
                f"artifact {run_id} ({reported})",
            )
    return problems


def load_repo_frontmatter(source: str):
    path = REPO_ROOT / source
    return frontmatter_block(path) if path.is_file() else None


def effort_setting_skill_sources() -> set[str]:
    """Every skill whose SKILL.md frontmatter declares effort:."""
    return {
        path.relative_to(REPO_ROOT).as_posix()
        for path in SKILLS_DIR.glob("*/SKILL.md")
        if frontmatter_field(frontmatter_block(path), "effort")
    }


def expected_sources() -> set[str]:
    agents = {p.relative_to(REPO_ROOT).as_posix() for p in AGENTS_DIR.glob("*.md")}
    return agents | effort_setting_skill_sources()


# --- real repository ---------------------------------------------------------


def test_log_passes_gate():
    errors = check_log(
        DECISION_LOG_PATH.read_text(encoding="utf-8"), load_repo_frontmatter
    )
    assert errors == []


def test_log_covers_every_agent_and_effort_setting_skill():
    _, rows, parse_errors = parse_log(DECISION_LOG_PATH.read_text(encoding="utf-8"))
    assert parse_errors == []
    actual = {r["Source"] for r in rows}
    expected = expected_sources()
    assert (expected - actual, actual - expected) == (set(), set())


# --- synthetic fixtures ------------------------------------------------------

GOOD_RUN_ID = "run-1"
UPGRADE_RUN_ID = "run-up"
GOOD_EVIDENCE = (
    f"eval:{GOOD_RUN_ID}; model:claude-haiku-5-5; effort:medium; "
    f"fixtures:{MIN_FIXTURES}; trials:3; delta:0; cost:0.40->0.02"
)
UPGRADE_EVIDENCE = (
    f"eval:{UPGRADE_RUN_ID}; model:claude-haiku-5-5; effort:medium; "
    f"fixtures:{MIN_FIXTURES}; trials:3; delta:0; cost:0.02->0.40"
)
FRONTMATTER_BY_SOURCE = {
    "a.md": "model: sonnet\neffort: high",
    "b.md": "model: haiku\neffort: medium",
    "o.md": "model: opus\neffort: high",
    "s.md": "effort: medium",
}
ROW_FIELDS = [
    "agent",
    "source",
    "baseline_model",
    "baseline_effort",
    "final_model",
    "final_effort",
    "decision",
    "fixtures",
    "evidence",
    "saving",
]
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


ARTIFACTS_BY_RUN_ID = {
    GOOD_RUN_ID: {
        "run_id": GOOD_RUN_ID,
        "agent": "b",
        "arms": [
            make_arm("baseline", "sonnet", "high", 0.4012),
            make_arm("candidate", "haiku", "medium", 0.0198),
        ],
    },
    UPGRADE_RUN_ID: {
        "run_id": UPGRADE_RUN_ID,
        "agent": "b",
        "arms": [
            make_arm("baseline", "haiku", "low", 0.02),
            make_arm("candidate", "haiku", "medium", 0.40),
        ],
    },
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
    return dict(zip(COLUMNS, (row[field] for field in ROW_FIELDS)))


def make_tier_change_row(**overrides):
    defaults = {
        "baseline_model": "sonnet",
        "baseline_effort": "high",
        "decision": DECISION_DOWNGRADE,
        "evidence": GOOD_EVIDENCE,
        "saving": "0.380",
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


def errors_for(row):
    return check_row(row, fake_frontmatter_for_source, fake_artifact_for_run)


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
        make_row(agent="s", source="s.md", baseline_model="n/a", final_model="n/a"),
    ]
    assert check_synthetic_log(make_log(rows, NO_CANDIDATES)) == []


def test_valid_downgrade_log_passes():
    assert check_synthetic_log(make_log([make_tier_change_row()], ONE_CANDIDATE)) == []


def test_final_model_drift_from_frontmatter_fails():
    row = make_tier_change_row(
        final_model="sonnet", evidence=GOOD_EVIDENCE.replace("haiku", "sonnet")
    )
    assert any("Final model differs" in e for e in errors_for(row))


def test_skill_row_effort_drift_fails():
    row = make_row(
        agent="s",
        source="s.md",
        baseline_model="n/a",
        final_model="n/a",
        final_effort="high",
    )
    assert any("Final effort differs" in e for e in errors_for(row))


def test_keep_decision_with_moved_tier_fails():
    assert any(
        f"contradicts the {DECISION_DOWNGRADE} movement" in e
        for e in errors_for(make_tier_change_row(decision=DECISION_KEEP))
    )


@pytest.mark.parametrize(
    "evidence",
    [
        "",
        "  ",
        "TBD",
        "baseline",
        "n/a",
        "ran it, fine",
        GOOD_EVIDENCE.replace("model:claude-haiku-5-5", "model:haiku"),
        GOOD_EVIDENCE.replace(f"eval:{GOOD_RUN_ID}", "eval:../run-1"),
    ],
)
def test_malformed_downgrade_evidence_fails(evidence):
    assert any(
        "missing or malformed" in e
        for e in errors_for(make_tier_change_row(evidence=evidence))
    )


def test_unversioned_model_family_in_evidence_is_rejected():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-haiku")
    assert any(
        "names a model family, not a concrete model ID" in e
        for e in errors_for(make_tier_change_row(evidence=evidence))
    )


def test_evidence_effort_must_match_final_effort():
    evidence = GOOD_EVIDENCE.replace("effort:medium", "effort:high")
    assert any(
        "evidence effort" in e
        for e in errors_for(make_tier_change_row(evidence=evidence))
    )


def test_evidence_model_must_match_final_model():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-sonnet-5-5")
    assert any(
        "evidence model" in e
        for e in errors_for(make_tier_change_row(evidence=evidence))
    )


def test_evidence_fixtures_must_equal_fixtures_column():
    assert any(
        "evidence fixtures must equal Fixtures" in e
        for e in errors_for(make_tier_change_row(fixtures=FIXTURES_ABOVE_MINIMUM))
    )


def test_evidence_fixtures_below_minimum_fails():
    thin = GOOD_EVIDENCE.replace(
        f"fixtures:{MIN_FIXTURES}", f"fixtures:{FIXTURES_BELOW_MINIMUM}"
    )
    row = make_tier_change_row(evidence=thin, fixtures=FIXTURES_BELOW_MINIMUM)
    assert any(f"and be >= {MIN_FIXTURES}" in e for e in errors_for(row))


def test_candidate_not_cheaper_fails():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.40->0.40")
    assert any(
        "not lower" in e
        for e in errors_for(make_tier_change_row(evidence=evidence, saving="0"))
    )


def test_saving_must_equal_cost_difference():
    assert any(
        "saving differs" in e for e in errors_for(make_tier_change_row(saving="9.9"))
    )


def test_decision_must_match_movement_direction():
    row = make_tier_change_row(baseline_model="haiku", baseline_effort="low")
    assert any(
        "decision 'downgrade' contradicts the upgrade movement" in e
        for e in errors_for(row)
    )


def test_mixed_movement_is_rejected():
    assert any(
        "contradicts the mixed movement" in e
        for e in errors_for(
            make_tier_change_row(
                baseline_model="haiku", baseline_effort="high", final_model="sonnet"
            )
        )
    )


def test_upgrade_with_evidence_passes_without_lower_cost():
    assert errors_for(make_upgrade_row()) == []


def test_upgrade_without_evidence_fails():
    assert any(
        "missing or malformed" in e for e in errors_for(make_upgrade_row(evidence=""))
    )


# --- evidence resolves to a committed run artifact ---------------------------


def test_evidence_run_without_an_artifact_is_rejected():
    evidence = GOOD_EVIDENCE.replace(f"eval:{GOOD_RUN_ID}", "eval:run-uncommitted")
    assert errors_for(make_tier_change_row(evidence=evidence)) == [
        "b: evidence run run-uncommitted has no committed artifact"
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
        final_effort="low",
        evidence=GOOD_EVIDENCE.replace("effort:medium", "effort:low"),
    )
    assert (
        f"b: artifact {GOOD_RUN_ID} has no claude-haiku-5-5 arm at effort low"
        in errors_for(row)
    )


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
    row = make_tier_change_row(evidence=evidence, saving="0.390")
    assert errors_for(row) == [
        f"b: evidence baseline cost 0.41 differs from artifact {GOOD_RUN_ID} (0.4012)"
    ]


def test_evidence_candidate_cost_differing_from_the_artifact_is_rejected():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.40->0.03")
    row = make_tier_change_row(evidence=evidence, saving="0.370")
    assert errors_for(row) == [
        f"b: evidence candidate cost 0.03 differs from artifact {GOOD_RUN_ID} (0.0198)"
    ]


def test_artifact_arms_are_matched_by_tier_not_label():
    reversed_labels = {
        **ARTIFACTS_BY_RUN_ID[GOOD_RUN_ID],
        "arms": [
            make_arm("baseline", "haiku", "medium", 0.0198),
            make_arm("candidate", "sonnet", "high", 0.4012),
        ],
    }
    errors = check_row(
        make_tier_change_row(),
        fake_frontmatter_for_source,
        {GOOD_RUN_ID: reversed_labels}.get,
    )
    assert errors == []


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


def test_duplicate_source_is_rejected():
    assert any(
        "more than once" in e
        for e in check_synthetic_log(make_log([make_row(), make_row()], NO_CANDIDATES))
    )


def test_row_for_missing_source_is_rejected():
    assert any(
        "no frontmatter source" in e
        for e in errors_for(make_row(agent="ghost", source="ghost.md"))
    )


def test_table_missing_column_is_rejected():
    text = "| Agent | Source |\n|---|---|\n| a | a.md |\n"
    assert any("missing column" in e for e in check_synthetic_log(text))


def test_short_row_is_a_named_parse_error():
    text = make_log([make_row()], NO_CANDIDATES) + "| b | b.md | haiku |\n"
    assert any("cells, expected" in e for e in check_synthetic_log(text))


def test_unknown_decision_is_rejected():
    assert any(
        "decision 'maybe' not in" in e for e in errors_for(make_row(decision="maybe"))
    )


@pytest.mark.parametrize("final_effort", ["ultra", ""])
def test_effort_outside_allowed_set_is_rejected(final_effort):
    assert any(
        "effort outside the allowed set" in e
        for e in errors_for(make_row(final_effort=final_effort))
    )


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
    assert any("Alias resolved must be a concrete model ID" in e for e in errors)


@pytest.mark.parametrize("value", ["maybe", "yes (low and high)", "Yes", ""])
def test_effort_variable_must_be_yes_or_no(value):
    errors = check_synthetic_log(
        make_log([make_row()], NO_CANDIDATES, effort_variable=value)
    )
    assert any("Effort variable must be yes or no" in e for e in errors)


@pytest.mark.parametrize("value", ["yes", "no"])
def test_effort_variable_accepts_yes_and_no(value):
    assert (
        check_synthetic_log(
            make_log([make_row()], NO_CANDIDATES, effort_variable=value)
        )
        == []
    )


def test_missing_header_fields_are_reported():
    text = (
        make_log([make_row()], NO_CANDIDATES)
        .replace("- Alias resolved: claude-haiku-5-5\n", "")
        .replace("- Effort variable: yes\n", "")
    )
    errors = check_synthetic_log(text)
    assert any("Alias resolved must be a concrete model ID" in e for e in errors)
    assert any("Effort variable must be yes or no" in e for e in errors)


def test_recall_gap_sentence_is_required():
    text = make_log([make_row()], NO_CANDIDATES, include_recall_gap=False)
    assert any("recall-gap sentence missing" in e for e in check_synthetic_log(text))


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
        make_row(
            agent="s",
            source="s.md",
            baseline_model="n/a",
            final_model="n/a",
            fixtures="0",
        ),
    ]
    assert check_synthetic_log(make_log(rows, "2")) == []
    assert any("rows show 2" in e for e in check_synthetic_log(make_log(rows, "3")))


def test_candidates_evaluated_must_match_rows():
    text = make_log([make_row()], "9")
    assert any("Candidates evaluated is '9'" in e for e in check_synthetic_log(text))


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
    assert any(
        "keep-row evidence must be one of the known reasons" in e
        for e in errors_for(make_row(evidence="TBD"))
    )


def test_no_fixture_reason_requires_zero_fixtures():
    assert any(
        "requires Fixtures of 0" in e
        for e in errors_for(
            make_row(evidence=REASON_NO_FIXTURE, fixtures=FIXTURES_AT_MINIMUM)
        )
    )


def test_insufficient_fixtures_reason_requires_fewer_than_the_minimum():
    row = make_row(evidence=REASON_INSUFFICIENT_FIXTURES, fixtures=FIXTURES_AT_MINIMUM)
    expected = (
        f"'{REASON_INSUFFICIENT_FIXTURES}' requires Fixtures below {MIN_FIXTURES}"
    )
    assert any(expected in e for e in errors_for(row))


def test_not_selected_reason_requires_the_minimum_fixtures():
    row = make_row(evidence=REASON_NOT_SELECTED, fixtures=FIXTURES_BELOW_MINIMUM)
    expected = f"'{REASON_NOT_SELECTED}' requires Fixtures of at least {MIN_FIXTURES}"
    assert any(expected in e for e in errors_for(row))


@pytest.mark.parametrize("fixtures", [FIXTURES_AT_MINIMUM, "TBD", ""])
def test_blank_reason_is_rejected_unless_fixtures_are_below_minimum(fixtures):
    row = make_row(evidence=REASON_BLANK, fixtures=fixtures)
    assert any(
        f"blank reason requires Fixtures below {MIN_FIXTURES}" in e
        for e in errors_for(row)
    )


def test_opus_not_run_reason_requires_an_opus_final_model():
    row = make_row(evidence=REASON_OPUS_NOT_RUN, fixtures=FIXTURES_AT_MINIMUM)
    assert any(
        f"'{REASON_OPUS_NOT_RUN}' requires Final model {OPUS}" in e
        for e in errors_for(row)
    )


def test_skill_row_with_a_baseline_model_is_rejected():
    row = make_row(agent="s", source="s.md", baseline_model="haiku", final_model="n/a")
    assert any("Baseline model must be n/a" in e for e in errors_for(row))


def test_unmoved_tier_routes_to_the_keep_row_checks():
    row = make_row(decision=DECISION_DOWNGRADE)
    assert tier_direction(row) == DIRECTION_UNCHANGED
    assert errors_for(row) == ["b: decision contradicts the baseline-to-final movement"]


def test_keep_row_with_saving_is_rejected():
    assert any("must not report" in e for e in errors_for(make_row(saving="0.2")))


def test_keep_row_cannot_carry_an_eval_record():
    assert any(
        "keep-row evidence must be one of the known reasons" in e
        for e in errors_for(make_row(evidence=GOOD_EVIDENCE))
    )
