"""Content-guard: setup/SKILL.md's Step 11 downstream `.gitignore` block
targets the `.claude/`-scoped and `.dev-team-reports/` domains, and the
stale `DEV_TEAM_TASK_METRICS`/`DEV_TEAM_REPORTS` path-override claim is
corrected (Slice 6, Step 6.3, plan opt-in-metrics-and-claude-scoped-artifacts.md).

Also asserts the idempotence marker was bumped (not left byte-identical to
the pre-#1406 marker) so an already-provisioned downstream project's
`/setup` re-run picks up the new `.dev-team-reports/` line instead of
silently reporting "already covered".
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

SKILL = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")


def test_step_11_appended_block_covers_claude_scoped_domains():
    assert ".claude/memory/" in SKILL
    assert ".claude/metrics/" in SKILL
    assert ".claude/plans/" in SKILL


def test_step_11_appended_block_covers_dev_team_reports():
    assert ".dev-team-reports/" in SKILL
    assert ".claude/reports/" not in SKILL


def test_step_11_marker_was_bumped_for_idempotent_reprovisioning():
    # The pre-#1406 marker was the bare string below with no trailing
    # annotation. If it's still present byte-for-byte as its own line, a
    # downstream project provisioned before this change would see
    # grep -qF match and skip re-appending the new .dev-team-reports/ line.
    old_marker_line = '"# dev-team workflow runtime artifacts"'
    assert old_marker_line not in SKILL
    assert "#1406" in SKILL


def test_no_path_override_claim_remains_for_either_env_var():
    assert "relocated `reports/` via `DEV_TEAM_REPORTS`" not in SKILL
    assert "relocated `metrics/` via" not in SKILL
    # Both env vars are described as on/off opt-outs only, never a path override.
    # Assertions use collapsed whitespace since the prose wraps across lines.
    collapsed = " ".join(SKILL.split())
    assert "is not an environment variable at all" in collapsed
    assert "on/off opt-out" in collapsed
