"""The C# static-analysis lane: `dotnet format` is the build-time lane's
autofix slot, the Roslyn ErrorLog SARIF exported by the same `dotnet build`
that confirms GREEN is its diagnostic slot, and that ErrorLog is also a
Tier 1 `/code-review` source. Both ride the .NET SDK — no extra tool
install. Content guards over the two reference docs the lane registration
fills: static-analysis-integration's tool-configs.md (Tier 1 entry +
Build-time lanes row) and language-setup.md (C# section).
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section_outside_code

REFERENCES = PLUGIN_ROOT / "skills" / "static-analysis-integration" / "references"
TOOL_CONFIGS = REFERENCES / "tool-configs.md"
LANGUAGE_SETUP = REFERENCES / "language-setup.md"

INSTALL_HINT = (
    "dotnet — .NET SDK (C# build, format, ErrorLog SARIF). "
    "install: https://dotnet.microsoft.com/download"
)
ERRORLOG_FLAG = "/p:ErrorLog=results.sarif,version=2.1"


def _tier1_roslyn_section() -> str:
    tier1 = section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^## Tier 1",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )
    return section_outside_code(
        tier1,
        r"^### Roslyn ErrorLog",
        boundary_pattern=r"^### ",
        include_start_line=True,
    )


def _csharp_lane() -> str:
    registry = section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^## Build-time lanes",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )
    return section_outside_code(
        registry,
        r"^### C\# lane",
        boundary_pattern=r"^### ",
        include_start_line=True,
    )


def _guide_csharp_section() -> str:
    return section_outside_code(
        LANGUAGE_SETUP.read_text(),
        r"^## C\#$",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- Build-time lanes registry: the C# lane row (tool-configs.md)


def test_csharp_lane_is_registered():
    lane = _csharp_lane()
    assert "No lane registered" not in lane
    assert len(lane.splitlines()) > 3, "C# lane row looks empty"


def test_csharp_lane_covers_cs_files_with_the_sdk_probe():
    lane = _csharp_lane()
    assert "`.cs`" in lane
    assert "command -v dotnet" in lane


def test_dotnet_format_is_the_lanes_autofix_provider():
    flat = _flat(_csharp_lane()).lower()
    assert "autofix" in flat
    assert "dotnet format" in flat


def test_fix_pass_runs_whitespace_and_style_at_every_checkpoint():
    lane = _csharp_lane()
    assert grep(r"dotnet format whitespace .*--include", lane)
    assert grep(r"dotnet format style .*--include", lane)
    assert "every checkpoint" in _flat(lane)


def test_analyzers_subcommand_defers_to_the_slice_boundary_checkpoint():
    lane = _csharp_lane()
    assert grep(r"dotnet format analyzers .*--include", lane)
    assert "slice-boundary" in _flat(lane)


def test_verify_pass_uses_the_tools_diagnose_only_mode():
    assert "--verify-no-changes" in _csharp_lane()


def test_lane_is_never_invoked_with_an_empty_include_list():
    flat = _flat(_csharp_lane()).lower()
    assert "empty" in flat and "--include" in flat
    assert "never" in flat


def test_format_operates_on_a_project_or_solution_not_bare_paths():
    lane = _csharp_lane()
    assert "MSBuild project or solution" in _flat(lane)
    assert "<project-or-solution>" in lane


def test_severity_honors_the_projects_editorconfig_at_default_warn():
    lane = _csharp_lane()
    assert ".editorconfig" in lane
    assert "--severity warn" in lane


def test_diagnostic_slot_is_the_errorlog_sarif_riding_the_build():
    flat = _flat(_csharp_lane()).lower()
    assert "diagnostic" in flat
    assert "errorlog" in flat
    assert "dotnet build" in flat


def test_lane_defers_scoping_and_freshness_to_the_mechanism_reference():
    """Post-hoc filtering to the changed set and rebuild-on-stale are the
    mechanism's C# accommodation — the lane row points there instead of
    restating them."""
    assert "static-self-heal.md" in _csharp_lane()


def test_lane_lists_no_recognized_equivalent_providers():
    flat = _flat(_csharp_lane()).lower()
    assert "equivalent providers" in flat
    assert ".csproj" in flat


# --- Tier 1: Roslyn ErrorLog as a native-SARIF /code-review source


def test_tier1_registers_roslyn_errorlog_for_csharp():
    section = _tier1_roslyn_section()
    assert section, "no Roslyn ErrorLog subsection under Tier 1"
    assert "C#" in section


def test_errorlog_rides_the_existing_build_invocation():
    section = _tier1_roslyn_section()
    assert ERRORLOG_FLAG in section
    assert "dotnet build" in section


def test_errorlog_is_native_sarif_with_no_adapter():
    assert grep(r"\*\*Adapter\*\*: none", _tier1_roslyn_section())


def test_missing_sdk_degrades_with_the_standard_install_hint():
    section = _tier1_roslyn_section()
    assert INSTALL_HINT in section
    assert "command -v dotnet" in section


def test_sdk_probe_is_language_conditional():
    """A non-C# repo must never see a "dotnet missing" warning — probe and
    hint only when .cs files are in the target set."""
    flat = _flat(_tier1_roslyn_section())
    assert "language-conditional" in flat
    assert ".cs" in flat


def test_v1_scope_is_single_project_with_the_multi_project_gap_documented():
    flat = _flat(_tier1_roslyn_section())
    assert "single-project" in flat
    assert "Directory.Build.props" in flat
    assert "$(MSBuildProjectName)" in flat


def test_incremental_build_caveat_is_documented():
    flat = _flat(_tier1_roslyn_section())
    assert "incremental" in flat
    assert "every" in flat and "build invocation" in flat


def test_code_review_reuses_a_same_commit_sarif():
    flat = _flat(_tier1_roslyn_section())
    assert "HEAD" in flat
    assert "same-commit" in flat


def test_missing_sarif_degrades_never_a_pipeline_failure():
    assert "never a pipeline failure" in _flat(_tier1_roslyn_section())


def test_errorlog_needs_no_dedup_chain_slot():
    flat = _flat(_tier1_roslyn_section()).lower()
    assert "dedup" in flat
    assert "semgrep" in flat


# --- per-language setup guide: C# section (language-setup.md)


def test_guide_csharp_section_is_filled_in():
    section = _guide_csharp_section()
    assert "No lane registered" not in section
    assert len(section.splitlines()) > 3, "guide C# section looks empty"


def test_guide_names_both_tools_and_their_roles():
    flat = _flat(_guide_csharp_section())
    assert "dotnet format" in flat
    assert "autofix-capable" in flat
    assert "ErrorLog" in flat
    assert "diagnostic-only" in flat


def test_guide_repo_level_install_is_the_global_json_sdk_pin():
    flat = _flat(_guide_csharp_section()).lower()
    assert "global.json" in flat
    assert "nothing to install" in flat


def test_guide_lists_editorconfig_as_the_honored_config():
    assert ".editorconfig" in _guide_csharp_section()


def test_guide_gives_the_detection_probe():
    assert "command -v dotnet" in _guide_csharp_section()


def test_guide_documents_the_opt_out_toggle():
    assert "DEV_TEAM_STATIC_SELF_HEAL=off" in _guide_csharp_section()


def test_guide_points_to_project_init():
    assert "/project-init" in _guide_csharp_section()


def test_guide_lists_no_recognized_equivalent_providers():
    flat = _flat(_guide_csharp_section()).lower()
    assert "equivalent providers" in flat
    assert ".csproj" in flat
