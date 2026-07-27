"""Unit tests for scripts/gherkin_analysis_coverage_gate.py (issue #1450).

Covers the Analysis Coverage detector: section extraction, per-category
bullet parsing, the missing/empty-category distinction, and the main()
CLI's exit-code contract (0 = all present, 1 = some missing, 2 = gate did
not run).
"""

from __future__ import annotations

import json
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_analysis_coverage_gate as gate

ALL_EIGHT_PRESENT = """# Surface inventory

## Analysis Coverage

- **Controllers**: OrdersController — 3 routes analyzed
- **Handlers**: none found in this codebase
- **Services**: OrderService enforces 2 business rules
- **Domain logic**: Order aggregate validates totals
- **Workflows**: none found in this codebase
- **Validation rules**: total must be positive
- **Error handling**: OrderNotFoundException mapped to 404
- **Business processes**: order fulfillment pipeline

## Surfaces
"""

MISSING_DOMAIN_LOGIC = """## Analysis Coverage

- **Controllers**: OrdersController
- **Handlers**: none found in this codebase
- **Services**: OrderService
- **Workflows**: none found in this codebase
- **Validation rules**: total must be positive
- **Error handling**: mapped to 404
- **Business processes**: order fulfillment pipeline
"""

EMPTY_DOMAIN_LOGIC = MISSING_DOMAIN_LOGIC.replace(
    "- **Services**: OrderService\n",
    "- **Services**: OrderService\n- **Domain logic**: \n",
)

PLACEHOLDER_DOMAIN_LOGIC = MISSING_DOMAIN_LOGIC.replace(
    "- **Services**: OrderService\n",
    "- **Services**: OrderService\n- **Domain logic**: <findings>\n",
)

NO_SECTION = """# Surface inventory

## Surfaces

Some other content, no Analysis Coverage heading at all.
"""


def test_all_eight_categories_present_yields_no_missing():
    section = gate.find_analysis_coverage_section(ALL_EIGHT_PRESENT)
    entries = gate.parse_category_bullets(section)
    assert gate.find_missing_categories(entries) == []


def test_absent_category_is_reported_missing():
    section = gate.find_analysis_coverage_section(MISSING_DOMAIN_LOGIC)
    entries = gate.parse_category_bullets(section)
    assert gate.find_missing_categories(entries) == ["domain logic"]


def test_empty_category_content_is_treated_as_missing_not_ok():
    section = gate.find_analysis_coverage_section(EMPTY_DOMAIN_LOGIC)
    entries = gate.parse_category_bullets(section)
    assert gate.find_missing_categories(entries) == ["domain logic"]


def test_placeholder_angle_bracket_content_is_treated_as_missing():
    section = gate.find_analysis_coverage_section(PLACEHOLDER_DOMAIN_LOGIC)
    entries = gate.parse_category_bullets(section)
    assert gate.find_missing_categories(entries) == ["domain logic"]


def test_section_extraction_stops_at_next_heading():
    section = gate.find_analysis_coverage_section(ALL_EIGHT_PRESENT)
    assert "## Surfaces" not in section
    assert "Controllers" in section


def test_no_analysis_coverage_heading_returns_none():
    assert gate.find_analysis_coverage_section(NO_SECTION) is None


def test_main_exits_0_when_all_eight_categories_present_and_non_empty(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(ALL_EIGHT_PRESENT)
    exit_code = gate.main(["--file", str(f)])
    assert exit_code == 0
    expected_count = len(gate._REQUIRED_CATEGORIES)
    assert (
        f"OK: all {expected_count} analysis categories recorded."
        in capsys.readouterr().out
    )


def test_main_exits_1_and_lists_missing_categories(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(MISSING_DOMAIN_LOGIC)
    exit_code = gate.main(["--file", str(f)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "domain logic" in out


def test_main_json_output_lists_each_missing_category(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(MISSING_DOMAIN_LOGIC)
    exit_code = gate.main(["--file", str(f), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["missing"] == ["domain logic"]


def test_main_exits_2_when_no_analysis_coverage_section_found(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(NO_SECTION)
    exit_code = gate.main(["--file", str(f)])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


def test_main_exits_2_when_file_does_not_exist(tmp_path, capsys):
    missing_file = tmp_path / "does-not-exist.md"
    exit_code = gate.main(["--file", str(missing_file)])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


def test_main_json_warns_when_no_section_found(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(NO_SECTION)
    exit_code = gate.main(["--file", str(f), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert "warning" in payload
