"""The Python static-analysis lane: Ruff (autofix-capable, Tier 1 native
SARIF) + mypy (diagnostic-only, Tier 3 JSON adapter), replacing the retired
Tier 4 pylint entry outright.

Content gates over the static-analysis-integration skill's docs, the
build-time lane registry row, the per-language setup guide, and this repo's
own dev toolchain. Mechanism (scoping, the shared fix loop, the attempt cap,
provider-binding semantics) is the build skill's — asserted by
test_build_static_self_heal.py, never restated here.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, REPO_ROOT, grep, section_outside_code

SAI = PLUGIN_ROOT / "skills" / "static-analysis-integration"
SAI_SKILL = SAI / "SKILL.md"
TOOL_CONFIGS = SAI / "references" / "tool-configs.md"
LANGUAGE_SETUP = SAI / "references" / "language-setup.md"
MYPY_ADAPTER = SAI / "adapters" / "mypy-adapter.py"
REQUIREMENTS_DEV = REPO_ROOT / "requirements-dev.txt"
DEV_SETUP = REPO_ROOT / "scripts" / "dev-setup.sh"

RUFF_INSTALL_HINT = (
    "ruff — Python lint + autofix. "
    "install: python3 -m pip install ruff (project venv / dev requirements)"
)
MYPY_INSTALL_HINT = (
    "mypy — Python type checking. "
    "install: python3 -m pip install mypy (project venv / dev requirements)"
)
FINAL_DEDUP_CHAIN = (
    "semgrep > gitleaks > trivy > hadolint > actionlint "
    "> ruff > mypy > oxlint > (legacy ESLint > tsc)"
)


def _skill_text() -> str:
    return SAI_SKILL.read_text()


def _configs_text() -> str:
    return TOOL_CONFIGS.read_text()


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _ruff_entry() -> str:
    return section_outside_code(
        _configs_text(), r"^### ruff$", boundary_pattern=r"^#{2,3} ",
        include_start_line=True,
    )


def _mypy_entry() -> str:
    return section_outside_code(
        _configs_text(), r"^### mypy$", boundary_pattern=r"^#{2,3} ",
        include_start_line=True,
    )


def _python_lane() -> str:
    return section_outside_code(
        _configs_text(), r"^### Python lane$", boundary_pattern=r"^#{2,3} ",
        include_start_line=False,
    )


def _python_guide() -> str:
    return section_outside_code(
        LANGUAGE_SETUP.read_text(), r"^## Python$", boundary_pattern=r"^## ",
        include_start_line=False,
    )


# --- Ruff: Tier 1 native-SARIF source for /code-review


def test_skill_tier1_table_lists_ruff():
    tier1 = section_outside_code(
        _skill_text(), r"^### Tier 1", boundary_pattern=r"^### ",
        include_start_line=True,
    )
    assert grep(r"^\|\s*ruff\s*\|", tier1)


def test_ruff_code_review_invocation_is_full_repo_native_sarif():
    for text in (_skill_text(), _configs_text()):
        assert "ruff check --output-format sarif ." in text


def test_ruff_entry_documents_the_sarif_minimum_version():
    assert "0.3.1" in _ruff_entry()


def test_ruff_entry_carries_repo_level_install_hint_and_detection():
    entry = _flat(_ruff_entry())
    assert RUFF_INSTALL_HINT in entry
    assert "command -v ruff" in entry


def test_ruff_presence_is_language_conditional_never_required():
    """A Python linter must not hard-fail install in a repo with no Python:
    ruff is dispatched (and its hint surfaced) only when .py files are in
    the target set, and never carries the [REQUIRED] prefix."""
    entry = _flat(_ruff_entry())
    assert "language-conditional" in entry
    assert grep(r"\.py.*files.*target set", entry)
    assert grep(r"never.*\[REQUIRED\]", entry)


def test_ruff_honors_project_config_with_no_plugin_curated_rule_set():
    entry = _flat(_ruff_entry())
    assert "ruff.toml" in entry
    assert "pyproject.toml" in entry
    assert "no curated rule set" in entry or "pins no curated" in entry


# --- mypy: Tier 3 JSON adapter for /code-review


def test_skill_tier3_registers_the_mypy_adapter():
    tier3 = section_outside_code(
        _skill_text(), r"^### Tier 3", boundary_pattern=r"^### ",
        include_start_line=True,
    )
    flat = _flat(tier3)
    assert "adapters/mypy-adapter.py" in flat
    assert "mypy --output json" in flat


def test_mypy_entry_documents_minimum_version_and_degrade_path():
    entry = _flat(_mypy_entry())
    assert "1.11" in entry
    assert "skip-with-warning" in entry
    assert "never a pipeline failure" in entry


def test_mypy_entry_carries_repo_level_install_hint_and_detection():
    entry = _flat(_mypy_entry())
    assert MYPY_INSTALL_HINT in entry
    assert "command -v mypy" in entry


def test_mypy_entry_maps_rule_ids_into_the_mypy_python_namespace():
    assert "mypy.python." in _flat(_mypy_entry())


def test_mypy_adapter_exists_next_to_the_tier3_precedent():
    assert MYPY_ADAPTER.is_file()


# --- pylint: retired outright, replaced by Ruff


def test_pylint_is_gone_from_the_skill_and_tool_configs():
    assert "pylint" not in _skill_text().lower()
    assert "pylint" not in _configs_text().lower()


def test_dedup_chain_matches_the_final_shared_chain():
    """Tier rank order preserved: Tier 1 tail gains ruff, Tier 3 adds
    mypy/oxlint above the legacy group; pylint is gone."""
    assert FINAL_DEDUP_CHAIN in _skill_text()


# --- Build-time lanes registry: the Python row


def test_python_lane_is_registered_not_a_placeholder():
    assert "No lane registered" not in _python_lane()


def test_python_lane_covers_py_extensions():
    assert grep(r"`\.py`", _python_lane())


def test_python_lane_autofix_slot_runs_ruff_fix_then_verify():
    lane = _flat(_python_lane())
    assert "ruff check --fix <scoped-files>" in lane
    assert "ruff check <scoped-files>" in lane


def test_python_lane_diagnostic_slot_is_mypy_with_scoped_follow_imports():
    lane = _flat(_python_lane())
    assert "mypy --follow-imports=silent <scoped-files>" in lane
    assert "diagnostic-only" in lane


def test_python_lane_carries_both_detection_probes():
    lane = _flat(_python_lane())
    assert "command -v ruff" in lane
    assert "command -v mypy" in lane


def test_python_lane_autofix_providers_include_black_flake8_pair_with_caveat():
    lane = _flat(_python_lane())
    assert "black" in lane
    assert "flake8" in lane
    assert "combined pair" in lane
    assert "partial mapping" in lane


def test_python_lane_diagnostic_providers_gate_pyright_on_an_adapter():
    lane = _flat(_python_lane())
    assert "pyright" in lane
    assert "gated" in lane
    assert "40 LOC" in lane


def test_python_lane_defers_mechanism_instead_of_restating_it():
    """The attempt cap, scoping commands, and binding semantics live in the
    build skill's mechanism reference — the lane row must not restate them."""
    lane = _flat(_python_lane())
    for restated in ("2-attempt", "git diff --name-only", "attempt cap"):
        assert restated not in lane


# --- per-language setup guide: the Python section


def test_guide_python_section_is_filled_in():
    assert "No lane registered" not in _python_guide()


def test_guide_python_section_states_tools_and_roles():
    flat = _flat(_python_guide())
    assert "autofix-capable" in flat
    assert "diagnostic-only" in flat


def test_guide_python_section_recommends_repo_level_install_only():
    flat = _flat(_python_guide())
    assert "venv" in flat
    assert grep(r"[Nn]ever.*(--user|user-level|global)", flat)


def test_guide_python_section_names_the_honored_config_files():
    flat = _flat(_python_guide())
    assert "ruff.toml" in flat
    assert "pyproject.toml" in flat


def test_guide_python_section_gives_the_verification_probes():
    flat = _flat(_python_guide())
    assert "command -v ruff" in flat
    assert "command -v mypy" in flat


def test_guide_python_section_documents_the_opt_out():
    assert "DEV_TEAM_STATIC_SELF_HEAL=off" in _python_guide()


def test_guide_python_section_lists_recognized_equivalent_providers():
    flat = _flat(_python_guide())
    assert "black" in flat and "flake8" in flat
    assert "pyright" in flat
    assert "partial mapping" in flat


def test_guide_python_section_points_to_project_init():
    assert "/project-init" in _python_guide()


# --- this repo's own dev toolchain


def test_requirements_dev_declares_ruff_and_mypy():
    text = REQUIREMENTS_DEV.read_text()
    assert grep(r"^ruff", text)
    assert grep(r"^mypy", text)


def test_dev_setup_verifying_section_probes_ruff_and_mypy():
    text = DEV_SETUP.read_text()
    assert "ruff" in text
    assert "mypy" in text
