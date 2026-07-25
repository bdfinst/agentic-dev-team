"""#1416 — Repowise's install steps in `project-init/SKILL.md` must gitignore
`.mcp.json` themselves, immediately as part of provisioning, and self-heal on
repos where Repowise was already installed before this guard existed.

`/setup` Step 11's `.mcp.json` hygiene block (#1376) is downstream-projects-
only and skipped entirely for the `in-repo` case, but Repowise's `init`
write happens in `/project-init` regardless of which skill invoked it — so
the write and the ignore-hygiene were decoupled, leaving an in-repo gap.
This must be fixed at the source: Repowise's own sub-section, as an
unconditional **standing check** (same shape as the Graphify settings.json
standing check, issue #1367, elsewhere in this file) rather than a step
gated behind the accept/decline branch — otherwise it would never run for a
repo where Repowise is already present (Step 4c's own "already present"
skip means the accept-gated install steps never re-run).

Same structural-sensor style as tests/skills/test_setup_gitignore_hygiene.py
— pure text greps over shipped SKILL.md prose.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, REPO_ROOT, collapsed, section_outside_code

PROJECT_INIT = (PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md").read_text(
    encoding="utf-8"
)
SETUP = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")


def _mcp_json_standing_check() -> str:
    """Bound to just the Repowise `.mcp.json` standing-check paragraph — not
    the whole Repowise sub-section — so a false pass can't come from `.mcp.json`
    incidentally appearing in the install steps' prose (it does, at the
    Step 2 write-awareness sentence) or in Step 6's summary line further
    down. `section_outside_code` (not `section`) because the paragraph
    itself embeds a fenced bash block, and a fence-naive boundary match
    could be tripped by a line inside that fence."""
    return section_outside_code(
        PROJECT_INIT,
        r"^\*\*Standing check — `\.mcp\.json` machine-specific-path hygiene",
        boundary_pattern=r"^#### ",
        include_start_line=True,
    )


def _setup_step_11_mcp_json_block() -> str:
    """Bound to `/setup`'s own `.mcp.json` paragraph (not the whole Step 11
    gitignore-hygiene section, which also covers the unrelated runtime-
    artifacts block) for the same false-pass reason as above."""
    return section_outside_code(
        SETUP,
        r"^\*\*`\.mcp\.json` machine-specific-path hygiene",
        boundary_pattern=r"^### ",
        include_start_line=True,
    )


def test_repowise_standing_check_gitignores_mcp_json():
    check = _mcp_json_standing_check()
    # Bound to the MCP_MARKER...fi bash block itself — .mcp.json also recurs
    # earlier in the install steps' prose and later in Step 6's summary, so
    # an unscoped substring check would be trivially satisfied even if this
    # block were deleted. section_outside_code already strips the ``` fence
    # delimiter lines (but keeps their content), so the block's own closing
    # `fi` — not a stripped-away ``` — is what bounds the match here.
    block = re.search(r'MCP_MARKER="# dev-team hygiene[^"]*".*?\bfi\b', collapsed(check))
    assert block, "expected the MCP_MARKER gitignore-append bash block in the standing check"
    content = block.group(0)
    assert ".mcp.json" in content
    assert 'grep -qF "$MCP_MARKER" .gitignore' in content


def test_repowise_standing_check_is_not_gated_behind_install_branch():
    check = _mcp_json_standing_check()
    assert "not" in check
    assert "already present" in check
    # The claim under test is that this is unconditional, not merely that
    # the words "/setup" and "/project-init" co-occur somewhere nearby.
    assert "never re-run" in check


def test_repowise_mcp_json_hygiene_uses_same_marker_as_setup_step_11():
    # Reusing the exact marker string from setup/SKILL.md's own .mcp.json
    # block means whichever runs first is idempotent against the other — no
    # duplicate .gitignore entry regardless of call order. grep -qF matches
    # the marker prefix only, so the differing issue-number suffixes in the
    # two appended comment lines don't break this.
    marker = '# dev-team hygiene — machine-specific MCP config'
    assert marker in _mcp_json_standing_check()
    setup_block = _setup_step_11_mcp_json_block()
    assert marker in setup_block
    assert 'grep -qF "$MCP_MARKER" .gitignore' in setup_block


def test_repowise_mcp_json_already_tracked_defers_to_operator():
    check = collapsed(_mcp_json_standing_check())
    assert "git rm --cached" in check
    assert "do not" in check and "untrack it automatically" in check


def test_repowise_standing_check_is_not_downstream_only():
    # Unlike /setup's Step 11 (which keeps the Step 2 in-repo skip), this
    # check is deliberately unconditional for in-repo too — a stale
    # machine-specific path breaks every clone regardless of which kind of
    # repo wrote it.
    check = collapsed(_mcp_json_standing_check())
    assert "in-repo" in check
    assert "downstream-only" in check or "downstream-projects-only" in check


def test_repowise_standing_check_records_state():
    check = collapsed(_mcp_json_standing_check())
    # A top-level "mcp_hygiene" key, not nested under "repowise" — the check
    # runs independently of Repowise's own install/decline state, so filing
    # its outcome under the Repowise key would misrepresent a run where
    # Repowise itself was declined but the standing check still fired.
    assert '"mcp_hygiene"' in check
    assert '"gitignore"' in check
    assert "init-state.json" in check


def test_repowise_standing_check_covers_already_tracked_state():
    # A third recorded outcome for the one branch that leaves the repo still
    # broken (already git-tracked, needs operator follow-up) — distinct from
    # "added" and "already-covered" so a re-run can tell them apart.
    check = collapsed(_mcp_json_standing_check())
    assert "added-but-tracked" in check


def test_repowise_subsection_head_carves_out_the_standing_check():
    # The Graphify sub-section explicitly tells the executing agent its own
    # Standing check (#1367) runs regardless of the opt-in outcome, right at
    # the top of that sub-section. The Repowise sub-section needs the same
    # carve-out at its own head — otherwise an agent following Step 4c's
    # "already present" or "declined" branches (both of which just print a
    # message and continue) never has a reason to read this far into the
    # Repowise sub-section at all.
    head = section_outside_code(
        PROJECT_INIT,
        r"^#### Repowise — keyless local index, MCP server",
        boundary_pattern=r"^\*\*Install steps",
    )
    assert "#1416" in head
    assert "regardless of the group" in head or "regardless of" in head


def test_repo_own_gitignore_preseeds_the_mcp_json_marker():
    # This repo is in-repo (not downstream), and the standing check is
    # unconditional for in-repo too — so without pre-seeding the entry here,
    # the very next /project-init (or /setup) run against this checkout would
    # append the block on the spot, producing exactly the unexpected dirty
    # working tree issue #1416 is about. Pre-seeding makes that first run a
    # no-op ("already-covered") instead.
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "# dev-team hygiene — machine-specific MCP config" in gitignore
    assert ".mcp.json" in gitignore


def test_setup_step_11_cross_references_project_init_1416():
    # #1416 moved primary responsibility to project-init's standing check;
    # setup's own block stays as a downstream-only defense-in-depth backstop
    # for .mcp.json files written by other means — that split should be
    # explicit in setup's own prose, not only in project-init's.
    block = collapsed(_setup_step_11_mcp_json_block())
    assert "#1416" in block
    assert "project-init" in block


def test_step_6_summary_mentions_mcp_json_hygiene_outcome():
    # Mirrors test_setup_gitignore_hygiene.py's
    # test_step_12_report_mentions_both_new_gitignore_entries — the
    # analogous reporting claim for project-init's own summary step.
    step_6 = section_outside_code(PROJECT_INIT, r"^### Step 6: Summary", boundary_pattern=r"^## ")
    assert ".mcp.json" in step_6
    assert "#1416" in step_6
