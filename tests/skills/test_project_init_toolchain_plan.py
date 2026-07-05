"""#822 — project-init confirms a three-column plan before writing anything
and installs only the missing slots' defaults, repo-level, per the recorded
#807-#811 decisions; it ends with each lane's registry probe. Documentation
gate over the skill prose and the language-setup guide's cross-links.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md"
GUIDE = (
    PLUGIN_ROOT
    / "skills"
    / "static-analysis-integration"
    / "references"
    / "language-setup.md"
)


def _text() -> str:
    return SKILL.read_text()


def _plan_section() -> str:
    return section(_text(), r"^### Step 3: Confirm the three-column plan")


def _install_section() -> str:
    return section(_text(), r"^### Step 4: Install missing tools")


def _verify_section() -> str:
    return section(_text(), r"^### Step 5: Verify")


# --- three-column plan + confirmation gate -----------------------------------


def test_plan_names_all_three_columns():
    s = _plan_section()
    for column in (
        "Found and keeping",
        "Missing and will add",
        "Found but can't participate",
    ):
        assert column in s, f"missing plan column: {column}"


def test_nothing_is_written_or_installed_before_the_user_confirms():
    s = _plan_section()
    assert grep(r"confirm", s, ignore_case=True)
    assert grep(r"before any file is written or any install runs", s)


def test_only_the_missing_and_will_add_column_installs_anything():
    assert grep(r"Only this column installs", _plan_section(), ignore_case=True)


def test_non_participating_tools_carry_a_reason_and_the_default_alongside():
    s = _plan_section()
    assert grep(r"reason stated", s, ignore_case=True)
    assert grep(r"never a\s+silent\s+replacement", s, ignore_case=True)


def test_existing_configs_are_never_overwritten():
    s = _plan_section()
    assert grep(r"never overwritten", s, ignore_case=True)
    assert "eslint.config.js" in s


# --- per-language installs (repo-level, per #807-#810) ------------------------


def test_python_installs_ruff_and_mypy_into_the_projects_dev_dependency_mechanism():
    s = _install_section()
    for needle in ("ruff", "mypy", "requirements-dev.txt", "pyproject.toml"):
        assert needle in s, f"missing Python install element: {needle}"


def test_python_adds_pytest_only_when_no_test_runner_is_present():
    assert grep(r"pytest.*no test runner", _install_section(), ignore_case=True)


def test_js_existing_projects_get_oxlint_as_a_devdependency():
    assert grep(r"npm install --save-dev oxlint", _install_section())


def test_csharp_installs_nothing_and_honors_a_global_json_pin():
    s = _install_section()
    assert grep(r"nothing to install", s, ignore_case=True)
    assert "global.json" in s
    assert "dotnet format" in s


def test_java_wraps_the_pinned_pmd_installer_script():
    s = _install_section()
    assert "install-java-static-analysis.py" in s
    assert ".pmd/" in s
    assert ".gitignore" in s


# Capability tools are user/system-level by nature (per capability-tools.md's
# "Install-level honesty" section) — there is no repo-local install for a
# general-purpose CLI like semgrep, codegraph, or graphify, so their fallback
# chains legitimately use pipx/--user. Only fenced blocks that install one of
# these known capability tools are exempt; lane tools (Python/JS/TS/C#/Java)
# must still always install repo-level.
_USER_LEVEL_CAPABILITY_TOOL_MARKERS = ("semgrep", "graphifyy", "codegraph")


def test_no_user_level_or_global_install_commands_in_any_code_block():
    fenced = re.findall(r"^```.*?\n(.*?)^```", _text(), re.MULTILINE | re.DOTALL)
    assert fenced, "expected fenced install commands in the skill body"
    for block in fenced:
        if any(marker in block for marker in _USER_LEVEL_CAPABILITY_TOOL_MARKERS):
            continue
        assert "--user" not in block, f"user-level install found: {block!r}"
        assert "pipx" not in block, f"pipx install found: {block!r}"
        assert not grep(r"npm install (-g|--global)", block), (
            f"global npm install found: {block!r}"
        )


# --- post-install verification (per #811's lane registry) ---------------------


def test_verify_runs_every_lanes_registry_probe():
    s = _verify_section()
    for probe in (
        "command -v ruff",
        "command -v mypy",
        "npx --no-install oxlint --version",
        "command -v dotnet",
        "command -v pmd",
    ):
        assert probe in s, f"missing lane probe: {probe}"


def test_java_probe_checks_the_repo_local_launcher_before_path():
    assert ".pmd/" in _verify_section()


def test_verify_reports_which_provider_each_slot_bound():
    assert grep(r"which provider each\s+slot bound", _verify_section())


# --- guide cross-links (coordinated with #811) --------------------------------


def test_every_language_setup_section_points_at_project_init():
    guide = GUIDE.read_text()
    for lang in ("Python", "JS/TS", "C#", "Java"):
        body = section(guide, rf"^## {re.escape(lang)}$", boundary_pattern=r"^## ")
        assert "/project-init" in body, f"{lang} section lacks a /project-init pointer"


def test_guide_has_no_stale_js_project_init_reference():
    assert "js-project-init" not in GUIDE.read_text()
