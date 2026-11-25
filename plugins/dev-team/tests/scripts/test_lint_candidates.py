"""Tests for scripts/lint_candidates.py.

Fixture agents are written under a tmp plugin root; the finder runs through
``main`` (in-process) or as a subprocess when the test is about process-level
properties (hash seed, imports).
"""

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lint_candidates import (
    CatalogEntry,
    load_catalog,
    lookup_catalog,
    main,
    mechanical_signal,
)

SHIPPED_CATALOG = SCRIPTS_DIR.parent / "knowledge" / "lint-rule-catalog.json"


def _agent_text(*bullets: str) -> str:
    body = "\n".join(f"- {b}" for b in bullets)
    return f"# Agent\n\n## Detect\n\n{body}\n\n## Output\n\nNothing.\n"


def _plugin(tmp_path: Path, agents: dict[str, list[str]], templates=None) -> Path:
    """Build a fixture plugin root with agents/ and templates/agents/ files."""
    root = tmp_path / "plugins" / "dev-team"
    (root / "agents").mkdir(parents=True)
    (root / "templates" / "agents").mkdir(parents=True)
    for name, bullets in agents.items():
        (root / "agents" / f"{name}.md").write_text(_agent_text(*bullets), "utf-8")
    for name, bullets in (templates or {}).items():
        (root / "templates" / "agents" / f"{name}.md").write_text(
            _agent_text(*bullets), "utf-8"
        )
    return root


def _catalog(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"entries": entries}), "utf-8")
    return path


def _run_json(capsys, *argv: str) -> dict:
    assert main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


class TestMechanicalSignal:
    def test_mechanical_tag_scores_one(self):
        assert mechanical_signal("anything at all", ["MECHANICAL"]) == 1.0

    def test_judgment_tag_scores_zero_even_with_positive_tokens(self):
        assert mechanical_signal("`var` never allowed", ["JUDGMENT"]) == 0.0

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            pytest.param("`var` never allowed", 1.0, id="backtick-and-never"),
            pytest.param("`require()` calls", 1.0, id="backticked-code"),
            pytest.param("more than 3 levels deep", 1.0, id="numeric-threshold"),
            pytest.param("never mutate shared state", 1.0, id="never"),
            pytest.param("files matching *.test.js", 1.0, id="glob"),
            pytest.param("matches [a-z] only", 1.0, id="regex-class"),
            pytest.param("names that are not meaningful", 0.0, id="negative-only"),
            pytest.param("consider an appropriate name", 0.0, id="two-negatives"),
            pytest.param("`x` is too many", 0.0, id="positive-cancelled"),
            pytest.param("`a` and `b` but consider more", 1.0, id="net-positive"),
            pytest.param("god objects doing too much", 0.0, id="no-tokens"),
            pytest.param("a clear opportunity", 0.0, id="clear-and-opportunity"),
        ],
    )
    def test_untagged_score_is_clamped_token_balance(self, text, expected):
        assert mechanical_signal(text, []) == expected

    def test_two_tags_is_treated_as_untagged(self):
        assert mechanical_signal("`var` never allowed", ["MECHANICAL", "JUDGMENT"]) == 1.0
        assert mechanical_signal("god objects", ["MECHANICAL", "JUDGMENT"]) == 0.0


class TestCatalog:
    def test_first_matching_pattern_wins(self, tmp_path):
        path = _catalog(
            tmp_path,
            [
                {"pattern": "require", "rule": "no-restricted-syntax", "rung": "b"},
                {"pattern": "require\\(\\)", "rule": "other", "rung": "a"},
            ],
        )
        hit = lookup_catalog("`require()` calls", load_catalog(path))
        assert hit == CatalogEntry("require", "no-restricted-syntax", "b")

    def test_miss_returns_none(self, tmp_path):
        path = _catalog(tmp_path, [{"pattern": "require", "rule": "r", "rung": "a"}])
        assert lookup_catalog("god objects", load_catalog(path)) is None

    def test_pattern_is_case_insensitive(self, tmp_path):
        path = _catalog(tmp_path, [{"pattern": "require", "rule": "r", "rung": "a"}])
        assert lookup_catalog("REQUIRE calls", load_catalog(path)) is not None

    def test_shipped_catalog_is_well_formed(self):
        entries = load_catalog(SHIPPED_CATALOG)
        assert entries
        for entry in entries:
            re.compile(entry.pattern)
            assert entry.rung in {"a", "b", "c", "d"}
            assert entry.rule

    def test_shipped_catalog_rules_are_known_rule_ids(self):
        from check_detect_tags import PENDING_RULE_IDS

        unknown = {e.rule for e in load_catalog(SHIPPED_CATALOG)} - PENDING_RULE_IDS
        assert not unknown

    def test_shipped_catalog_maps_the_pilot_bullets(self):
        entries = load_catalog(SHIPPED_CATALOG)
        assert lookup_catalog("`var` → use `const`/`let`", entries).rule == "no-var"
        assert lookup_catalog("`require()` calls", entries).rule == "no-restricted-syntax"
        assert lookup_catalog("Duplicated code blocks", entries) is None


class TestCensus:
    def test_lists_agents_and_templates_with_repo_relative_sorted_paths(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"zeta-review": ["Z one [JUDGMENT]"], "alpha-review": ["A one [JUDGMENT]"]},
            templates={"esm-enforcer": ["`require()` calls [MECHANICAL] rule: x"]},
        )
        report = _run_json(
            capsys, "--plugin-root", str(root), "--catalog", str(SHIPPED_CATALOG)
        )
        files = [c["file"] for c in report["candidates"]]
        assert files == [
            "agents/alpha-review.md",
            "templates/agents/esm-enforcer.md",
            "agents/zeta-review.md",
        ]
        assert not any(str(tmp_path) in f for f in files)

    def test_tagged_bullet_reports_tag_and_untagged_reports_exact_score(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"a-review": ["tagged one [JUDGMENT]", "`var` never allowed"]},
        )
        report = _run_json(
            capsys, "--plugin-root", str(root), "--catalog", str(SHIPPED_CATALOG)
        )
        by_text = {c["text"]: c for c in report["candidates"]}
        tagged = by_text["tagged one"]
        untagged = by_text["`var` never allowed"]
        assert (tagged["tag"], tagged["score"]) == ("JUDGMENT", 0.0)
        assert (untagged["tag"], untagged["score"]) == ("untagged", 1.0)

    def test_census_carries_catalog_rule_and_rung_or_null(self, tmp_path, capsys):
        root = _plugin(
            tmp_path,
            {"a-review": ["`var` → use `const` [MECHANICAL] rule: no-var", "God objects [JUDGMENT]"]},
        )
        report = _run_json(
            capsys, "--plugin-root", str(root), "--catalog", str(SHIPPED_CATALOG)
        )
        miss, hit = report["candidates"]  # sorted by text: "G" < "`"
        assert hit["text"].startswith("`var`")
        assert (hit["rule"], hit["rung"]) == ("no-var", "a")
        assert (miss["rule"], miss["rung"]) == (None, None)

    def test_markdown_format_lists_every_bullet(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["one [JUDGMENT]", "two | pipe [JUDGMENT]"]})
        assert (
            main(["--plugin-root", str(root), "--catalog", str(SHIPPED_CATALOG),
                  "--format", "markdown"])
            == 0
        )
        out = capsys.readouterr().out
        assert "one" in out
        assert "two \\| pipe" in out
        assert str(tmp_path) not in out
