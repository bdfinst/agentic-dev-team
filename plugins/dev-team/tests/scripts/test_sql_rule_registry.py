"""Registry meta-test for the SQL anti-pattern rules (#2283, AC3).

Every rule in ``scripts/lib/sql_rules_*.py`` must:

- pass ``validate_rule`` (shape, one-line message and fix, fixtures present),
- behave as its fixtures declare (script-owned rules), or point at existing
  eval fixtures (agent-owned rules),
- have exactly one entry in ``knowledge/sql-anti-patterns/*.md`` whose family,
  dialect, owner, and severity match, and the catalog must hold no entry
  without a rule.

The per-rule tests are parametrized by rule id, so a failure names the rule.
"""

import re
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_DIR.parents[1]
sys.path.insert(0, str(PLUGIN_DIR / "scripts" / "lib"))

import sql_rules
import sql_scan

CATALOG_DIR = PLUGIN_DIR / "knowledge" / "sql-anti-patterns"
EVAL_FIXTURES = REPO_ROOT / "evals" / "fixtures"

ENTRY_HEADING_RE = re.compile(r"^### (sql\.\S+)\s*$")
FIELD_RE = re.compile(r"^- \*\*(Family|Dialect|Owner|Severity):\*\* (\S+)\s*$")

RULES = sql_rules.discover_rules()
RULE_IDS = [r.id for r in RULES]


def parse_catalog(directory: Path = CATALOG_DIR) -> dict[str, dict]:
    """Map rule id -> {family, dialect, owner, severity, file} for every entry."""
    entries: dict[str, dict] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name == "README.md":
            continue
        current = None
        for line in path.read_text(encoding="utf-8").splitlines():
            heading = ENTRY_HEADING_RE.match(line)
            if heading:
                current = heading.group(1)
                if current in entries:
                    raise AssertionError(f"duplicate catalog entry {current}")
                entries[current] = {"file": path.stem}
                continue
            field = FIELD_RE.match(line)
            if field and current:
                entries[current][field.group(1).lower()] = field.group(2)
    return entries


def parity_problems(rules, entries) -> list[str]:
    """Differences between the registry and the catalog, in both directions."""
    problems: list[str] = []
    by_id = {r.id: r for r in rules}
    for rule_id, rule in by_id.items():
        entry = entries.get(rule_id)
        if entry is None:
            problems.append(f"{rule_id}: no catalog entry")
            continue
        if entry["file"] != rule.family:
            problems.append(
                f"{rule_id}: catalog file {entry['file']}.md is not its family {rule.family}"
            )
        for field in ("family", "dialect", "owner", "severity"):
            if entry.get(field) != getattr(rule, field):
                problems.append(
                    f"{rule_id}: catalog {field} {entry.get(field)!r} != registry {getattr(rule, field)!r}"
                )
    for rule_id in entries:
        if rule_id not in by_id:
            problems.append(f"{rule_id}: catalog entry has no rule")
    return problems


def script_rules():
    return [r for r in RULES if r.owner == sql_rules.OWNER_SCRIPT]


def agent_rules():
    return [r for r in RULES if r.owner == sql_rules.OWNER_AGENT]


def fires(rule, sql) -> list[int]:
    findings = sql_scan.scan_text(
        sql, "fixture.sql", dialect=rule.dialect, rules=[rule]
    )
    return [f["line"] for f in findings if f["rule"] == rule.id]


# --- Registry shape --------------------------------------------------------


def test_the_registry_is_not_empty():
    assert RULES


@pytest.mark.parametrize("rule", RULES, ids=RULE_IDS)
def test_rule_entry_is_valid(rule):
    assert sql_rules.validate_rule(rule) == []


@pytest.mark.parametrize("rule", RULES, ids=RULE_IDS)
def test_rule_declares_a_positive_and_a_negative_fixture(rule):
    assert rule.positive, f"{rule.id} has no positive fixture"
    assert rule.negative, f"{rule.id} has no negative fixture"


# --- Script-owned rules behave as declared ---------------------------------


@pytest.mark.parametrize("rule", script_rules(), ids=[r.id for r in script_rules()])
def test_positive_fixtures_fire_on_the_declared_lines(rule):
    for fixture in rule.positive:
        assert fires(rule, fixture.sql) == list(fixture.lines), fixture.name


@pytest.mark.parametrize("rule", script_rules(), ids=[r.id for r in script_rules()])
def test_negative_fixtures_do_not_fire(rule):
    for fixture in rule.negative:
        assert fires(rule, fixture.sql) == [], fixture.name


# --- Agent-owned rules have eval fixtures ------------------------------------


def test_agent_rule_eval_fixtures_exist():
    """Vacuous until the first agent-owned rule lands; then it names the rule."""
    missing = [
        f"{rule.id}: evals/fixtures/{name}"
        for rule in agent_rules()
        for name in (*rule.positive, *rule.negative)
        if not (EVAL_FIXTURES / name).is_file()
    ]
    assert missing == []


# --- Catalog parity ---------------------------------------------------------


def test_catalog_matches_registry():
    assert parity_problems(RULES, parse_catalog()) == []


@pytest.mark.parametrize("rule", RULES, ids=RULE_IDS)
def test_rule_has_a_catalog_entry(rule):
    assert rule.id in parse_catalog(), (
        f"{rule.id} has no entry in knowledge/sql-anti-patterns/"
    )


def test_catalog_has_no_entry_without_a_rule():
    orphans = sorted(set(parse_catalog()) - set(RULE_IDS))
    assert orphans == []


# --- The checks themselves can fail --------------------------------------------


def _synthetic(**overrides):
    base = {
        "id": "sql.demo.thing",
        "family": "demo",
        "dialect": "ansi",
        "owner": "script",
        "severity": "warning",
        "message": "m",
        "fix": "f",
        "positive": (sql_rules.Fixture("p", "x", (1,)),),
        "negative": (sql_rules.Fixture("n", "y"),),
        "check": lambda ctx: [],
    }
    base.update(overrides)
    return sql_rules.Rule(**base)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"positive": ()}, "no positive fixture"),
        ({"negative": ()}, "no negative fixture"),
        ({"check": None}, "has no check"),
        ({"severity": "fatal"}, "unknown severity"),
        ({"message": "two\nlines"}, "message must be one"),
        ({"family": "other"}, "differs from the id"),
        ({"positive": (sql_rules.Fixture("p", "x"),)}, "positive fixture must be"),
    ],
)
def test_validate_rule_rejects_a_malformed_entry(overrides, expected):
    problems = sql_rules.validate_rule(_synthetic(**overrides))
    assert any(expected in p for p in problems), problems


def test_parity_check_flags_a_rule_without_an_entry():
    assert parity_problems([_synthetic()], {}) == ["sql.demo.thing: no catalog entry"]


def test_parity_check_flags_an_entry_without_a_rule():
    entries = {"sql.demo.ghost": {"file": "demo", "family": "demo"}}
    assert parity_problems([], entries) == ["sql.demo.ghost: catalog entry has no rule"]


def test_parity_check_flags_a_severity_mismatch():
    entries = {
        "sql.demo.thing": {
            "file": "demo",
            "family": "demo",
            "dialect": "ansi",
            "owner": "script",
            "severity": "error",
        }
    }
    problems = parity_problems([_synthetic()], entries)
    assert len(problems) == 1 and "severity" in problems[0]


def test_a_misbehaving_fixture_is_detected():
    rule = _synthetic(positive=(sql_rules.Fixture("p", "x", (1,)),))
    assert fires(rule, "x") != list(rule.positive[0].lines)


def test_catalog_parser_reads_a_family_file(tmp_path):
    (tmp_path / "README.md").write_text("### sql.not.an-entry\n")
    (tmp_path / "demo.md").write_text(
        "### sql.demo.thing\n\n- **Family:** demo\n- **Dialect:** tsql\n- **Owner:** agent\n- **Severity:** error\n"
    )
    assert parse_catalog(tmp_path) == {
        "sql.demo.thing": {
            "file": "demo",
            "family": "demo",
            "dialect": "tsql",
            "owner": "agent",
            "severity": "error",
        }
    }
