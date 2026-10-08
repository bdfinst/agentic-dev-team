"""Gate for docs/model-effort-decisions.md.

The log records the per-agent model/effort decision and its eval evidence.
Agent frontmatter stays authoritative; this gate checks that the log's Final
columns equal it and that every downgrade carries well-formed evidence.
Baseline is historical text: nothing here reads git.
"""

from __future__ import annotations

import re
import sys

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tests" / "agents"))

from _plugin_dirs import frontmatter_block, frontmatter_field

LOG = REPO_ROOT / "docs" / "model-effort-decisions.md"
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
SKILL_SOURCES = [
    "plugins/dev-team/skills/co-evolution-audit/SKILL.md",
    "plugins/dev-team/skills/autoship/SKILL.md",
]

COLUMNS = [
    "Agent", "Source", "Baseline model", "Baseline effort", "Final model",
    "Final effort", "Decision", "Fixtures", "Evidence", "Projected saving",
]
MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
NOT_APPLICABLE = "n/a"
DECISIONS = {"keep", "downgrade"}
KEEP_ONLY = {"correctness-review", "architect", "security-engineer"}
MAX_CANDIDATES = 8
KEEP_REASONS = {"", "no fixture", "insufficient fixtures"}
RECALL_GAP_SENTENCE = (
    "correctness-review recall gap is known and unfixed; "
    "its results are excluded from evidence."
)
EVIDENCE_RE = re.compile(
    r"^eval:\S+; model:(claude-[a-z0-9-]+); "
    r"effort:(low|medium|high|xhigh|max); fixtures:\d+; trials:3; delta:0; "
    r"cost:(\d+(?:\.\d+)?)->(\d+(?:\.\d+)?)$"
)
HEADER_FIELD_RE = re.compile(
    r"^- (Candidates evaluated|Alias resolved|Effort variable): (.+)$", re.MULTILINE
)


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
    rows = []
    for ln in lines[2:]:
        values = [c.strip() for c in ln.strip("|").split("|")]
        rows.append(dict(zip(cells, values)))
    return headers, rows, []


def check_log(text: str, frontmatter_of) -> list[str]:
    """Return one error string per violation; empty means the log passes."""
    headers, rows, errors = parse_log(text)
    if errors:
        return errors
    if RECALL_GAP_SENTENCE not in text:
        errors.append("recall-gap sentence missing from header")
    count = headers.get("Candidates evaluated", "")
    if not count.isdigit() or int(count) > MAX_CANDIDATES:
        errors.append(f"Candidates evaluated must be an integer <= {MAX_CANDIDATES}")
    sources = [r["Source"] for r in rows]
    for dup in sorted({s for s in sources if sources.count(s) > 1}):
        errors.append(f"{dup}: listed more than once")
    for row in rows:
        errors += check_row(row, frontmatter_of)
    return errors


def check_row(row: dict[str, str], frontmatter_of) -> list[str]:
    name = row["Agent"]
    err = lambda msg: [f"{name}: {msg}"]
    fm = frontmatter_of(row["Source"])
    if fm is None:
        return err(f"no frontmatter source at {row['Source']}")
    model_f, effort_f = row["Final model"], row["Final effort"]
    if row["Decision"] not in DECISIONS:
        return err(f"decision '{row['Decision']}' not in {sorted(DECISIONS)}")
    if effort_f not in EFFORT_RANK or row["Baseline effort"] not in EFFORT_RANK:
        return err("effort outside the allowed set")
    is_skill = model_f == NOT_APPLICABLE
    if not is_skill and (model_f not in MODEL_RANK or row["Baseline model"] not in MODEL_RANK):
        return err("model outside the allowed set")
    problems = []
    if frontmatter_field(fm, "model") != ("" if is_skill else model_f):
        problems += err("Final model differs from frontmatter")
    if frontmatter_field(fm, "effort") != effort_f:
        problems += err("Final effort differs from frontmatter")
    same = (row["Baseline model"], row["Baseline effort"]) == (model_f, effort_f)
    if same != (row["Decision"] == "keep"):
        problems += err("decision contradicts the baseline-to-final movement")
    if not same:
        problems += check_downgrade(name, row)
    elif row["Evidence"] and row["Evidence"] not in KEEP_REASONS and not EVIDENCE_RE.match(row["Evidence"]):
        problems += err("keep-row evidence is neither a reason nor well-formed")
    if name in KEEP_ONLY and not same:
        problems += err("agent is keep-only")
    return problems


def check_downgrade(name: str, row: dict[str, str]) -> list[str]:
    """Rank order, then evidence format and cost, for a row whose tier moved."""
    err = lambda msg: [f"{name}: {msg}"]
    rank_up = (
        MODEL_RANK.get(row["Final model"], 0) > MODEL_RANK.get(row["Baseline model"], 0)
        or EFFORT_RANK[row["Final effort"]] > EFFORT_RANK[row["Baseline effort"]]
    )
    if rank_up:
        return err("tier rises; this change is downgrade-only")
    match = EVIDENCE_RE.match(row["Evidence"])
    if not match:
        return err("evidence missing or malformed")
    if match.group(1) in {"claude-haiku", "claude-sonnet", "claude-opus"}:
        return err("evidence names an alias, not a concrete model ID")
    if not float(match.group(4)) < float(match.group(3)):
        return err("candidate cost is not lower than baseline")
    return []


def repo_frontmatter(source: str):
    path = REPO_ROOT / source
    return frontmatter_block(path) if path.is_file() else None


# --- real repository ---------------------------------------------------------

def expected_sources() -> set[str]:
    agents = {str(p.relative_to(REPO_ROOT)) for p in AGENTS_DIR.glob("*.md")}
    return agents | set(SKILL_SOURCES)


def test_log_passes_gate():
    errors = check_log(LOG.read_text(encoding="utf-8"), repo_frontmatter)
    assert errors == []


def test_log_covers_every_agent_and_named_skill():
    _, rows, _ = parse_log(LOG.read_text(encoding="utf-8"))
    assert {r["Source"] for r in rows} == expected_sources()


# --- synthetic fixtures ------------------------------------------------------

GOOD_EVIDENCE = (
    "eval:run-1; model:claude-haiku-5-5; effort:medium; fixtures:3; "
    "trials:3; delta:0; cost:0.40->0.02"
)
FM = {
    "a.md": "model: sonnet\neffort: high",
    "b.md": "model: haiku\neffort: medium",
    "s.md": "effort: medium",
}


def fm_of(source):
    return FM.get(source)


def make_log(rows, candidates="1", recall=True):
    head = f"- Candidates evaluated: {candidates}\n"
    head += (RECALL_GAP_SENTENCE + "\n") if recall else ""
    table = "| " + " | ".join(COLUMNS) + " |\n|" + "---|" * len(COLUMNS) + "\n"
    for r in rows:
        table += "| " + " | ".join(r) + " |\n"
    return head + table


def row(agent, source, bm, be, fm_, fe, decision, evidence="", fixtures="3"):
    return [agent, source, bm, be, fm_, fe, decision, fixtures, evidence, ""]


KEEP_B = row("b", "b.md", "haiku", "medium", "haiku", "medium", "keep")
KEEP_A = row("a", "a.md", "sonnet", "high", "sonnet", "high", "keep")
SKILL = row("s", "s.md", "n/a", "medium", "n/a", "medium", "keep")


def test_valid_log_passes():
    assert check_log(make_log([KEEP_A, KEEP_B, SKILL]), fm_of) == []


def test_valid_downgrade_passes():
    new_fm = dict(FM, **{"a.md": "model: haiku\neffort: medium"})
    d = row("a", "a.md", "sonnet", "high", "haiku", "medium", "downgrade", GOOD_EVIDENCE)
    assert check_log(make_log([d]), new_fm.get) == []


def test_final_drifts_from_frontmatter():
    drift = row("a", "a.md", "sonnet", "high", "haiku", "high", "downgrade", GOOD_EVIDENCE)
    assert any("a: Final model differs" in e for e in check_log(make_log([drift]), fm_of))


def test_decision_contradicts_movement():
    bad = row("b", "b.md", "sonnet", "medium", "haiku", "medium", "keep")
    assert any("contradicts" in e for e in check_log(make_log([bad]), fm_of))


def test_bad_evidence_cases_fail():
    for ev in ["", "  ", "TBD", "baseline", "n/a", "ran it, fine",
               GOOD_EVIDENCE.replace("model:claude-haiku-5-5", "model:haiku")]:
        d = row("b", "b.md", "sonnet", "medium", "haiku", "medium", "downgrade", ev)
        assert any("evidence" in e for e in check_log(make_log([d]), fm_of)), ev


def test_candidate_not_cheaper_fails():
    ev = GOOD_EVIDENCE.replace("cost:0.40->0.02", "cost:0.40->0.40")
    d = row("b", "b.md", "sonnet", "medium", "haiku", "medium", "downgrade", ev)
    assert any("not lower" in e for e in check_log(make_log([d]), fm_of))


def test_upgrade_is_rejected():
    d = row("a", "a.md", "haiku", "high", "sonnet", "high", "downgrade", GOOD_EVIDENCE)
    assert any("downgrade-only" in e for e in check_log(make_log([d]), fm_of))


def test_keep_only_agents_cannot_change():
    fm = {"x.md": "model: sonnet\neffort: high"}.get
    d = row("architect", "x.md", "opus", "high", "sonnet", "high", "downgrade", GOOD_EVIDENCE)
    assert any("keep-only" in e for e in check_log(make_log([d]), fm))


def test_high_stakes_change_without_evidence_fails():
    fm = {"x.md": "model: sonnet\neffort: high"}.get
    d = row("security-review", "x.md", "opus", "high", "sonnet", "high", "downgrade", "")
    assert any("evidence" in e for e in check_log(make_log([d]), fm))


def test_duplicate_stale_and_unparseable():
    dup = check_log(make_log([KEEP_B, KEEP_B]), fm_of)
    assert any("more than once" in e for e in dup)
    ghost = row("ghost", "ghost.md", "haiku", "medium", "haiku", "medium", "keep")
    assert any("no frontmatter source" in e for e in check_log(make_log([ghost]), fm_of))
    no_col = "| Agent | Source |\n|---|---|\n| a | a.md |\n"
    assert any("missing column" in e for e in check_log(no_col, fm_of))


def test_invalid_enums_fail():
    maybe = row("b", "b.md", "haiku", "medium", "haiku", "medium", "maybe")
    ultra = row("b", "b.md", "haiku", "medium", "haiku", "ultra", "keep")
    assert any("decision" in e for e in check_log(make_log([maybe]), fm_of))
    assert any("effort outside" in e for e in check_log(make_log([ultra]), fm_of))


def test_haiku_agent_needs_valid_effort():
    blank = row("b", "b.md", "haiku", "medium", "haiku", "", "keep")
    assert any("effort outside" in e for e in check_log(make_log([blank]), fm_of))


def test_skill_row_effort_drift_fails():
    drift = row("s", "s.md", "n/a", "medium", "n/a", "high", "downgrade", GOOD_EVIDENCE)
    assert any("Final effort differs" in e for e in check_log(make_log([drift]), fm_of))


def test_header_rules():
    assert any("recall-gap" in e for e in check_log(make_log([KEEP_B], recall=False), fm_of))
    assert any("Candidates evaluated" in e for e in check_log(make_log([KEEP_B], candidates="9"), fm_of))


def test_keep_reasons_allowed_and_unknown_rejected():
    ok = row("b", "b.md", "haiku", "medium", "haiku", "medium", "keep", "no fixture")
    junk = row("b", "b.md", "haiku", "medium", "haiku", "medium", "keep", "TBD")
    assert check_log(make_log([ok]), fm_of) == []
    assert any("keep-row evidence" in e for e in check_log(make_log([junk]), fm_of))
