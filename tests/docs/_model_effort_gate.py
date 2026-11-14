"""Gate rules for docs/model-effort-decisions.md.

The log records the per-agent model/effort decision and its eval evidence.
Agent frontmatter stays authoritative; these rules check that the log's Final
columns equal it, that every tier change carries well-formed evidence tied to
the row, and that each evidence run ID resolves to a complete, committed run
artifact whose model, effort, fixtures, trials, cost and saving agree with the
row. Baseline is historical text: nothing here reads git.

Named without a leading ``test_`` so pytest does not collect it; the tests are
in ``test_model_effort_decisions.py``.
"""

from __future__ import annotations

import json
import re

from _plugin_dirs import frontmatter_block, frontmatter_field

from _repo_root import REPO_ROOT

DECISION_LOG_PATH = REPO_ROOT / "docs" / "model-effort-decisions.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
SKILLS_DIR = REPO_ROOT / "plugins" / "dev-team" / "skills"
RUNS_DIR = REPO_ROOT / "evals" / "model-effort" / "runs"

EVIDENCE_COLUMN = "Evidence or reason"
SAVING_COLUMN = "Eval cost saving (USD)"
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
    SAVING_COLUMN,
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
# The value scripts/lib/model_effort/run_status.py writes as RunStatus.COMPLETE.
RUN_STATUS_COMPLETE = "complete"
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
# every trial passed. An upgrade records delta:+N, the number of expected
# findings the higher tier catches in at least half its trials that the
# current tier misses in every trial; the stress run's verdict lists them.
EVIDENCE_RE = re.compile(
    r"^eval:(?P<run_id>[A-Za-z0-9][A-Za-z0-9-]*); "
    r"model:(?P<model>claude-[a-z0-9-]+); "
    rf"effort:(?P<effort>{'|'.join(map(re.escape, EFFORT_RANK))}); "
    r"fixtures:(?P<fixtures>\d+); "
    r"trials:(?P<trials>\d+); delta:(?P<delta>0|\+[1-9]\d*); "
    r"cost:(?P<baseline_cost>\d+(?:\.\d+)?)->(?P<candidate_cost>\d+(?:\.\d+)?)$"
)
DOWNGRADE_DELTA = "0"
# Agents whose results are excluded from evidence; the same set as
# scripts/lib/model_effort/verdict.py RECALL_GAP_EXCLUDED_AGENTS.
RECALL_GAP_AGENTS = {"correctness-review"}
SAVING_RE = re.compile(r"^\d+(?:\.\d+)?$")
CONCRETE_MODEL_ID_RE = re.compile(r"^claude-[a-z0-9-]+$")
EFFORT_VARIABLE_VALUES = {"yes", "no"}
HEADER_FIELD_RE = re.compile(
    r"^- (Candidates evaluated|Alias resolved|Effort variable): (.+)$", re.MULTILINE
)


def as_violation(name: str, message: str) -> list[str]:
    return [f"{name}: {message}"]


def load_repo_artifact(run_id: str):
    """The committed run artifact for run_id, or None when no file exists."""
    path = RUNS_DIR / f"{run_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


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


def check_log(text: str, frontmatter_for_source, artifact_for_run) -> list[str]:
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
    row: dict[str, str], frontmatter_for_source, artifact_for_run
) -> list[str]:
    name = row["Agent"]
    frontmatter = frontmatter_for_source(row["Source"])
    if frontmatter is None:
        return as_violation(name, f"no frontmatter source at {row['Source']}")
    final_model, final_effort = row["Final model"], row["Final effort"]
    if row["Decision"] not in DECISIONS:
        return as_violation(
            name, f"decision '{row['Decision']}' not in {sorted(DECISIONS)}"
        )
    if final_effort not in EFFORT_RANK or row["Baseline effort"] not in EFFORT_RANK:
        return as_violation(name, "effort outside the allowed set")
    is_skill = final_model == NOT_APPLICABLE
    if is_skill and row["Baseline model"] != NOT_APPLICABLE:
        return as_violation(
            name,
            f"Baseline model must be {NOT_APPLICABLE} when Final model is {NOT_APPLICABLE}",
        )
    if not is_skill and (
        final_model not in MODEL_RANK or row["Baseline model"] not in MODEL_RANK
    ):
        return as_violation(name, "model outside the allowed set")
    problems = []
    if frontmatter_field(frontmatter, "model") != ("" if is_skill else final_model):
        problems += as_violation(name, "Final model differs from frontmatter")
    if frontmatter_field(frontmatter, "effort") != final_effort:
        problems += as_violation(name, "Final effort differs from frontmatter")
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
        return as_violation(name, "decision contradicts the baseline-to-final movement")
    if row[SAVING_COLUMN]:
        return as_violation(name, "keep row must not report a cost saving")
    if reason == REASON_NO_FIXTURE and row["Fixtures"] != "0":
        return as_violation(name, f"'{REASON_NO_FIXTURE}' requires Fixtures of 0")
    if reason == REASON_INSUFFICIENT_FIXTURES and (
        not row["Fixtures"].isdigit() or has_minimum_fixtures(row)
    ):
        return as_violation(
            name,
            f"'{REASON_INSUFFICIENT_FIXTURES}' requires Fixtures below {MIN_FIXTURES}",
        )
    if reason == REASON_NOT_SELECTED and not has_minimum_fixtures(row):
        return as_violation(
            name,
            f"'{REASON_NOT_SELECTED}' requires Fixtures of at least {MIN_FIXTURES}",
        )
    if reason == REASON_BLANK and (
        not row["Fixtures"].isdigit() or has_minimum_fixtures(row)
    ):
        return as_violation(
            name, f"a blank reason requires Fixtures below {MIN_FIXTURES}"
        )
    if reason == REASON_OPUS_NOT_RUN and row["Final model"] != OPUS:
        return as_violation(
            name, f"'{REASON_OPUS_NOT_RUN}' requires Final model {OPUS}"
        )
    if reason not in KEEP_REASONS:
        return as_violation(name, "keep-row evidence must be one of the known reasons")
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
        return as_violation(
            name, f"decision '{row['Decision']}' contradicts the {direction} movement"
        )
    if name in RECALL_GAP_AGENTS:
        return as_violation(
            name,
            "results are excluded from evidence (known recall gap), "
            "so the tier cannot move",
        )
    match = EVIDENCE_RE.match(row[EVIDENCE_COLUMN])
    if not match:
        return as_violation(name, "evidence missing or malformed")
    if direction == DECISION_DOWNGRADE and match["delta"] != DOWNGRADE_DELTA:
        return as_violation(name, "downgrade evidence must record delta:0")
    if direction == DECISION_UPGRADE and match["delta"] == DOWNGRADE_DELTA:
        return as_violation(
            name, "upgrade evidence must record delta:+N, the expected findings gained"
        )
    if match["model"] in UNVERSIONED_MODEL_IDS:
        return as_violation(
            name, "evidence names a model family, not a concrete model ID"
        )
    if match["effort"] != row["Final effort"]:
        return as_violation(name, "evidence effort differs from Final effort")
    if row["Final model"] != NOT_APPLICABLE and not match["model"].startswith(
        f"claude-{row['Final model']}-"
    ):
        return as_violation(name, "evidence model differs from Final model")
    if int(match["fixtures"]) < MIN_FIXTURES or match["fixtures"] != row["Fixtures"]:
        return as_violation(
            name, f"evidence fixtures must equal Fixtures and be >= {MIN_FIXTURES}"
        )
    problems = check_saving_cell(name, row, match, direction)
    if problems:
        return problems
    return check_artifact(name, row, match, direction, artifact_for_run)


def check_saving_cell(
    name: str, row: dict[str, str], match: re.Match, direction: str
) -> list[str]:
    """A downgrade reports a numeric saving from a cheaper candidate; an upgrade reports none.

    The saving's value is checked against the artifact, not the written costs:
    a cost written at coarse precision could otherwise hide a wrong saving.
    """
    saving = row[SAVING_COLUMN]
    if direction == DECISION_UPGRADE:
        return (
            as_violation(name, "upgrade row must not report a cost saving")
            if saving
            else []
        )
    if not float(match["candidate_cost"]) < float(match["baseline_cost"]):
        return as_violation(name, "candidate cost is not lower than baseline")
    if not SAVING_RE.match(saving):
        return as_violation(name, "downgrade row must report a numeric cost saving")
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
    name: str, row: dict[str, str], match: re.Match, direction: str, artifact_for_run
) -> list[str]:
    """The evidence run resolves to a complete artifact that ran this agent at both tiers with the row's numbers.

    Arms are matched by tier, not by label: a re-run may record the proposed
    tier as its baseline arm.
    """
    run_id = match["run_id"]
    artifact = artifact_for_run(run_id)
    if artifact is None:
        return as_violation(name, f"evidence run {run_id} has no committed artifact")
    if artifact["run_id"] != run_id:
        return as_violation(
            name, f"artifact for {run_id} records run_id '{artifact['run_id']}'"
        )
    if artifact["status"] != RUN_STATUS_COMPLETE:
        return as_violation(
            name,
            f"artifact {run_id} status is '{artifact['status']}', not '{RUN_STATUS_COMPLETE}'",
        )
    if artifact["agent"] != name:
        return as_violation(
            name, f"artifact {run_id} ran agent '{artifact['agent']}', not this row's"
        )
    if artifact.get("tier_change_eligible") is False:
        return as_violation(
            name,
            f"artifact {run_id} is not tier-change eligible "
            "(too few graded trials for its grader)",
        )
    problems = check_verdict(name, row, match, direction, artifact)
    if problems:
        return problems
    arms = artifact["arms"]
    model_arms = [a for a in arms if a["model_id"] == match["model"]]
    if not model_arms:
        return as_violation(
            name, f"artifact {run_id} has no arm with model {match['model']}"
        )
    final_arm = next((a for a in model_arms if a["effort"] == match["effort"]), None)
    if final_arm is None:
        return as_violation(
            name,
            f"artifact {run_id} has no {match['model']} arm at effort {match['effort']}",
        )
    baseline_arm = next(
        (a for a in arms if a is not final_arm and arm_at_baseline_tier(a, row)), None
    )
    if baseline_arm is None:
        return as_violation(
            name, f"artifact {run_id} has no arm at the Baseline model and effort"
        )
    problems = []
    for arm in (baseline_arm, final_arm):
        if len(arm["fixtures"]) != int(match["fixtures"]):
            problems += as_violation(
                name,
                f"evidence fixtures differ from artifact {run_id} "
                f"{arm['effort']} arm ({len(arm['fixtures'])})",
            )
        if arm["trials_per_fixture"] != int(match["trials"]):
            problems += as_violation(
                name,
                f"evidence trials differ from artifact {run_id} "
                f"{arm['effort']} arm ({arm['trials_per_fixture']})",
            )
    for column, arm in (("baseline", baseline_arm), ("candidate", final_arm)):
        reported = arm["totals"]["actual_cost_usd"]
        if not cost_matches(match[f"{column}_cost"], reported):
            problems += as_violation(
                name,
                f"evidence {column} cost {match[f'{column}_cost']} differs from "
                f"artifact {run_id} ({reported})",
            )
    if direction == DECISION_DOWNGRADE:
        artifact_saving = (
            baseline_arm["totals"]["actual_cost_usd"]
            - final_arm["totals"]["actual_cost_usd"]
        )
        if abs(float(row[SAVING_COLUMN]) - artifact_saving) > SAVING_TOLERANCE:
            problems += as_violation(
                name,
                f"saving {row[SAVING_COLUMN]} differs from artifact {run_id} "
                f"baseline minus final cost ({artifact_saving:.4f})",
            )
    return problems


def check_verdict(
    name: str, row: dict[str, str], match: re.Match, direction: str, artifact: dict
) -> list[str]:
    """A stress run's verdict must pick this row's decision and Final tier.

    An upgrade must cite a stress run, since only its verdict shows the higher
    tier catching what the current tier misses; its delta counts those findings.
    An A/B run (no verdict) still backs a downgrade by its arms alone.
    """
    run_id = match["run_id"]
    verdict = artifact.get("verdict")
    if verdict is None:
        if direction == DECISION_UPGRADE:
            return as_violation(
                name,
                "upgrade evidence must cite a stress run with a verdict; "
                f"artifact {run_id} has none",
            )
        return []
    if verdict["decision"] != direction:
        return as_violation(
            name,
            f"artifact {run_id} verdict is '{verdict['decision']}', not "
            f"'{direction}': {verdict['reason']}",
        )
    row_tier = f"{row['Final model']}/{row['Final effort']}"
    verdict_tier = f"{verdict['model']}/{verdict['effort']}"
    model_matches = (
        row["Final model"] == NOT_APPLICABLE or verdict["model"] == row["Final model"]
    )
    if not model_matches or verdict["effort"] != row["Final effort"]:
        return as_violation(
            name,
            f"artifact {run_id} verdict moves to {verdict_tier}, not the row's {row_tier}",
        )
    if direction == DECISION_UPGRADE:
        gained = len(verdict["upgrade"]["findings"])
        if int(match["delta"]) != gained:
            return as_violation(
                name,
                f"evidence delta {match['delta']} differs from artifact {run_id} "
                f"verdict's {gained} upgrade finding(s)",
            )
    return []
