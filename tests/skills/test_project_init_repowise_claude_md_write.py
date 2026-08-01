"""#1670 item 3 (corrected) — Repowise's `.claude/CLAUDE.md` write is
intended, expected behavior, not a bug, and this skill's own prose must
keep saying so.

An earlier round of this fix wrongly treated Repowise's `## Codebase
Intelligence for <project> (Repowise)` write as something to revert, and
shipped `tests/skills/test_project_init_repowise_claude_md_guard.py`
pinning that (incorrect) guard wiring. The repo owner corrected this
mid-review: the write is intended and should be committed. That whole file
was deleted along with the guard wiring it pinned — but deleting it also
dropped the only sensor for two claims that still hold:

1. The pre-existing `.mcp.json` write-awareness sentence (issues #1416,
   #1376) in Step 2's install steps, which `test_project_init_mcp_json_hygiene.py`
   deliberately does NOT cover (its own docstring excludes the Step 2
   sentence specifically, to avoid a false pass from `.mcp.json` merely
   appearing in the install-steps prose).
2. The corrected claim itself — that the `## Codebase Intelligence` write
   is intended, committed, and not reverted — which had no sensor at all
   before this file.

Same structural-sensor style as tests/skills/test_project_init_mcp_json_hygiene.py
— pure text greps over shipped SKILL.md prose.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, section_outside_code

PROJECT_INIT = (PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md").read_text(
    encoding="utf-8"
)


def _install_steps_step_2() -> str:
    """Bound to Step 2's own paragraph (index + .mcp.json + CLAUDE.md write
    awareness) — not the whole Repowise sub-section — so a false pass can't
    come from `.mcp.json` or `Codebase Intelligence` incidentally appearing
    in Step 4c's prompt table or the Standing check further down."""
    return section_outside_code(
        PROJECT_INIT,
        r"^2\. Index keyless",
        boundary_pattern=r"^3\. ",
        include_start_line=True,
    )


def test_repowise_step_2_still_notes_the_mcp_json_write():
    step = collapsed(_install_steps_step_2())
    assert ".mcp.json" in step
    assert "standing check" in step


def test_repowise_claude_md_write_is_documented_as_intended_not_reverted():
    step = collapsed(_install_steps_step_2())
    assert "Codebase Intelligence" in step
    assert "intended" in step
    assert "not reverted" in step
    assert "#1670" in step


def test_repowise_claude_md_write_is_noted_as_structurally_derived():
    # Distinguishes this from free-form model-generated prose landing
    # unreviewed in an agent-loaded instruction file (security-review
    # concern raised while correcting the earlier, incorrect guard).
    # Asserts on the re-examination sentence's own wording, not on
    # `--no-prose` alone — that flag also appears in Step 2's pre-existing
    # `repowise init` invocation line and would leave this sensor unable to
    # detect the re-examination sentence being deleted.
    step = collapsed(_install_steps_step_2())
    assert "derived structurally" in step
    assert "not free-form model-generated prose" in step
    # The reassuring half alone isn't enough — pin the qualifying half too,
    # so a future edit can't quietly drop back to the overclaiming
    # "structurally derived = safe" framing this sentence was written to
    # avoid.
    assert "third-party-tool-generated" in step
    assert "not this note alone" in step


def test_repowise_prompt_bullet_uses_the_full_section_header():
    # Step 4c's confirmation prompt and Step 2 must name the same section
    # header, so an operator who greps for it after the run finds it.
    prompt_bullet = section_outside_code(
        PROJECT_INIT,
        r"^    - Repowise   — local keyless index",
        boundary_pattern=r"^  ```",
    )
    assert "Codebase Intelligence for <project> (Repowise)" in collapsed(prompt_bullet)


def _yes_semantics_affirmative_repowise_bullet() -> str:
    """Bound to just the Affirmative bucket's keyless-pair bullet — not the
    whole `--yes` semantics section — so a `#1690` match can't be satisfied
    by the *Conservative* Graphify bullet instead, which cites the same
    issue for a different reason (#1670 item 3 review finding: both bullets
    mention #1690, so an unscoped assertion doesn't actually sense either
    one's own tracking pointer)."""
    return section_outside_code(
        PROJECT_INIT,
        r"^- \*\*Step 4c keyless pair",
        boundary_pattern=r"^\*\*Conservative\*\*",
        include_start_line=True,
    )


def test_step_6_summary_reports_the_claude_md_write():
    # The deleted guard used to be the operator's only run-time signal that
    # something landed in `.claude/CLAUDE.md`; removing it must not leave
    # an unattended `--yes` run silent about the write (ai-provenance-review
    # finding, #1670 item 3 correction) — Step 6's summary is where that
    # signal now lives instead.
    step_6 = section_outside_code(PROJECT_INIT, r"^### Step 6: Summary", boundary_pattern=r"^## ")
    text = collapsed(step_6)
    assert "Codebase Intelligence for <project> (Repowise)" in text
    assert "#1670" in text


def test_yes_semantics_note_why_repowise_stays_in_the_affirmative_bucket():
    # #1670's correction means Repowise now writes to the tracked
    # CLAUDE.md same as Graphify does — the `--yes` Affirmative/Conservative
    # split must explain why that doesn't move Repowise into the
    # Conservative bucket below. Asserts on the load-bearing phrase and the
    # tracking pointer directly, rather than on "Repowise"/"CLAUDE.md"
    # alone — both already appear in pre-existing prose nearby and would
    # leave this sensor unable to catch the explanatory sentence itself
    # being deleted.
    text = collapsed(_yes_semantics_affirmative_repowise_bullet())
    assert "not a surprise mutation" in text
    assert "#1690" in text
