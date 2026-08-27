"""Unit tests for scripts/lib/session_log/redact.py (#2045, epic #2040).

The corpus-based, end-to-end proof that no sentinel string escapes either
extractor's OUTPUT lives in `tests/scripts/test_session_report_golden.py`
(`test_no_sentinel_leaks_in_either_golden`, extended by this issue with an
absolute-POSIX-path sentinel alongside the existing Windows one). This file
covers `redact()` itself in isolation: the allowlist gate, the two-shape
`from_path` contract, and why "always basename first" would be unsafe.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

from session_log import redact

# ---------------------------------------------------------------------------
# from_path=False (default) -- strict allowlist only, no path-stripping
# ---------------------------------------------------------------------------


def test_plain_name_passes_through():
    assert redact.redact("correctness-review") == "correctness-review"


def test_name_with_spaces_collapses_to_other():
    assert redact.redact("please continue") == "other"


def test_prompt_text_sentinel_collapses_to_other():
    assert redact.redact("SENTINEL_PROMPT_DO_NOT_LEAK: starting the task") == "other"


def test_source_code_sentinel_collapses_to_other():
    assert redact.redact("def foo():\n    return 'SENTINEL_CODE_DO_NOT_LEAK'\n") == "other"


def test_full_command_string_collapses_to_other():
    # Contains a slash and spaces -- fails the allowlist outright rather than
    # being basenamed down to something that would pass it (see the
    # `from_path` docstring / test below for why that distinction matters).
    assert redact.redact("rm -rf /tmp/SENTINEL_CMD_do_not_leak") == "other"


def test_a_path_not_marked_from_path_fails_the_allowlist():
    # Absent `from_path=True`, a slash is simply an unsafe character -- the
    # value is NOT silently basenamed on the caller's behalf.
    assert redact.redact("/repo/file.py") == "other"


# ---------------------------------------------------------------------------
# from_path=True -- basename first, then the same allowlist
# ---------------------------------------------------------------------------


def test_posix_path_reduces_to_basename():
    assert redact.redact("/repo/file.py", from_path=True) == "file.py"


def test_windows_path_reduces_to_basename():
    assert (
        redact.redact(r"C:\Users\SENTINEL_USER\project\file.py", from_path=True)
        == "file.py"
    )
    assert "SENTINEL_USER" not in redact.redact(
        r"C:\Users\SENTINEL_USER\project\file.py", from_path=True
    )


def test_posix_path_username_does_not_leak():
    assert "SENTINEL_POSIX_USER" not in redact.redact(
        "/home/SENTINEL_POSIX_USER/workspace/secret_file.py", from_path=True
    )
    assert redact.redact(
        "/home/SENTINEL_POSIX_USER/workspace/secret_file.py", from_path=True
    ) == "secret_file.py"


def test_bare_filename_is_unaffected_by_from_path():
    assert redact.redact("file.py", from_path=True) == "file.py"


# ---------------------------------------------------------------------------
# Why the two-shape signature exists, not "always basename first"
# ---------------------------------------------------------------------------


def test_basenaming_an_unmarked_command_string_would_have_looked_safe():
    """Documents the failure mode `from_path` exists to prevent: a full shell
    command basenamed as if it were a path can coincidentally produce a
    string that passes the strict allowlist -- proving `redact()` must never
    basename a value the caller hasn't affirmatively marked as a path."""
    from session_log import classify

    command = "rm -rf /tmp/SENTINEL_CMD_do_not_leak"
    # If redact() blindly basenamed every input, this is what it would emit:
    would_be_emitted = classify.safe_name(classify.basename(command))
    assert would_be_emitted == "SENTINEL_CMD_do_not_leak"  # looks "safe" -- isn't
    # redact() with the correct (default) from_path=False never does this:
    assert redact.redact(command) == "other"
