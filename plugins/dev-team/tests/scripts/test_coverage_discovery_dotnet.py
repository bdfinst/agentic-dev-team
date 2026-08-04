"""Tests for coverage_discovery_dotnet.py — .NET solution discovery (#1781).

Every `dotnet` subprocess call is stubbed, so this suite runs inside the
pre-push pytest gate with no .NET SDK installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import coverage_config as cc
import coverage_discovery_dotnet as dnd

_TEST = cc.TestClassification.TEST
_NOT_TEST = cc.TestClassification.NOT_TEST
_AMBIGUOUS = cc.TestClassification.AMBIGUOUS


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _csproj(*package_refs: str) -> str:
    items = "\n".join(f"    {ref}" for ref in package_refs)
    return f'<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n{items}\n  </ItemGroup>\n</Project>\n'


def _solution(tmp_path: Path, *project_rel_paths: str) -> Path:
    """Create a `.sln` file. Its contents are irrelevant — `dotnet sln list` is
    stubbed — but it has to exist, because that is the discovery trigger."""
    _write(tmp_path / "App.sln", "Microsoft Visual Studio Solution File\n")
    return tmp_path / "App.sln"


@pytest.fixture
def stub_sln_list(monkeypatch: pytest.MonkeyPatch):
    """Stub the one `dotnet sln list` subprocess boundary."""

    def _stub(*project_rel_paths: str) -> None:
        monkeypatch.setattr(
            dnd, "run_dotnet_sln_list", lambda _sln: list(project_rel_paths)
        )

    return _stub


def _classification_of(projects: list[cc.DiscoveredProject], path: str):
    return next(project.classification for project in projects if project.path == path)


# ---------------------------------------------------------------------------
# Not-applicable signal
# ---------------------------------------------------------------------------


def test_no_solution_is_not_applicable(tmp_path: Path) -> None:
    _write(tmp_path / "App" / "App.csproj", _csproj())

    result = dnd.discover(tmp_path)

    # Identity, not equality: an empty list means "multi-project repo, found
    # nothing", which is a hard failure, not "keep the single-command path".
    assert result is cc.DISCOVERY_NOT_APPLICABLE


def test_two_solutions_is_a_discovery_error_naming_both(tmp_path: Path) -> None:
    _write(tmp_path / "One.sln", "")
    _write(tmp_path / "Two.sln", "")

    with pytest.raises(cc.DiscoveryError) as excinfo:
        dnd.discover(tmp_path)

    assert "One.sln" in str(excinfo.value)
    assert "Two.sln" in str(excinfo.value)


def test_an_explicit_solution_path_wins_over_ambiguity(tmp_path: Path, stub_sln_list) -> None:
    _write(tmp_path / "One.sln", "")
    _write(tmp_path / "Two.sln", "")
    _write(tmp_path / "src" / "App" / "App.csproj", _csproj())
    stub_sln_list("src/App/App.csproj")

    result = dnd.discover(tmp_path, solution=tmp_path / "One.sln")

    assert [project.path for project in result] == ["src/App/App.csproj"]


# ---------------------------------------------------------------------------
# Classification 1 — inline Microsoft.NET.Test.Sdk PackageReference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "package_ref",
    [
        '<PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />',
        # Attribute order reversed.
        '<PackageReference Version="17.11.1" Include="Microsoft.NET.Test.Sdk" />',
        # Central Package Management: no Version attribute at all.
        '<PackageReference Include="Microsoft.NET.Test.Sdk" />',
        # Element form rather than self-closing.
        '<PackageReference Include="Microsoft.NET.Test.Sdk"></PackageReference>',
        # Single quotes and extra whitespace.
        "<PackageReference    Include='Microsoft.NET.Test.Sdk'   />",
        # `Update` rather than `Include` (CPM version pinning).
        '<PackageReference Update="Microsoft.NET.Test.Sdk" Version="17.11.1" />',
    ],
)
def test_inline_marker_classifies_test_in_any_attribute_form(
    tmp_path: Path, stub_sln_list, package_ref: str
) -> None:
    _solution(tmp_path)
    _write(tmp_path / "tests" / "A.Tests" / "A.Tests.csproj", _csproj(package_ref))
    stub_sln_list("tests/A.Tests/A.Tests.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "tests/A.Tests/A.Tests.csproj") is _TEST


def test_a_project_with_no_marker_anywhere_classifies_not_test(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(
        tmp_path / "src" / "App" / "App.csproj",
        _csproj('<PackageReference Include="Newtonsoft.Json" Version="13.0.3" />'),
    )
    stub_sln_list("src/App/App.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "src/App/App.csproj") is _NOT_TEST


def test_a_lookalike_package_name_is_not_the_marker(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(
        tmp_path / "src" / "App" / "App.csproj",
        _csproj('<PackageReference Include="Microsoft.NET.Test.Sdk.Extras" Version="1.0" />'),
    )
    stub_sln_list("src/App/App.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "src/App/App.csproj") is _NOT_TEST


def test_the_marker_in_a_comment_is_not_a_reference(
    tmp_path: Path, stub_sln_list
) -> None:
    # A substring search over the raw file — the #1759 script's approach — would
    # call this a test project.
    _solution(tmp_path)
    _write(
        tmp_path / "src" / "App" / "App.csproj",
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        '  <!-- <PackageReference Include="Microsoft.NET.Test.Sdk" /> removed in 2024 -->\n'
        "</Project>\n",
    )
    stub_sln_list("src/App/App.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "src/App/App.csproj") is _NOT_TEST


def test_the_legacy_msbuild_xml_namespace_is_handled(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(
        tmp_path / "tests" / "Old.Tests" / "Old.Tests.csproj",
        '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\n'
        "  <ItemGroup>\n"
        '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />\n'
        "  </ItemGroup>\n"
        "</Project>\n",
    )
    stub_sln_list("tests/Old.Tests/Old.Tests.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "tests/Old.Tests/Old.Tests.csproj") is _TEST


@pytest.mark.parametrize("extension", [".csproj", ".fsproj", ".vbproj"])
def test_every_dotnet_project_extension_is_classified(
    tmp_path: Path, stub_sln_list, extension: str
) -> None:
    rel = f"tests/A.Tests/A.Tests{extension}"
    _solution(tmp_path)
    _write(
        tmp_path / rel,
        _csproj('<PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />'),
    )
    stub_sln_list(rel)

    result = dnd.discover(tmp_path)

    assert _classification_of(result, rel) is _TEST


# ---------------------------------------------------------------------------
# Classification 2 — ancestor Directory.Build.props
# ---------------------------------------------------------------------------

_UNCONDITIONED_PROPS = (
    '<Project>\n  <ItemGroup>\n'
    '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />\n'
    "  </ItemGroup>\n</Project>\n"
)

_CONDITIONED_PROPS = (
    '<Project>\n  <ItemGroup>\n'
    '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" '
    "Condition=\"'$(IsTestProject)' == 'true'\" />\n"
    "  </ItemGroup>\n</Project>\n"
)

_ITEMGROUP_CONDITIONED_PROPS = (
    "<Project>\n"
    "  <ItemGroup Condition=\"$(MSBuildProjectName.EndsWith('.Tests'))\">\n"
    '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />\n'
    "  </ItemGroup>\n</Project>\n"
)


def test_unconditioned_ancestor_props_classifies_test(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(tmp_path / "tests" / "Directory.Build.props", _UNCONDITIONED_PROPS)
    _write(tmp_path / "tests" / "A.Tests" / "A.Tests.csproj", _csproj())
    stub_sln_list("tests/A.Tests/A.Tests.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "tests/A.Tests/A.Tests.csproj") is _TEST


@pytest.mark.parametrize(
    "props", [_CONDITIONED_PROPS, _ITEMGROUP_CONDITIONED_PROPS]
)
def test_conditioned_ancestor_props_classifies_ambiguous(
    tmp_path: Path, stub_sln_list, props: str
) -> None:
    # Never silently negative: the runtime condition is not evaluated, so a human
    # decides. This is the #1759 failure shape's direction.
    _solution(tmp_path)
    _write(tmp_path / "tests" / "Directory.Build.props", props)
    _write(tmp_path / "tests" / "A.Tests" / "A.Tests.csproj", _csproj())
    stub_sln_list("tests/A.Tests/A.Tests.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "tests/A.Tests/A.Tests.csproj") is _AMBIGUOUS


def test_an_inline_marker_beats_a_conditioned_ancestor(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(tmp_path / "tests" / "Directory.Build.props", _CONDITIONED_PROPS)
    _write(
        tmp_path / "tests" / "A.Tests" / "A.Tests.csproj",
        _csproj('<PackageReference Include="Microsoft.NET.Test.Sdk" />'),
    )
    stub_sln_list("tests/A.Tests/A.Tests.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "tests/A.Tests/A.Tests.csproj") is _TEST


def test_an_unconditioned_ancestor_beats_a_conditioned_nearer_one(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(tmp_path / "Directory.Build.props", _UNCONDITIONED_PROPS)
    _write(tmp_path / "tests" / "Directory.Build.props", _CONDITIONED_PROPS)
    _write(tmp_path / "tests" / "A.Tests" / "A.Tests.csproj", _csproj())
    stub_sln_list("tests/A.Tests/A.Tests.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "tests/A.Tests/A.Tests.csproj") is _TEST


def test_props_outside_the_solution_directory_is_not_consulted(
    tmp_path: Path, stub_sln_list
) -> None:
    solution_dir = tmp_path / "repo"
    _write(tmp_path / "Directory.Build.props", _UNCONDITIONED_PROPS)
    _solution(solution_dir)
    _write(solution_dir / "tests" / "A.Tests" / "A.Tests.csproj", _csproj())
    stub_sln_list("tests/A.Tests/A.Tests.csproj")

    result = dnd.discover(solution_dir)

    assert _classification_of(result, "tests/A.Tests/A.Tests.csproj") is _NOT_TEST


def test_a_props_file_with_no_marker_leaves_the_project_not_test(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(
        tmp_path / "Directory.Build.props",
        '<Project>\n  <PropertyGroup><LangVersion>latest</LangVersion></PropertyGroup>\n</Project>\n',
    )
    _write(tmp_path / "src" / "App" / "App.csproj", _csproj())
    stub_sln_list("src/App/App.csproj")

    result = dnd.discover(tmp_path)

    assert _classification_of(result, "src/App/App.csproj") is _NOT_TEST


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_malformed_csproj_is_a_discovery_error_naming_the_project(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(
        tmp_path / "tests" / "Broken.Tests" / "Broken.Tests.csproj",
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup></Project>',
    )
    stub_sln_list("tests/Broken.Tests/Broken.Tests.csproj")

    with pytest.raises(cc.DiscoveryError) as excinfo:
        dnd.discover(tmp_path)

    # Not a crash, and not a silent NOT_TEST.
    assert "tests/Broken.Tests/Broken.Tests.csproj" in str(excinfo.value)


def test_malformed_directory_build_props_is_a_discovery_error(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    _write(tmp_path / "Directory.Build.props", "<Project><ItemGroup></Project>")
    _write(tmp_path / "src" / "App" / "App.csproj", _csproj())
    stub_sln_list("src/App/App.csproj")

    with pytest.raises(cc.DiscoveryError, match="Directory.Build.props"):
        dnd.discover(tmp_path)


def test_a_missing_csproj_file_is_a_discovery_error(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    stub_sln_list("tests/Ghost.Tests/Ghost.Tests.csproj")

    with pytest.raises(cc.DiscoveryError, match="Ghost.Tests"):
        dnd.discover(tmp_path)


def test_dotnet_missing_from_path_is_a_discovery_error_not_an_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sln = _solution(tmp_path)

    def _no_dotnet(*_args: object, **_kwargs: object):
        raise FileNotFoundError(2, "No such file or directory: 'dotnet'")

    monkeypatch.setattr(dnd.subprocess, "run", _no_dotnet)

    with pytest.raises(cc.DiscoveryError) as excinfo:
        dnd.run_dotnet_sln_list(sln)

    message = str(excinfo.value)
    assert "dotnet" in message
    assert "PATH" in message


def test_a_failing_dotnet_invocation_is_a_discovery_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    sln = _solution(tmp_path)

    def _fails(*_args: object, **_kwargs: object):
        raise subprocess.CalledProcessError(
            1, "dotnet sln list", stderr="MSB1011: more than one project"
        )

    monkeypatch.setattr(dnd.subprocess, "run", _fails)

    with pytest.raises(cc.DiscoveryError, match="MSB1011"):
        dnd.run_dotnet_sln_list(sln)


def test_a_dotnet_timeout_is_a_discovery_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    sln = _solution(tmp_path)

    def _times_out(*_args: object, **_kwargs: object):
        raise subprocess.TimeoutExpired("dotnet sln list", 60)

    monkeypatch.setattr(dnd.subprocess, "run", _times_out)

    with pytest.raises(cc.DiscoveryError, match="timed out"):
        dnd.run_dotnet_sln_list(sln)


@pytest.mark.parametrize(
    "unsafe",
    [
        "/etc/passwd/Evil.csproj",
        "../outside/Evil.csproj",
        "-Evil.csproj",
        "tests/A;rm -rf ~/A.csproj",
        "tests/$(whoami)/A.csproj",
    ],
)
def test_an_unsafe_discovered_path_is_rejected(
    tmp_path: Path, stub_sln_list, unsafe: str
) -> None:
    _solution(tmp_path)
    stub_sln_list(unsafe)

    with pytest.raises(cc.DiscoveryError, match="unsafe"):
        dnd.discover(tmp_path)


# ---------------------------------------------------------------------------
# Path identity + output shape
# ---------------------------------------------------------------------------


def test_discovered_paths_are_recorded_exactly_as_dotnet_printed_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No normalization — `coverage_config` matches identity as an exact string, so
    # discovery must not rewrite what the tool emitted beyond trimming the line's
    # own surrounding whitespace. Driven through the real subprocess boundary so
    # the parse step is part of the assertion.
    import subprocess

    _solution(tmp_path)
    _write(
        tmp_path / "tests" / "A.Tests" / "A.Tests.csproj",
        _csproj('<PackageReference Include="Microsoft.NET.Test.Sdk" />'),
    )
    stdout = "Project(s)\n----------\n  tests/A.Tests/A.Tests.csproj  \n"
    monkeypatch.setattr(
        dnd.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, stdout, ""),
    )

    result = dnd.discover(tmp_path)

    assert [project.path for project in result] == ["tests/A.Tests/A.Tests.csproj"]


def test_discovery_is_sorted_and_covers_every_listed_project(
    tmp_path: Path, stub_sln_list
) -> None:
    _solution(tmp_path)
    marker = '<PackageReference Include="Microsoft.NET.Test.Sdk" />'
    _write(tmp_path / "tests" / "Z.Tests" / "Z.Tests.csproj", _csproj(marker))
    _write(tmp_path / "tests" / "A.Tests" / "A.Tests.csproj", _csproj(marker))
    _write(tmp_path / "src" / "App" / "App.csproj", _csproj())
    stub_sln_list(
        "tests/Z.Tests/Z.Tests.csproj",
        "src/App/App.csproj",
        "tests/A.Tests/A.Tests.csproj",
    )

    result = dnd.discover(tmp_path)

    assert [project.path for project in result] == [
        "src/App/App.csproj",
        "tests/A.Tests/A.Tests.csproj",
        "tests/Z.Tests/Z.Tests.csproj",
    ]


# ---------------------------------------------------------------------------
# `dotnet sln list` output parsing
# ---------------------------------------------------------------------------


def test_sln_list_output_parsing_drops_headers_and_rules() -> None:
    output = (
        "Project(s)\n"
        "----------\n"
        "src/App/App.csproj\n"
        "tests/A.Tests/A.Tests.fsproj\n"
        "\n"
        "some/readme.txt\n"
    )

    assert dnd.parse_sln_list_output(output) == [
        "src/App/App.csproj",
        "tests/A.Tests/A.Tests.fsproj",
    ]


def test_sln_list_output_parsing_keeps_windows_separators_verbatim() -> None:
    assert dnd.parse_sln_list_output("tests\\A.Tests\\A.Tests.csproj\n") == [
        "tests\\A.Tests\\A.Tests.csproj"
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_emits_json_classifications(
    tmp_path: Path, stub_sln_list, capsys: pytest.CaptureFixture[str]
) -> None:
    _solution(tmp_path)
    _write(
        tmp_path / "tests" / "A.Tests" / "A.Tests.csproj",
        _csproj('<PackageReference Include="Microsoft.NET.Test.Sdk" />'),
    )
    _write(tmp_path / "src" / "App" / "App.csproj", _csproj())
    stub_sln_list("tests/A.Tests/A.Tests.csproj", "src/App/App.csproj")

    exit_code = dnd.main([str(tmp_path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "applicable": True,
        "projects": [
            {"path": "src/App/App.csproj", "classification": "not_test"},
            {"path": "tests/A.Tests/A.Tests.csproj", "classification": "test"},
        ],
    }


def test_cli_reports_not_applicable_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = dnd.main([str(tmp_path)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"applicable": False, "projects": []}


def test_cli_reports_a_discovery_error_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / "One.sln", "")
    _write(tmp_path / "Two.sln", "")

    exit_code = dnd.main([str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err
