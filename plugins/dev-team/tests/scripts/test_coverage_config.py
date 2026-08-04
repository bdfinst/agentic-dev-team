"""Tests for coverage_config.py — shared multi-project coverage config (#1780)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import coverage_config as cc

# `TestClassification` is deliberately never bound at this module's top level —
# pytest would try to collect any module-level name starting with `Test`.
_TEST = cc.TestClassification.TEST
_NOT_TEST = cc.TestClassification.NOT_TEST
_AMBIGUOUS = cc.TestClassification.AMBIGUOUS


def _discovered(*pairs: tuple[str, cc.TestClassification]) -> list[cc.DiscoveredProject]:
    return [cc.DiscoveredProject(path=path, classification=kind) for path, kind in pairs]


# ---------------------------------------------------------------------------
# Shared constants / enum / error helper
# ---------------------------------------------------------------------------


def test_discovery_not_applicable_is_a_falsey_identity_sentinel() -> None:
    # #1781/#1782 both assert `result is DISCOVERY_NOT_APPLICABLE`, so it must be a
    # single shared object, not a value another module could reconstruct by accident.
    assert cc.DISCOVERY_NOT_APPLICABLE is cc.DISCOVERY_NOT_APPLICABLE
    assert not cc.DISCOVERY_NOT_APPLICABLE
    assert cc.DISCOVERY_NOT_APPLICABLE != []
    assert repr(cc.DISCOVERY_NOT_APPLICABLE) == "DISCOVERY_NOT_APPLICABLE"


def test_test_classification_has_exactly_three_states() -> None:
    assert {member.name for member in cc.TestClassification} == {
        "TEST",
        "NOT_TEST",
        "AMBIGUOUS",
    }


@pytest.mark.parametrize(
    ("classification", "expected"),
    [(_TEST, True), (_AMBIGUOUS, True), (_NOT_TEST, False)],
)
def test_needs_accounting_covers_test_and_ambiguous_only(
    classification: cc.TestClassification, expected: bool
) -> None:
    # AMBIGUOUS must need accounting: "never silently negative" is the whole point.
    assert cc.needs_accounting(classification) is expected


def test_discovery_error_raises_a_catchable_discovery_error() -> None:
    with pytest.raises(cc.DiscoveryError, match="malformed thing"):
        cc.discovery_error("malformed thing")


# ---------------------------------------------------------------------------
# ISO-8601 helpers (pinned, shared format)
# ---------------------------------------------------------------------------


def test_utc_now_iso_round_trips_through_the_pinned_format() -> None:
    now = cc.utc_now_iso()
    assert now.endswith("Z")
    assert cc.format_iso8601(cc.parse_iso8601(now)) == now


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-04T12:00:00Z", datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)),
        (
            "2026-08-04T12:00:00+00:00",
            datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc),
        ),
        (
            "2026-08-04T12:00:00.123456Z",
            datetime(2026, 8, 4, 12, 0, 0, 123456, tzinfo=timezone.utc),
        ),
        # The `Z` shim must not drop the real offset it replaces.
        ("2026-08-04T14:00:00+02:00", datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)),
        # A naive timestamp is read as UTC, not as local time.
        ("2026-08-04T12:00:00", datetime(2026, 8, 4, 12, 0, 0, tzinfo=timezone.utc)),
    ],
)
def test_parse_iso8601_yields_the_exact_instant(value: str, expected: datetime) -> None:
    assert cc.parse_iso8601(value) == expected


def test_parse_iso8601_rejects_an_unparseable_value_by_name() -> None:
    with pytest.raises(cc.DiscoveryError, match="not-a-timestamp"):
        cc.parse_iso8601("not-a-timestamp")


# ---------------------------------------------------------------------------
# load_or_bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_writes_all_discovered_projects_included_zero_exclusions(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "coverage-config.json"
    discovered = _discovered(
        ("tests/B.Tests/B.Tests.csproj", _TEST),
        ("tests/A.Tests/A.Tests.csproj", _TEST),
        ("src/App/App.csproj", _NOT_TEST),
    )

    result = cc.load_or_bootstrap(config_path, discovered, "2026-08-04T12:00:00Z")

    assert result.bootstrapped is True
    on_disk = json.loads(config_path.read_text(encoding="utf-8"))
    assert on_disk == {
        "included": ["tests/A.Tests/A.Tests.csproj", "tests/B.Tests/B.Tests.csproj"],
        "excluded": [],
        "bootstrapped_at": "2026-08-04T12:00:00Z",
    }
    assert result.config == on_disk


def test_bootstrap_includes_ambiguous_projects(tmp_path: Path) -> None:
    config_path = tmp_path / "coverage-config.json"
    discovered = _discovered(("tests/Maybe/Maybe.csproj", _AMBIGUOUS))

    result = cc.load_or_bootstrap(config_path, discovered, "2026-08-04T12:00:00Z")

    assert result.config["included"] == ["tests/Maybe/Maybe.csproj"]


def test_bootstrap_returns_the_exact_operator_notice(tmp_path: Path) -> None:
    config_path = tmp_path / "coverage-config.json"

    result = cc.load_or_bootstrap(
        config_path,
        _discovered(("tests/A/A.csproj", _TEST)),
        "2026-08-04T12:00:00Z",
    )

    assert result.notice == cc.BOOTSTRAP_NOTICE_TEMPLATE.format(
        bootstrapped_at="2026-08-04T12:00:00Z",
        count=1,
        config_path=config_path,
    )


def test_existing_valid_config_is_never_overwritten(tmp_path: Path) -> None:
    config_path = tmp_path / "coverage-config.json"
    original = {
        "included": ["tests/A/A.csproj"],
        "excluded": [{"path": "tests/B/B.csproj", "reason": "flaky, being rewritten"}],
        "bootstrapped_at": "2026-01-01T00:00:00Z",
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")

    result = cc.load_or_bootstrap(
        config_path,
        _discovered(("tests/Z/Z.csproj", _TEST)),
        "2026-08-04T12:00:00Z",
    )

    assert result.bootstrapped is False
    assert result.notice is None
    assert result.config == original
    assert json.loads(config_path.read_text(encoding="utf-8")) == original


def test_malformed_json_config_is_treated_as_absent_and_rebootstrapped(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "coverage-config.json"
    config_path.write_text("{ this is not json", encoding="utf-8")

    result = cc.load_or_bootstrap(
        config_path,
        _discovered(("tests/A/A.csproj", _TEST)),
        "2026-08-04T12:00:00Z",
    )

    assert result.bootstrapped is True
    assert result.config["included"] == ["tests/A/A.csproj"]
    assert result.notice is not None
    assert result.notice != cc.BOOTSTRAP_NOTICE_TEMPLATE.format(
        bootstrapped_at="2026-08-04T12:00:00Z", count=1, config_path=config_path
    )
    assert "re-record" in result.notice


_BOOTSTRAPPED_AT = '"bootstrapped_at": "2026-01-01T00:00:00Z"'


@pytest.mark.parametrize(
    "payload",
    [
        '["not", "an", "object"]',
        '{"included": "not-a-list", ' + _BOOTSTRAPPED_AT + "}",
        '{"included": [], "excluded": {"not": "a list"}, ' + _BOOTSTRAPPED_AT + "}",
        '{"included": [], "excluded": [["not", "an", "object"]], ' + _BOOTSTRAPPED_AT + "}",
        '{"included": [], "excluded": [{"reason": "no path key"}], ' + _BOOTSTRAPPED_AT + "}",
        '{"included": [], "excluded": [{"path": 7, "reason": "nope"}], '
        + _BOOTSTRAPPED_AT
        + "}",
        '{"included": [], "excluded": [{"path": "p", "reason": true}], '
        + _BOOTSTRAPPED_AT
        + "}",
        '{"included": [1, 2], ' + _BOOTSTRAPPED_AT + "}",
        # No `bootstrapped_at` at all: `measurement_basis_notice` could never fire
        # against such a config, so it is not a usable one.
        '{"included": ["tests/A/A.csproj"], "excluded": []}',
        '{"included": [], "excluded": [], "bootstrapped_at": 20260101}',
        '{"included": [], "excluded": [], "bootstrapped_at": "   "}',
        # An empty object, and the legacy `discover_coverage_projects.py` (#1759)
        # schema written to a file of the identical name. Neither may read as an
        # empty-but-valid config — that would hard-fail every discovered project
        # as unaccounted-for while the operator's real reasons sat unread.
        "{}",
        '{"known_projects": ["tests/A/A.csproj"], "exclusions": []}',
    ],
)
def test_valid_json_but_wrong_shape_is_also_rebootstrapped(
    tmp_path: Path, payload: str
) -> None:
    config_path = tmp_path / "coverage-config.json"
    config_path.write_text(payload, encoding="utf-8")

    result = cc.load_or_bootstrap(
        config_path, _discovered(("tests/A/A.csproj", _TEST)), "2026-08-04T12:00:00Z"
    )

    assert result.bootstrapped is True
    assert result.config["included"] == ["tests/A/A.csproj"]
    # The notice must be the unreadable-config one, naming the shape problem —
    # not the plain absent-config notice.
    prefix, _, suffix = cc.BOOTSTRAP_AFTER_UNREADABLE_NOTICE_TEMPLATE.partition(
        "{reason}"
    )
    assert result.notice is not None
    assert prefix.format(config_path=config_path) in result.notice
    assert (
        suffix.format(bootstrapped_at="2026-08-04T12:00:00Z", count=1) in result.notice
    )


def test_bootstrap_with_no_discovered_projects_writes_an_empty_included_list(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "coverage-config.json"

    result = cc.load_or_bootstrap(config_path, [], "2026-08-04T12:00:00Z")

    assert result.config["included"] == []
    assert "0 discovered project(s)" in result.notice


def test_bootstrap_refuses_the_not_applicable_sentinel(tmp_path: Path) -> None:
    with pytest.raises(cc.DiscoveryError, match="DISCOVERY_NOT_APPLICABLE"):
        cc.load_or_bootstrap(
            tmp_path / "coverage-config.json",
            cc.DISCOVERY_NOT_APPLICABLE,  # type: ignore[arg-type]
            "2026-08-04T12:00:00Z",
        )


def test_bootstrap_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "coverage-config.json"

    cc.load_or_bootstrap(
        config_path, _discovered(("tests/A/A.csproj", _TEST)), "2026-08-04T12:00:00Z"
    )

    assert config_path.is_file()
    assert [p.name for p in config_path.parent.iterdir()] == [config_path.name]


def test_atomic_write_leaves_no_temp_file_when_the_payload_is_unserializable(
    tmp_path: Path,
) -> None:
    # `json.dumps` raises TypeError, which the `except OSError` cleanup cannot
    # catch — so serialization has to happen before the temp file exists.
    target = tmp_path / "coverage-config.json"

    with pytest.raises(TypeError):
        cc.atomic_write_json(target, {"included": {object()}})

    assert list(tmp_path.iterdir()) == []


def test_atomic_write_removes_the_temp_file_and_reraises_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "coverage-config.json"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(cc.os, "replace", _boom)

    with pytest.raises(OSError, match="disk full"):
        cc.atomic_write_json(target, {"included": []})

    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# drift_check
# ---------------------------------------------------------------------------


def _config(
    included: list[str] | None = None, excluded: list[dict] | None = None
) -> dict:
    return {
        "included": included or [],
        "excluded": excluded or [],
        "bootstrapped_at": "2026-01-01T00:00:00Z",
    }


def test_fully_accounted_discovery_is_clean() -> None:
    config = _config(
        included=["tests/A/A.csproj"],
        excluded=[{"path": "tests/B/B.csproj", "reason": "helper only"}],
    )
    discovered = _discovered(
        ("tests/A/A.csproj", _TEST),
        ("tests/B/B.csproj", _TEST),
        ("src/App/App.csproj", _NOT_TEST),
    )

    report = cc.drift_check(config, discovered)

    assert report.errors == []
    assert report.warnings == []
    assert report.ok is True


def test_unaccounted_test_project_hard_fails_with_the_exact_message() -> None:
    report = cc.drift_check(_config(), _discovered(("tests/New/New.csproj", _TEST)))

    assert report.ok is False
    assert report.errors == [
        cc.UNACCOUNTED_TEST_PROJECT_TEMPLATE.format(path="tests/New/New.csproj")
    ]


def test_unaccounted_ambiguous_project_hard_fails_with_a_distinct_message() -> None:
    report = cc.drift_check(_config(), _discovered(("tests/Hmm/Hmm.csproj", _AMBIGUOUS)))

    assert report.ok is False
    assert report.errors == [
        cc.UNACCOUNTED_AMBIGUOUS_PROJECT_TEMPLATE.format(path="tests/Hmm/Hmm.csproj")
    ]
    # The two hard-failure messages must not be interchangeable — an operator has to be
    # able to tell "we know this is a test project" from "we could not decide".
    assert cc.UNACCOUNTED_AMBIGUOUS_PROJECT_TEMPLATE != cc.UNACCOUNTED_TEST_PROJECT_TEMPLATE
    assert "ambiguous" in cc.UNACCOUNTED_AMBIGUOUS_PROJECT_TEMPLATE
    assert "ambiguous" not in cc.UNACCOUNTED_TEST_PROJECT_TEMPLATE


def test_not_test_projects_never_need_accounting() -> None:
    report = cc.drift_check(_config(), _discovered(("src/App/App.csproj", _NOT_TEST)))

    assert report.ok is True


def test_conflicting_entry_hard_fails() -> None:
    config = _config(
        included=["tests/A/A.csproj"],
        excluded=[{"path": "tests/A/A.csproj", "reason": "also excluded, somehow"}],
    )

    report = cc.drift_check(config, _discovered(("tests/A/A.csproj", _TEST)))

    assert report.ok is False
    assert report.errors == [
        cc.CONFLICTING_ENTRY_TEMPLATE.format(path="tests/A/A.csproj")
    ]


def test_conflicting_entry_is_reported_even_when_not_discovered() -> None:
    config = _config(
        included=["tests/Gone/Gone.csproj"],
        excluded=[{"path": "tests/Gone/Gone.csproj", "reason": "deleted"}],
    )

    report = cc.drift_check(config, [])

    assert cc.CONFLICTING_ENTRY_TEMPLATE.format(path="tests/Gone/Gone.csproj") in (
        report.errors
    )


def test_reasonless_exclusion_hard_fails() -> None:
    config = _config(excluded=[{"path": "tests/A/A.csproj", "reason": "   "}])

    report = cc.drift_check(config, _discovered(("tests/A/A.csproj", _TEST)))

    assert report.ok is False
    assert report.errors == [
        cc.EXCLUSION_MISSING_REASON_TEMPLATE.format(path="tests/A/A.csproj")
    ]


def test_stale_exclusion_warns_without_blocking() -> None:
    config = _config(
        included=["tests/A/A.csproj"],
        excluded=[{"path": "tests/Gone/Gone.csproj", "reason": "retired in Q1"}],
    )

    report = cc.drift_check(config, _discovered(("tests/A/A.csproj", _TEST)))

    assert report.ok is True
    assert report.errors == []
    assert report.warnings == [
        cc.STALE_EXCLUSION_TEMPLATE.format(
            path="tests/Gone/Gone.csproj", reason="retired in Q1"
        )
    ]


def test_path_identity_is_an_exact_unmodified_string_match() -> None:
    # No cross-stack normalization: a backslash path and a forward-slash path are
    # different identities, and the drift check must say so rather than quietly
    # matching them.
    config = _config(included=["tests/A/A.csproj"])

    report = cc.drift_check(config, _discovered((r"tests\A\A.csproj", _TEST)))

    assert report.ok is False
    assert report.errors == [
        cc.UNACCOUNTED_TEST_PROJECT_TEMPLATE.format(path=r"tests\A\A.csproj")
    ]


def test_a_reasonless_duplicate_entry_is_not_masked_by_a_reasoned_one() -> None:
    # Collapsing entries to a path->reason dict would make the outcome depend on
    # entry order; both orders must hard-fail.
    for excluded in (
        [
            {"path": "tests/A/A.csproj"},
            {"path": "tests/A/A.csproj", "reason": "real reason"},
        ],
        [
            {"path": "tests/A/A.csproj", "reason": "real reason"},
            {"path": "tests/A/A.csproj"},
        ],
    ):
        report = cc.drift_check(
            _config(excluded=excluded), _discovered(("tests/A/A.csproj", _TEST))
        )

        assert report.errors == [
            cc.EXCLUSION_MISSING_REASON_TEMPLATE.format(path="tests/A/A.csproj")
        ]


def test_unaccounted_message_matches_the_wording_the_issue_specified() -> None:
    # Independently transcribed, not re-formatted from the module constant, so a
    # wording regression in the template is detectable rather than self-consistent.
    report = cc.drift_check(_config(), _discovered(("tests/New/New.csproj", _TEST)))

    (message,) = report.errors
    assert message.startswith("unaccounted-for test project: tests/New/New.csproj.")
    assert "structural marker" in message
    assert "neither 'included' nor 'excluded'" in message
    assert '"reason"' in message
    assert "No baseline is written" in message


def test_errors_are_ordered_by_path_within_a_category() -> None:
    discovered = _discovered(
        ("tests/Z/Z.csproj", _TEST),
        ("tests/A/A.csproj", _TEST),
        ("tests/M/M.csproj", _AMBIGUOUS),
    )

    report = cc.drift_check(_config(), discovered)

    assert report.errors == [
        cc.UNACCOUNTED_TEST_PROJECT_TEMPLATE.format(path="tests/A/A.csproj"),
        cc.UNACCOUNTED_AMBIGUOUS_PROJECT_TEMPLATE.format(path="tests/M/M.csproj"),
        cc.UNACCOUNTED_TEST_PROJECT_TEMPLATE.format(path="tests/Z/Z.csproj"),
    ]
    assert report.errors == cc.drift_check(_config(), discovered).errors


# ---------------------------------------------------------------------------
# weighted_merge
# ---------------------------------------------------------------------------


def _report(
    path: str,
    line_pct: float | None,
    statements_total: int,
    branch_pct: float | None = None,
    branches_total: int = 0,
) -> dict:
    return {
        "path": path,
        "line_pct": line_pct,
        "statements_total": statements_total,
        "branch_pct": branch_pct,
        "branches_total": branches_total,
    }


def test_merge_is_weighted_by_statement_count_not_a_simple_average() -> None:
    merged = cc.weighted_merge(
        [_report("small", 100.0, 10), _report("large", 50.0, 1000)]
    )

    assert merged["line_pct"] == pytest.approx(50.5, abs=0.01)
    assert merged["line_pct"] != pytest.approx(75.0, abs=0.01)
    assert merged["statements_total"] == 1010


def test_merge_weights_branches_independently_of_statements() -> None:
    merged = cc.weighted_merge(
        [
            _report("small", 100.0, 10, branch_pct=100.0, branches_total=4),
            _report("large", 50.0, 1000, branch_pct=25.0, branches_total=400),
        ]
    )

    # (4*1.0 + 400*0.25) / 404 = 104/404 = 25.7425…
    assert merged["branch_pct"] == pytest.approx(25.74, abs=0.01)
    assert merged["branches_total"] == 404


def test_merge_records_the_projects_it_merged() -> None:
    merged = cc.weighted_merge([_report("b", 50.0, 2), _report("a", 50.0, 2)])

    assert merged["projects"] == ["a", "b"]


def test_merge_of_a_single_project_is_that_project() -> None:
    merged = cc.weighted_merge([_report("only", 41.2, 500, branch_pct=28.7, branches_total=100)])

    assert merged["line_pct"] == pytest.approx(41.2, abs=0.01)
    assert merged["branch_pct"] == pytest.approx(28.7, abs=0.01)


def test_merge_reports_null_branch_coverage_when_no_project_measures_branches() -> None:
    merged = cc.weighted_merge([_report("go-ish", 62.5, 800)])

    assert merged["branch_pct"] is None
    assert merged["branches_total"] == 0


def test_merge_skips_a_project_that_did_not_measure_a_dimension() -> None:
    merged = cc.weighted_merge(
        [
            _report("measured", 80.0, 100, branch_pct=60.0, branches_total=50),
            _report("branchless", 40.0, 100, branch_pct=None, branches_total=0),
        ]
    )

    assert merged["line_pct"] == pytest.approx(60.0, abs=0.01)
    assert merged["branch_pct"] == pytest.approx(60.0, abs=0.01)


def test_reported_totals_are_the_denominators_of_the_reported_percentages() -> None:
    # `branchless` declares 200 branches but measured none of them. Counting its
    # weight in `branches_total` while excluding it from `branch_pct` would make
    # `pct * total` over-count covered branches ~5x.
    merged = cc.weighted_merge(
        [
            _report("measured", 80.0, 100, branch_pct=60.0, branches_total=50),
            _report("branchless", 40.0, 100, branch_pct=None, branches_total=200),
        ]
    )

    assert merged["branch_pct"] == pytest.approx(60.0, abs=0.01)
    assert merged["branches_total"] == 50
    assert merged["statements_total"] == 200


def test_merge_treats_zero_percent_coverage_as_measured_not_skipped() -> None:
    # A truthiness check (`if not pct`) would silently drop the uncovered
    # project's weight and report 100%.
    merged = cc.weighted_merge(
        [_report("uncovered", 0.0, 100), _report("covered", 100.0, 100)]
    )

    assert merged["line_pct"] == pytest.approx(50.0, abs=0.01)
    assert merged["statements_total"] == 200


def test_merge_of_zero_projects_is_a_diagnosable_hard_failure() -> None:
    with pytest.raises(cc.DiscoveryError, match="no included"):
        cc.weighted_merge([])


@pytest.mark.parametrize(
    "bad",
    [
        _report("p", 101.0, 10),
        _report("p", -1.0, 10),
        _report("p", 50.0, -3),
        _report("p", "fifty", 10),  # type: ignore[arg-type]
        _report("p", 50.0, 10, branch_pct=101.0, branches_total=5),
        _report("p", True, 10),  # type: ignore[arg-type]
        {**_report("p", 50.0, 10), "statements_total": True},
        {**_report("p", 50.0, 10), "path": 7},
    ],
)
def test_merge_rejects_a_nonsensical_project_report(bad: dict) -> None:
    with pytest.raises(cc.DiscoveryError):
        cc.weighted_merge([bad])


@pytest.mark.parametrize("missing", cc._REQUIRED_REPORT_KEYS)
def test_merge_rejects_a_report_with_a_missing_key_rather_than_defaulting_it(
    missing: str,
) -> None:
    # A producer that omits `statements_total` must not silently contribute
    # weight 0 and vanish from the merged percentage.
    incomplete = {
        key: value
        for key, value in _report("p", 50.0, 100, branch_pct=50.0, branches_total=10).items()
        if key != missing
    }

    with pytest.raises(cc.DiscoveryError, match="missing required key"):
        cc.weighted_merge([incomplete])


# ---------------------------------------------------------------------------
# measurement_basis_notice
# ---------------------------------------------------------------------------


def test_notice_fires_when_the_baseline_predates_the_bootstrap() -> None:
    notice = cc.measurement_basis_notice(
        bootstrapped_at="2026-08-04T12:00:00Z", captured_at="2026-07-01T09:30:00Z"
    )

    assert notice == cc.MEASUREMENT_BASIS_NOTICE_TEMPLATE.format(
        bootstrapped_at="2026-08-04T12:00:00Z", captured_at="2026-07-01T09:30:00Z"
    )


@pytest.mark.parametrize(
    "captured_at",
    ["2026-08-04T12:00:00Z", "2026-09-01T00:00:00Z"],
)
def test_notice_is_silent_when_the_baseline_is_not_older(captured_at: str) -> None:
    assert (
        cc.measurement_basis_notice(
            bootstrapped_at="2026-08-04T12:00:00Z", captured_at=captured_at
        )
        is None
    )


def test_notice_compares_across_offset_forms_not_lexicographically() -> None:
    # 11:00Z is earlier than 12:00Z, but "2026-08-04T13:00:00+02:00" sorts later as a
    # string. Comparison must be instant-based.
    assert (
        cc.measurement_basis_notice(
            bootstrapped_at="2026-08-04T12:00:00Z",
            captured_at="2026-08-04T13:00:00+02:00",
        )
        is not None
    )


@pytest.mark.parametrize(
    ("bootstrapped_at", "captured_at"),
    [(None, "2026-07-01T09:30:00Z"), ("2026-08-04T12:00:00Z", None), (None, None)],
)
def test_notice_is_silent_when_either_timestamp_is_absent(
    bootstrapped_at: str | None, captured_at: str | None
) -> None:
    assert cc.measurement_basis_notice(bootstrapped_at, captured_at) is None


def test_notice_rejects_an_unparseable_timestamp_by_name() -> None:
    with pytest.raises(cc.DiscoveryError, match="whenever"):
        cc.measurement_basis_notice(
            bootstrapped_at="whenever", captured_at="2026-07-01T09:30:00Z"
        )
