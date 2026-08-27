"""Unit tests for scripts/lib/session_log/classify.py (#2043, epic #2040).

Covers the 12-symbol classification core unified from the two forked
extractors — see the module's docstring for the full per-symbol
reconciliation table. `basename` gets the most scrutiny: it's flagged as the
highest-stakes symbol (a Windows-path privacy fix a prior hand-port dropped
once already), pinned here against the golden corpus's own Windows-style
backslash path fixture.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

from session_log import classify

CORPUS_MAIN_TRANSCRIPT = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "session_log"
    / "projects"
    / "-tmp-golden-project"
    / "99999999-8888-7777-6666-555555555555.jsonl"
)


# ---------------------------------------------------------------------------
# basename — the highest-stakes symbol (Windows-path privacy fix)
# ---------------------------------------------------------------------------


def test_basename_strips_windows_style_path():
    assert classify.basename(r"C:\Users\alice\proj\secrets.env") == "secrets.env"


def test_basename_strips_posix_style_path():
    assert classify.basename("/repo/file.py") == "file.py"


def test_basename_bare_filename_passes_through():
    assert classify.basename("file.py") == "file.py"


def test_basename_against_corpus_windows_path_fixture():
    # The corpus embeds a Windows-style absolute path
    # (C:\Users\SENTINEL_USER\project\file.py) in two Edit tool_use blocks,
    # specifically to pin this fix. Confirm neither the full path nor the
    # username component survives basename().
    raw = CORPUS_MAIN_TRANSCRIPT.read_text(encoding="utf-8")
    assert "SENTINEL_USER" in raw  # sanity: the fixture really has it
    stripped = classify.basename(r"C:\Users\SENTINEL_USER\project\file.py")
    assert stripped == "file.py"
    assert "SENTINEL_USER" not in stripped


# ---------------------------------------------------------------------------
# safe_name
# ---------------------------------------------------------------------------


def test_safe_name_allows_safe_charset():
    assert classify.safe_name("dev-team:plan_v2.1") == "dev-team:plan_v2.1"


def test_safe_name_rejects_unsafe_value():
    assert classify.safe_name("has spaces") == classify.UNSAFE_NAME


def test_safe_name_rejects_trailing_newline():
    # fullmatch, not match: `$` also matches immediately BEFORE a trailing
    # newline (#1994 review) — a `.match()`-based check would wrongly admit
    # "name\n".
    assert classify.safe_name("name\n") == classify.UNSAFE_NAME


# ---------------------------------------------------------------------------
# strip_ns
# ---------------------------------------------------------------------------


def test_strip_ns_dev_team_prefix():
    assert classify.strip_ns("dev-team:plan") == "plan"


def test_strip_ns_agentic_dev_team_prefix():
    assert classify.strip_ns("agentic-dev-team:plan") == "plan"


def test_strip_ns_no_prefix_passes_through():
    assert classify.strip_ns("plan") == "plan"


# ---------------------------------------------------------------------------
# text_of
# ---------------------------------------------------------------------------


def test_text_of_plain_string():
    assert classify.text_of("hello") == "hello"


def test_text_of_block_list():
    content = [{"type": "text", "text": "hello"}, {"type": "tool_use", "name": "X"}]
    assert classify.text_of(content) == "hello"


def test_text_of_non_string_non_list_returns_empty():
    assert classify.text_of(None) == ""
    assert classify.text_of(42) == ""


# ---------------------------------------------------------------------------
# classification regex vocabulary
# ---------------------------------------------------------------------------


def test_verify_re_matches_known_verify_commands():
    assert classify.VERIFY_RE.search("npm run test")
    assert classify.VERIFY_RE.search("pytest -q")
    assert not classify.VERIFY_RE.search("echo hello")


def test_correction_re_matches_correction_keywords():
    assert classify.CORRECTION_RE.search("no, that's wrong")
    assert not classify.CORRECTION_RE.search("looks great, ship it")


def test_permission_re_matches_denial_language():
    assert classify.PERMISSION_RE.search("Permission denied")


def test_oldstring_re_matches_failed_edit_language():
    assert classify.OLDSTRING_RE.search("old_string not found in file")


def test_harness_attributions_excludes_role_labels():
    assert "workflow-subagent" in classify.HARNESS_ATTRIBUTIONS
    assert "claude" in classify.HARNESS_ATTRIBUTIONS
    assert "correctness-review" not in classify.HARNESS_ATTRIBUTIONS


# ---------------------------------------------------------------------------
# commit / bypass detection (the classify.py stand-in for ADR 0036's
# _COMMIT_RE / _BYPASS_RE, which no longer exist as literal regex symbols —
# see module docstring)
# ---------------------------------------------------------------------------


def test_is_git_commit_argv_true_for_plain_commit():
    assert classify.is_git_commit_argv(["git", "commit", "-m", "msg"])


def test_is_git_commit_argv_true_past_global_options():
    assert classify.is_git_commit_argv(["git", "-C", "/repo", "commit"])


def test_is_git_commit_argv_false_for_other_subcommand():
    assert not classify.is_git_commit_argv(["git", "status"])


def test_bash_segments_splits_on_top_level_operators():
    segments = classify.bash_segments("git add -A && git commit -m 'msg'")
    assert segments == [["git", "add", "-A"], ["git", "commit", "-m", "msg"]]


def test_bash_segments_does_not_split_inside_quoted_message():
    segments = classify.bash_segments('git commit -m "a && b"')
    assert segments == [["git", "commit", "-m", "a && b"]]


def test_commit_bypass_detection_end_to_end():
    segments = classify.bash_segments("git commit --no-verify -m msg")
    assert len(segments) == 1
    assert classify.is_git_commit_argv(segments[0])
    assert any(tok in classify.COMMIT_BYPASS_TOKENS for tok in segments[0][1:])
