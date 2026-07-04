"""#810 — the Java lane of /build's static self-heal pass and PMD's Tier 1
/code-review registration.

This file guards only the Java tool facts: the diagnostic-only lane row in
tool-configs.md's Build-time lanes registry, the Tier 1 PMD entry (native
SARIF, language-conditional), ruleset resolution, the shipped
quickstart-wrapping default ruleset, the language-setup Java section, and
the warn-only dev-setup presence check. The mechanism itself (scoping, fix
loop, caps, ladder) is #811's and is guarded by
test_build_static_self_heal.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from skill_doc_helpers import (
    PLUGIN_ROOT,
    REPO_ROOT,
    grep,
    section_outside_code,
)

SAI_ROOT = PLUGIN_ROOT / "skills" / "static-analysis-integration"
TOOL_CONFIGS = SAI_ROOT / "references" / "tool-configs.md"
LANGUAGE_SETUP = SAI_ROOT / "references" / "language-setup.md"
SAI_SKILL = SAI_ROOT / "SKILL.md"
DEFAULT_RULESET = SAI_ROOT / "rulesets" / "pmd-quickstart.xml"
DEV_SETUP = REPO_ROOT / "scripts" / "dev-setup.sh"

PMD_NS = "http://pmd.sourceforge.net/ruleset/2.0.0"

GENERATED_OUTPUT_DIRS = ("target", "build", "out", ".gradle")


def _java_lane() -> str:
    return section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^### Java lane",
        boundary_pattern=r"^#{1,3} ",
        include_start_line=True,
    )


def _pmd_tier1_entry() -> str:
    return section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^### pmd",
        boundary_pattern=r"^#{1,3} [^#]",
        include_start_line=True,
    )


def _java_guide_section() -> str:
    return section_outside_code(
        LANGUAGE_SETUP.read_text(),
        r"^## Java$",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- Build-time lanes registry: the Java row


def test_java_lane_is_registered_and_diagnostic_only():
    lane = _flat(_java_lane())
    assert "No lane registered" not in lane
    assert "diagnostic-only" in lane
    assert "`*.java`" in lane


def test_java_lane_has_no_autofix_slot():
    lane = _flat(_java_lane()).lower()
    assert "autofix" in lane
    assert "none" in lane


def test_java_lane_invocation_is_scoped_via_file_list_json():
    lane = _java_lane()
    text = TOOL_CONFIGS.read_text()
    java_start = text.index("### Java lane")
    java_block = text[java_start:]
    for fragment in ("pmd check", "--file-list", "-f json", "--no-progress"):
        assert fragment in java_block, f"Java lane invocation missing: {fragment}"
    assert lane  # section extraction sanity


def test_java_lane_records_the_empty_file_set_contract():
    lane = _flat(_java_lane()).lower()
    assert "empty" in lane and "skip" in lane


def test_java_lane_records_exit_code_4_as_findings_not_failure():
    lane = _flat(_java_lane()).lower()
    assert "exit code 4" in lane or "exits 0 on clean, 4" in lane
    assert "4" in lane


def test_java_lane_probes_repo_local_install_before_path():
    lane = _java_lane()
    assert ".pmd/" in lane
    assert "command -v pmd" in lane
    assert lane.index(".pmd/") < lane.index("command -v pmd")


def test_java_lane_provider_list_is_pmd_then_checkstyle():
    lane = _java_lane()
    assert "checkstyle" in lane
    assert lane.lower().index("pmd") < lane.lower().index("checkstyle")


def test_checkstyle_qualification_is_recorded_as_tier1_native_sarif():
    lane = _flat(_java_lane())
    assert "10.3" in lane
    assert "SARIF" in lane


def test_spotbugs_stays_out_of_the_per_step_lane():
    lane = _flat(_java_lane())
    assert "SpotBugs" in lane
    assert "bytecode" in lane


# --- Tier 1 /code-review entry


def test_tool_configs_has_a_tier1_pmd_entry_with_native_sarif():
    entry = _pmd_tier1_entry()
    assert entry, "no `### pmd` Tier 1 entry in tool-configs.md"
    text = TOOL_CONFIGS.read_text()
    pmd_start = text.index("### pmd")
    tier2_start = text.index("## Tier 2")
    assert pmd_start < tier2_start, "pmd entry must sit in the Tier 1 section"
    entry_block = text[pmd_start:tier2_start]
    for fragment in ("pmd check", "-f sarif", "--no-progress"):
        assert fragment in entry_block, f"pmd SARIF invocation missing: {fragment}"


def test_tier1_pmd_entry_needs_no_adapter():
    assert grep(r"\*\*Adapter\*\*: none", _pmd_tier1_entry())


def test_tier1_pmd_entry_is_language_conditional():
    entry = _flat(_pmd_tier1_entry())
    assert ".java" in entry
    assert "only when" in entry.lower() or "language-conditional" in entry.lower()


def test_tier1_pmd_detection_is_repo_local_first():
    entry = _pmd_tier1_entry()
    assert ".pmd/" in entry
    assert "command -v pmd" in entry
    assert entry.index(".pmd/") < entry.index("command -v pmd")


def test_tier1_pmd_install_hint_names_the_repo_level_installer():
    assert "install-java-static-analysis.py" in _pmd_tier1_entry()


def test_skill_tier1_table_lists_pmd():
    tier1 = section_outside_code(
        SAI_SKILL.read_text(),
        r"^### Tier 1",
        boundary_pattern=r"^### ",
        include_start_line=True,
    )
    assert grep(r"^\| pmd \|", tier1), "SKILL.md Tier 1 table has no pmd row"
    assert "sarif" in tier1.lower()


# --- Ruleset resolution


def test_ruleset_resolution_is_documented_and_shared_by_both_invocations():
    entry = _flat(TOOL_CONFIGS.read_text())
    assert "pmd-ruleset.xml" in entry
    assert "quickstart" in entry
    assert "both" in entry.lower()


def test_custom_rulesets_carry_their_own_excludes():
    text = _flat(TOOL_CONFIGS.read_text()).lower()
    assert "exclude-pattern" in text
    assert "their own" in text or "its own" in text


def test_default_ruleset_ships_with_the_plugin():
    assert DEFAULT_RULESET.is_file(), f"missing shipped ruleset: {DEFAULT_RULESET}"


def test_default_ruleset_wraps_pmd_quickstart():
    root = ET.parse(DEFAULT_RULESET).getroot()
    assert root.tag == f"{{{PMD_NS}}}ruleset"
    refs = [rule.get("ref") for rule in root.findall(f"{{{PMD_NS}}}rule")]
    assert refs == ["rulesets/java/quickstart.xml"]


def test_default_ruleset_excludes_generated_output_dirs():
    root = ET.parse(DEFAULT_RULESET).getroot()
    patterns = [
        (node.text or "").strip()
        for node in root.findall(f"{{{PMD_NS}}}exclude-pattern")
    ]
    for directory in GENERATED_OUTPUT_DIRS:
        escaped = directory.replace(".", r"\.")
        assert any(
            f"/{escaped}/" in p for p in patterns
        ), f"no exclude-pattern for {directory}/ in {patterns}"


def _pmd_launcher():
    for launcher in (REPO_ROOT / ".pmd").glob("pmd-bin-*/bin/pmd"):
        if os.access(launcher, os.X_OK):
            return str(launcher)
    return shutil.which("pmd")


@pytest.mark.skipif(
    _pmd_launcher() is None or shutil.which("java") is None,
    reason="pmd (repo-local or PATH) and java are required for the fixture walk",
)
def test_full_repo_walk_reports_nothing_from_excluded_dirs(tmp_path):
    """A copied source under target/ produces no findings; the same source
    under src/ still does — proving the excludes trim noise, not rules."""
    violation = (
        "public class Sample {\n"
        "    public void run() {\n"
        "        try {\n"
        "            System.out.println(\"x\");\n"
        "        } catch (Exception e) {\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Sample.java").write_text(violation)
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "Sample.java").write_text(violation)

    result = subprocess.run(
        [
            _pmd_launcher(),
            "check",
            "-d",
            str(tmp_path),
            "-R",
            str(DEFAULT_RULESET),
            "-f",
            "json",
            "--no-progress",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 4), result.stderr
    report = json.loads(result.stdout)
    files_with_findings = [
        entry["filename"] for entry in report.get("files", []) if entry["violations"]
    ]
    assert not any(
        f"{os.sep}target{os.sep}" in name for name in files_with_findings
    ), f"excluded dir leaked findings: {files_with_findings}"
    assert any(
        f"{os.sep}src{os.sep}" in name for name in files_with_findings
    ), "fixture violation under src/ did not fire — excludes test is vacuous"


# --- Per-language setup guide: the Java section


def test_java_guide_section_is_registered():
    guide = _java_guide_section()
    assert guide
    assert "No lane registered" not in guide


def test_java_guide_covers_tools_and_roles():
    guide = _flat(_java_guide_section())
    assert "PMD" in guide
    assert "diagnostic-only" in guide


def test_java_guide_covers_repo_level_install():
    guide = _java_guide_section()
    assert "install-java-static-analysis.py" in guide
    assert ".pmd/" in guide


def test_java_guide_covers_configuration():
    assert "pmd-ruleset.xml" in _java_guide_section()


def test_java_guide_covers_verification_probes():
    guide = _java_guide_section()
    assert "command -v pmd" in guide
    assert "--version" in guide


def test_java_guide_covers_opt_out():
    assert "DEV_TEAM_STATIC_SELF_HEAL=off" in _java_guide_section()


def test_java_guide_covers_recognized_providers():
    guide = _flat(_java_guide_section())
    assert "checkstyle" in guide
    assert "SpotBugs" in guide


def test_java_guide_points_to_project_init():
    assert "/project-init" in _java_guide_section()


# --- dev-setup.sh presence check


def _dev_setup_pmd_block() -> str:
    text = DEV_SETUP.read_text()
    match = re.search(r"^if command -v pmd .*?^fi$", text, re.MULTILINE | re.DOTALL)
    assert match, "dev-setup.sh has no pmd presence check"
    return match.group(0)


def test_dev_setup_pmd_check_is_warn_only():
    block = _dev_setup_pmd_block()
    assert "warn" in block
    assert "note_failure" not in block, "pmd absence must not affect the exit code"
    assert "err " not in block


def test_dev_setup_pmd_check_names_the_installer():
    assert "install-java-static-analysis.py" in _dev_setup_pmd_block()
