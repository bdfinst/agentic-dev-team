"""Gate for docs/model-effort-decisions.md.

The log records the per-agent model/effort decision and its eval evidence.
Agent frontmatter stays authoritative; this gate checks that the log's Final
columns equal it, that every tier change carries well-formed evidence tied to
the row, and that agent_info.md's Model column agrees with frontmatter.
Baseline is historical text: nothing here reads git.
"""

from __future__ import annotations

import re

import pytest
from _plugin_dirs import frontmatter_block, frontmatter_field

from _repo_root import REPO_ROOT

DECISION_LOG_PATH = REPO_ROOT / "docs" / "model-effort-decisions.md"
AGENT_INFO_PATH = REPO_ROOT / "plugins" / "dev-team" / "docs" / "agent_info.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
SKILL_SOURCES = [
    "plugins/dev-team/skills/co-evolution-audit/SKILL.md",
    "plugins/dev-team/skills/autoship/SKILL.md",
]

COLUMNS = [
    "Agent", "Source", "Baseline model", "Baseline effort", "Final model",
    "Final effort", "Decision", "Fixtures", "Evidence", "Eval cost saving (USD)",
]
MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
NOT_APPLICABLE = "n/a"
DECISIONS = {"keep", "downgrade", "upgrade"}
MIN_FIXTURES = 3
SAVING_TOLERANCE = 0.001
HEADER_AND_SEPARATOR_LINES = 2
AGENT_INFO_AGENT_COLUMN = "Agent"
AGENT_INFO_MODEL_COLUMN = "Model"
MODEL_ALIASES = {"claude-haiku", "claude-sonnet", "claude-opus"}
# Keep-row reasons that mean the agent was evaluated and not changed.
EVALUATED_KEEP_REASONS = {"failed eval", "weak evidence: tools withheld"}
KEEP_REASONS = {
    "", "no fixture", "insufficient fixtures", "directory fixtures only",
} | EVALUATED_KEEP_REASONS
RECALL_GAP_SENTENCE = (
    "correctness-review recall gap is known and unfixed; "
    "its results are excluded from evidence."
)
# delta:0 means zero lost and zero added expected findings across all trials.
EVIDENCE_RE = re.compile(
    r"^eval:\S+; model:(?P<model>claude-[a-z0-9-]+); "
    r"effort:(?P<effort>low|medium|high|xhigh|max); fixtures:(?P<fixtures>\d+); "
    r"trials:\d+; delta:0; "
    r"cost:(?P<baseline_cost>\d+(?:\.\d+)?)->(?P<candidate_cost>\d+(?:\.\d+)?)$"
)
CONCRETE_MODEL_ID_RE = re.compile(r"^claude-[a-z0-9-]+$")
EFFORT_VARIABLE_VALUES = {"yes", "no"}
HEADER_FIELD_RE = re.compile(
    r"^- (Candidates evaluated|Alias resolved|Effort variable): (.+)$", re.MULTILINE
)


def violation(name: str, message: str) -> list[str]:
    return [f"{name}: {message}"]


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
            errors.append(f"row has {len(values)} cells, expected {len(cells)}: {line[:60]}")
            continue
        rows.append(dict(zip(cells, values)))
    return headers, rows, errors


def check_log(text: str, frontmatter_for_source) -> list[str]:
    """Return one error string per violation; empty means the log passes."""
    headers, rows, errors = parse_log(text)
    if RECALL_GAP_SENTENCE not in text:
        errors.append("recall-gap sentence missing from header")
    errors += check_header_fields(headers)
    sources = [r["Source"] for r in rows]
    for dup in sorted({s for s in sources if sources.count(s) > 1}):
        errors.append(f"{dup}: listed more than once")
    for row in rows:
        errors += check_row(row, frontmatter_for_source)
    evaluated = sum(1 for r in rows if is_evaluated(r))
    if headers.get("Candidates evaluated") != str(evaluated):
        errors.append(
            f"Candidates evaluated is '{headers.get('Candidates evaluated')}', "
            f"rows show {evaluated}"
        )
    return errors


def is_evaluated(row: dict[str, str]) -> bool:
    """True when the agent was A/B evaluated: its tier changed or it failed the eval."""
    return row["Decision"] != "keep" or row["Evidence"] in EVALUATED_KEEP_REASONS


def check_header_fields(headers: dict[str, str]) -> list[str]:
    errors = []
    alias = headers.get("Alias resolved", "")
    if not CONCRETE_MODEL_ID_RE.match(alias) or alias in MODEL_ALIASES:
        errors.append(f"Alias resolved must be a concrete model ID, got '{alias}'")
    effort_variable = headers.get("Effort variable", "")
    if effort_variable not in EFFORT_VARIABLE_VALUES:
        errors.append(f"Effort variable must be yes or no, got '{effort_variable}'")
    return errors


def check_row(row: dict[str, str], frontmatter_for_source) -> list[str]:
    name = row["Agent"]
    frontmatter = frontmatter_for_source(row["Source"])
    if frontmatter is None:
        return violation(name, f"no frontmatter source at {row['Source']}")
    final_model, final_effort = row["Final model"], row["Final effort"]
    if row["Decision"] not in DECISIONS:
        return violation(name, f"decision '{row['Decision']}' not in {sorted(DECISIONS)}")
    if final_effort not in EFFORT_RANK or row["Baseline effort"] not in EFFORT_RANK:
        return violation(name, "effort outside the allowed set")
    is_skill = final_model == NOT_APPLICABLE
    if is_skill and row["Baseline model"] != NOT_APPLICABLE:
        return violation(name, "Baseline model must be n/a when Final model is n/a")
    if not is_skill and (
        final_model not in MODEL_RANK or row["Baseline model"] not in MODEL_RANK
    ):
        return violation(name, "model outside the allowed set")
    problems = []
    if frontmatter_field(frontmatter, "model") != ("" if is_skill else final_model):
        problems += violation(name, "Final model differs from frontmatter")
    if frontmatter_field(frontmatter, "effort") != final_effort:
        problems += violation(name, "Final effort differs from frontmatter")
    is_unchanged = (row["Baseline model"], row["Baseline effort"]) == (final_model, final_effort)
    if is_unchanged:
        problems += check_keep_row(name, row)
    else:
        problems += check_tier_change(name, row)
    return problems


def check_keep_row(name: str, row: dict[str, str]) -> list[str]:
    evidence = row["Evidence"]
    if row["Decision"] != "keep":
        return violation(name, "decision contradicts the baseline-to-final movement")
    if row["Eval cost saving (USD)"]:
        return violation(name, "keep row must not report a cost saving")
    if evidence == "no fixture" and row["Fixtures"] != "0":
        return violation(name, "'no fixture' requires Fixtures of 0")
    if evidence == "insufficient fixtures" and not (
        row["Fixtures"].isdigit() and int(row["Fixtures"]) < MIN_FIXTURES
    ):
        return violation(name, f"'insufficient fixtures' requires Fixtures below {MIN_FIXTURES}")
    if evidence not in KEEP_REASONS:
        return violation(name, "keep-row evidence must be one of the known reasons")
    return []


def tier_direction(row: dict[str, str]) -> str:
    """'downgrade', 'upgrade', 'mixed', or 'unchanged' when no ranked pair moved."""
    pairs = [(EFFORT_RANK[row["Baseline effort"]], EFFORT_RANK[row["Final effort"]])]
    if row["Final model"] != NOT_APPLICABLE:
        pairs.append((MODEL_RANK[row["Baseline model"]], MODEL_RANK[row["Final model"]]))
    if any(f > b for b, f in pairs) and any(f < b for b, f in pairs):
        return "mixed"
    if any(f > b for b, f in pairs):
        return "upgrade"
    return "downgrade" if any(f < b for b, f in pairs) else "unchanged"


def check_tier_change(name: str, row: dict[str, str]) -> list[str]:
    """Direction, then evidence format, tie to the row, and cost."""
    direction = tier_direction(row)
    if row["Decision"] != direction:
        return violation(name, f"decision '{row['Decision']}' contradicts a {direction} movement")
    match = EVIDENCE_RE.match(row["Evidence"])
    if not match:
        return violation(name, "evidence missing or malformed")
    if match["model"] in MODEL_ALIASES:
        return violation(name, "evidence names an alias, not a concrete model ID")
    if match["effort"] != row["Final effort"]:
        return violation(name, "evidence effort differs from Final effort")
    if row["Final model"] != NOT_APPLICABLE and not match["model"].startswith(
        f"claude-{row['Final model']}-"
    ):
        return violation(name, "evidence model differs from Final model")
    if int(match["fixtures"]) < MIN_FIXTURES or match["fixtures"] != row["Fixtures"]:
        return violation(name, f"evidence fixtures must equal Fixtures and be >= {MIN_FIXTURES}")
    if direction == "upgrade":
        return []
    baseline, candidate = float(match["baseline_cost"]), float(match["candidate_cost"])
    if not candidate < baseline:
        return violation(name, "candidate cost is not lower than baseline")
    saving = row["Eval cost saving (USD)"]
    if not saving or abs(float(saving) - (baseline - candidate)) > SAVING_TOLERANCE:
        return violation(name, "saving differs from baseline minus candidate cost")
    return []


def agent_info_model_pairs(text: str) -> list[tuple[str, str]]:
    """(agent, model) per row of the table whose header has Agent and Model columns."""
    pairs, columns = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            columns = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if columns is None:
            if AGENT_INFO_AGENT_COLUMN in cells and AGENT_INFO_MODEL_COLUMN in cells:
                columns = (cells.index(AGENT_INFO_AGENT_COLUMN), cells.index(AGENT_INFO_MODEL_COLUMN))
            continue
        if set("".join(cells)) <= {"-", ":", " "}:
            continue
        agent_index, model_index = columns
        pairs.append((cells[agent_index].strip("`"), cells[model_index]))
    return pairs


def agent_info_mismatches(pairs, declared_model_for) -> list[str]:
    """One error per pair whose table model differs from the declared one."""
    errors = []
    for agent, table_model in pairs:
        declared = declared_model_for(agent)
        if declared is None:
            errors.append(f"{agent}: no agent file")
        elif declared != table_model:
            errors.append(f"{agent}: table says {table_model}, frontmatter says {declared}")
    return errors


def repo_declared_model(agent: str):
    source = AGENTS_DIR / f"{agent}.md"
    return frontmatter_field(frontmatter_block(source), "model") if source.is_file() else None


def load_repo_frontmatter(source: str):
    path = REPO_ROOT / source
    return frontmatter_block(path) if path.is_file() else None


def expected_sources() -> set[str]:
    agents = {str(p.relative_to(REPO_ROOT)) for p in AGENTS_DIR.glob("*.md")}
    return agents | set(SKILL_SOURCES)


# --- real repository ---------------------------------------------------------

def test_log_passes_gate():
    errors = check_log(DECISION_LOG_PATH.read_text(encoding="utf-8"), load_repo_frontmatter)
    assert errors == []


def test_log_covers_every_agent_and_named_skill():
    _, rows, parse_errors = parse_log(DECISION_LOG_PATH.read_text(encoding="utf-8"))
    assert parse_errors == []
    actual = {r["Source"] for r in rows}
    expected = expected_sources()
    assert (expected - actual, actual - expected) == (set(), set())


def test_agent_info_model_column_matches_frontmatter():
    pairs = agent_info_model_pairs(AGENT_INFO_PATH.read_text(encoding="utf-8"))
    assert pairs, "no agent rows found under a Model column"
    assert agent_info_mismatches(pairs, repo_declared_model) == []


# --- synthetic fixtures ------------------------------------------------------

GOOD_EVIDENCE = (
    "eval:run-1; model:claude-haiku-5-5; effort:medium; fixtures:3; "
    "trials:3; delta:0; cost:0.40->0.02"
)
FRONTMATTER_BY_SOURCE = {
    "a.md": "model: sonnet\neffort: high",
    "b.md": "model: haiku\neffort: medium",
    "s.md": "effort: medium",
}
ROW_FIELDS = [
    "agent", "source", "baseline_model", "baseline_effort", "final_model",
    "final_effort", "decision", "fixtures", "evidence", "saving",
]


def frontmatter_fake(source):
    return FRONTMATTER_BY_SOURCE.get(source)


def make_log(
    rows, candidates=None, include_recall_gap=True,
    alias="claude-haiku-5-5", effort_variable="yes",
):
    evaluated = candidates if candidates is not None else str(sum(1 for r in rows if is_evaluated(r)))
    head = f"- Candidates evaluated: {evaluated}\n"
    head += f"- Alias resolved: {alias}\n- Effort variable: {effort_variable}\n"
    head += (RECALL_GAP_SENTENCE + "\n") if include_recall_gap else ""
    table = "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n"
    return head + table + "".join("| " + " | ".join(r[c] for c in COLUMNS) + " |\n" for r in rows)


def make_row(**overrides):
    row = {
        "agent": "b", "source": "b.md", "baseline_model": "haiku",
        "baseline_effort": "medium", "final_model": "haiku",
        "final_effort": "medium", "decision": "keep", "evidence": "",
        "fixtures": "3", "saving": "", **overrides,
    }
    return dict(zip(COLUMNS, (row[field] for field in ROW_FIELDS)))


def make_downgrade_row(**overrides):
    defaults = {
        "baseline_model": "sonnet", "baseline_effort": "high",
        "decision": "downgrade", "evidence": GOOD_EVIDENCE, "saving": "0.380",
    }
    return make_row(**{**defaults, **overrides})


def errors_for(row):
    return check_log(make_log([row]), frontmatter_fake)


def test_valid_log_passes():
    rows = [
        make_row(agent="a", source="a.md", baseline_model="sonnet", baseline_effort="high",
                 final_model="sonnet", final_effort="high"),
        make_row(),
        make_row(agent="s", source="s.md", baseline_model="n/a", final_model="n/a"),
    ]
    assert check_log(make_log(rows), frontmatter_fake) == []


def test_valid_downgrade_passes():
    assert errors_for(make_downgrade_row()) == []


def test_final_model_drift_from_frontmatter_fails():
    row = make_downgrade_row(final_model="sonnet", evidence=GOOD_EVIDENCE.replace("haiku", "sonnet"))
    assert any("Final model differs" in e for e in errors_for(row))


def test_skill_row_effort_drift_fails():
    row = make_row(agent="s", source="s.md", baseline_model="n/a", final_model="n/a", final_effort="high")
    assert any("Final effort differs" in e for e in errors_for(row))


def test_keep_decision_with_moved_tier_fails():
    assert any("contradicts" in e for e in errors_for(make_downgrade_row(decision="keep")))


@pytest.mark.parametrize("evidence", [
    "", "  ", "TBD", "baseline", "n/a", "ran it, fine",
    GOOD_EVIDENCE.replace("model:claude-haiku-5-5", "model:haiku"),
])
def test_malformed_downgrade_evidence_fails(evidence):
    assert any("missing or malformed" in e for e in errors_for(make_downgrade_row(evidence=evidence)))


def test_alias_in_evidence_is_rejected():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-haiku")
    assert any("alias" in e for e in errors_for(make_downgrade_row(evidence=evidence)))


def test_evidence_effort_must_match_final_effort():
    evidence = GOOD_EVIDENCE.replace("effort:medium", "effort:high")
    assert any("evidence effort" in e for e in errors_for(make_downgrade_row(evidence=evidence)))


def test_evidence_model_must_match_final_model():
    evidence = GOOD_EVIDENCE.replace("claude-haiku-5-5", "claude-sonnet-5-5")
    assert any("evidence model" in e for e in errors_for(make_downgrade_row(evidence=evidence)))


def test_evidence_fixtures_must_equal_fixtures_column():
    assert any("fixtures" in e for e in errors_for(make_downgrade_row(fixtures="4")))


def test_evidence_fixtures_below_minimum_fails():
    thin = GOOD_EVIDENCE.replace("fixtures:3", "fixtures:1")
    assert any("fixtures" in e for e in errors_for(make_downgrade_row(evidence=thin, fixtures="1")))


def test_candidate_not_cheaper_fails():
    evidence = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.40->0.40")
    assert any("not lower" in e for e in errors_for(make_downgrade_row(evidence=evidence, saving="0")))


def test_saving_must_equal_cost_difference():
    assert any("saving differs" in e for e in errors_for(make_downgrade_row(saving="9.9")))


def test_decision_must_match_movement_direction():
    row = make_downgrade_row(baseline_model="haiku", baseline_effort="low")
    assert any("contradicts a upgrade movement" in e for e in errors_for(row))


def test_mixed_movement_is_rejected():
    assert any("mixed" in e for e in errors_for(make_downgrade_row(baseline_model="haiku", baseline_effort="high", final_model="sonnet")))


def test_upgrade_with_evidence_passes_without_lower_cost():
    row = make_downgrade_row(
        baseline_model="haiku", baseline_effort="low", decision="upgrade",
        evidence=GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.02->0.40"), saving="",
    )
    assert errors_for(row) == []


def test_upgrade_without_evidence_fails():
    row = make_downgrade_row(baseline_model="haiku", baseline_effort="low", decision="upgrade", evidence="")
    assert any("missing or malformed" in e for e in errors_for(row))


def test_duplicate_source_is_rejected():
    assert any("more than once" in e for e in check_log(make_log([make_row(), make_row()]), frontmatter_fake))


def test_row_for_missing_source_is_rejected():
    assert any("no frontmatter source" in e for e in errors_for(make_row(agent="ghost", source="ghost.md")))


def test_table_missing_column_is_rejected():
    text = "| Agent | Source |\n|---|---|\n| a | a.md |\n"
    assert any("missing column" in e for e in check_log(text, frontmatter_fake))


def test_short_row_is_a_named_parse_error():
    text = make_log([make_row()]) + "| b | b.md | haiku |\n"
    assert any("cells, expected" in e for e in check_log(text, frontmatter_fake))


def test_unknown_decision_is_rejected():
    assert any("decision" in e for e in errors_for(make_row(decision="maybe")))


def test_unknown_effort_is_rejected():
    assert any("effort outside" in e for e in errors_for(make_row(final_effort="ultra")))


def test_haiku_row_needs_valid_effort():
    assert any("effort outside" in e for e in errors_for(make_row(final_effort="")))


@pytest.mark.parametrize("alias", [
    "haiku", "claude-haiku", "claude-haiku-5-5 (resolved via headless run)", "Claude-Haiku-5-5", "",
])
def test_alias_resolved_must_be_a_concrete_model_id(alias):
    errors = check_log(make_log([make_row()], alias=alias), frontmatter_fake)
    assert any("Alias resolved must be a concrete model ID" in e for e in errors)


@pytest.mark.parametrize("value", ["maybe", "yes (low and high)", "Yes", ""])
def test_effort_variable_must_be_yes_or_no(value):
    errors = check_log(make_log([make_row()], effort_variable=value), frontmatter_fake)
    assert any("Effort variable must be yes or no" in e for e in errors)


@pytest.mark.parametrize("value", ["yes", "no"])
def test_effort_variable_accepts_yes_and_no(value):
    assert check_log(make_log([make_row()], effort_variable=value), frontmatter_fake) == []


def test_missing_header_fields_are_reported():
    text = make_log([make_row()]).replace("- Alias resolved: claude-haiku-5-5\n", "").replace(
        "- Effort variable: yes\n", ""
    )
    errors = check_log(text, frontmatter_fake)
    assert any("Alias resolved must be a concrete model ID" in e for e in errors)
    assert any("Effort variable must be yes or no" in e for e in errors)


AGENT_INFO_TABLE = """\
| Agent | File | Purpose |
| --- | --- | --- |
| `team` | t.md | not a model table |

| Agent | File | Model | What It Checks |
| --- | --- | --- | --- |
| `a` | a.md | sonnet | x |
| `b` | b.md | haiku | y |
"""


def test_agent_info_pairs_come_from_the_model_column_only():
    assert agent_info_model_pairs(AGENT_INFO_TABLE) == [("a", "sonnet"), ("b", "haiku")]


def test_agent_info_table_without_a_model_column_yields_no_pairs():
    assert agent_info_model_pairs("| Agent | File |\n| --- | --- |\n| `a` | a.md |\n") == []


def test_agent_info_model_mismatch_is_reported():
    declared = {"a": "sonnet", "b": "sonnet"}.get
    assert agent_info_mismatches(agent_info_model_pairs(AGENT_INFO_TABLE), declared) == [
        "b: table says haiku, frontmatter says sonnet"
    ]


def test_agent_info_row_without_an_agent_file_is_reported():
    assert agent_info_mismatches([("ghost", "haiku")], {}.get) == ["ghost: no agent file"]


def test_recall_gap_sentence_is_required():
    text = make_log([make_row()], include_recall_gap=False)
    assert any("recall-gap" in e for e in check_log(text, frontmatter_fake))


def test_candidates_evaluated_counts_tier_changes_and_failed_evals_only():
    rows = [
        make_downgrade_row(),
        make_row(agent="a", source="a.md", baseline_model="sonnet", baseline_effort="high",
                 final_model="sonnet", final_effort="high", evidence="failed eval", fixtures="10"),
        make_row(agent="s", source="s.md", baseline_model="n/a", final_model="n/a", fixtures="0"),
    ]
    assert check_log(make_log(rows, candidates="2"), frontmatter_fake) == []
    assert any("rows show 2" in e for e in check_log(make_log(rows, candidates="3"), frontmatter_fake))


def test_candidates_evaluated_must_match_rows():
    text = make_log([make_row()], candidates="9")
    assert any("Candidates evaluated" in e for e in check_log(text, frontmatter_fake))


@pytest.mark.parametrize("reason,fixtures", [
    ("insufficient fixtures", "1"), ("directory fixtures only", "6"),
    ("no fixture", "0"), ("failed eval", "10"),
])
def test_known_keep_reasons_are_accepted(reason, fixtures):
    assert errors_for(make_row(evidence=reason, fixtures=fixtures)) == []


def test_unknown_keep_reason_is_rejected():
    assert any("known reasons" in e for e in errors_for(make_row(evidence="TBD")))


def test_no_fixture_reason_requires_zero_fixtures():
    assert any("requires Fixtures of 0" in e for e in errors_for(make_row(evidence="no fixture", fixtures="6")))


def test_insufficient_fixtures_reason_requires_fewer_than_the_minimum():
    row = make_row(evidence="insufficient fixtures", fixtures="3")
    assert any("'insufficient fixtures' requires Fixtures below 3" in e for e in errors_for(row))


def test_skill_row_with_a_baseline_model_is_rejected():
    row = make_row(agent="s", source="s.md", baseline_model="haiku", final_model="n/a")
    assert any("Baseline model must be n/a" in e for e in errors_for(row))


def test_unmoved_tier_is_not_reported_as_a_downgrade():
    row = make_row(agent="s", source="s.md", baseline_model="haiku", final_model="n/a")
    assert tier_direction(row) == "unchanged"


def test_keep_row_with_saving_is_rejected():
    assert any("must not report" in e for e in errors_for(make_row(saving="0.2")))


def test_keep_row_cannot_carry_an_eval_record():
    assert any("known reasons" in e for e in errors_for(make_row(evidence=GOOD_EVIDENCE)))
