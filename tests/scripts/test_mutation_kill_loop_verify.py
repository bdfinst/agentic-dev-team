"""Pytest tests for mutation_kill_loop.py's verify/commit subprocess wiring —
``dotnet_build``/``dotnet_test`` (#1564 split of ``test_mutation_kill_loop.py``).
Every dotnet subprocess is mocked; no real .NET tooling runs.

``git_revert``/``git_commit``/``git_reset_and_revert`` are re-exported
bindings onto ``mutation_kill_shared.py``'s implementation (#1583); their
full behavioral suite (timeout handling, argv shape, add/commit/reset branch
coverage) lives in ``test_mutation_kill_shared.py`` as the single source of
truth (#1603) — this file keeps only the identity check below, confirming
the re-export stays wired to the shared implementation rather than drifting
into a local copy.

The script's CLI dispatch and the cross-module no-repo-specific-literal sweep
live in ``test_mutation_kill_loop_cli.py`` — a separate file so this one stays
scoped to the verify/commit subprocess primitives alone.
"""

from __future__ import annotations

import pytest
from _mutation_kill_loop_test_helpers import _write_config

import mutation_kill_loop as loop  # noqa: E402 (sys.path set up by the helper import above)
import mutation_kill_shared as shared  # noqa: E402


# =============================================================================
# Verify/commit subprocess wiring — targets come from config (no literals)
# =============================================================================
def test_dotnet_build_uses_configured_test_project(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    config = loop.load_loop_config(
        _write_config(tmp_path, test_projects=("test/Foo.Tests/Foo.Tests.csproj",))
    )
    seen: list = []

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        loop.subprocess, "run", lambda argv, **k: seen.append(argv) or _R()
    )

    assert loop.dotnet_build(loop.dotnet_test_project_targets(config)) is True
    assert seen[0] == [
        "dotnet",
        "build",
        "test/Foo.Tests/Foo.Tests.csproj",
        "-c",
        "Debug",
        "--nologo",
    ]


# =============================================================================
# Scenario: A hung `dotnet build`/`dotnet test` is bounded by a timeout — it
# fails (and reverts) rather than hanging the loop forever (#1558)
# =============================================================================
def test_dotnet_build_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    loop.dotnet_build(["test/Foo.Tests/Foo.Tests.csproj"])

    assert captured["timeout"] == loop.DOTNET_BUILD_TIMEOUT_S


def test_dotnet_build_timeout_is_treated_as_a_build_failure(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_build(["test/Foo.Tests/Foo.Tests.csproj"]) is False
    err = capsys.readouterr().err
    assert str(loop.DOTNET_BUILD_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_BUILD_TIMEOUT_S" in err


def test_dotnet_build_returns_false_on_nonzero_returncode(
    monkeypatch: pytest.MonkeyPatch
):
    """dotnet_build's own failure-path logic (a non-zero exit, no timeout
    involved) — direct coverage, not mocked away at the orchestration level
    (#1584)."""

    class _R:
        returncode = 1
        stdout = ""
        stderr = "error CS0000: something broke\n"

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_build(["Foo.Tests.csproj"]) is False


def test_dotnet_build_stops_after_the_first_failing_target(
    monkeypatch: pytest.MonkeyPatch
):
    """dotnet_build's per-target loop short-circuits on the first failure —
    a second, later-configured test-project target must never be built once
    an earlier one has already failed (#1563 gap 1)."""

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R(1) if len(calls) == 1 else _R(0)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_build(["Foo.Tests.csproj", "Bar.Tests.csproj"]) is False
    assert len(calls) == 1
    assert calls[0][2] == "Foo.Tests.csproj"


def test_dotnet_test_returns_false_on_nonzero_returncode_even_with_zero_failed(
    monkeypatch: pytest.MonkeyPatch
):
    """A non-zero `dotnet test` exit fails the round even when the "Failed:"
    line itself parses to 0 (e.g. the process crashed before reporting) —
    direct coverage of dotnet_test's own failure-path logic (#1584)."""

    class _R:
        returncode = 1
        stdout = "Failed: 0, Passed: 5\n"
        stderr = ""

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_test(["Foo.Tests.csproj"], "FooTests") is False


def test_dotnet_test_accumulates_failed_count_across_multiple_assemblies(
    monkeypatch: pytest.MonkeyPatch
):
    """A single `dotnet test` invocation spanning multiple test assemblies
    prints one "Failed: N" line per assembly. The scan must SUM them, not
    let a later, clean assembly's "Failed: 0" line overwrite an earlier
    assembly's real failures — a last-match-wins scan would falsely report
    success here (#1598). Fixture shape matches real `dotnet test` per-
    assembly summary lines (item 11, #1598/#1584 review), not a synthetic
    shorthand — see also the rollup-line non-double-count test below."""

    class _R:
        returncode = 0
        stdout = (
            "Failed!  - Failed:     3, Passed:     7, Skipped:     0, "
            "Total:    10, Duration: 120 ms - Bar.Tests.dll\n"
            "Passed!  - Failed:     0, Passed:    12, Skipped:     0, "
            "Total:    12, Duration: 40 ms - Foo.Tests.dll\n"
        )
        stderr = ""

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_test(["Foo.Tests.csproj"], "FooTests") is False


def test_dotnet_test_trailing_lowercase_rollup_line_does_not_flip_a_clean_run(
    monkeypatch: pytest.MonkeyPatch
):
    """Newer `dotnet test` SDKs (7/8) also print a final, lowercase rollup
    line ("Test summary: total: ... failed: 0 ...") after the per-assembly
    summaries. The scan is capital-F "Failed:" only, so this rollup line
    must not be mistaken for a second, independent "Failed:" occurrence —
    a fully clean multi-assembly run (returncode 0, every real "Failed:"
    count is 0) must still report success (item 11, #1598/#1584 review)."""

    class _R:
        returncode = 0
        stdout = (
            "Passed!  - Failed:     0, Passed:    10, Skipped:     0, "
            "Total:    10, Duration: 40 ms - Foo.Tests.dll\n"
            "\n"
            "Test summary: total: 10, failed: 0, succeeded: 10, skipped: 0, "
            "duration: 0.1s\n"
        )
        stderr = ""

    monkeypatch.setattr(loop.subprocess, "run", lambda argv, **k: _R())

    assert loop.dotnet_test(["Foo.Tests.csproj"], "FooTests") is True


def test_dotnet_test_stops_after_the_first_failing_target(
    monkeypatch: pytest.MonkeyPatch
):
    """dotnet_test's per-target loop short-circuits on the first failure —
    a second, later-configured test-project target must never be tested once
    an earlier one has already failed (#1563 gap 1)."""

    class _R:
        def __init__(self, returncode):
            self.returncode = returncode
            self.stdout = "Failed:     1, Passed:     0\n" if returncode else ""
            self.stderr = ""

    calls: list = []

    def fake_run(argv, **k):
        calls.append(argv)
        return _R(1) if len(calls) == 1 else _R(0)

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_test(["Foo.Tests.csproj", "Bar.Tests.csproj"], "FooTests") is False
    assert len(calls) == 1
    assert calls[0][2] == "Foo.Tests.csproj"


def test_sum_failed_counts_is_case_sensitive_not_double_counting_the_rollup_line():
    """A fixture where both a correct (case-sensitive) scan and a buggy
    (case-insensitive) scan sum to 0 can't actually catch a regression to
    ``re.IGNORECASE`` (#1598/#1584 review, item 12) — the boolean
    ``dotnet_test`` result would be identical either way. Asserting the
    NUMERIC total directly against a nonzero per-assembly count (3) plus a
    nonzero lowercase rollup count (3) proves the scan is case-sensitive:
    a case-insensitive regex would sum both `Failed:`-shaped occurrences
    (3 + 3 = 6); the correct, case-sensitive scan counts only the real
    capital-F per-assembly line (3)."""
    text = (
        "Failed!  - Failed:     3, Passed:     7, Skipped:     0, "
        "Total:    10, Duration: 120 ms - Bar.Tests.dll\n"
        "\n"
        "Test summary: total: 10, failed: 3, succeeded: 7, skipped: 0, "
        "duration: 0.1s\n"
    )

    assert loop._sum_failed_counts(text) == 3


def test_dotnet_test_passes_a_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_test(["test/Foo.Tests/Foo.Tests.csproj"], "FooTests") is True
    assert captured["timeout"] == loop.DOTNET_TEST_TIMEOUT_S


def test_dotnet_test_timeout_is_treated_as_a_test_failure(
    monkeypatch: pytest.MonkeyPatch, capsys
):
    def fake_run(argv, **kwargs):
        raise loop.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(loop.subprocess, "run", fake_run)

    assert loop.dotnet_test(["test/Foo.Tests/Foo.Tests.csproj"], "FooTests") is False
    err = capsys.readouterr().err
    assert str(loop.DOTNET_TEST_TIMEOUT_S) in err
    assert "DEV_TEAM_MUTATION_TEST_TIMEOUT_S" in err


# =============================================================================
# git_revert / git_commit / git_reset_and_revert — identity check only.
# Full behavioral coverage (timeout handling, argv shape, add/commit/reset
# branch coverage) lives in test_mutation_kill_shared.py as the single
# source of truth (#1603); this confirms the re-export stays wired to that
# shared implementation rather than drifting into a local copy.
# =============================================================================
def test_git_helpers_are_the_shared_implementation():
    assert loop.git_revert is shared.git_revert
    assert loop.git_commit is shared.git_commit
    assert loop.git_reset_and_revert is shared.git_reset_and_revert
