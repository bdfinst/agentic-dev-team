"""Tests for scripts/lint_candidates.py.

Fixture agents are written under a tmp plugin root; the finder runs through
``main`` (in-process) or as a subprocess when the test is about process-level
properties (hash seed, imports).
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


# --- Step 2.2: dynamic mining, join, rank ---------------------------------

LOG_REL = Path(".claude/metrics/review-findings.jsonl")
RAW_REL = Path(".dev-team-reports/code-review/raw")


def _log_row(lens: str, category: str, **extra) -> str:
    row = {"lens": lens, "category": category, "severity": "warning",
           "iteration": 1, "fixed": False, **extra}
    return json.dumps(row)


def _write_log(project: Path, lines: list[str]) -> None:
    path = project / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")


def _write_raw(project: Path, name: str, payload) -> None:
    path = project / RAW_REL / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), "utf-8")


def _mine(capsys, root: Path, project: Path, fmt: str = "json") -> dict | str:
    argv = ["--plugin-root", str(root), "--project-root", str(project),
            "--catalog", str(SHIPPED_CATALOG), "--format", fmt]
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
        assert (second["score"], second["occurrences"], second["rank"]) == (0.0, 5, 0.0)

    def test_frequency_breaks_equal_scores_regardless_of_agent_name(
        self, tmp_path, capsys
    ):
        root = _plugin(
            tmp_path,
            {"alpha-review": ["A check [MECHANICAL] rule: no-var"],
             "zeta-review": ["Z check [MECHANICAL] rule: no-var"]},
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
            {"b-review": ["zebra [JUDGMENT]", "apple [JUDGMENT]"],
             "a-review": ["mango [JUDGMENT]"]},
        )
        _write_log(tmp_path, [])
        report = _mine(capsys, root, tmp_path)
        assert [(c["agent"], c["text"]) for c in report["candidates"]] == [
            ("a-review", "mango"), ("b-review", "apple"), ("b-review", "zebra"),
        ]

    def test_rank_is_distinct_files_times_occurrences_times_score(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        findings = [
            {"agent": "a-review", "file": "src/x.js", "category": "require", "message": "m"},
            {"agent": "a-review", "file": "./src/x.js", "category": "require", "message": "m2"},
            {"agent": "a-review", "file": "src/y.js", "category": "require", "message": "m3"},
        ]
        _write_raw(tmp_path, "section-1.json", findings)
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"], cand["rank"]) == (2, 3, 6.0)

    def test_raw_artifact_shapes_are_all_read(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        one = {"agent": "a-review", "file": "a.js", "category": "require", "message": "m"}
        _write_raw(tmp_path, "section-1.json", one)
        _write_raw(tmp_path, "section-2.json", {"findings": [dict(one, file="b.js")]})
        _write_raw(tmp_path, "section-3.json", [dict(one, file="c.js")])
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"]) == (3, 3)

    def test_log_and_raw_findings_are_summed(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(tmp_path, [_log_row("a-review", "require")] * 2)
        _write_raw(tmp_path, "section-1.json",
                   [{"agent": "a-review", "file": "a.js", "category": "require", "message": "m"}])
        (cand,) = _mine(capsys, root, tmp_path)["candidates"]
        assert (cand["distinct_files"], cand["occurrences"]) == (1, 3)

    def test_unmatched_groups_are_listed_separately_and_sorted(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        _write_log(
            tmp_path,
            [_log_row("ghost-review", "zzz"), _log_row("a-review", "no-such-keyword")] * 2
            + [_log_row("a-review", "require")],
        )
        report = _mine(capsys, root, tmp_path)
        assert [(u["agent"], u["category"], u["occurrences"]) for u in report["unmatched"]] == [
            ("a-review", "no-such-keyword", 2), ("ghost-review", "zzz", 2),
        ]
        assert report["candidates"][0]["occurrences"] == 1

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

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param('{"severity": "warning"}', id="no-lens-no-category"),
            pytest.param('{"lens": "a-review"}', id="no-category"),
            pytest.param('{"category": "require"}', id="no-lens"),
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

    def test_unreadable_or_incomplete_raw_artifacts_are_counted(self, tmp_path, capsys):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        raw = tmp_path / RAW_REL
        raw.mkdir(parents=True)
        (raw / "section-bad.json").write_text("{nope", "utf-8")
        _write_raw(tmp_path, "section-ok.json",
                   [{"agent": "a-review", "file": "a.js", "category": "require", "message": "m"},
                    {"file": "a.js", "message": "no agent or category"}])
        report = _mine(capsys, root, tmp_path)
        assert report["skipped"] == 2
        assert report["candidates"][0]["occurrences"] == 1


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

    def test_markdown_has_no_frequency_column_in_census_only_mode(
        self, tmp_path, capsys
    ):
        root = _plugin(tmp_path, {"a-review": ["one [JUDGMENT]"]})
        out = _mine(capsys, root, tmp_path, fmt="markdown")
        assert "occurrences" not in out
        assert "one" in out

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
        out = _mine(capsys, root, tmp_path, fmt="markdown")
        assert "occurrences" in out and "files" in out and "rank" in out
        assert "| 1 | a-review |" in out


class TestStability:
    def _fixture(self, tmp_path: Path, order: list[int]) -> tuple[Path, Path]:
        root = _plugin(
            tmp_path,
            {"naming-review": ["Consider meaningful names"],
             "js-review": ["`var` → use `const`", "`let` never reassigned"]},
            templates={"esm-enforcer": ["`require()` calls"]},
        )
        rows = (
            [_log_row("naming-review", "meaningful")] * 5
            + [_log_row("esm-enforcer", "require")] * 3
            + [_log_row("js-review", "var")] * 3
            + [_log_row("js-review", "never reassigned")] * 3
            + [_log_row("ghost", "g1"), _log_row("ghost", "g2"), "{bad"]
        )
        _write_log(tmp_path, [rows[i] for i in order])
        raw = [
            {"agent": "esm-enforcer", "file": f"src/{n}.js", "category": "require", "message": "m"}
            for n in "dcba"
        ]
        for idx in order[:4]:
            _write_raw(tmp_path, f"section-{idx}.json", raw[idx % 4:] + raw[: idx % 4])
        return root, tmp_path

    def _run(self, root: Path, project: Path, seed: str, fmt: str) -> bytes:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "lint_candidates.py"),
             "--plugin-root", str(root), "--project-root", str(project),
             "--format", fmt],
            capture_output=True, env=env, check=True, cwd=str(project),
        )
        return proc.stdout

    def test_output_is_byte_identical_across_hash_seeds_and_input_order(self, tmp_path):
        count = 3 + 5 + 3 + 3 + 3
        forward = list(range(count))
        shuffled = forward[::-1]
        outputs = {}
        for label, seed, order in (("a", "1", forward), ("b", "4242", shuffled)):
            project = tmp_path / label
            project.mkdir()
            root, project = self._fixture(project, order)
            outputs[label] = {
                fmt: self._run(root, project, seed, fmt) for fmt in ("json", "markdown")
            }
            outputs[label]["project"] = str(project)
        for fmt in ("json", "markdown"):
            assert outputs["a"][fmt] == outputs["b"][fmt], fmt
            text = outputs["a"][fmt].decode()
            assert outputs["a"]["project"] not in text
            assert str(tmp_path) not in text
            assert not re.search(r"\d{4}-\d{2}-\d{2}", text)

    def test_json_keys_are_sorted(self, tmp_path):
        root = _plugin(tmp_path, {"a-review": ["`require()` calls"]})
        out = self._run(root, tmp_path, "0", "json").decode()
        assert json.dumps(json.loads(out), sort_keys=True, indent=2, ensure_ascii=False) + "\n" == out


MODEL_SDK_MODULES = frozenset(
    {"anthropic", "openai", "claude_agent_sdk", "litellm", "langchain",
                "google", "cohere", "mistralai", "ollama", "transformers"}
)


class TestNoModelSdk:

    def _imports(self) -> set[str]:
        tree = ast.parse((SCRIPTS_DIR / "lint_candidates.py").read_text("utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
        return roots

    def test_imports_no_model_sdk(self):
        assert not self._imports() & MODEL_SDK_MODULES

    def test_every_import_is_stdlib_or_a_sibling_module(self):
        siblings = {"detect_bullets", "finding_signature"}
        unexpected = self._imports() - set(sys.stdlib_module_names) - siblings
        assert not unexpected
