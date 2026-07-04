"""#808 — the JS/TS static-analysis lane: oxlint registered as the
build-time autofix tool in the "Build-time lanes" registry, a SARIF-native
/code-review entry (the planned Tier 3 JSON adapter substituted per the
issue's version-pin instruction), the dedup chain ranking oxlint ahead of
the legacy JS tools, and the JS/TS section of the per-language setup guide.

Tool facts only — the mechanism (scoping, fix loop, attempt cap, provider
binding, granularity) is #811's and is guarded elsewhere.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, grep, section_outside_code

SAI = PLUGIN_ROOT / "skills" / "static-analysis-integration"
TOOL_CONFIGS = SAI / "references" / "tool-configs.md"
LANGUAGE_SETUP = SAI / "references" / "language-setup.md"
SAI_SKILL = SAI / "SKILL.md"

OXLINT_INSTALL_HINT = "oxlint — JS/TS linting. install: npm install --save-dev oxlint"


def _lane_section() -> str:
    registry = section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^## Build-time lanes",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )
    return section_outside_code(
        registry,
        r"^### JS/TS lane",
        boundary_pattern=r"^### ",
        include_start_line=True,
    )


def _oxlint_review_entry() -> str:
    return section_outside_code(
        TOOL_CONFIGS.read_text(),
        r"^### oxlint",
        boundary_pattern=r"^#{2,3} ",
        include_start_line=True,
    )


def _guide_js_section() -> str:
    return section_outside_code(
        LANGUAGE_SETUP.read_text(),
        r"^## JS/TS$",
        boundary_pattern=r"^## ",
        include_start_line=True,
    )


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- Build-time lanes registry — JS/TS lane row


def test_js_lane_is_registered_not_a_placeholder():
    lane = _lane_section()
    assert lane, "JS/TS lane section missing"
    assert "No lane registered" not in lane


def test_js_lane_partitions_all_six_extensions():
    lane = _lane_section()
    for ext in ("*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs", "*.cjs"):
        assert ext in lane, f"missing extension: {ext}"


def test_js_lane_fix_pass_is_oxlint_fix_on_scoped_files():
    assert "npx oxlint --fix <scoped-files>" in TOOL_CONFIGS.read_text()


def test_js_lane_verify_pass_is_oxlint_check_mode_on_scoped_files():
    assert "npx oxlint <scoped-files>" in TOOL_CONFIGS.read_text()


def test_js_lane_detection_probe_is_npx_no_install():
    assert "npx --no-install oxlint --version" in _lane_section()


def test_js_lane_probe_prefers_repo_local_over_global():
    s = _flat(_lane_section())
    assert "node_modules/.bin" in s
    assert "devDependency" in s


def test_js_lane_orders_providers_oxlint_then_biome_then_eslint():
    lane = _flat(_lane_section()).lower()
    i_ox, i_bi, i_es = (lane.index(t) for t in ("oxlint", "biome", "eslint"))
    assert i_ox < i_bi < i_es


def test_js_lane_names_oxlint_as_default_and_last_resort_provider():
    s = _flat(_lane_section()).lower()
    assert "default" in s
    assert "last-resort" in s


def test_js_lane_records_biome_as_full_speed():
    s = _flat(_lane_section()).lower()
    assert grep(r"biome.*full-speed", s)


def test_js_lane_binds_eslint_with_demotion_to_slice_boundary():
    s = _flat(_lane_section()).lower()
    assert "slice-boundary" in s
    assert grep(r"eslint[^.]*latency", s) or "item c" in s


def test_js_lane_tells_the_user_the_fast_default_exists_when_eslint_binds():
    s = _flat(_lane_section()).lower()
    assert grep(r"(tells|told).*(fast )?default", s)


def test_js_lane_documents_partial_autofix_residue_to_agent_same_attempt():
    s = _flat(_lane_section()).lower()
    assert "same attempt" in s


def test_js_lane_carries_the_install_hint_in_hint_format():
    assert OXLINT_INSTALL_HINT in _lane_section()


def test_js_lane_pins_oxlint_minimum_version_with_verify_note():
    s = _flat(_lane_section())
    assert ">= 1.0.0" in s
    assert grep(r"[Vv]erif\w+.*flag", _flat(_lane_section()))


# --- /code-review entry — SARIF-native, Tier 3 adapter substituted


def test_code_review_entry_invokes_oxlint_with_native_sarif_full_repo():
    assert "npx oxlint --format sarif ." in _oxlint_review_entry()


def test_code_review_entry_notes_the_tier3_json_adapter_substitution():
    s = _flat(_oxlint_review_entry()).lower()
    assert "native" in s and "sarif" in s
    assert grep(r"tier 3|json adapter", s)


def test_code_review_entry_needs_no_adapter():
    s = _flat(_oxlint_review_entry())
    assert grep(r"\*\*Adapter\*\*: none", s)


def test_code_review_entry_documents_the_rule_id_prefix():
    assert "oxlint.js.<rule-id>" in _oxlint_review_entry()


def test_code_review_entry_detects_via_npx_never_command_v():
    entry = _oxlint_review_entry()
    assert "npx --no-install oxlint --version" in entry
    assert "command -v oxlint" not in entry


def test_code_review_entry_carries_the_install_hint():
    assert OXLINT_INSTALL_HINT in _oxlint_review_entry()


def test_code_review_entry_pins_minimum_version_with_verify_note():
    s = _flat(_oxlint_review_entry())
    assert ">= 1.0.0" in s
    assert grep(r"[Vv]erif\w+", s)


def test_oxlint_lands_alongside_legacy_eslint_entry_not_replacing_it():
    text = TOOL_CONFIGS.read_text()
    assert grep(r"^### ESLint", text), "Tier 4 legacy ESLint entry must remain"
    assert grep(r"^### oxlint", text)


def test_drop_eslint_checklist_has_three_conditions_next_to_the_entry():
    text = TOOL_CONFIGS.read_text()
    checklist = section_outside_code(
        text,
        r"^#### When a project may drop ESLint",
        boundary_pattern=r"^#{2,4} ",
        include_start_line=True,
    )
    assert checklist, "drop-ESLint checklist missing"
    s = _flat(checklist)
    assert grep(r"^1\.", checklist) and grep(r"^2\.", checklist) and grep(r"^3\.", checklist)
    assert "eslint-plugin-oxlint" in s
    for element in ("supported-rules", "framework plugin", "dual run"):
        assert element.lower() in s.lower(), f"checklist condition missing: {element}"


# --- dedup chain (SKILL.md step 4)


def test_dedup_chain_ranks_oxlint_ahead_of_the_legacy_js_group():
    assert (
        "semgrep > gitleaks > trivy > hadolint > actionlint > ruff > mypy > oxlint"
        " > (legacy ESLint > tsc)" in SAI_SKILL.read_text()
    )


# --- per-language setup guide — JS/TS section


def test_guide_js_section_is_filled_not_a_placeholder():
    s = _guide_js_section()
    assert s, "JS/TS guide section missing"
    assert "No lane registered" not in s


def test_guide_js_section_names_oxlint_autofix_capable_with_partial_caveat():
    s = _flat(_guide_js_section()).lower()
    assert "oxlint" in s
    assert "autofix" in s
    assert grep(r"partial|subset", s)


def test_guide_js_section_keeps_eslint_as_the_optional_deep_pass():
    s = _flat(_guide_js_section()).lower()
    assert grep(r"eslint.*deep pass", s)


def test_guide_js_section_gives_the_repo_level_install_command():
    s = _flat(_guide_js_section())
    assert "npm install --save-dev oxlint" in s
    assert grep(r"[Nn]ever.*npm install -g", s)


def test_guide_js_section_documents_honored_config_files():
    s = _flat(_guide_js_section())
    assert ".oxlintrc.json" in s
    assert "eslint-plugin-oxlint" in s


def test_guide_js_section_gives_the_verification_probe():
    assert "npx --no-install oxlint --version" in _guide_js_section()


def test_guide_js_section_covers_the_opt_out_toggle():
    assert "DEV_TEAM_STATIC_SELF_HEAL=off" in _guide_js_section()


def test_guide_js_section_lists_the_provider_order_with_statuses():
    js = _guide_js_section()
    providers = _flat(js[js.index("Recognized equivalent providers") :]).lower()
    i_ox, i_bi, i_es = (providers.index(t) for t in ("oxlint", "biome", "eslint"))
    assert i_ox < i_bi < i_es
    assert "full-speed" in providers
    assert "slice-boundary" in providers


def test_guide_js_section_points_to_the_project_init_skill():
    assert "/project-init" in _guide_js_section()
