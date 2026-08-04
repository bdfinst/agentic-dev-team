"""Tests for discover_coverage_projects.py (#1759)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "coverage-baseline"
    / "scripts"
)
sys.path.insert(0, str(_SCRIPTS_DIR))

import discover_coverage_projects as dcp

_SKILL_MD = (
    Path(__file__).resolve().parents[2] / "skills" / "coverage-baseline" / "SKILL.md"
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_TEST_SDK_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />
  </ItemGroup>
</Project>
"""

_PLAIN_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
  </ItemGroup>
</Project>
"""


def _write_csproj(path: Path, *, is_test_project: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TEST_SDK_CSPROJ if is_test_project else _PLAIN_CSPROJ, encoding="utf-8")


def _make_solution(tmp_path: Path, project_specs: dict[str, bool]) -> Path:
    """Create a solution dir with a dummy .sln and one .csproj per entry in
    project_specs (relative path -> is_test_project). Returns the .sln path."""
    sln_dir = tmp_path / "solution"
    sln_dir.mkdir(parents=True, exist_ok=True)
    sln_path = sln_dir / "MySolution.sln"
    sln_path.write_text("Microsoft Visual Studio Solution File\n", encoding="utf-8")
    for rel_path, is_test in project_specs.items():
        _write_csproj(sln_dir / rel_path, is_test_project=is_test)
    return sln_path


def _sln_list_response(argv, project_paths: list[str]) -> subprocess.CompletedProcess:
    """Build the `dotnet sln <sln> list` stdout response shared by both fake
    subprocess runners below."""
    header = "Project(s)\n----------\n"
    body = "\n".join(project_paths)
    return subprocess.CompletedProcess(
        args=argv, returncode=0, stdout=header + body + "\n", stderr=""
    )


def _fake_sln_list_run(project_paths: list[str]):
    """Build a monkeypatch replacement for subprocess.run that answers
    `dotnet sln <sln> list` with the given project paths and fails any
    other dotnet invocation it doesn't recognize."""

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["dotnet", "sln"]:
            return _sln_list_response(argv, project_paths)
        raise AssertionError(f"unexpected subprocess invocation in this test: {argv}")

    return _fake_run


def _list_tests_output(test_count: int) -> str:
    header = "The following Tests are available:\n"
    body = "\n".join(f"    TestMethod{i}" for i in range(test_count))
    return header + body + "\n"


def _fake_dotnet_run(project_paths: list[str], list_tests_by_abs_path: dict[str, str]):
    """Like `_fake_sln_list_run`, but also answers
    `dotnet test <csproj> --list-tests` for the given absolute paths."""

    def _fake_run(argv, **kwargs):
        if argv[:2] == ["dotnet", "sln"]:
            return _sln_list_response(argv, project_paths)
        if argv[:2] == ["dotnet", "test"] and "--list-tests" in argv:
            csproj_arg = argv[2]
            if csproj_arg not in list_tests_by_abs_path:
                raise AssertionError(f"no --list-tests fixture for {csproj_arg}")
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout=list_tests_by_abs_path[csproj_arg], stderr=""
            )
        raise AssertionError(f"unexpected subprocess invocation in this test: {argv}")

    return _fake_run


# ---------------------------------------------------------------------------
# Step 1.1 — happy path (5-of-6, marker only) + empty case
# ---------------------------------------------------------------------------


def test_discovers_five_of_six_marker_only_no_path_filter(monkeypatch, tmp_path) -> None:
    # 5 of 6 projects carry the Test.Sdk marker; none live under a
    # conventional "test" directory naming — proves marker-only matching.
    specs = {
        "src/App/App.csproj": False,
        "src/App.Contracts/App.Contracts.csproj": True,
        "src/App.Fixtures/App.Fixtures.csproj": True,
        "src/App.Harness/App.Harness.csproj": True,
        "src/App.Probes/App.Probes.csproj": True,
        "src/App.Sandbox/App.Sandbox.csproj": True,
    }
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(
        dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys()))
    )

    discovered = dcp.discover_test_projects(sln_path)

    expected = sorted(p for p, is_test in specs.items() if is_test)
    assert sorted(discovered) == expected


def test_no_test_projects_returns_empty_list(monkeypatch, tmp_path) -> None:
    specs = {
        "src/App/App.csproj": False,
        "src/App.Lib/App.Lib.csproj": False,
    }
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(
        dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys()))
    )

    discovered = dcp.discover_test_projects(sln_path)

    assert discovered == []


def test_main_exits_zero_with_empty_projects_list(monkeypatch, tmp_path, capsys) -> None:
    specs = {"src/App/App.csproj": False}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(
        dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys()))
    )

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["projects"] == []


def test_parse_sln_list_output_skips_header_and_separator() -> None:
    output = (
        "Project(s)\n"
        "----------\n"
        "src/App/App.csproj\n"
        "tests/App.Tests/App.Tests.csproj\n"
    )
    assert dcp.parse_sln_list_output(output) == [
        "src/App/App.csproj",
        "tests/App.Tests/App.Tests.csproj",
    ]


def test_parse_sln_list_output_normalizes_backslashes() -> None:
    output = "Project(s)\n----------\nsrc\\App\\App.csproj\n"
    assert dcp.parse_sln_list_output(output) == ["src/App/App.csproj"]


# ---------------------------------------------------------------------------
# Step 1.2 — known_projects baseline + exclusions; hard-fail on new projects
# ---------------------------------------------------------------------------


def test_absent_config_self_bootstraps(monkeypatch, tmp_path) -> None:
    specs = {
        "src/App/App.csproj": False,
        "tests/App.Tests/App.Tests.csproj": True,
        "tests/App.More/App.More.csproj": True,
    }
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    assert not config_path.exists()

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 0
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert sorted(written["known_projects"]) == sorted(
        p for p, is_test in specs.items() if is_test
    )
    assert written["exclusions"] == []


def test_newly_appeared_project_not_in_either_list_is_hard_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    specs = {
        "tests/A.Tests/A.Tests.csproj": True,
        "tests/B.Tests/B.Tests.csproj": True,
        "tests/C.Tests/C.Tests.csproj": True,
        "tests/D.Tests/D.Tests.csproj": True,
        "tests/E.Tests/E.Tests.csproj": True,
        "tests/F.Tests/F.Tests.csproj": True,  # the 6th, newly-appeared project
    }
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    known_five = sorted(p for p in specs if p != "tests/F.Tests/F.Tests.csproj")
    dcp.write_config(config_path, known_five, [])

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 1
    assert "F.Tests/F.Tests.csproj" in capsys.readouterr().err


def test_already_known_project_included_with_no_config_change(
    monkeypatch, tmp_path
) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    dcp.write_config(config_path, ["tests/App.Tests/App.Tests.csproj"], [])
    before = config_path.read_text(encoding="utf-8")

    result = dcp.discover(sln_path)

    assert result["projects"] == ["tests/App.Tests/App.Tests.csproj"]
    assert config_path.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# Step 1.3 — malformed-input hard failures (named path, never a traceback)
# ---------------------------------------------------------------------------


def test_malformed_config_json_is_hard_failure_naming_the_path(
    monkeypatch, tmp_path, capsys
) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    config_path.write_text("{not valid json", encoding="utf-8")

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert str(config_path) in err
    assert "Traceback" not in err


def test_missing_sln_path_is_hard_failure_naming_the_path(tmp_path, capsys) -> None:
    missing_sln = tmp_path / "DoesNotExist.sln"

    exit_code = dcp.main([str(missing_sln)])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert str(missing_sln) in err
    assert "Traceback" not in err


def test_config_top_level_not_object_is_hard_failure(monkeypatch, tmp_path, capsys) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    config_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    exit_code = dcp.main([str(sln_path)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert str(config_path) in err
    assert "Traceback" not in err


def test_config_exclusion_entry_missing_path_is_hard_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    config_path.write_text(
        json.dumps({"known_projects": [], "exclusions": [{"reason": "no path field"}]}),
        encoding="utf-8",
    )

    exit_code = dcp.main([str(sln_path)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert str(config_path) in err
    assert "Traceback" not in err


def test_config_exclusion_entry_non_string_path_is_hard_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    config_path.write_text(
        json.dumps(
            {"known_projects": [], "exclusions": [{"path": 5, "excluded_test_count": 3}]}
        ),
        encoding="utf-8",
    )

    exit_code = dcp.main([str(sln_path)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert str(config_path) in err
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Step 1.3b — path containment: reject absolute/traversal exclusion paths
# ---------------------------------------------------------------------------


def test_exclusion_absolute_path_is_hard_failure(monkeypatch, tmp_path, capsys) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    escape_path = str(tmp_path / "outside" / "Evil.csproj")
    dcp.write_config(
        config_path,
        ["tests/App.Tests/App.Tests.csproj"],
        [{"path": escape_path, "reason": "abs path attempt", "excluded_test_count": 1}],
    )

    exit_code = dcp.main([str(sln_path)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Traceback" not in err


def test_exclusion_path_traversal_is_hard_failure(monkeypatch, tmp_path, capsys) -> None:
    specs = {"tests/App.Tests/App.Tests.csproj": True}
    sln_path = _make_solution(tmp_path, specs)
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    dcp.write_config(
        config_path,
        ["tests/App.Tests/App.Tests.csproj"],
        [
            {
                "path": "../../etc/Evil.csproj",
                "reason": "traversal attempt",
                "excluded_test_count": 1,
            }
        ],
    )

    exit_code = dcp.main([str(sln_path)])

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Step 1.3c — argument injection: reject option-like paths before dotnet
# ---------------------------------------------------------------------------


def test_sln_path_starting_with_dash_is_rejected() -> None:
    with pytest.raises(dcp.DiscoveryError, match="CLI option"):
        dcp.run_dotnet_sln_list(Path("-weird.sln"))


def test_project_path_starting_with_dash_is_rejected() -> None:
    with pytest.raises(dcp.DiscoveryError, match="CLI option"):
        dcp.count_test_methods(Path("-weird/App.Tests.csproj"))


# ---------------------------------------------------------------------------
# Step 1.4 — non-circular stale-exclusion warning via test-count drift
# ---------------------------------------------------------------------------


def test_stale_exclusion_entry_produces_warning(monkeypatch, tmp_path, capsys) -> None:
    specs = {
        "tests/App.Tests/App.Tests.csproj": True,
        "tests/App.Legacy.Tests/App.Legacy.Tests.csproj": True,
    }
    sln_path = _make_solution(tmp_path, specs)
    excluded_rel = "tests/App.Legacy.Tests/App.Legacy.Tests.csproj"
    excluded_abs = str(sln_path.parent / excluded_rel)
    monkeypatch.setattr(
        dcp.subprocess,
        "run",
        _fake_dotnet_run(list(specs.keys()), {excluded_abs: _list_tests_output(5)}),
    )
    config_path = dcp.config_path_for(sln_path)
    dcp.write_config(
        config_path,
        ["tests/App.Tests/App.Tests.csproj"],
        [{"path": excluded_rel, "reason": "flaky, being rewritten", "excluded_test_count": 3}],
    )

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "stale" in captured.err.lower()
    assert excluded_rel in captured.err
    payload = json.loads(captured.out)
    assert payload["projects"] == ["tests/App.Tests/App.Tests.csproj"]


def test_non_stale_exclusion_produces_no_warning(monkeypatch, tmp_path, capsys) -> None:
    specs = {
        "tests/App.Tests/App.Tests.csproj": True,
        "tests/App.Legacy.Tests/App.Legacy.Tests.csproj": True,
    }
    sln_path = _make_solution(tmp_path, specs)
    excluded_rel = "tests/App.Legacy.Tests/App.Legacy.Tests.csproj"
    excluded_abs = str(sln_path.parent / excluded_rel)
    monkeypatch.setattr(
        dcp.subprocess,
        "run",
        _fake_dotnet_run(list(specs.keys()), {excluded_abs: _list_tests_output(3)}),
    )
    config_path = dcp.config_path_for(sln_path)
    dcp.write_config(
        config_path,
        ["tests/App.Tests/App.Tests.csproj"],
        [{"path": excluded_rel, "reason": "flaky, being rewritten", "excluded_test_count": 3}],
    )

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "stale" not in captured.err.lower()
    payload = json.loads(captured.out)
    assert payload["projects"] == ["tests/App.Tests/App.Tests.csproj"]


def test_missing_excluded_test_count_emits_skip_warning(monkeypatch, tmp_path, capsys) -> None:
    specs = {
        "tests/App.Tests/App.Tests.csproj": True,
        "tests/App.Legacy.Tests/App.Legacy.Tests.csproj": True,
    }
    sln_path = _make_solution(tmp_path, specs)
    excluded_rel = "tests/App.Legacy.Tests/App.Legacy.Tests.csproj"
    # No --list-tests fixture provided — `dotnet test` must never be invoked
    # for this entry, since it has no `excluded_test_count` to compare against.
    monkeypatch.setattr(dcp.subprocess, "run", _fake_sln_list_run(list(specs.keys())))
    config_path = dcp.config_path_for(sln_path)
    dcp.write_config(
        config_path,
        ["tests/App.Tests/App.Tests.csproj"],
        [{"path": excluded_rel, "reason": "flaky, being rewritten"}],
    )

    exit_code = dcp.main([str(sln_path)])

    assert exit_code == 0
    err = capsys.readouterr().err
    assert "skipped" in err.lower()
    assert excluded_rel in err


# ---------------------------------------------------------------------------
# Step 1.5 — wiring: discovery script is never invoked for non-.sln rows
# ---------------------------------------------------------------------------


def test_non_dotnet_stack_unaffected() -> None:
    content = _SKILL_MD.read_text(encoding="utf-8")
    manifest_rows = [
        line
        for line in content.splitlines()
        if line.strip().startswith("|") and not re.fullmatch(r"\|[\s:|-]+\|", line.strip())
    ]
    header, *rows = manifest_rows
    assert "Manifest" in header

    sln_rows = [row for row in rows if ".sln" in row]
    assert len(sln_rows) == 1, "expected exactly one .sln/.csproj manifest row"
    assert "discover_coverage_projects.py" in sln_rows[0]

    other_rows = [row for row in rows if row not in sln_rows]
    assert len(other_rows) >= 5, "expected the other stacks' rows to remain"
    for row in other_rows:
        assert "discover_coverage_projects.py" not in row
