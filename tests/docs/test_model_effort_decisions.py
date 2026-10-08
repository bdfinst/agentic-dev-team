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
    sources = [r["Source"] for r in rows]
    for dup in sorted({s for s in sources if sources.count(s) > 1}):
        errors.append(f"{dup}: listed more than once")
    for row in rows:
        errors += check_row(row, frontmatter_for_source)
    evaluated = sum(
        1 for r in rows
        if r["Decision"] != "keep" or r["Evidence"] in EVALUATED_KEEP_REASONS
    )
    if headers.get("Candidates evaluated") != str(evaluated):
        errors.append(
            f"Candidates evaluated is '{headers.get('Candidates evaluated')}', "
            f"rows show {evaluated}"
        )
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
    if evidence not in KEEP_REASONS and not EVIDENCE_RE.match(evidence):
        return violation(name, "keep-row evidence is neither a reason nor well-formed")
    return []


def tier_direction(row: dict[str, str]) -> str:
    """'downgrade', 'upgrade', or 'mixed' for a row whose tier moved."""
    pairs = [(EFFORT_RANK[row["Baseline effort"]], EFFORT_RANK[row["Final effort"]])]
    if row["Final model"] != NOT_APPLICABLE:
        pairs.append((MODEL_RANK[row["Baseline model"]], MODEL_RANK[row["Final model"]]))
    if any(f > b for b, f in pairs) and any(f < b for b, f in pairs):
        return "mixed"
    return "upgrade" if any(f > b for b, f in pairs) else "downgrade"


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
    mismatches = []
    for line in AGENT_INFO_PATH.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"`[a-z0-9-]+`", cells[0]):
            continue
        source = AGENTS_DIR / f"{cells[0].strip('`')}.md"
        if source.is_file() and cells[2] in MODEL_RANK:
            declared = frontmatter_field(frontmatter_block(source), "model")
            if declared != cells[2]:
                mismatches.append(f"{cells[0]}: table says {cells[2]}, frontmatter says {declared}")
    assert mismatches == []


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


def make_log(rows, candidates=None, include_recall_gap=True):
    evaluated = candidates if candidates is not None else str(
        sum(1 for r in rows if r[6] != "keep" or r[8] in EVALUATED_KEEP_REASONS)
    )
    head = f"- Candidates evaluated: {evaluated}\n"
    head += (RECALL_GAP_SENTENCE + "\n") if include_recall_gap else ""
    table = "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n"
    return head + table + "".join("| " + " | ".join(r) + " |\n" for r in rows)


def make_row(**overrides):
    row = {
        "agent": "b", "source": "b.md", "baseline_model": "haiku",
        "baseline_effort": "medium", "final_model": "haiku",
        "final_effort": "medium", "decision": "keep", "evidence": "",
        "fixtures": "3", "saving": "", **overrides,
    }
    return [row[field] for field in ROW_FIELDS]


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


def test_recall_gap_sentence_is_required():
    text = make_log([make_row()], include_recall_gap=False)
    assert any("recall-gap" in e for e in check_log(text, frontmatter_fake))


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
    assert any("keep-row evidence" in e for e in errors_for(make_row(evidence="TBD")))


def test_no_fixture_reason_requires_zero_fixtures():
    assert any("requires Fixtures of 0" in e for e in errors_for(make_row(evidence="no fixture", fixtures="6")))


def test_keep_row_with_saving_is_rejected():
    assert any("must not report" in e for e in errors_for(make_row(saving="0.2")))
