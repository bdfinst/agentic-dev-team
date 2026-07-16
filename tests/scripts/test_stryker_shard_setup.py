"""Pytest tests for stryker_shard_setup.py — the generic Stryker shard-config
generator (Slice 4 of the ACI mutation-pipeline fold, #1136).

Each test maps to a Slice 4 Gherkin scenario in
``plans/generalize-aci-mutation-pipeline-fold-into-mutation-kill.md``. Solution
files are synthetic .sln text written to a tmp_path repo root — no real dotnet
is invoked, and every project name is generic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

import pytest

# Ensure the module's dir is on the path so we can import it directly.
SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import stryker_shard_setup  # noqa: E402


# =============================================================================
# Fixture helpers
# =============================================================================
_PROJECT_TYPE_GUID = "9A19103F-16F7-4668-BE54-9A1E7A4F7556"


def _project_line(name: str, csproj: str, guid: str) -> str:
    return (
        f'Project("{{{_PROJECT_TYPE_GUID}}}") = "{name}", "{csproj}", "{{{guid}}}"\n'
        "EndProject\n"
    )


def _write_solution(
    repo_root: Path,
    projects: Sequence[tuple],
    *,
    filename: str = "App.sln",
) -> Path:
    """Write a minimal .sln listing (name, csproj-relpath) tuples.

    A .csproj file is created on disk for each project so path resolution is
    exercised against real files under the repo root.
    """
    lines = [stryker_shard_setup._SLN_HEADER]
    for index, (name, csproj) in enumerate(projects):
        guid = f"{index:08d}-0000-0000-0000-000000000000"
        lines.append(_project_line(name, csproj.replace("/", "\\"), guid))
        csproj_path = repo_root / csproj
        csproj_path.parent.mkdir(parents=True, exist_ok=True)
        csproj_path.write_text("<Project />\n", encoding="utf-8")
    sln_path = repo_root / filename
    sln_path.write_text("".join(lines), encoding="utf-8")
    return sln_path


def _run(repo_root: Path, *extra: str) -> int:
    argv = ["--repo-root", str(repo_root), *extra]
    return stryker_shard_setup.main(argv)


def _shard_configs(repo_root: Path) -> list:
    return sorted(repo_root.glob("stryker-config.shard-*.json"))


def _load_shard(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["stryker-config"]


# =============================================================================
# Scenario: One shard config per source project
# =============================================================================
def test_one_shard_config_per_source_project(tmp_path: Path):
    _write_solution(
        tmp_path,
        [
            ("Widget.WebApi", "src/Widget.WebApi/Widget.WebApi.csproj"),
            ("Widget.Domain", "src/Widget.Domain/Widget.Domain.csproj"),
            ("Widget.WebApi.Tests", "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"),
            ("Widget.Domain.Tests", "test/Widget.Domain.Tests/Widget.Domain.Tests.csproj"),
        ],
    )

    assert _run(tmp_path) == 0

    configs = _shard_configs(tmp_path)
    names = {p.name for p in configs}
    assert names == {
        "stryker-config.shard-web-api.json",
        "stryker-config.shard-domain.json",
    }

    web_api = _load_shard(tmp_path / "stryker-config.shard-web-api.json")
    assert web_api["test-projects"] == [
        "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"
    ]

    # Stryker.sln lists every source and test project.
    sln = (tmp_path / "Stryker.sln").read_text(encoding="utf-8")
    for name in ("Widget.WebApi", "Widget.Domain", "Widget.WebApi.Tests", "Widget.Domain.Tests"):
        assert name in sln


# =============================================================================
# Scenario: A source project with no matching test project falls back to all
# =============================================================================
def test_unmatched_source_falls_back_to_all_test_projects(tmp_path: Path):
    _write_solution(
        tmp_path,
        [
            ("Widget.Orphan", "src/Widget.Orphan/Widget.Orphan.csproj"),
            ("Widget.WebApi.Tests", "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"),
            ("Widget.Domain.Tests", "test/Widget.Domain.Tests/Widget.Domain.Tests.csproj"),
        ],
    )

    assert _run(tmp_path) == 0

    orphan = _load_shard(tmp_path / "stryker-config.shard-orphan.json")
    assert orphan["test-projects"] == [
        "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj",
        "test/Widget.Domain.Tests/Widget.Domain.Tests.csproj",
    ]
    assert orphan["test-projects"] != []


# =============================================================================
# Scenario: Multiple test projects matching one source project are all paired
# =============================================================================
def test_multiple_matching_test_projects_all_paired(tmp_path: Path):
    _write_solution(
        tmp_path,
        [
            ("Widget.Domain", "src/Widget.Domain/Widget.Domain.csproj"),
            ("Widget.Domain.Tests", "test/Widget.Domain.Tests/Widget.Domain.Tests.csproj"),
            (
                "Widget.Domain.IntegrationTests",
                "test/Widget.Domain.IntegrationTests/Widget.Domain.IntegrationTests.csproj",
            ),
        ],
    )

    assert _run(tmp_path) == 0

    domain = _load_shard(tmp_path / "stryker-config.shard-domain.json")
    assert set(domain["test-projects"]) == {
        "test/Widget.Domain.Tests/Widget.Domain.Tests.csproj",
        "test/Widget.Domain.IntegrationTests/Widget.Domain.IntegrationTests.csproj",
    }


# =============================================================================
# Scenario: Duplicate slugs from identical last name segments are disambiguated
# =============================================================================
def test_duplicate_last_segments_produce_distinct_filenames(tmp_path: Path):
    _write_solution(
        tmp_path,
        [
            ("Widget.WebApi", "src/Widget.WebApi/Widget.WebApi.csproj"),
            ("Gadget.WebApi", "src/Gadget.WebApi/Gadget.WebApi.csproj"),
        ],
    )

    assert _run(tmp_path) == 0

    configs = _shard_configs(tmp_path)
    # Two distinct source projects → two distinct shard config filenames,
    # neither overwriting the other.
    assert len(configs) == 2
    names = {p.name for p in configs}
    assert len(names) == 2

    # Each shard instruments its own source project.
    projects = {_load_shard(p)["project"] for p in configs}
    assert projects == {
        "src/Widget.WebApi/Widget.WebApi.csproj",
        "src/Gadget.WebApi/Gadget.WebApi.csproj",
    }


# =============================================================================
# Scenario: Dry-run writes nothing
# =============================================================================
def test_dry_run_writes_nothing(tmp_path: Path, capsys):
    _write_solution(
        tmp_path,
        [
            ("Widget.WebApi", "src/Widget.WebApi/Widget.WebApi.csproj"),
            ("Widget.WebApi.Tests", "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"),
        ],
    )

    assert _run(tmp_path, "--dry-run") == 0

    assert _shard_configs(tmp_path) == []
    assert not (tmp_path / "Stryker.sln").exists()
    assert not (tmp_path / "stryker-pipeline.json").exists()

    out = capsys.readouterr().out
    assert "shard-web-api" in out
    assert "No files were written" in out


# =============================================================================
# Scenario: A missing solution file is an actionable error
# =============================================================================
def test_missing_solution_is_actionable_error(tmp_path: Path, capsys):
    # Empty repo root — no *.sln to discover.
    assert _run(tmp_path) != 0

    err = capsys.readouterr().err
    assert "--solution" in err


def test_explicit_missing_solution_names_the_flag(tmp_path: Path, capsys):
    assert _run(tmp_path, "--solution", "Nope.sln") != 0

    err = capsys.readouterr().err
    assert "--solution" in err


# =============================================================================
# Scenario: The generated configs carry no repo-specific literal
# =============================================================================
def test_emitted_configs_carry_no_repo_specific_literal(tmp_path: Path):
    _write_solution(
        tmp_path,
        [
            ("Widget.WebApi", "src/Widget.WebApi/Widget.WebApi.csproj"),
            ("Widget.WebApi.Tests", "test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj"),
        ],
    )

    assert _run(tmp_path) == 0

    forbidden = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]
    emitted = _shard_configs(tmp_path) + [
        tmp_path / "Stryker.sln",
        tmp_path / "stryker-pipeline.json",
    ]
    for artifact in emitted:
        text = artifact.read_text(encoding="utf-8")
        present = [lit for lit in forbidden if lit in text]
        assert present == [], f"repo-specific literal leaked into {artifact.name}: {present}"


def test_module_source_carries_no_repo_specific_literal():
    source = (SCRIPTS_DIR / "stryker_shard_setup.py").read_text(encoding="utf-8")

    forbidden = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]
    present = [lit for lit in forbidden if lit in source]
    assert present == [], f"repo-specific literals leaked into module: {present}"


# =============================================================================
# Scenario: A hostile project name cannot write a shard config outside the repo
# =============================================================================
def test_malicious_project_name_cannot_escape_repo_root(tmp_path: Path):
    # The .sln lives in a nested repo root so any traversal would land in the
    # tmp_path parent, where we can detect the escape.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_solution(
        repo_root,
        [
            # Path-traversal sequences in the (untrusted) project name.
            ("Foo/../../evil", "src/Evil/Evil.csproj"),
            ("Foo.Tests", "test/Foo.Tests/Foo.Tests.csproj"),
        ],
    )

    assert _run(repo_root) == 0

    # No .json (shard config or otherwise) was written outside the repo root.
    escaped = [
        p
        for p in tmp_path.rglob("*.json")
        if repo_root.resolve() != p.resolve().parent
        and repo_root.resolve() not in p.resolve().parents
    ]
    assert escaped == [], f"files escaped the repo root: {escaped}"

    # The generated shard config has a sanitized, path-separator-free name.
    configs = _shard_configs(repo_root)
    assert configs, "expected a shard config for the source project"
    for cfg in configs:
        assert "/" not in cfg.name and "\\" not in cfg.name and ".." not in cfg.name


def test_sanitize_slug_strips_traversal_and_separators():
    assert stryker_shard_setup._sanitize_slug("foo/../../evil") == "foo-evil"
    assert stryker_shard_setup._sanitize_slug("..") == ""
    assert stryker_shard_setup._sanitize_slug("web-api") == "web-api"


# =============================================================================
# Slug derivation unit coverage (kebab-case of last dotted segment)
# =============================================================================
@pytest.mark.parametrize(
    "name, expected",
    [
        ("Widget.WebApi", "web-api"),
        ("Widget.ApplicationServices", "application-services"),
        ("Widget.DomainModel", "domain-model"),
        ("Widget.Domain", "domain"),
    ],
)
def test_slug_is_kebab_case_of_last_segment(name: str, expected: str):
    assert stryker_shard_setup.slug(name) == expected
