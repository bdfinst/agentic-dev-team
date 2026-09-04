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

# Tokens the bash script itself can echo.
SCRIPT_ECHOED_TOKENS = (
    "concise-preference-added",
    "concise-preference-already-covered",
    "concise-preference-skipped-symlink",
)
# Tokens recorded directly from prose branches, before the script ever runs.
PROSE_ONLY_TOKENS = (
    "concise-preference-declined",
    "concise-preference-skipped-under-yes",
)


def _step_8a_body() -> str:
    """Just Step 8a's own section, from its heading up to Step 9's."""
    start = SKILL.index("### 8a. Ask about concise-response preference")
    end = SKILL.index("### 9. Generate PostToolUse formatting hook", start)
    return SKILL[start:end]


def _step_8a_script() -> str:
    """The literal ```bash ... ``` code fence inside Step 8a."""
    body = _step_8a_body()
    start = body.index("```bash\n") + len("```bash\n")
    end = body.index("\n```", start)
    return body[start:end]


def _step_8a_record_outcome_sentence() -> str:
    body = _step_8a_body()
    return body[body.index("Record the outcome") :]


def test_step_8a_marker_is_not_a_substring_of_the_appended_prose():
    marker = "<!-- dev-team: concise-response preference v1 -->"
    assert marker in SKILL
    # The marker must not itself be inside the single-quoted heredoc body —
    # if it were, a rewording of the *marker* would also change the prose,
    # defeating the purpose of decoupling them.
    heredoc_start = SKILL.index("<<'CONCISE_BLOCK'") + len("<<'CONCISE_BLOCK'")
    heredoc_end = SKILL.index("\nCONCISE_BLOCK", heredoc_start)
    assert marker not in SKILL[heredoc_start:heredoc_end]


def test_step_8a_creates_claude_dir_before_appending():
    script = _step_8a_script()
    assert "mkdir -p .claude" in script
    # Order matters: mkdir must run before the append redirect, or the
    # append silently no-ops when .claude/ doesn't exist yet.
    assert script.index("mkdir -p .claude") < script.index(">> .claude/CLAUDE.md")


def test_step_8a_symlink_guard_covers_both_the_dir_and_the_file():
    script = _step_8a_script()
    assert "[ -L .claude ]" in script
    assert "[ -L .claude/CLAUDE.md ]" in script
    assert "concise-preference-skipped-symlink" in script
    # The symlink check must run before mkdir/touch, not after.
    assert script.index("[ -L .claude ]") < script.index("mkdir -p .claude")


def test_step_8a_script_echoes_its_own_outcome_tokens():
    script = _step_8a_script()
    for token in SCRIPT_ECHOED_TOKENS:
        assert token in script, f"{token!r} should be echoed by the bash script"


def test_step_8a_outcome_tokens_all_reach_the_report_instruction():
    sentence = _step_8a_record_outcome_sentence()
    for token in SCRIPT_ECHOED_TOKENS + PROSE_ONLY_TOKENS:
        assert token in sentence, f"{token!r} should be named in the 'Record the outcome' instruction"


def test_step_8a_outcome_tokens_all_reach_the_step_12_report_line():
    line = next(line for line in SKILL.splitlines() if "Step 8a concise-response preference" in line)
    for token in SCRIPT_ECHOED_TOKENS + PROSE_ONLY_TOKENS:
        assert token in line, f"{token!r} should be listed in the Step 12 report line"
