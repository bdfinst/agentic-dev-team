"""#1670 item 3 — Repowise's `repowise init` install step must be wrapped in
the `.claude/CLAUDE.md` write-reverting guard, not run bare.

Step 2b's prose IS the enforcement mechanism here — nothing in the shipped
tree calls `run_install_reverting_unexpected_writes` except an executing
agent following this paragraph. Every sibling behavioral claim in this
sub-section already has a structural-sensor content guard (e.g.
`test_project_init_mcp_json_hygiene.py` pins the #1416 standing check down
to its marker string and phrasing) — this file is that same sensor for the
CLAUDE.md write guard, so a future reword/renumber/cleanup pass can't
silently drop the wiring while `claude_md_guard.py`'s own unit tests
(`plugins/dev-team/tests/scripts/test_claude_md_guard.py`) stay green (those
verify the function works, not that anything in the shipped skill calls it).

Same structural-sensor style as tests/skills/test_project_init_mcp_json_hygiene.py
— pure text greps over shipped SKILL.md prose.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, section_outside_code

PROJECT_INIT = (PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md").read_text(
    encoding="utf-8"
)


def _claude_md_write_guard_step() -> str:
    """Bound to just step 2b's own paragraph — not the whole Repowise
    sub-section — so a false pass can't come from `run_install_with_guard`
    or `.claude/CLAUDE.md` incidentally appearing elsewhere in this file
    (the Graphify sub-section's own guard, or Step 4c's prompt table)."""
    return section_outside_code(
        PROJECT_INIT,
        r"^2b\. \*\*CLAUDE\.md write guard",
        boundary_pattern=r"^3\. ",
        include_start_line=True,
    )


def test_repowise_install_step_wraps_the_reverting_guard():
    step = collapsed(_claude_md_write_guard_step())
    assert "run_install_reverting_unexpected_writes" in step
    assert "scripts/lib/claude_md_guard.py" in step
    assert "#1670" in step


def test_repowise_claude_md_expected_completely_untouched():
    step = collapsed(_claude_md_write_guard_step())
    assert "completely untouched" in step


def test_repowise_guard_contract_branches_on_reverted_not_added():
    # The whole point of #1670 item 3's fix: a deletion-only write still
    # reverts and still needs reporting, even though it adds nothing — the
    # caller must not use `bool(added)` as the "did anything happen" signal.
    step = collapsed(_claude_md_write_guard_step())
    assert "(reverted, added)" in step
    assert "branch on" in step and "reverted" in step


def test_repowise_guard_operator_message_reports_count_not_content():
    # Repowise-authored text is untrusted third-party content — the operator
    # message must report only a count, never echo the reverted lines
    # verbatim (security-review finding, #1670 item 3 follow-up).
    step = collapsed(_claude_md_write_guard_step())
    assert "count" in step
    assert "never" in step and "content verbatim" in step


def test_repowise_guard_reverts_even_if_installer_raises():
    step = collapsed(_claude_md_write_guard_step())
    assert "even if the installer itself then raises" in step


def test_repowise_subsection_still_notes_the_mcp_json_write_awareness():
    # Guard against step 2b accidentally swallowing or displacing the
    # pre-existing Step 2 sentence about the .mcp.json write (#1416/#1376) —
    # both live in the same install-steps block and must both survive.
    full_block = section_outside_code(
        PROJECT_INIT,
        r"^\*\*Install steps \(executed only when the all-or-none group is accepted\):\*\*",
        boundary_pattern=r"^\*\*Detection probe",
    )
    text = collapsed(full_block)
    assert ".mcp.json" in text
    assert "run_install_reverting_unexpected_writes" in text
