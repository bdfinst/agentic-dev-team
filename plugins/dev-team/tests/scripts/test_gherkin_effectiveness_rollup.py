"""Tests for gherkin_effectiveness_rollup.py (issue #1296)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import gherkin_effectiveness_rollup as rollup

GHERKIN_MD = """# Surface inventory

| Surface | Discovery source | Provenance | Mode | Files |
| --- | --- | --- | --- | --- |
| POST /orders | openapi | specification | bdd-runner | features/orders-post.feature |
| GET /orders/{id} | route | specification | bdd-runner | features/orders-get.feature |
| legacy CSV export | test | characterization | xunit-with-annotations | features/csv-export.feature |
"""

GHERKIN_MD_NO_TABLE = "# Surface inventory\n\nNo surfaces discovered.\n"


def test_parse_surface_table_extracts_rows():
    rows = rollup.parse_surface_table(GHERKIN_MD)
    assert len(rows) == 3
    assert rows[0] == {
        "surface": "POST /orders",
        "discovery_source": "openapi",
        "provenance": "specification",
        "binding_mode": "bdd-runner",
        "files": "features/orders-post.feature",
    }
    assert rows[2]["provenance"] == "characterization"


def test_parse_surface_table_returns_empty_when_no_table():
    assert rollup.parse_surface_table(GHERKIN_MD_NO_TABLE) == []


def test_load_scenarios_missing_file_raises_warning(tmp_path):
    with pytest.raises(rollup.RollupWarning):
        rollup.load_scenarios(tmp_path / "missing.md")


def test_load_scenarios_none_returns_empty():
    assert rollup.load_scenarios(None) == []


def test_coverage_delta_computes_pct_change():
    baseline = {"line_pct": 41.2, "branch_pct": 28.7}
    current = {"line_pct": 55.0, "branch_pct": 40.0}
    delta = rollup.coverage_delta(baseline, current)
    assert delta == {"line_pct": 13.8, "branch_pct": 11.3}


def test_coverage_delta_none_when_either_missing():
    assert rollup.coverage_delta(None, {"line_pct": 1}) is None
    assert rollup.coverage_delta({"line_pct": 1}, None) is None


def test_mutation_delta_computes_survivor_change():
    baseline = {"survivors_after": 12}
    current = {"survivors_after": 4}
    assert rollup.mutation_delta(baseline, current) == {"survivors_after_delta": -8}


def test_build_records_attaches_bindings_and_deltas():
    scenarios = [{"surface": "POST /orders", "provenance": "specification", "binding_mode": "bdd-runner"}]
    bindings = {"POST /orders": 311}
    records = rollup.build_records(scenarios, bindings, {"line_pct": 5.0}, {"survivors_after_delta": -2})
    assert records == [
        {
            "surface": "POST /orders",
            "discovery_source": None,
            "provenance": "specification",
            "binding_mode": "bdd-runner",
            "bound_story": 311,
            "coverage_delta": {"line_pct": 5.0},
            "mutation_delta": {"survivors_after_delta": -2},
        }
    ]


def test_append_jsonl_is_append_only(tmp_path):
    out = tmp_path / "gherkin-derive-effectiveness.jsonl"
    rollup.append_jsonl([{"a": 1}], out)
    rollup.append_jsonl([{"a": 2}], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"a": 1}, {"a": 2}]


def test_main_end_to_end(tmp_path, capsys):
    gherkin_md = tmp_path / "gherkin.md"
    gherkin_md.write_text(GHERKIN_MD, encoding="utf-8")

    bindings_json = tmp_path / "gherkin-bindings.json"
    bindings_json.write_text(json.dumps({"POST /orders": 311}), encoding="utf-8")

    baseline_cov = tmp_path / "baseline-coverage.json"
    baseline_cov.write_text(json.dumps({"line_pct": 40.0, "branch_pct": 30.0}), encoding="utf-8")
    current_cov = tmp_path / "current-coverage.json"
    current_cov.write_text(json.dumps({"line_pct": 50.0, "branch_pct": 35.0}), encoding="utf-8")

    out = tmp_path / "out.jsonl"

    exit_code = rollup.main(
        [
            "--gherkin-md", str(gherkin_md),
            "--bindings-json", str(bindings_json),
            "--baseline-coverage", str(baseline_cov),
            "--current-coverage", str(current_cov),
            "--out", str(out),
        ]
    )

    assert exit_code == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    orders_record = next(r for r in records if r["surface"] == "POST /orders")
    assert orders_record["bound_story"] == 311
    assert orders_record["coverage_delta"] == {"line_pct": 10.0, "branch_pct": 5.0}

    captured = capsys.readouterr()
    assert "wrote 3 record(s)" in captured.out


def test_main_no_gherkin_md_writes_nothing(tmp_path, capsys):
    out = tmp_path / "out.jsonl"
    exit_code = rollup.main(["--out", str(out)])
    assert exit_code == 0
    assert not out.exists()
    captured = capsys.readouterr()
    assert "no scenarios to roll up" in captured.err


def test_main_missing_gherkin_md_warns_and_continues(tmp_path, capsys):
    out = tmp_path / "out.jsonl"
    exit_code = rollup.main(["--gherkin-md", str(tmp_path / "missing.md"), "--out", str(out)])
    assert exit_code == 0
    assert not out.exists()
    captured = capsys.readouterr()
    assert "surface inventory not found" in captured.err
