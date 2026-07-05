"""Verifies the .NET smoke fixture for issue #524. Structural checks
only — whether the LLM-produced excerpts are semantically correct is the
human merge reviewer's call.

Ported from tests/bats/stack-aware-dotnet-fixture.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "evals" / "fixtures" / "dotnet-http-smoke"


def test_fixture_directory_exists_and_contains_csproj() -> None:
    assert FIXTURE_DIR.is_dir()
    csproj_files = [
        p
        for p in FIXTURE_DIR.rglob("*.csproj")
        if len(p.relative_to(FIXTURE_DIR).parts) <= 2
    ]
    assert len(csproj_files) >= 1


def test_fixture_contains_at_least_one_tests_cs_file() -> None:
    tests_files = [
        p
        for p in FIXTURE_DIR.rglob("*Tests.cs")
        if len(p.relative_to(FIXTURE_DIR).parts) <= 2
    ]
    assert len(tests_files) >= 1


def test_fixture_test_file_contains_deliberate_mock_httpclient_smell() -> None:
    # The fixture's whole point is to give /test-smell-review something to
    # flag. Without this line, the manual verification step's smell
    # scenario is vacuous.
    pattern = re.compile(r"Mock<HttpClient>|new Mock\(typeof\(HttpClient\)\)")
    found = any(
        pattern.search(p.read_text(encoding="utf-8"))
        for p in FIXTURE_DIR.glob("*Tests.cs")
    )
    assert found


def test_fixture_client_class_accepts_httpclient_as_constructor_parameter() -> None:
    # Defines the 'outbound HTTP code path' trigger from acceptance
    # criterion A5.
    pattern = re.compile(r"\(HttpClient[ \t]+[a-zA-Z_]|\([ \t]*HttpClient[ \t]*\)")
    found = any(
        pattern.search(p.read_text(encoding="utf-8")) for p in FIXTURE_DIR.glob("*.cs")
    )
    assert found
