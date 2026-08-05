"""Tests for scripts/coverage_discovery_dotnet.py (issue #1759, Slice 2).

The `dotnet` subprocess boundary (`shutil.which` + `subprocess.run`) is
mocked/stubbed throughout — no real .NET SDK is required to run this file,
keeping it inside the required `ci-local.sh`/pre-push pytest gate.
"""

import contextlib
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_dotnet as cdd
from coverage_config import DISCOVERY_NOT_APPLICABLE, TestClassification

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sln(repo_root: Path, name: str = "App.sln") -> None:
    write(repo_root / name, "Microsoft Visual Studio Solution File\n")


@contextlib.contextmanager
def stub_dotnet(project_paths, returncode: int = 0, stderr: str = ""):
    """Context manager stubbing `shutil.which("dotnet")` and the
    `dotnet sln <sln> list` subprocess call. `project_paths` becomes the
    stubbed stdout's project listing. Yields the `subprocess.run` mock so
    callers can assert on how it was invoked (e.g. its `env` kwarg)."""
    stdout = "Project(s)\n----------\n" + "\n".join(project_paths) + "\n"
    completed = subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )
    with (
        patch.object(cdd.shutil, "which", return_value="/usr/bin/dotnet"),
        patch.object(cdd.subprocess, "run", return_value=completed) as run_mock,
    ):
        yield run_mock


# ---------------------------------------------------------------------------
# Step 2.1 — classification scenarios
# ---------------------------------------------------------------------------


def test_inline_marker_any_attribute_order_is_test(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Version="17.8.0" Include="Microsoft.NET.Test.Sdk" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [{"path": csproj_rel, "classification": TestClassification.TEST}]


def test_bare_version_less_package_reference_cpm_is_test(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [{"path": csproj_rel, "classification": TestClassification.TEST}]


def test_inline_marker_case_insensitive_include_is_test(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="microsoft.net.test.sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [{"path": csproj_rel, "classification": TestClassification.TEST}]


def test_unconditioned_directory_build_props_inherited_is_test(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
</Project>
""",
    )
    write(
        tmp_path / "tests" / "Directory.Build.props",
        """<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [{"path": csproj_rel, "classification": TestClassification.TEST}]


def test_directory_build_props_at_solution_root_is_test(tmp_path):
    """Directory.Build.props two directories above the .csproj (i.e. at the
    solution root itself, unconditioned) is still walked and classified —
    proves the ancestor walk reaches the solution root, not just one level
    up."""
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
</Project>
""",
    )
    write(
        tmp_path / "Directory.Build.props",
        """<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [{"path": csproj_rel, "classification": TestClassification.TEST}]


def test_namespaced_package_reference_is_still_classified_test(tmp_path):
    """MSBuild's 2003 XML namespace (present in some hand-authored or
    older-tooling-generated .csproj files) must not defeat classification —
    locks in that `_local_name`'s namespace-stripping actually matters."""
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [{"path": csproj_rel, "classification": TestClassification.TEST}]


def test_conditioned_directory_build_props_reference_is_ambiguous(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
</Project>
""",
    )
    write(
        tmp_path / "tests" / "Directory.Build.props",
        """<Project>
  <ItemGroup Condition="'$(IsTestProject)'=='true'">
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [
        {"path": csproj_rel, "classification": TestClassification.AMBIGUOUS}
    ]


def test_no_reference_anywhere_is_not_test(tmp_path):
    sln(tmp_path)
    csproj_rel = "src/Foo/Foo.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
</Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [
        {"path": csproj_rel, "classification": TestClassification.NOT_TEST}
    ]


def test_malformed_csproj_is_discovery_error_not_crash(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(tmp_path / csproj_rel, "<Project><PropertyGroup></Project>")
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert csproj_rel in result["message"]


def test_malformed_directory_build_props_is_discovery_error_not_crash(tmp_path):
    sln(tmp_path)
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        tmp_path / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
</Project>
""",
    )
    write(tmp_path / "tests" / "Directory.Build.props", "<Project><PropertyGroup></Project>")
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "Directory.Build.props" in result["message"]


def test_symlinked_directory_build_props_escaping_solution_root_is_discovery_error(
    tmp_path,
):
    """A `Directory.Build.props` in an ancestor directory that is itself
    inside the solution root can still be a symlink pointing outside it —
    the containment check must resolve the file itself, not just confirm
    its containing directory is inside the solution (mirrors
    test_coverage_discovery_js.py's
    test_symlinked_package_json_escaping_repo_root_is_discovery_error)."""
    repo_root = tmp_path / "repo"
    csproj_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    write(
        repo_root / csproj_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
</Project>
""",
    )
    sln(repo_root)

    outside_props = tmp_path / "outside-Directory.Build.props"
    write(outside_props, "<Project><PropertyGroup></PropertyGroup></Project>")
    try:
        (repo_root / "tests" / "Directory.Build.props").symlink_to(outside_props)
    except OSError as exc:
        pytest.skip(f"symlinks not supported on this platform: {exc}")

    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(repo_root)

    assert result["signal"] == "error"
    assert "outside the solution root" in result["message"]


def test_csproj_with_doctype_is_discovery_error_not_parsed(tmp_path):
    sln(tmp_path)
    csproj_rel = "src/Foo/Foo.csproj"
    write(
        tmp_path / csproj_rel,
        """<?xml version="1.0"?>
<!DOCTYPE Project [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Project Sdk="Microsoft.NET.Sdk"></Project>
""",
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "DOCTYPE" in result["message"]


def test_utf16le_csproj_with_doctype_is_rejected(tmp_path):
    """expat auto-detects encoding from the byte stream and would happily
    parse a UTF-16LE `.csproj` even though the old guard only decoded the
    file as UTF-8 text — silently missing a DOCTYPE that's really there."""
    sln(tmp_path)
    csproj_rel = "src/Foo/Foo.csproj"
    text = (
        '<?xml version="1.0" encoding="utf-16"?>\n'
        '<!DOCTYPE Project [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        '<Project Sdk="Microsoft.NET.Sdk"></Project>\n'
    )
    (tmp_path / csproj_rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / csproj_rel).write_bytes(text.encode("utf-16le"))

    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "DOCTYPE" in result["message"]


def test_doctype_past_1024_byte_window_is_still_rejected(tmp_path):
    """The old guard only sniffed the first 1024 bytes — a DOCTYPE placed
    behind a long enough leading comment slipped past it entirely and went
    straight to `ET.parse`. The full-content screen must catch it regardless
    of position in the file."""
    sln(tmp_path)
    csproj_rel = "src/Foo/Foo.csproj"
    padding_comment = "<!-- " + ("x" * 2000) + " -->\n"
    write(
        tmp_path / csproj_rel,
        '<?xml version="1.0"?>\n'
        + padding_comment
        + '<!DOCTYPE Project [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        + '<Project Sdk="Microsoft.NET.Sdk"></Project>\n',
    )
    with stub_dotnet([csproj_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "DOCTYPE" in result["message"]


def test_multiple_projects_each_classified_independently(tmp_path):
    sln(tmp_path)
    test_rel = "tests/Foo.Tests/Foo.Tests.csproj"
    console_rel = "src/Foo/Foo.csproj"
    write(
        tmp_path / test_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
  </ItemGroup>
</Project>
""",
    )
    write(
        tmp_path / console_rel,
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType></PropertyGroup>
</Project>
""",
    )
    with stub_dotnet([test_rel, console_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result == [
        {"path": test_rel, "classification": TestClassification.TEST},
        {"path": console_rel, "classification": TestClassification.NOT_TEST},
    ]


# ---------------------------------------------------------------------------
# Step 2.2 — no-.sln, missing-dotnet, malformed-solution edge cases
# ---------------------------------------------------------------------------


def test_no_sln_present_reports_not_applicable(tmp_path):
    write(tmp_path / "src" / "Foo" / "Foo.csproj", "<Project></Project>")
    # No stubbing needed — the not-applicable check happens before any
    # dotnet lookup or subprocess call.
    result = cdd.discover_dotnet_projects(tmp_path)

    assert result is DISCOVERY_NOT_APPLICABLE


def test_multiple_sln_files_is_discovery_error_naming_both(tmp_path):
    sln(tmp_path, "App.sln")
    sln(tmp_path, "Other.sln")
    # No stubbing needed — the multiple-.sln check happens before any
    # dotnet lookup or subprocess call.
    result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "App.sln" in result["message"]
    assert "Other.sln" in result["message"]


def test_dotnet_not_on_path_is_tool_missing_discovery_error(tmp_path):
    sln(tmp_path)
    with patch.object(cdd.shutil, "which", return_value=None):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "dotnet" in result["message"].lower()
    assert "PATH" in result["message"]


def test_sln_list_nonzero_exit_is_discovery_error(tmp_path):
    sln(tmp_path)
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="solution file is corrupt"
    )
    with (
        patch.object(cdd.shutil, "which", return_value="/usr/bin/dotnet"),
        patch.object(cdd.subprocess, "run", return_value=completed),
    ):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "solution file is corrupt" in result["message"]


def test_sln_list_invokes_dotnet_with_invariant_locale_env(tmp_path):
    """A non-English-locale .NET SDK translates `dotnet sln list`'s header
    line, which would otherwise defeat `_parse_sln_list_output`'s exact
    English string match. Force invariant CLI output via
    DOTNET_CLI_UI_LANGUAGE."""
    sln(tmp_path)
    csproj_rel = "src/Foo/Foo.csproj"
    write(tmp_path / csproj_rel, "<Project></Project>")
    with stub_dotnet([csproj_rel]) as run_mock:
        cdd.discover_dotnet_projects(tmp_path)

    _, kwargs = run_mock.call_args
    assert kwargs["env"]["DOTNET_CLI_UI_LANGUAGE"] == "en"


def test_sln_list_passes_timeout(tmp_path):
    sln(tmp_path)
    csproj_rel = "src/Foo/Foo.csproj"
    write(tmp_path / csproj_rel, "<Project></Project>")
    with stub_dotnet([csproj_rel]) as run_mock:
        cdd.discover_dotnet_projects(tmp_path)

    _, kwargs = run_mock.call_args
    assert kwargs["timeout"] == 120


def test_sln_list_oserror_is_discovery_error_not_crash(tmp_path):
    sln(tmp_path)
    with (
        patch.object(cdd.shutil, "which", return_value="/usr/bin/dotnet"),
        patch.object(cdd.subprocess, "run", side_effect=OSError("dotnet crashed")),
    ):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "dotnet crashed" in result["message"]


def test_sln_list_timeout_is_discovery_error_not_crash(tmp_path):
    sln(tmp_path)
    with (
        patch.object(cdd.shutil, "which", return_value="/usr/bin/dotnet"),
        patch.object(
            cdd.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="dotnet sln list", timeout=120),
        ),
    ):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert "timed out" in result["message"].lower()


def test_sln_referencing_missing_project_path_is_discovery_error(tmp_path):
    sln(tmp_path)
    missing_rel = "tests/Ghost.Tests/Ghost.Tests.csproj"
    with stub_dotnet([missing_rel]):
        result = cdd.discover_dotnet_projects(tmp_path)

    assert result["signal"] == "error"
    assert missing_rel in result["message"]


def test_project_path_outside_repo_root_is_discovery_error(tmp_path):
    """A `.sln` entry containing `..` that resolves outside the repository
    root must be rejected before it is ever read — never classified, and
    never used to locate a Directory.Build.props outside the root."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sln(repo_root)
    outside_rel = "../outside/Outside.csproj"
    # Deliberately do NOT create anything at tmp_path / "outside" — if the
    # escape check fails to reject this path before reading it, this test
    # would either crash (FileNotFoundError) or silently misclassify.
    with stub_dotnet([outside_rel]):
        result = cdd.discover_dotnet_projects(repo_root)

    assert result["signal"] == "error"
    assert "Outside.csproj" in result["message"]
    assert not (tmp_path / "outside").exists()
