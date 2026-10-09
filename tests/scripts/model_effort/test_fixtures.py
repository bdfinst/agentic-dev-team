"""Fixture resolution (model_effort.fixtures)."""

from __future__ import annotations

import pytest
from _model_effort_support import (
    _make_directory_fixture,
    _make_file_fixture,
    _write_expected,
)
from model_effort import fixtures as fixture_resolution
from model_effort.errors import UsageError


class TestIsExpectedClean:
    def test_expected_status_pass_is_clean(self):
        entry = {"agents": {"a": {"expectedStatus": "pass"}}}

        assert fixture_resolution.is_expected_clean(entry, "a") is True

    def test_expected_status_fail_is_not_clean(self):
        entry = {"agents": {"a": {"expectedStatus": "fail"}}}

        assert fixture_resolution.is_expected_clean(entry, "a") is False

    def test_agent_missing_from_entry_is_not_clean(self):
        assert fixture_resolution.is_expected_clean({"agents": {}}, "a") is False


class TestDescribeFixture:
    def test_file_stem_drops_one_extension_and_kind_is_file(self, fixture_root):
        path = _make_file_fixture(fixture_root, "a.b.html")

        assert fixture_resolution.describe_fixture(path) == (
            "a.b",
            fixture_resolution.FixtureKind.FILE,
        )

    def test_directory_stem_is_its_name_and_kind_is_directory(self, fixture_root):
        path = _make_directory_fixture(fixture_root)

        assert fixture_resolution.describe_fixture(path) == (
            "service",
            fixture_resolution.FixtureKind.DIRECTORY,
        )


class TestResolveFixtures:
    def test_agent_named_by_no_expected_entry_is_refused_saying_so(
        self, expected_dir, fixture_root
    ):
        _write_expected(expected_dir, "other-case", "other", "pass")

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures(
                "scout", None, expected_dir, fixture_root
            )

        assert "no evals/expected entry names it" in str(excinfo.value)

    def test_entries_without_a_matching_fixture_are_refused_listing_the_stems(
        self, expected_dir, fixture_root
    ):
        _write_expected(expected_dir, "ghost-case", "scout", "pass")
        _write_expected(expected_dir, "phantom-case", "scout", "fail")

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures(
                "scout", None, expected_dir, fixture_root
            )

        message = str(excinfo.value)
        assert "entries exist but no fixture matches" in message
        assert "ghost-case" in message and "phantom-case" in message
        assert "no evals/expected entry names it" not in message

    def test_runnable_fixtures_carry_kind_path_and_expected_clean(
        self, expected_dir, fixture_root
    ):
        _write_expected(expected_dir, "clean-form", "scout", "pass")
        _write_expected(expected_dir, "layered-svc", "scout", "fail")
        form = _make_file_fixture(fixture_root, "clean-form.html")
        service = fixture_root / "layered-svc"
        service.mkdir()

        resolved = fixture_resolution.resolve_fixtures(
            "scout", None, expected_dir, fixture_root
        )

        assert resolved == [
            fixture_resolution.ResolvedFixture(
                stem="clean-form",
                path=form,
                kind=fixture_resolution.FixtureKind.FILE,
                expected_clean=True,
            ),
            fixture_resolution.ResolvedFixture(
                stem="layered-svc",
                path=service,
                kind=fixture_resolution.FixtureKind.DIRECTORY,
                expected_clean=False,
            ),
        ]

    def test_missing_fixtures_directory_is_refused_naming_it(
        self, expected_dir, tmp_path
    ):
        _write_expected(expected_dir, "clean-form", "scout", "pass")
        missing = tmp_path / "no-fixtures"

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures("scout", None, expected_dir, missing)

        assert str(missing) in str(excinfo.value)

    def test_malformed_expected_json_is_refused_naming_the_file(
        self, expected_dir, fixture_root
    ):
        (expected_dir / "broken.json").write_text("{not json", encoding="utf-8")

        with pytest.raises(UsageError) as excinfo:
            fixture_resolution.resolve_fixtures(
                "scout", None, expected_dir, fixture_root
            )

        assert str(expected_dir / "broken.json") in str(excinfo.value)
