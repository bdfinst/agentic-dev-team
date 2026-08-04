"""Tests for scripts/coverage_config.py (issue #1759)."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_config import (
    DISCOVERY_NOT_APPLICABLE,
    TestClassification,
    atomic_write_json,
    discovery_error,
    drift_check,
    format_active_exclusions,
    load_or_bootstrap,
    measurement_basis_notice,
    needs_accounting,
    weighted_merge,
)

TEST = TestClassification.TEST
AMBIGUOUS = TestClassification.AMBIGUOUS
NOT_TEST = TestClassification.NOT_TEST


def discovered(*pairs):
    """Build a discovered_projects list from (path, classification) pairs."""
    return [{"path": path, "classification": classification} for path, classification in pairs]

# ---------------------------------------------------------------------------
# Step 1.1: load_or_bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_when_config_absent(tmp_path):
    config_path = tmp_path / "coverage-config.json"
    discovered_projects = discovered(
        ("src/ProjectA.csproj", TEST), ("src/ProjectB.csproj", TEST)
    )

    config, notice = load_or_bootstrap(
        config_path, discovered_projects, "2026-08-04T12:00:00Z"
    )

    assert config == {
        "included": ["src/ProjectA.csproj", "src/ProjectB.csproj"],
        "excluded": [],
        "bootstrapped_at": "2026-08-04T12:00:00Z",
    }
    assert notice == (
        "coverage-config.json did not exist; created it from fresh discovery "
        "with 2 project(s) included and zero exclusions. Review and add "
        "exclusions (with a reason) if any project should not count toward "
        "coverage."
    )
    # Written to disk atomically, matching the returned config.
    on_disk = json.loads(config_path.read_text(encoding="utf-8"))
    assert on_disk == config


def test_bootstrap_excludes_not_test_entries_from_included(tmp_path):
    config_path = tmp_path / "coverage-config.json"
    discovered_projects = discovered(
        ("src/ProjectA.csproj", TEST),
        ("src/NotATestProject.csproj", NOT_TEST),
        ("src/ProjectB.csproj", AMBIGUOUS),
    )

    config, notice = load_or_bootstrap(
        config_path, discovered_projects, "2026-08-04T12:00:00Z"
    )

    assert config["included"] == ["src/ProjectA.csproj", "src/ProjectB.csproj"]
    assert "with 2 project(s) included" in notice


def test_bootstrap_notice_count_interpolates_correctly(tmp_path):
    config_path = tmp_path / "coverage-config.json"

    _, notice = load_or_bootstrap(
        config_path, discovered(("only-one", TEST)), "2026-08-04T12:00:00Z"
    )

    assert "with 1 project(s) included" in notice


def test_existing_config_read_verbatim_not_overwritten(tmp_path):
    config_path = tmp_path / "coverage-config.json"
    existing = {
        "included": ["src/ProjectA.csproj"],
        "excluded": [{"path": "src/ProjectB.csproj", "reason": "flaky"}],
    }
    config_path.write_text(json.dumps(existing), encoding="utf-8")
    mtime_before = config_path.stat().st_mtime_ns

    config, notice = load_or_bootstrap(
        config_path,
        discovered(("src/ProjectA.csproj", TEST), ("src/ProjectB.csproj", TEST)),
        "2026-08-04T12:00:00Z",
    )

    assert config == existing
    assert notice is None
    assert config_path.stat().st_mtime_ns == mtime_before


def test_existing_config_with_bootstrapped_at_read_verbatim(tmp_path):
    config_path = tmp_path / "coverage-config.json"
    existing = {
        "included": ["src/ProjectA.csproj"],
        "excluded": [],
        "bootstrapped_at": "2026-01-01T00:00:00Z",
    }
    config_path.write_text(json.dumps(existing), encoding="utf-8")

    config, notice = load_or_bootstrap(
        config_path, discovered(("src/ProjectA.csproj", TEST)), "2026-08-04T12:00:00Z"
    )

    assert config == existing
    assert notice is None


def test_malformed_json_treated_as_absent_bootstraps_fresh(tmp_path):
    config_path = tmp_path / "coverage-config.json"
    config_path.write_text("{not valid json", encoding="utf-8")
    discovered_projects = discovered(("src/ProjectA.csproj", TEST))

    config, notice = load_or_bootstrap(
        config_path, discovered_projects, "2026-08-04T12:00:00Z"
    )

    assert config["included"] == ["src/ProjectA.csproj"]
    assert config["excluded"] == []
    assert config["bootstrapped_at"] == "2026-08-04T12:00:00Z"
    assert notice is not None
    on_disk = json.loads(config_path.read_text(encoding="utf-8"))
    assert on_disk == config


def test_identity_is_exact_string_no_normalization(tmp_path):
    config_path = tmp_path / "coverage-config.json"
    posix_style = "services/api/Api.Tests.csproj"
    opaque_label = "api-tests"
    discovered_projects = discovered((posix_style, TEST), (opaque_label, TEST))

    config, _ = load_or_bootstrap(config_path, discovered_projects, "2026-08-04T12:00:00Z")

    # Both identities are preserved byte-for-byte, in the form discovery
    # produced them — no path normalization, case-folding, or separator
    # translation.
    assert config["included"] == [posix_style, opaque_label]


def test_bootstrap_then_drift_check_round_trip_zero_unaccounted(tmp_path):
    """The exact shape drift_check expects flows straight out of
    load_or_bootstrap's own bootstrap — no shape translation needed, and a
    NOT_TEST entry correctly stays out of `included` while still not
    tripping `unaccounted` (it never needed accounting in the first
    place)."""
    config_path = tmp_path / "coverage-config.json"
    discovered_projects = discovered(
        ("src/ProjectA.csproj", TEST),
        ("src/ProjectB.csproj", AMBIGUOUS),
        ("src/NotATestProject.csproj", NOT_TEST),
    )

    config, _ = load_or_bootstrap(
        config_path, discovered_projects, "2026-08-04T12:00:00Z"
    )
    result = drift_check(config, discovered_projects)

    assert result["unaccounted"] == []
    assert result["conflicts"] == []
    assert result["hard_failure"] is False


# ---------------------------------------------------------------------------
# Step 1.1: needs_accounting
# ---------------------------------------------------------------------------


def test_needs_accounting_true_for_test_and_ambiguous():
    assert needs_accounting(TestClassification.TEST) is True
    assert needs_accounting(TestClassification.AMBIGUOUS) is True


def test_needs_accounting_false_for_not_test():
    assert needs_accounting(TestClassification.NOT_TEST) is False


# ---------------------------------------------------------------------------
# Step 1.2: drift_check
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "included": ["A"],
    "excluded": [{"path": "B", "reason": "all pending stubs"}],
}


def test_unaccounted_definite_test_project_is_hard_failure():
    result = drift_check(BASE_CONFIG, discovered(("A", TEST), ("B", TEST), ("C", TEST)))

    assert result["unaccounted"] == ["C"]
    assert result["unaccounted_ambiguous"] == []
    assert result["conflicts"] == []
    assert result["hard_failure"] is True
    assert result["hard_failure_message"] == (
        "Coverage capture stopped: 1 discovered project(s) are not "
        "accounted for in coverage-config.json: C. Add each to "
        "\"included\", or to \"excluded\" with a \"reason\", then re-run."
    )


def test_unaccounted_ambiguous_project_gets_distinct_explanation():
    result = drift_check(BASE_CONFIG, discovered(("A", TEST), ("B", TEST), ("D", AMBIGUOUS)))

    assert result["unaccounted"] == ["D"]
    assert result["unaccounted_ambiguous"] == ["D"]
    assert result["hard_failure"] is True
    assert result["hard_failure_message"] == (
        "Coverage capture stopped: 1 discovered project(s) are not "
        "accounted for in coverage-config.json: D. Add each to "
        "\"included\", or to \"excluded\" with a \"reason\", then re-run. "
        "1 of these could not be classified with certainty from their "
        "test markers: D."
    )


def test_conflicting_project_is_hard_failure():
    config = {
        "included": ["A"],
        "excluded": [{"path": "A", "reason": "listed twice by mistake"}],
    }

    result = drift_check(config, discovered(("A", TEST)))

    assert result["unaccounted"] == []
    assert result["conflicts"] == ["A"]
    assert result["hard_failure"] is True
    assert (
        "1 project(s) are listed in both \"included\" and \"excluded\": A. "
        "Remove each from one list, then re-run." in result["hard_failure_message"]
    )


def test_stale_exclusion_is_non_blocking_warning():
    result = drift_check(BASE_CONFIG, discovered(("A", TEST)))

    assert result["stale_exclusions"] == [{"path": "B", "reason": "all pending stubs"}]
    assert result["hard_failure"] is False
    assert result["hard_failure_message"] is None
    assert result["stale_warning_message"] == (
        "Warning: excluded entry 'B' (reason: 'all pending stubs') no "
        "longer matches any discovered project — it may have been "
        "removed, renamed, or the config is out of date. This does not "
        "block the run."
    )


def test_all_drift_conditions_together_carry_all_three_sentences_in_order():
    config = {
        "included": ["A"],
        "excluded": [
            {"path": "A", "reason": "listed twice by mistake"},
            {"path": "B", "reason": "all pending stubs"},
        ],
    }

    result = drift_check(config, discovered(("A", TEST), ("C", TEST), ("D", AMBIGUOUS)))

    assert result["unaccounted"] == ["C", "D"]
    assert result["unaccounted_ambiguous"] == ["D"]
    assert result["conflicts"] == ["A"]
    assert result["stale_exclusions"] == [{"path": "B", "reason": "all pending stubs"}]
    assert result["hard_failure"] is True

    message = result["hard_failure_message"]
    base_idx = message.index("not accounted for in coverage-config.json")
    ambiguous_idx = message.index("could not be classified with certainty")
    conflict_idx = message.index("listed in both")
    assert base_idx < ambiguous_idx < conflict_idx


def test_bare_string_excluded_entry_is_normalized():
    """A bare string in `excluded` (instead of `{"path": ..., "reason":
    ...}`) is normalized rather than raising TypeError on `entry["path"]`."""
    config = {"included": ["A"], "excluded": ["B"]}

    result = drift_check(config, discovered(("A", TEST)))

    assert result["stale_exclusions"] == [{"path": "B", "reason": ""}]
    assert result["hard_failure"] is False


def test_excluded_entry_missing_reason_uses_placeholder():
    """An excluded entry missing "reason" renders a placeholder in the
    stale-warning message rather than raising KeyError."""
    config = {"included": ["A"], "excluded": [{"path": "B"}]}

    result = drift_check(config, discovered(("A", TEST)))

    assert result["stale_warning_message"] == (
        "Warning: excluded entry 'B' (reason: '<no reason recorded>') no "
        "longer matches any discovered project — it may have been "
        "removed, renamed, or the config is out of date. This does not "
        "block the run."
    )


def test_non_list_included_raises_clear_value_error():
    config = {"included": "not-a-list", "excluded": []}

    with pytest.raises(ValueError, match="included"):
        drift_check(config, discovered(("A", TEST)))


def test_non_list_excluded_raises_clear_value_error():
    config = {"included": [], "excluded": "not-a-list"}

    with pytest.raises(ValueError, match="excluded"):
        drift_check(config, discovered(("A", TEST)))


def test_discovery_error_returns_shared_error_signal_shape():
    assert discovery_error("x") == {"signal": "error", "message": "x"}


def test_discovery_not_applicable_signal_shape():
    assert DISCOVERY_NOT_APPLICABLE == {"signal": "not_applicable"}


def test_two_stale_exclusions_both_appear_in_excluded_order():
    config = {
        "included": [],
        "excluded": [
            {"path": "B", "reason": "flaky"},
            {"path": "C", "reason": "pending"},
        ],
    }

    result = drift_check(config, discovered(("A", TEST)))

    assert result["stale_exclusions"] == [
        {"path": "B", "reason": "flaky"},
        {"path": "C", "reason": "pending"},
    ]
    message = result["stale_warning_message"]
    assert "'B'" in message and "'C'" in message
    lines = message.split("\n")
    assert len(lines) == 2
    assert "'B'" in lines[0]
    assert "'C'" in lines[1]


def test_conflict_fires_even_when_path_absent_from_discovered_projects():
    """drift_check's conflict check inspects only `config`, never
    `discovered_projects` — a conflicting path stays a hard failure even if
    current discovery has nothing to say about it."""
    config = {
        "included": ["A"],
        "excluded": [{"path": "A", "reason": "listed twice by mistake"}],
    }

    result = drift_check(config, discovered(("Z", TEST)))

    assert result["conflicts"] == ["A"]
    assert result["hard_failure"] is True


# ---------------------------------------------------------------------------
# Step 1.3: weighted_merge
# ---------------------------------------------------------------------------


def test_weighted_merge_combines_differently_sized_projects_correctly():
    project_a = {
        "covered_statements": 10,
        "total_statements": 10,
        "covered_branches": 0,
        "total_branches": 0,
    }
    project_b = {
        "covered_statements": 500,
        "total_statements": 1000,
        "covered_branches": 0,
        "total_branches": 0,
    }

    result = weighted_merge([project_a, project_b])

    assert result["line_pct"] == pytest.approx(50.5, abs=0.01)


def test_weighted_merge_single_project_returns_its_own_percentage():
    project = {
        "covered_statements": 75,
        "total_statements": 100,
        "covered_branches": 30,
        "total_branches": 40,
    }

    result = weighted_merge([project])

    assert result["line_pct"] == pytest.approx(75.0)
    assert result["branch_pct"] == pytest.approx(75.0)


def test_weighted_merge_zero_total_statements_returns_none():
    project = {
        "covered_statements": 0,
        "total_statements": 0,
        "covered_branches": 0,
        "total_branches": 0,
    }

    result = weighted_merge([project])

    assert result["line_pct"] is None
    assert result["branch_pct"] is None


def test_weighted_merge_none_branch_totals_degrade_to_zero_total():
    """A per-project report with `None`-valued branch totals (this repo's
    own Go-coverage convention for a tool with no native branch coverage)
    coerces to 0 rather than raising TypeError, degrading to the existing
    zero-total -> None result."""
    project = {
        "covered_statements": 10,
        "total_statements": 10,
        "covered_branches": None,
        "total_branches": None,
    }

    result = weighted_merge([project])

    assert result["line_pct"] == pytest.approx(100.0)
    assert result["branch_pct"] is None


# ---------------------------------------------------------------------------
# Step 1.4: measurement_basis_notice
# ---------------------------------------------------------------------------


def test_measurement_basis_notice_none_when_never_bootstrapped():
    assert measurement_basis_notice(None, "2026-08-04T12:00:00Z") is None


def test_measurement_basis_notice_present_when_baseline_predates_bootstrap():
    notice = measurement_basis_notice("2026-08-04T12:00:00Z", "2026-08-01T00:00:00Z")

    assert notice == (
        "Note: this baseline predates multi-project discovery (bootstrapped "
        "2026-08-04T12:00:00Z). This delta may reflect a widened "
        "measurement scope, not only a real coverage change. Consider "
        "re-running /coverage-baseline for a directly comparable baseline."
    )


def test_measurement_basis_notice_none_when_baseline_is_after_bootstrap():
    notice = measurement_basis_notice("2026-08-01T00:00:00Z", "2026-08-04T12:00:00Z")

    assert notice is None


def test_measurement_basis_notice_none_when_captured_at_equals_bootstrapped_at():
    notice = measurement_basis_notice("2026-08-04T12:00:00Z", "2026-08-04T12:00:00Z")

    assert notice is None


def test_measurement_basis_notice_none_for_same_instant_different_iso_suffix():
    """A `Z` suffix and an explicit `+00:00` offset for the same instant must
    not be misordered by a raw string comparison."""
    notice = measurement_basis_notice(
        "2026-08-04T12:00:00Z", "2026-08-04T12:00:00+00:00"
    )

    assert notice is None


# ---------------------------------------------------------------------------
# format_active_exclusions — always-shown, informational exclusion listing
# (issue #1759, Slice 5 fix — distinct from drift_check's stale_warning)
# ---------------------------------------------------------------------------


def test_format_active_exclusions_empty_excluded_returns_none():
    assert format_active_exclusions({"included": ["A"], "excluded": []}) is None


def test_format_active_exclusions_one_entry_exact_template():
    config = {
        "included": ["A"],
        "excluded": [{"path": "tests/ProjectStubs/ProjectStubs.csproj", "reason": "all pending stubs"}],
    }

    assert format_active_exclusions(config) == (
        "Excluded: 'tests/ProjectStubs/ProjectStubs.csproj' (reason: "
        "'all pending stubs')"
    )


def test_format_active_exclusions_multiple_entries_newline_joined():
    config = {
        "included": ["A"],
        "excluded": [
            {"path": "B", "reason": "flaky"},
            {"path": "C", "reason": "all pending stubs"},
        ],
    }

    assert format_active_exclusions(config) == (
        "Excluded: 'B' (reason: 'flaky')\n"
        "Excluded: 'C' (reason: 'all pending stubs')"
    )


# ---------------------------------------------------------------------------
# atomic_write_json — no leaked temp file on a failed write
# ---------------------------------------------------------------------------


def test_atomic_write_json_removes_temp_file_on_serialization_failure(tmp_path):
    path = tmp_path / "coverage-config.json"

    with pytest.raises(TypeError):
        # A raw TestClassification enum value is not JSON-serializable —
        # this is exactly the shape fix #1 above prevents reaching this
        # function via `included`, but the function itself must still be
        # robust to it.
        atomic_write_json(path, {"included": [TestClassification.TEST]})

    assert not path.exists()
    leftover_tmp_files = list(tmp_path.glob(f".{path.name}-*.tmp"))
    assert leftover_tmp_files == []
