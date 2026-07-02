"""Verifies the .NET smoke fixture and PR-body evidence draft for issue
#524 (Slice 4 of plans/stack-aware-reference-loading.md). Structural
checks only — whether the LLM-produced excerpts are semantically correct
is the human merge reviewer's call.

Ported from tests/bats/stack-aware-dotnet-fixture.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "evals" / "fixtures" / "dotnet-http-smoke"
PR_BODY = REPO_ROOT / "plans" / "pr-bodies" / "524.md"


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


def test_pr_body_draft_exists() -> None:
    assert PR_BODY.is_file()


def test_pr_body_draft_contains_evidence_heading() -> None:
    text = PR_BODY.read_text(encoding="utf-8")
    assert re.search(r"^## Evidence", text, re.MULTILINE)


def test_pr_body_draft_cites_dotnet_stack_profile_path() -> None:
    text = PR_BODY.read_text(encoding="utf-8")
    assert "knowledge/test-stack-profiles/dotnet.md" in text


def test_pr_body_draft_cites_csharp_http_client_reference_path() -> None:
    text = PR_BODY.read_text(encoding="utf-8")
    assert "knowledge/references/csharp-http-client-testing.md" in text
