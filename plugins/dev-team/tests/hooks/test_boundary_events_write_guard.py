"""Unit tests for hooks/boundary_events_write_guard.py (#2171).

Plan Step 1.1 covers the Write/Edit path-match guard. Plan Step 1.2 adds
Bash `tool_input.command` write-shape detection (`bash_command_writes_to_ledger`)
and its `main()` dispatch — covered below.

In-process, stdin-monkeypatched, with `emit_boundary_event` stubbed (same
split `test_destructive_guard.py` uses) — real subprocess + real-ledger
end-to-end coverage lives in `tests/hooks/test_boundary_events_write_guard.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"
_TESTS_LIB = _PLUGIN_DIR / "tests" / "lib"

for _p in (_PLUGIN_DIR / "hooks", _TESTS_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import boundary_events_write_guard as guard
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

# Test-file-local constant (not `guard._LEDGER_NAME` — importing the code
# under test's own constant would make the test oracle circular).
_LEDGER_REL_PATH = ".claude/metrics/boundary-events.jsonl"

# Captured before any per-test monkeypatching can shadow it, so
# `test_main_swallows_exception_from_real_emit_boundary_event` can restore
# the real wrapper regardless of `_no_boundary_events`'s autouse stub.
_REAL_EMIT_BOUNDARY_EVENT = guard.emit_boundary_event


@pytest.fixture(autouse=True)
def _no_boundary_events(monkeypatch):
    """Unit-level tests call `main()`/`targets_ledger()` in-process — stub
    the emit so no real ledger write happens as a side effect of testing
    the guard itself. `tests/hooks/test_boundary_events_write_guard.py`
    exercises the real subprocess + real emit path (matches
    pre_tool_guard.py's own test split)."""
    # double-waiver: B1 — emit_boundary_event opens a real file handle
    monkeypatch.setattr(guard, "emit_boundary_event", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# _extract_file_path
# ---------------------------------------------------------------------------


def test_extract_file_path_prefers_file_path():
    assert guard._extract_file_path({"file_path": "a.py", "path": "b.py"}) == "a.py"


def test_extract_file_path_falls_back_to_path():
    assert guard._extract_file_path({"path": "b.py"}) == "b.py"


def test_extract_file_path_empty_when_neither():
    assert guard._extract_file_path({}) == ""


def test_extract_file_path_empty_when_not_a_dict():
    assert guard._extract_file_path("a.py") == ""


# ---------------------------------------------------------------------------
# targets_ledger — path-form matrix (relative, absolute, "./"-prefixed)
# ---------------------------------------------------------------------------


def test_targets_ledger_relative_path(tmp_path):
    assert guard.targets_ledger(_LEDGER_REL_PATH, str(tmp_path))


def test_targets_ledger_dot_slash_prefixed_path(tmp_path):
    assert guard.targets_ledger("./" + _LEDGER_REL_PATH, str(tmp_path))


def test_targets_ledger_absolute_path(tmp_path):
    absolute = str(tmp_path / ".claude" / "metrics" / "boundary-events.jsonl")
    assert guard.targets_ledger(absolute, str(tmp_path))


def test_targets_ledger_false_for_unrelated_file_under_metrics(tmp_path):
    assert not guard.targets_ledger(
        ".claude/metrics/session-digest.jsonl", str(tmp_path)
    )


def test_targets_ledger_false_for_review_verdicts_store(tmp_path):
    """Slice 2's own store — matches the exact ledger name/path, not a
    `.claude/metrics/` prefix (plan Step 1.1 implementation note)."""
    assert not guard.targets_ledger(
        ".claude/metrics/review-verdicts.jsonl", str(tmp_path)
    )


def test_targets_ledger_false_for_empty_path(tmp_path):
    assert not guard.targets_ledger("", str(tmp_path))


def test_targets_ledger_true_for_relative_path_via_symlinked_cwd(tmp_path):
    """Review finding (Step 1.1 correction): `targets_ledger()` compared an
    `os.path.abspath`-normalized candidate against a
    `artifact_paths.resolve_file()`/git-resolved ledger path — an
    asymmetric comparison. `resolve_file()` -> `project_root()` finds the
    repo root via `git rev-parse --show-toplevel`, which resolves a
    symlinked `cwd` to its real location; joining `file_path` against the
    *unresolved* `cwd` then comparing only with `os.path.abspath` (no
    symlink resolution) left a genuine false negative whenever `cwd`
    itself is reached through a symlink. Reproduced here with a real git
    repo and a real symlink (not mocked — this is exactly the git/
    filesystem interaction that produced the asymmetry) to prove the fix:
    before the fix this returned False; after realpath'ing the `cwd`
    anchor, it correctly returns True."""
    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(real_repo),
        env=hermetic_git_env(home=tmp_path),
        check=True,
    )
    link_parent = tmp_path / "link-parent"
    link_parent.mkdir()
    symlinked_cwd = link_parent / "repo-link"
    os.symlink(str(real_repo), str(symlinked_cwd), target_is_directory=True)

    assert guard.targets_ledger(_LEDGER_REL_PATH, str(symlinked_cwd))


def test_targets_ledger_true_for_legacy_pre_migration_path(tmp_path):
    """Domain-review finding (#2171): `emit_boundary_event()` resolves the
    ledger with `resolve_file(..., migrate=True)` (the writer default),
    which `shutil.move`s an untracked `<project-root>/metrics/
    boundary-events.jsonl` into `.claude/metrics/boundary-events.jsonl`
    the next time anything emits, whenever the new-location file does not
    yet exist. Matching only the new location would let a Write/Edit plant
    a forged file at the legacy path — unguarded — that a later,
    legitimate emit then silently promotes into ledger history. Both
    locations must be blocked."""
    legacy = str(tmp_path / "metrics" / "boundary-events.jsonl")
    assert guard.targets_ledger(legacy, str(tmp_path))


def test_targets_ledger_false_for_legacy_unrelated_file(tmp_path):
    legacy_unrelated = str(tmp_path / "metrics" / "session-digest.jsonl")
    assert not guard.targets_ledger(legacy_unrelated, str(tmp_path))


# ---------------------------------------------------------------------------
# main() — in-process, stdin-monkeypatched (Write and Edit tool shapes)
# ---------------------------------------------------------------------------


def _stdin(monkeypatch, payload):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))


def test_main_blocks_write_to_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "emit_boundary_event()" in out
    assert "BLOCKED" in out


def test_main_blocks_edit_to_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "emit_boundary_event()" in out


def test_main_allows_write_to_unrelated_file(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/metrics/session-digest.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_allows_write_to_review_verdicts_store(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/metrics/review-verdicts.jsonl"},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_fails_open_on_missing_tool_input(monkeypatch, tmp_path, capsys):
    _stdin(monkeypatch, {"tool_name": "Write", "cwd": str(tmp_path)})
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_fails_open_on_non_json_stdin(monkeypatch, capsys):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_fails_open_on_empty_stdin(monkeypatch, capsys):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_silent_pass_when_file_path_absent(monkeypatch, tmp_path, capsys):
    _stdin(monkeypatch, {"tool_name": "Write", "tool_input": {}, "cwd": str(tmp_path)})
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_fails_open_on_non_string_cwd_with_embedded_nul(monkeypatch, capsys):
    """`cwd` falls back to "." when it isn't a usable string — including a
    string containing an embedded NUL byte, which would otherwise reach
    `subprocess.run(cwd=...)` (inside `artifact_paths.project_root`, via
    `targets_ledger` -> `resolve_file`) and raise `ValueError`. This exact
    hazard was a previously-fixed real defect elsewhere in this codebase:
    #1904 item 16 in `artifact_paths.project_root`'s own docstring
    documents a `cwd` with an embedded NUL byte raising `ValueError` from
    `subprocess.run`, not `OSError` — escaping that function's "never
    raises" contract. `file_path` here names a file that is never the
    ledger regardless of what "." resolves to for the ambient test
    process, so this test stays deterministic across environments while
    still proving the NUL-byte `cwd` was normalized away before reaching
    any subprocess call (main() doesn't raise, and evaluation proceeds to
    an ordinary "not blocked" verdict rather than crashing)."""
    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/metrics/session-digest.jsonl"},
            "cwd": "bad\0cwd",
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_swallows_exception_from_real_emit_boundary_event(
    monkeypatch, tmp_path, capsys
):
    """WARNING-severity coverage gap (review finding): `main()`'s local
    `emit_boundary_event` safety-net wrapper (#859 — "even a misbehaving
    helper must never affect this hook's exit code/stdout/stderr") was
    never exercised with a raising underlying emit; every other test stubs
    the wrapper itself via the autouse fixture, never proving the wrapper's
    own `try`/`except` actually does anything. This test restores the real
    wrapper and forces the underlying `_emit_boundary_event` to raise,
    confirming `main()`'s exit code and stdout are unaffected."""
    # double-waiver: B1 — emit_boundary_event opens a real file handle
    monkeypatch.setattr(guard, "emit_boundary_event", _REAL_EMIT_BOUNDARY_EVENT)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated emit failure")

    # double-waiver: B1 — the underlying real emit also opens a file handle
    monkeypatch.setattr(guard, "_emit_boundary_event", _raise)

    _stdin(
        monkeypatch,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "emit_boundary_event()" in out


# ---------------------------------------------------------------------------
# bash_command_writes_to_ledger — write-shaped commands (Step 1.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # Redirect, across all four path forms (Examples Outline).
        "echo '{}' >> " + _LEDGER_REL_PATH,
        "echo '{}' >> /repo/" + _LEDGER_REL_PATH,
        "echo '{}' >> ./" + _LEDGER_REL_PATH,
        "cd .claude/metrics && echo '{}' >> boundary-events.jsonl",
        # Heredoc, caught via its trailing redirect operator, not `<<`.
        "cat <<'EOF' >> " + _LEDGER_REL_PATH + "\n{}\nEOF",
        # tee
        "echo '{}' | tee -a " + _LEDGER_REL_PATH,
        # tee with the ledger NOT as its first operand (review finding —
        # previously a false negative: the pattern required the ledger to
        # be tee's first argument).
        "tee /tmp/log " + _LEDGER_REL_PATH,
        # sed -i
        "sed -i 's/a/b/' " + _LEDGER_REL_PATH,
        # sed --in-place (GNU long form — review finding: previously only
        # `-i` matched).
        "sed --in-place 's/a/b/' " + _LEDGER_REL_PATH,
        # cp/mv/rm/truncate/dd
        "rm " + _LEDGER_REL_PATH,
        "mv " + _LEDGER_REL_PATH + " /tmp/moved.jsonl",
        "cp " + _LEDGER_REL_PATH + " /tmp/copy.jsonl",
        "truncate -s 0 " + _LEDGER_REL_PATH,
        "dd if=/dev/null of=" + _LEDGER_REL_PATH,
        # python3 -c with a write/append-mode open()
        "python3 -c \"open('" + _LEDGER_REL_PATH + "', 'w').write('{}')\"",
        "python3 -c \"open('" + _LEDGER_REL_PATH + "', 'a').write('{}')\"",
        # open() in read+write mode ("r+") — review finding: previously a
        # false negative, since only w/a/x-prefixed modes matched despite
        # "r+" permitting writes.
        "python3 -c \"open('" + _LEDGER_REL_PATH + "', 'r+').write('{}')\"",
        # open() with the keyword form of mode= — review finding:
        # previously a false negative, since the pattern only matched a
        # positional mode argument.
        "python3 -c \"open('" + _LEDGER_REL_PATH + "', mode='a').write('{}')\"",
        # `~/`-prefixed path — review finding: previously a false
        # negative, since the prefix character class excluded `~`.
        "echo '{}' >> ~/" + _LEDGER_REL_PATH,
        # Quoted path expanding an env var, with characters ($, {, })
        # previously excluded from the prefix character class (review
        # finding).
        'echo \'{}\' >> "$CLAUDE_PROJECT_DIR/' + _LEDGER_REL_PATH + '"',
        # Quoted path containing a space in a directory component (review
        # finding: previously excluded from the prefix character class).
        'echo \'{}\' >> "My Notes/' + _LEDGER_REL_PATH + '"',
    ],
)
def test_bash_command_writes_to_ledger_true_for_write_shaped_commands(command):
    assert guard.bash_command_writes_to_ledger(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "tail -20 " + _LEDGER_REL_PATH,
        "cat " + _LEDGER_REL_PATH,
        "grep foo " + _LEDGER_REL_PATH,
        "head " + _LEDGER_REL_PATH,
        # read-mode (mode omitted, defaults to "r") open()
        "python3 -c \"print(open('" + _LEDGER_REL_PATH + "').read())\"",
        # reads the ledger, writes elsewhere — tee's own target is not the ledger
        "cat " + _LEDGER_REL_PATH + " | tee /tmp/copy.jsonl",
        # write-shaped, but targets an unrelated file
        "echo '{}' >> .claude/metrics/session-digest.jsonl",
        "",
    ],
)
def test_bash_command_writes_to_ledger_false_for_read_or_unrelated_commands(command):
    assert guard.bash_command_writes_to_ledger(command) is False


def test_bash_command_writes_to_ledger_fast_path_on_long_non_matching_command():
    """Security-review finding (#2171): the write-shape patterns' `[^;|&\\n]*`
    classes overlap with the path-suffix class, giving a long non-matching
    command quadratic backtracking — a plausible hang/bypass (a padded `rm`
    ahead of the real write could stall the scan past a timeout). Every
    pattern requires the literal `_LEDGER_NAME` substring, so an `in`
    fast-path is semantically equivalent and turns this from O(n^2) into
    O(n). Bounded timing assertion (generous — this is a regression guard,
    not a benchmark) proves the fast path is actually taken."""
    long_command = "rm " + ("a" * 200_000) + " ; echo done"
    assert guard._LEDGER_NAME not in long_command

    start = time.monotonic()
    result = guard.bash_command_writes_to_ledger(long_command)
    elapsed = time.monotonic() - start

    assert result is False
    assert elapsed < 1.0


# ---------------------------------------------------------------------------
# main() — Bash tool shape (Step 1.2)
# ---------------------------------------------------------------------------


def test_main_blocks_bash_redirect_to_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "echo '{}' >> " + _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 2
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "hooks/lib/boundary_events.py" in out
    assert "--event" in out
    assert "--subject-hash" in out
    # Bash-path message names the CLI, not the Python-only function
    # (plan-review-ux finding, Step 1.2).
    assert "emit_boundary_event()" not in out


def test_main_allows_bash_read_of_ledger(monkeypatch, tmp_path, capsys):
    _stdin(
        monkeypatch,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "tail -20 " + _LEDGER_REL_PATH},
            "cwd": str(tmp_path),
        },
    )
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_main_allows_bash_command_with_no_command_field(monkeypatch, tmp_path, capsys):
    _stdin(monkeypatch, {"tool_name": "Bash", "tool_input": {}, "cwd": str(tmp_path)})
    assert guard.main() == 0
    assert capsys.readouterr().out == ""
