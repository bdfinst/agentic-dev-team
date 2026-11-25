"""Tests for scripts/lint_candidates.py.

Fixture agents are written under a tmp plugin root; the finder runs through
``main`` (in-process) or as a subprocess when the test is about process-level
properties (hash seed, imports, console encoding).
"""

import ast
import json
import os
import re
import subprocess
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
SCRIPT = SCRIPTS_DIR / "lint_candidates.py"


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


# A small fixture catalog: census and ranking tests must not depend on which
# bullets the shipped catalog happens to map.
FIXTURE_ENTRIES = [
    {"pattern": "`var`", "rule": "no-var", "rung": "a"},
    {"pattern": "`let` never reassigned", "rule": "prefer-const", "rung": "a"},
    {"pattern": "require\\(\\)", "rule": "no-restricted-syntax", "rung": "b"},
]


def _fixture_catalog(tmp_path: Path) -> Path:
    return _catalog(tmp_path, FIXTURE_ENTRIES)


def _run_json(capsys, tmp_path: Path, root: Path) -> dict:
    argv = ["--plugin-root", str(root), "--catalog", str(_fixture_catalog(tmp_path))]
    assert main(argv) == 0
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
        assert (
            mechanical_signal("`var` never allowed", ["MECHANICAL", "JUDGMENT"]) == 1.0
        )
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
        from check_detect_tags import load_rule_ids

        unknown = {
            e.rule for e in load_catalog(SHIPPED_CATALOG)
        } - load_rule_ids().mappable
        assert not unknown

    def test_shipped_catalog_maps_the_pilot_bullets(self):
        entries = load_catalog(SHIPPED_CATALOG)
        assert lookup_catalog("`var` → use `const`/`let`", entries).rule == "no-var"
        assert (
            lookup_catalog("`require()` calls", entries).rule == "no-restricted-syntax"
        )
        assert lookup_catalog("Duplicated code blocks", entries) is None

    @pytest.mark.parametrize(
        "method",
        ["push", "pop", "shift", "unshift", "splice", "reverse", "sort", "fill"],
    )
    @pytest.mark.parametrize("call", ["`.{m}()` → copy", "`arr.{m}(item)` call"])
    def test_shipped_catalog_maps_array_mutations_with_or_without_arguments(
        self, method, call
    ):
        hit = lookup_catalog(call.format(m=method), load_catalog(SHIPPED_CATALOG))
        assert hit is not None
        assert hit.rule == "functional/immutable-data"

    def test_shipped_catalog_does_not_map_the_spread_copy_exception(self):
        text = "Exception: mutations on spread copies `[...arr].sort()` allowed"
        assert lookup_catalog(text, load_catalog(SHIPPED_CATALOG)) is None


class TestCensus:
    def test_lists_agents_and_templates_with_repo_relative_sorted_paths(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"zeta-review": ["Z one [JUDGMENT]"], "alpha-review": ["A one [JUDGMENT]"]},
            templates={"esm-enforcer": ["`require()` calls [MECHANICAL] rule: x"]},
        )
        report = _run_json(capsys, tmp_path, root)
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
        report = _run_json(capsys, tmp_path, root)
        by_text = {c["text"]: c for c in report["candidates"]}
        tagged = by_text["tagged one"]
        untagged = by_text["`var` never allowed"]
        assert (tagged["tag"], tagged["score"]) == ("JUDGMENT", 0.0)
        assert (untagged["tag"], untagged["score"]) == ("untagged", 1.0)

    def test_census_carries_catalog_rule_and_rung_or_null(self, tmp_path, capsys):
        root = _plugin(
            tmp_path,
            {
                "a-review": [
                    "`var` → use `const` [MECHANICAL] rule: no-var",
                    "God objects [JUDGMENT]",
                ]
            },
        )
        report = _run_json(capsys, tmp_path, root)
        miss, hit = report["candidates"]  # sorted by text: "G" < "`"
        assert hit["text"].startswith("`var`")
        assert (hit["rule"], hit["rung"]) == ("no-var", "a")
        assert (miss["rule"], miss["rung"]) == (None, None)

    def test_markdown_format_lists_every_bullet_with_pipes_escaped(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path, {"a-review": ["one [JUDGMENT]", "two | pipe [JUDGMENT]"]}
        )
        argv = [
            "--plugin-root",
            str(root),
            "--catalog",
            str(_fixture_catalog(tmp_path)),
            "--format",
            "markdown",
        ]
        assert main(argv) == 0
        lines = capsys.readouterr().out.splitlines()
        assert "| # | agent | tag | score | rule | rung | bullet |" in lines
        assert "| 1 | a-review | JUDGMENT | 0.0 | - | - | one |" in lines
        assert "| 2 | a-review | JUDGMENT | 0.0 | - | - | two \\| pipe |" in lines
        assert not any(str(tmp_path) in line for line in lines)

    @pytest.mark.parametrize(
        ("column", "entry"),
        [
            pytest.param("rule", {"pattern": "one", "rule": "a|b"}, id="rule"),
            pytest.param(
                "rung", {"pattern": "one", "rule": "r", "rung": "c|d"}, id="rung"
            ),
        ],
    )
    def test_markdown_escapes_pipes_in_catalog_cells(
        self, tmp_path, capsys, column, entry
    ):
        root = _plugin(tmp_path, {"a-review": ["one [JUDGMENT]"]})
        catalog = _catalog(tmp_path, [{"rung": "a", **entry}])
        argv = [
            "--plugin-root",
            str(root),
            "--catalog",
            str(catalog),
            "--format",
            "markdown",
        ]
        assert main(argv) == 0
        row = capsys.readouterr().out.splitlines()[-1]
        escaped = entry[column].replace("|", "\\|")
        assert escaped in row
        assert len(re.split(r"(?<!\\)\|", row)) == 9  # 7 cells + 2 outer edges


# --- Step 2.2: dynamic mining, join, rank ---------------------------------

LOG_REL = Path(".claude/metrics/review-findings.jsonl")
RAW_REL = Path(".dev-team-reports/code-review/raw")


def _log_row(lens: str, category: str, **extra) -> str:
    row = {
        "lens": lens,
        "category": category,
        "severity": "warning",
        "iteration": 1,
        "fixed": False,
        **extra,
    }
    return json.dumps(row)


def _write_log(project: Path, lines: list[str]) -> None:
    path = project / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")


def _write_log_bytes(project: Path, data: bytes) -> None:
    path = project / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_raw(project: Path, name: str, payload) -> None:
    path = project / RAW_REL / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), "utf-8")


def _raw_finding(file: str, **overrides) -> dict:
    return {
        "agent": "a-review",
        "file": file,
        "category": "require",
        "message": "m",
        **overrides,
    }


def _mine(capsys, root: Path, project: Path, fmt: str = "json") -> dict | str:
    argv = [
        "--plugin-root",
        str(root),
        "--project-root",
        str(project),
        "--catalog",
        str(_fixture_catalog(project)),
        "--format",
        fmt,
    ]
    assert main(argv) == 0
    out = capsys.readouterr().out
    return json.loads(out) if fmt == "json" else out


def _order(report: dict) -> list[str]:
    return [c["agent"] for c in report["candidates"]]


class TestRanking:
    def test_repeated_mechanical_finding_outranks_repeated_judgment_finding(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"naming-review": ["Consider meaningful names"]},
            templates={"esm-enforcer": ["`require()` calls"]},
        )
        _write_log(
            tmp_path,
            [_log_row("naming-review", "meaningful")] * 5
            + [_log_row("esm-enforcer", "require")] * 3,
        )
        report = _mine(capsys, root, tmp_path)
        assert _order(report) == ["esm-enforcer", "naming-review"]
        first, second = report["candidates"]
        assert (first["score"], first["occurrences"], first["rank"]) == (1.0, 3, 3.0)
        assert (second["score"], second["occurrences"], second["rank"]) == (
            0.0,
            5,
            0.0,
        )

    def test_frequency_breaks_equal_scores_regardless_of_agent_name(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {
                "alpha-review": ["A check [MECHANICAL] rule: no-var"],
                "zeta-review": ["Z check [MECHANICAL] rule: no-var"],
            },
        )
        _write_log(
            tmp_path,
            [_log_row("alpha-review", "check")] * 2
            + [_log_row("zeta-review", "check")] * 4,
        )
        report = _mine(capsys, root, tmp_path)
        assert _order(report) == ["zeta-review", "alpha-review"]

    def test_equal_rank_ties_break_by_agent_then_bullet_text(self, tmp_path, capsys):
        root = _plugin(
            tmp_path,
            {
                "b-review": ["zebra [JUDGMENT]", "apple [JUDGMENT]"],
                "a-review": ["mango [JUDGMENT]"],
            },
        )
        _write_log(tmp_path, [])
        report = _mine(capsys, root, tmp_path)
        assert [(c["agent"], c["text"]) for c in report["candidates"]] == [
            ("a-review", "mango"),
            ("b-review", "apple"),
            ("b-review", "zebra"),
        ]

    def test_rank_is_distinct_files_times_occurrences_times_score(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        findings = [
            _raw_finding("src/x.js"),
            _raw_finding("./src/x.js", message="m2"),
            _raw_finding("src/y.js", message="m3"),
        ]
        _write_raw(tmp_path, "section-1.json", findings)
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"], cand["rank"]) == (
            2,
            3,
            6.0,
        )

    def test_backslash_and_slash_paths_are_one_distinct_file(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_raw(
            tmp_path,
            "section-1.json",
            [_raw_finding("src\\x.js"), _raw_finding("src/x.js")],
        )
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"]) == (1, 2)

    def test_raw_artifact_shapes_are_all_read(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        one = _raw_finding("a.js")
        _write_raw(tmp_path, "section-1.json", one)
        _write_raw(tmp_path, "section-2.json", {"findings": [dict(one, file="b.js")]})
        _write_raw(tmp_path, "section-3.json", [dict(one, file="c.js")])
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"]) == (3, 3)

    def test_raw_finding_with_agent_name_and_rule_id_joins_its_bullet(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_raw(
            tmp_path,
            "section-1.json",
            [{"agentName": "a-review", "file": "a.js", "ruleId": "require"}],
        )
        report = _mine(capsys, root, tmp_path)
        assert report["candidates"][0]["occurrences"] == 1
        assert report["unmatched"] == []

    def test_log_and_raw_findings_are_summed(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(tmp_path, [_log_row("a-review", "require")] * 2)
        _write_raw(tmp_path, "section-1.json", [_raw_finding("a.js")])
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"]) == (1, 3)

    def test_unmatched_groups_are_listed_separately_and_sorted(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(
            tmp_path,
            [_log_row("ghost-review", "zzz"), _log_row("a-review", "no-such-keyword")]
            * 2
            + [_log_row("a-review", "require")],
        )
        report = _mine(capsys, root, tmp_path)
        assert [
            (u["agent"], u["category"], u["occurrences"]) for u in report["unmatched"]
        ] == [
            ("a-review", "no-such-keyword", 2),
            ("ghost-review", "zzz", 2),
        ]
        assert report["candidates"][0]["occurrences"] == 1

    def test_category_with_no_alphanumerics_is_unmatched(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(tmp_path, [_log_row("a-review", "---")])
        report = _mine(capsys, root, tmp_path)
        assert [(u["category"], u["occurrences"]) for u in report["unmatched"]] == [
            ("---", 1)
        ]
        assert report["candidates"][0]["occurrences"] == 0

    def test_group_joins_the_first_matching_bullet_in_census_order(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"a-review": ["`require()` in tests", "`require()` calls"]},
        )
        _write_log(tmp_path, [_log_row("a-review", "require")] * 2)
        by_text = {
            c["text"]: c["occurrences"]
            for c in _mine(capsys, root, tmp_path)["candidates"]
        }
        # census order sorts by text: "calls" < "in tests"
        assert by_text == {"`require()` calls": 2, "`require()` in tests": 0}

    def test_category_matches_only_its_own_agents_bullets(self, tmp_path, capsys):
        root = _plugin(
            tmp_path,
            {"a-review": ["`require()` calls"], "b-review": ["`require()` calls"]},
        )
        _write_log(tmp_path, [_log_row("a-review", "require")] * 2)
        by_agent = {c["agent"]: c for c in _mine(capsys, root, tmp_path)["candidates"]}
        assert by_agent["a-review"]["occurrences"] == 2
        assert by_agent["b-review"]["occurrences"] == 0


class TestSkippedRows:
    def test_malformed_log_line_is_counted_and_skipped(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(
            tmp_path,
            [_log_row("a-review", "require")] * 3 + ["{not json"],
        )
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 1
        assert report["candidates"][0]["occurrences"] == 3

    def test_undecodable_log_line_is_counted_and_skipped(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        good = _log_row("a-review", "require").encode("utf-8")
        _write_log_bytes(tmp_path, good + b"\n" + b"\xff\n" + good + b"\n")
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 1
        assert report["candidates"][0]["occurrences"] == 2

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param('{"severity": "warning"}', id="no-lens-no-category"),
            pytest.param('{"lens": "a-review"}', id="no-category"),
            pytest.param('{"category": "require"}', id="no-lens"),
            pytest.param('{"lens": "a-review", "rule": "require"}', id="rule-only"),
            pytest.param('{"lens": "a-review", "smell": "require"}', id="smell-only"),
            pytest.param("[1, 2]", id="not-an-object"),
        ],
    )
    def test_rows_missing_lens_or_category_are_counted_and_skipped(
        self, tmp_path, capsys, line
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(tmp_path, [_log_row("a-review", "require"), line])
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 1
        assert report["candidates"][0]["occurrences"] == 1

    def test_malformed_or_incomplete_raw_artifacts_are_counted(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        raw = tmp_path / RAW_REL
        raw.mkdir(parents=True)
        (raw / "section-bad.json").write_text("{nope", "utf-8")
        _write_raw(
            tmp_path,
            "section-ok.json",
            [
                _raw_finding("a.js"),
                {"file": "a.js", "message": "no agent or category"},
            ],
        )
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 2
        assert report["candidates"][0]["occurrences"] == 1

    def test_undecodable_raw_artifact_is_counted_and_skipped(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_raw(tmp_path, "section-ok.json", [_raw_finding("a.js")])
        (tmp_path / RAW_REL / "section-bad.json").write_bytes(b"\xff\xfe\x00")
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 1
        assert report["candidates"][0]["occurrences"] == 1

    def test_raw_artifact_that_cannot_be_read_is_counted_and_skipped(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_raw(tmp_path, "section-ok.json", [_raw_finding("a.js")])
        (tmp_path / RAW_REL / "dir.json").mkdir()
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 1
        assert report["candidates"][0]["occurrences"] == 1


CENSUS_HEADER = "| # | agent | tag | score | rule | rung | bullet |"
FREQUENCY_HEADER = (
    "| # | agent | tag | score | files | occurrences | rank | rule | rung | bullet |"
)


class TestCensusOnly:
    def test_missing_inputs_give_census_only_report_without_frequency(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"a-review": ["one [JUDGMENT]", "two [MECHANICAL] rule: no-var"]},
            templates={"t-enforcer": ["`require()` calls"]},
        )
        report = _mine(capsys, root, tmp_path)
        assert report["frequency_available"] is False
        assert len(report["candidates"]) == 3
        for cand in report["candidates"]:
            assert not {"occurrences", "distinct_files", "rank"} & cand.keys()
        assert "unmatched" not in report

    def test_census_only_candidates_keep_their_tags(self, tmp_path, capsys):
        root = _plugin(
            tmp_path,
            {"a-review": ["one [JUDGMENT]", "two [MECHANICAL] rule: no-var"]},
            templates={"t-enforcer": ["`require()` calls"]},
        )
        tags = {
            c["agent"] + ":" + c["text"][:3]: c["tag"]
            for c in _mine(capsys, root, tmp_path)["candidates"]
        }
        assert tags == {
            "a-review:one": "JUDGMENT",
            "a-review:two": "MECHANICAL",
            "t-enforcer:`re": "untagged",
        }

    def test_markdown_has_no_frequency_column_in_census_only_mode(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["one [JUDGMENT]"]})
        lines = _mine(capsys, root, tmp_path, fmt="markdown").splitlines()
        assert lines[0] == "# Lint candidate census"
        assert CENSUS_HEADER in lines
        assert FREQUENCY_HEADER not in lines
        assert "| 1 | a-review | JUDGMENT | 0.0 | - | - | one |" in lines

    def test_empty_log_still_reports_frequency_columns(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["one [JUDGMENT]"]})
        _write_log(tmp_path, [])
        report = _mine(capsys, root, tmp_path)
        assert report["frequency_available"] is True
        assert report["candidates"][0]["occurrences"] == 0
        assert report["candidates"][0]["distinct_files"] == 0

    def test_markdown_with_frequency_lists_rank_columns(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(tmp_path, [_log_row("a-review", "require")])
        lines = _mine(capsys, root, tmp_path, fmt="markdown").splitlines()
        assert lines[0] == "# Lint candidates"
        assert FREQUENCY_HEADER in lines
        assert (
            "| 1 | a-review | untagged | 1.0 | 1 | 1 | 1.0 | no-restricted-syntax"
            " | b | `require()` calls |"
        ) in lines

    def test_markdown_renders_unmatched_groups_with_cells_escaped(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(
            tmp_path,
            [
                _log_row("ghost|review", "a|b\nc"),
                _log_row("ghost|review", "a|b\nc"),
            ],
        )
        lines = _mine(capsys, root, tmp_path, fmt="markdown").splitlines()
        section = lines[lines.index("## Unmatched finding groups") :]
        assert section == [
            "## Unmatched finding groups",
            "",
            "| agent | category | files | occurrences |",
            "| --- | --- | --- | --- |",
            "| ghost\\|review | a\\|b c | 1 | 2 |",
        ]

    def test_markdown_omits_unmatched_section_when_every_group_joins(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(tmp_path, [_log_row("a-review", "require")])
        assert "## Unmatched finding groups" not in _mine(
            capsys, root, tmp_path, fmt="markdown"
        )


def _log_rows() -> list[str]:
    return (
        [_log_row("naming-review", "meaningful")] * 5
        + [_log_row("esm-enforcer", "require")] * 3
        + [_log_row("js-review", "var")] * 3
        + [_log_row("js-review", "never reassigned")] * 3
        + [_log_row("ghost", "g1"), _log_row("ghost", "g2"), "{bad"]
    )


@pytest.fixture(scope="module")
def stability_runs(tmp_path_factory) -> dict:
    """Two projects (forward/shuffled rows, different hash seeds), both formats."""
    outputs = {}
    for label, seed, reverse in (("a", "1", False), ("b", "4242", True)):
        project = tmp_path_factory.mktemp(label)
        root, project = TestStability._fixture(project, reverse)
        outputs[label] = {
            "project": str(project),
            **{
                fmt: TestStability._run(root, project, seed, fmt)
                for fmt in ("json", "markdown")
            },
        }
    outputs["base"] = str(tmp_path_factory.getbasetemp())
    return outputs


class TestStability:
    @staticmethod
    def _fixture(tmp_path: Path, reverse: bool) -> tuple[Path, Path]:
        root = _plugin(
            tmp_path,
            {
                "naming-review": ["Consider meaningful names"],
                "js-review": ["`var` → use `const`", "`let` never reassigned"],
            },
            templates={"esm-enforcer": ["`require()` calls"]},
        )
        rows = _log_rows()
        order = list(range(len(rows)))
        if reverse:
            order.reverse()
        _write_log(tmp_path, [rows[i] for i in order])
        raw = [_raw_finding(f"src/{n}.js", agent="esm-enforcer") for n in "dcba"]
        for idx in order[:4]:
            _write_raw(tmp_path, f"section-{idx}.json", raw[idx % 4 :] + raw[: idx % 4])
        return root, tmp_path

    @staticmethod
    def _run(root: Path, project: Path, seed: str, fmt: str) -> bytes:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--plugin-root",
                str(root),
                "--project-root",
                str(project),
                "--catalog",
                str(_fixture_catalog(project)),
                "--format",
                fmt,
            ],
            capture_output=True,
            env=env,
            check=True,
            cwd=str(project),
        )
        return proc.stdout

    @pytest.mark.parametrize("fmt", ["json", "markdown"])
    def test_output_is_identical_across_hash_seeds_and_input_order(
        self, stability_runs, fmt
    ):
        assert stability_runs["a"][fmt] == stability_runs["b"][fmt]

    @pytest.mark.parametrize("fmt", ["json", "markdown"])
    def test_output_contains_no_absolute_path(self, stability_runs, fmt):
        text = stability_runs["a"][fmt].decode()
        assert stability_runs["a"]["project"] not in text
        assert stability_runs["base"] not in text

    @pytest.mark.parametrize("fmt", ["json", "markdown"])
    def test_output_contains_no_date(self, stability_runs, fmt):
        assert not re.search(r"\d{4}-\d{2}-\d{2}", stability_runs["a"][fmt].decode())

    def test_json_keys_are_sorted(self, tmp_path):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        out = self._run(root, tmp_path, "0", "json").decode()
        assert (
            json.dumps(json.loads(out), sort_keys=True, indent=2, ensure_ascii=False)
            + "\n"
            == out
        )


class TestConsoleEncoding:
    def test_non_ascii_bullet_prints_under_a_legacy_console_encoding(self, tmp_path):
        root = _plugin(tmp_path, {"a-review": ["`var` → use `const`"]})
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--plugin-root",
                str(root),
                "--catalog",
                str(_fixture_catalog(tmp_path)),
                "--project-root",
                str(tmp_path),
            ],
            capture_output=True,
            env=env,
            cwd=str(tmp_path),
            check=False,
        )
        assert proc.returncode == 0, proc.stderr.decode()
        assert "→" in proc.stdout.decode("utf-8")


class TestNoModelSdk:
    def test_every_import_is_stdlib_or_a_sibling_module(self):
        tree = ast.parse(SCRIPT.read_text("utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
        siblings = {"detect_bullets", "finding_signature"}
        assert not roots - set(sys.stdlib_module_names) - siblings
