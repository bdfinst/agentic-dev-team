"""Content test: /setup scaffolds the lint config and /upgrade refreshes it.

The behavior (gating, stamp, check, refresh) is covered by fixtures in
plugins/dev-team/tests/scripts/test_scaffold_lint_config.py. This file only
pins that the two skills call the script through ${CLAUDE_PLUGIN_ROOT} with
the flags it accepts.
"""

from __future__ import annotations

import re
import sys

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import scaffold_lint_config as scaffold

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
SETUP = (PLUGIN / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")
UPGRADE = (PLUGIN / "skills" / "upgrade" / "SKILL.md").read_text(encoding="utf-8")
SCRIPT_CALL = '"${CLAUDE_PLUGIN_ROOT}/scripts/scaffold_lint_config.py"'


def _section(text: str, heading: str, next_heading: str) -> str:
    match = re.search(
        rf"^{heading}.*?(?=^{next_heading})", text, re.DOTALL | re.MULTILINE
    )
    assert match, f"no section {heading!r} before {next_heading!r}"
    return match.group(0)


def test_script_the_skills_call_exists_and_is_executable():
    script = PLUGIN / "scripts" / "scaffold_lint_config.py"
    assert script.is_file()
    assert script.stat().st_mode & 0o111


def test_setup_scaffolds_only_for_a_js_ts_stack_via_the_plugin_root():
    step = _section(SETUP, r"### 7b\.", r"### 8\.")
    assert SCRIPT_CALL in step
    assert '--project "$PWD"' in step
    assert "JavaScript or TypeScript" in step
    assert ".claude/project-stack.json" in step


def test_setup_prints_files_mode_and_next_step_and_never_edits_user_config():
    step = _section(SETUP, r"### 7b\.", r"### 8\.")
    for needle in ("written", "skipped", "typed", "untyped", "DEVTEAM_POST_LINT=1"):
        assert needle in step, needle
    assert "never edits" in step
    assert "eslint.config.js" in step and "tsconfig.json" in step


def test_setup_skips_the_scaffold_under_dry_run_and_reports_it():
    step = _section(SETUP, r"### 7b\.", r"### 8\.")
    assert "--dry-run" in step
    assert "Lint config:" in SETUP.split("### 12. Report", 1)[1]


def test_upgrade_runs_check_lists_stale_edited_and_offers_refresh_of_unedited():
    step = _section(UPGRADE, r"### 5\.", r"## Notes")
    assert f"{SCRIPT_CALL} --project" in step
    assert "--check" in step and "--refresh" in step
    assert "stale-edited" in step and "stale-unedited" in step
    assert "diff" in step
    assert "does not compare stamps" in step


def test_upgrade_reports_every_status_the_script_can_emit():
    step = _section(UPGRADE, r"### 5\.", r"## Notes")
    statuses = {
        value for name, value in vars(scaffold).items() if name.startswith("STATUS_")
    }
    missing = {status for status in statuses if f"`{status}`" not in step}
    assert not missing
