"""Content-guard: setup/SKILL.md's Step 8a concise-response preference.

Mirrors test_setup_skill_artifact_paths.py's Step 11 marker-bump test: the
idempotency marker must be a dedicated, content-free sentinel (not a
substring of the prose it guards), so a future wording tweak to the
appended block can never desync the `grep -qF` check from what it's
supposed to detect. Also pins the outcome-token vocabulary so the bash
script's `echo` output, the "Record the outcome" instruction, and the
Step 12 report line never drift from one another (a review finding on the
PR that introduced this step, #2103).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT

SKILL = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")

OUTCOME_TOKENS = (
    "concise-preference-added",
    "concise-preference-already-covered",
    "concise-preference-declined",
    "concise-preference-skipped-under-yes",
    "concise-preference-skipped-symlink",
)


def test_step_8a_marker_is_not_a_substring_of_the_appended_prose():
    marker = "<!-- dev-team: concise-response preference v1 -->"
    assert marker in SKILL
    # The marker must not itself be inside the single-quoted heredoc body —
    # if it were, a rewording of the *marker* would also change the prose,
    # defeating the purpose of decoupling them.
    heredoc_start = SKILL.index("<<'CONCISE_BLOCK'") + len("<<'CONCISE_BLOCK'")
    heredoc_end = SKILL.index("\nCONCISE_BLOCK", heredoc_start)
    assert marker not in SKILL[heredoc_start:heredoc_end]


def test_step_8a_guards_against_duplicate_general_heading():
    assert "grep -q '^## General$'" in SKILL


def test_step_8a_creates_claude_dir_before_append():
    assert "mkdir -p .claude" in SKILL


def test_step_8a_outcome_tokens_are_consistent_everywhere():
    # Every token the script echoes must also appear in the "Record the
    # outcome" instruction and the Step 12 report bracket — one vocabulary,
    # not three independently-spelled ones.
    for token in OUTCOME_TOKENS:
        assert SKILL.count(token) >= 2, f"{token!r} should appear in both the script and the report"


def test_step_8a_symlink_guard_present():
    assert "[ -L .claude/CLAUDE.md ]" in SKILL
    assert "concise-preference-skipped-symlink" in SKILL
