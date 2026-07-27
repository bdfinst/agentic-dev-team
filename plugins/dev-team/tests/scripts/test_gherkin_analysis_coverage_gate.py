"""Unit tests for scripts/gherkin_analysis_coverage_gate.py (issue #1450,
generalized for issue #1464).

Covers the Analysis Coverage detector: section extraction, per-category
bullet parsing, the missing/empty-category distinction, and the main()
CLI's exit-code contract (0 = all present, 1 = some missing, 2 = gate did
not run) — for both gherkin-derive's default `## Analysis Coverage` (H2)
configuration and cd-test-architecture's `### Components & patterns` (H3)
configuration (issue #1464's generalization).
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


def test_main_exits_2_when_analysis_coverage_section_is_empty(tmp_path, capsys):
    # The empty-section "did not run" distinction (issue #1464) is shared
    # logic, not cd-test-architecture-specific — confirm it holds for
    # gherkin-derive's own default configuration too.
    f = tmp_path / "gherkin.md"
    f.write_text("# Surface inventory\n\n## Analysis Coverage\n\n## Surfaces\n")
    exit_code = gate.main(["--file", str(f)])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


# --- cd-test-architecture configuration (issue #1464) -----------------
#
# `### Components & patterns` is an H3 heading — a *different* level than
# gherkin-derive's own H2 `## Analysis Coverage`. The fixtures below
# specifically probe the heading-level parameter, not just the section
# name: `CD_TEST_ARCH_WRONG_HEADING_LEVEL` uses the right section name at
# the *wrong* level (H2) to catch a regression where the level parameter is
# accepted on the CLI but silently ignored internally (a hardcoded `##`
# would wrongly match that fixture and this config would never hit its
# genuine exit-2 "did not run" path).

CD_TEST_ARCH_ALL_EIGHT_PRESENT = """# CD Test Architecture

### Components & patterns

- **UI**: web checkout flow — 4 pages analyzed
- **API Provider**: OrdersController — 3 routes
- **API Consumer**: PaymentClient calls the Stripe API
- **Event Consumer**: none found in this codebase
- **Event Producer**: OrderPlaced event published to the bus
- **Stateful Service**: OrderService holds an in-memory cache
- **CLI-Library**: none found in this codebase
- **Scheduled Job**: nightly reconciliation batch job

### Current tests (in-repo)
"""

CD_TEST_ARCH_MISSING_ONE = """### Components & patterns

- **UI**: web checkout flow
- **API Provider**: OrdersController
- **API Consumer**: PaymentClient calls the Stripe API
- **Event Producer**: OrderPlaced event published to the bus
- **Stateful Service**: OrderService holds an in-memory cache
- **CLI-Library**: none found in this codebase
- **Scheduled Job**: nightly reconciliation batch job
"""
# Missing: Event Consumer

CD_TEST_ARCH_MISSING_THREE = """### Components & patterns

- **UI**: web checkout flow
- **API Provider**: OrdersController
- **API Consumer**: PaymentClient calls the Stripe API
- **Event Consumer**: none found in this codebase
- **Event Producer**: OrderPlaced event published to the bus
"""
# Missing exactly 3: Stateful Service, CLI-Library, Scheduled Job

CD_TEST_ARCH_EMPTY_SECTION = """# CD Test Architecture

### Components & patterns

### Current tests (in-repo)

No category rows at all beneath the heading — distinct from "some missing".
"""

CD_TEST_ARCH_WRONG_HEADING_LEVEL = """## Components & patterns

- **UI**: web checkout flow
- **API Provider**: OrdersController
- **API Consumer**: PaymentClient calls the Stripe API
- **Event Consumer**: none found in this codebase
- **Event Producer**: OrderPlaced event published to the bus
- **Stateful Service**: OrderService holds an in-memory cache
- **CLI-Library**: none found in this codebase
- **Scheduled Job**: nightly reconciliation batch job
"""

CD_TEST_ARCH_NO_SECTION = """# CD Test Architecture

### Current tests (in-repo)

No Components & patterns heading at all.
"""


def test_cd_test_architecture_config_all_eight_present_yields_no_missing():
    section = gate.find_analysis_coverage_section(
        CD_TEST_ARCH_ALL_EIGHT_PRESENT, gate.CD_TEST_ARCHITECTURE_CONFIG
    )
    assert section is not None
    entries = gate.parse_category_bullets(section)
    assert (
        gate.find_missing_categories(entries, gate.CD_TEST_ARCHITECTURE_CONFIG) == []
    )


def test_cd_test_architecture_config_single_omitted_category_is_named():
    # Plan scenario: "Gate fails when a category is silently omitted".
    section = gate.find_analysis_coverage_section(
        CD_TEST_ARCH_MISSING_ONE, gate.CD_TEST_ARCHITECTURE_CONFIG
    )
    entries = gate.parse_category_bullets(section)
    missing = gate.find_missing_categories(entries, gate.CD_TEST_ARCHITECTURE_CONFIG)
    assert missing == ["event consumer"]


def test_cd_test_architecture_config_three_omitted_categories_all_named():
    # Plan scenario: "Gate fails and names all missing categories when
    # several are omitted" (3 of the 8 required categories' rows missing).
    section = gate.find_analysis_coverage_section(
        CD_TEST_ARCH_MISSING_THREE, gate.CD_TEST_ARCHITECTURE_CONFIG
    )
    entries = gate.parse_category_bullets(section)
    missing = gate.find_missing_categories(entries, gate.CD_TEST_ARCHITECTURE_CONFIG)
    assert missing == ["stateful service", "cli-library", "scheduled job"]


def test_cd_test_architecture_h3_heading_found_at_correct_level(tmp_path, capsys):
    f = tmp_path / "report.md"
    f.write_text(CD_TEST_ARCH_ALL_EIGHT_PRESENT)
    exit_code = gate.main(["--file", str(f), "--config", "cd-test-architecture"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK: all 8 component-pattern categories recorded." in out


def test_cd_test_architecture_h2_heading_does_not_satisfy_h3_config(tmp_path, capsys):
    """Dedicated H3-level fixture (issue #1464): the same section name at
    the wrong heading level (H2) must NOT be found by the cd-test-architecture
    (H3) configuration — the heading-level parameter is a real match
    constraint, not a cosmetic no-op."""
    f = tmp_path / "report.md"
    f.write_text(CD_TEST_ARCH_WRONG_HEADING_LEVEL)
    exit_code = gate.main(["--file", str(f), "--config", "cd-test-architecture"])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


def test_cd_test_architecture_config_main_exits_1_and_lists_missing(tmp_path, capsys):
    f = tmp_path / "report.md"
    f.write_text(CD_TEST_ARCH_MISSING_THREE)
    exit_code = gate.main(["--file", str(f), "--config", "cd-test-architecture"])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "stateful service" in out
    assert "cli-library" in out
    assert "scheduled job" in out


def test_cd_test_architecture_config_main_exits_2_when_no_section_found(
    tmp_path, capsys
):
    f = tmp_path / "report.md"
    f.write_text(CD_TEST_ARCH_NO_SECTION)
    exit_code = gate.main(["--file", str(f), "--config", "cd-test-architecture"])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


def test_cd_test_architecture_config_main_exits_2_when_section_is_empty(
    tmp_path, capsys
):
    # Plan scenario: "did not run" distinct from "nothing missing" — the
    # section header exists but has zero category rows beneath it. This
    # must NOT be reported as "8 missing" (exit 1) — a section with no
    # rows at all was never actually filled in, distinct from a partial
    # gap, so it gets the same exit-2 "did not run" treatment as an absent
    # heading or a missing file.
    f = tmp_path / "report.md"
    f.write_text(CD_TEST_ARCH_EMPTY_SECTION)
    exit_code = gate.main(["--file", str(f), "--config", "cd-test-architecture"])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


def test_cd_test_architecture_config_main_exits_2_when_file_missing(tmp_path, capsys):
    missing_file = tmp_path / "does-not-exist.md"
    exit_code = gate.main(
        ["--file", str(missing_file), "--config", "cd-test-architecture"]
    )
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "gate did not run" in out


def test_default_config_is_gherkin_derive_when_config_flag_omitted(tmp_path, capsys):
    f = tmp_path / "gherkin.md"
    f.write_text(ALL_EIGHT_PRESENT)
    exit_code = gate.main(["--file", str(f)])
    assert exit_code == 0
