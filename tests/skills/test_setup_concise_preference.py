"""Content-guard: setup/SKILL.md's Step 8a concise-response preference.

Mirrors test_setup_skill_artifact_paths.py's Step 11 marker-bump test: the
idempotency marker must be a dedicated, content-free sentinel (not a
substring of the prose it guards), so a future wording tweak to the
appended block can never desync the `grep -qF` check from what it's
supposed to detect. Also pins the outcome-token vocabulary so the bash
script's `echo` output, the "Record the outcome" instruction, and the
Step 12 report line never drift from one another (a review finding on the
PR that introduced this step, #2103), and pins that an already-covered
repo is never prompted at all (#2112 follow-up).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed

SKILL = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")

# Tokens the append script itself can echo.
SCRIPT_ECHOED_TOKENS = (
    "concise-preference-added",
    "concise-preference-already-covered",
    "concise-preference-skipped-symlink",
    "concise-preference-write-failed",
)
# Tokens recorded directly from prose branches, before the append script ever runs.
PROSE_ONLY_TOKENS = (
    "concise-preference-declined",
    "concise-preference-skipped-under-yes",
)


def _step_8a_body() -> str:
    """Just Step 8a's own section, from its heading up to Step 9's."""
    start = SKILL.index("### 8a. Ask about concise-response preference")
    end = SKILL.index("### 9. Generate PostToolUse formatting hook", start)
    return SKILL[start:end]


def _nth_bash_fence(body: str, n: int) -> str:
    """The literal ```bash ... ``` code fence content, 0-indexed by
    appearance order within `body`."""
    pos = 0
    for _ in range(n + 1):
        start = body.index("```bash\n", pos) + len("```bash\n")
        pos = start
    end = body.index("\n```", start)
    return body[start:end]


def _step_8a_precheck_script() -> str:
    """The first ```bash fence — the already-covered gate that must run
    before any prompt."""
    return _nth_bash_fence(_step_8a_body(), 0)


def _step_8a_append_script() -> str:
    """The second ```bash fence — the actual idempotent-append logic,
    reached only once the pre-check found the marker absent."""
    return _nth_bash_fence(_step_8a_body(), 1)


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


def test_step_8a_precheck_runs_before_the_prompt():
    # The already-covered gate must be textually positioned before the
    # operator is ever asked — an already-covered repo must never see the
    # prompt at all, under any flag combination.
    body = _step_8a_body()
    assert body.index("```bash") < body.index("Ask the operator")


def test_step_8a_precheck_uses_the_same_marker_as_the_append_script():
    marker = "<!-- dev-team: concise-response preference v1 -->"
    precheck = _step_8a_precheck_script()
    append = _step_8a_append_script()
    assert marker in precheck
    assert marker in append


def test_step_8a_precheck_short_circuits_the_whole_step():
    body = collapsed(_step_8a_body())
    assert "skip the rest of this step entirely" in body
    assert "no prompt" in body


def test_step_8a_creates_claude_dir_before_appending():
    script = _step_8a_append_script()
    assert "mkdir -p .claude" in script
    # Order matters: mkdir must run before the append redirect, or the
    # append silently no-ops when .claude/ doesn't exist yet.
    assert script.index("mkdir -p .claude") < script.index(">> .claude/CLAUDE.md")


def test_step_8a_symlink_guard_covers_both_the_dir_and_the_file():
    script = _step_8a_append_script()
    assert "[ -L .claude ]" in script
    assert "[ -L .claude/CLAUDE.md ]" in script
    assert "concise-preference-skipped-symlink" in script
    # The symlink check must run before mkdir/touch, not after.
    assert script.index("[ -L .claude ]") < script.index("mkdir -p .claude")


def test_step_8a_script_echoes_its_own_outcome_tokens():
    script = _step_8a_append_script()
    for token in SCRIPT_ECHOED_TOKENS:
        assert token in script, f"{token!r} should be echoed by the append script"


def test_step_8a_append_outcome_is_gated_on_write_success():
    # A prior version echoed "added" unconditionally after the redirect,
    # so a failed mkdir/touch/append (e.g. .claude exists as a regular
    # file, or the tree is read-only) was silently misreported as success.
    script = _step_8a_append_script()
    assert ">> .claude/CLAUDE.md && echo" in script
    assert "|| echo \"concise-preference-write-failed\"" in script


def test_step_8a_outcome_tokens_all_reach_the_report_instruction():
    sentence = _step_8a_record_outcome_sentence()
    for token in SCRIPT_ECHOED_TOKENS + PROSE_ONLY_TOKENS:
        assert token in sentence, f"{token!r} should be named in the 'Record the outcome' instruction"


def test_step_8a_outcome_tokens_all_reach_the_step_12_report_line():
    line = next(line for line in SKILL.splitlines() if "Step 8a concise-response preference" in line)
    for token in SCRIPT_ECHOED_TOKENS + PROSE_ONLY_TOKENS:
        assert token in line, f"{token!r} should be listed in the Step 12 report line"
