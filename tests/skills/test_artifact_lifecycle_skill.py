"""Tests for the /artifact-lifecycle skill and harness-audit integration.

Ported from tests/skills/artifact_lifecycle_skill_tests.bats (issue #674).
"""

from __future__ import annotations

from conftest import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "artifact-lifecycle" / "SKILL.md"
HARNESS_AUDIT = PLUGIN_ROOT / "skills" / "harness-audit" / "SKILL.md"
REGISTRY = PLUGIN_ROOT / "knowledge" / "agent-registry.md"


# ---------------------------------------------------------------------------
# Structural checks for artifact-lifecycle/SKILL.md
# ---------------------------------------------------------------------------


def test_artifact_lifecycle_skill_md_exists():
    assert SKILL.is_file()


def test_artifact_lifecycle_frontmatter_has_user_invocable_true():
    assert "user-invocable: true" in SKILL.read_text()


def test_artifact_lifecycle_references_metrics_artifact_usage_json():
    assert "artifact-usage.json" in SKILL.read_text()


def test_artifact_lifecycle_documents_ge_30_days_stale_threshold_inclusive():
    assert ">= 30" in SKILL.read_text()


def test_artifact_lifecycle_documents_ge_90_days_archive_threshold_inclusive():
    assert ">= 90" in SKILL.read_text()


def test_artifact_lifecycle_references_pinned_skills_exemption():
    assert "Pinned Skills" in SKILL.read_text()


def test_artifact_lifecycle_constrains_writes_to_project_claude_md_only_not_plugins_dev_team():
    assert grep(r"plugins/dev-team", SKILL.read_text(), ignore_case=True)


def test_artifact_lifecycle_describes_no_data_exit_message():
    assert grep(r"no usage data", SKILL.read_text(), ignore_case=True)


def test_artifact_lifecycle_describes_all_active_message():
    assert grep(
        r"all tracked artifacts are active", SKILL.read_text(), ignore_case=True
    )


# ---------------------------------------------------------------------------
# harness-audit integration
# ---------------------------------------------------------------------------


def test_harness_audit_references_artifact_usage_json_in_data_input_section():
    assert "artifact-usage.json" in HARNESS_AUDIT.read_text()


# ---------------------------------------------------------------------------
# Registry sync
# ---------------------------------------------------------------------------


def test_registry_artifact_lifecycle_is_listed_in_agent_registry_md():
    assert "artifact-lifecycle" in REGISTRY.read_text()


def test_registry_artifact_lifecycle_entry_has_a_skill_file_path():
    assert "skills/artifact-lifecycle/SKILL.md" in REGISTRY.read_text()
