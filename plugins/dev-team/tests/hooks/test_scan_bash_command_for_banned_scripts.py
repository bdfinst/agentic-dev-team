"""Unit tests for hooks/scan_bash_command_for_banned_scripts.py (#1755).

Real-time PreToolUse denial of new shell-script writes under
plugins/dev-team/ — the point-of-write half of the #1755 hook pair.
scan_worktree_for_banned_scripts.py (PostToolUse, the working-tree backstop)
has its own test file.

No git repo needed: `project_root()` falls back to its `start` argument
when not inside a git repo, and pytest's `tmp_path` is never itself part of
one, so every scenario here treats `tmp_path` as the resolved root directly.

The `_plugin_scope_dir` autouse fixture pre-creates `plugins/dev-team/` under
`tmp_path` for every test in this file, so each one exercises the command
scan itself rather than the (#1861) early-exit guard — that guard has its
own dedicated test using a directory that intentionally lacks this.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "scan_bash_command_for_banned_scripts.py"


@pytest.fixture(autouse=True)
def _plugin_scope_dir(tmp_path: Path) -> None:
    (tmp_path / "plugins" / "dev-team").mkdir(parents=True)


def _run(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "cwd": str(cwd),
        "tool_input": {"command": command},
    }
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_allows_python_write(tmp_path: Path) -> None:
    result = _run("echo hi > plugins/dev-team/hooks/foo.py", tmp_path)
    assert result.returncode == 0


def test_blocks_new_shell_script_via_redirect(tmp_path: Path) -> None:
    result = _run("echo hi > plugins/dev-team/hooks/foo.sh", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/foo.sh" in result.stdout
    assert "plugins/dev-team/hooks/foo.sh" in result.stderr
    assert result.stdout.startswith("[BLOCK]")


def test_blocks_append_redirect(tmp_path: Path) -> None:
    result = _run("echo hi >> plugins/dev-team/scripts/run.bash", tmp_path)
    assert result.returncode == 2
    assert "run.bash" in result.stdout


def test_blocks_cp_destination(tmp_path: Path) -> None:
    result = _run("cp template.txt plugins/dev-team/scripts/run.sh", tmp_path)
    assert result.returncode == 2
    assert "run.sh" in result.stdout


def test_cp_multiple_sources_picks_last_arg_as_destination(tmp_path: Path) -> None:
    result = _run("cp a.py b.py plugins/dev-team/hooks/dest.cmd", tmp_path)
    assert result.returncode == 2
    assert "dest.cmd" in result.stdout


def test_flags_before_destination_are_ignored(tmp_path: Path) -> None:
    result = _run("cp -v a.py plugins/dev-team/hooks/dest.ps1", tmp_path)
    assert result.returncode == 2


def test_blocks_tee_destination(tmp_path: Path) -> None:
    result = _run("echo hi | tee plugins/dev-team/hooks/foo.sh", tmp_path)
    assert result.returncode == 2
    assert "foo.sh" in result.stdout


def test_blocks_mv_destination(tmp_path: Path) -> None:
    result = _run("mv /tmp/staged.txt plugins/dev-team/scripts/deploy.bat", tmp_path)
    assert result.returncode == 2


def test_allows_install_sh_carveout(tmp_path: Path) -> None:
    result = _run("cat > plugins/dev-team/install.sh", tmp_path)
    assert result.returncode == 0


def test_allows_py_sh_carveout(tmp_path: Path) -> None:
    result = _run("cp bootstrap.tpl plugins/dev-team/hooks/py.sh", tmp_path)
    assert result.returncode == 0


def test_ignores_repo_root_scripts_outside_plugin_scope(tmp_path: Path) -> None:
    result = _run("echo hi > scripts/dev-setup.sh", tmp_path)
    assert result.returncode == 0


def test_compound_command_still_matches_redirect(tmp_path: Path) -> None:
    result = _run(
        "git add -A && echo done > plugins/dev-team/hooks/generated.sh", tmp_path
    )
    assert result.returncode == 2
    assert "generated.sh" in result.stdout


def test_missing_command_passes(tmp_path: Path) -> None:
    payload = {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {}}
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_malformed_json_stdin_passes(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="not json{{{",
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_malformed_quoting_does_not_crash(tmp_path: Path) -> None:
    result = _run("echo 'unterminated", tmp_path)
    assert result.returncode == 0


def test_empty_stdin_passes(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="",
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


# --- (#1864 sub-claim 3) quoted redirect targets ---------------------------


def test_double_quoted_redirect_target_still_detected(tmp_path: Path) -> None:
    result = _run('echo hi > "plugins/dev-team/hooks/evil.sh"', tmp_path)
    assert result.returncode == 2
    assert "evil.sh" in result.stdout


def test_single_quoted_redirect_target_still_detected(tmp_path: Path) -> None:
    result = _run("echo hi > 'plugins/dev-team/hooks/evil.sh'", tmp_path)
    assert result.returncode == 2
    assert "evil.sh" in result.stdout


# --- (#1875) cp/mv destination heuristic: last positional arg only ---------


def test_mv_rename_banned_to_python_not_blocked(tmp_path: Path) -> None:
    """Renaming a banned file to a legit extension is the correct
    remediation — must not be flagged just because the source had a
    banned extension."""
    result = _run("mv plugins/dev-team/hooks/foo.sh plugins/dev-team/hooks/foo.py", tmp_path)
    assert result.returncode == 0


def test_cp_moving_banned_file_out_of_scope_not_blocked(tmp_path: Path) -> None:
    """Copying a banned file OUT of scope is not a new banned-script write."""
    result = _run("cp plugins/dev-team/hooks/foo.sh /tmp/backup", tmp_path)
    assert result.returncode == 0


def test_mv_destination_with_banned_extension_still_blocked(tmp_path: Path) -> None:
    """A destination that itself has a banned extension is still blocked."""
    result = _run("mv a.py plugins/dev-team/hooks/dest.sh", tmp_path)
    assert result.returncode == 2
    assert "dest.sh" in result.stdout


# --- (#1878) GNU cp/mv target-directory forms -------------------------------


def test_cp_target_directory_short_flag_blocks_source(tmp_path: Path) -> None:
    result = _run("cp -t plugins/dev-team/hooks src1.sh src2.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_cp_target_directory_equals_form_blocks_source(tmp_path: Path) -> None:
    result = _run("cp --target-directory=plugins/dev-team/hooks src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_cp_target_directory_space_form_blocks_source(tmp_path: Path) -> None:
    result = _run("cp --target-directory plugins/dev-team/hooks src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_mv_target_directory_flag_blocks_source(tmp_path: Path) -> None:
    result = _run("mv -t plugins/dev-team/hooks src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_cp_target_directory_flag_allows_python_source(tmp_path: Path) -> None:
    result = _run("cp -t plugins/dev-team/hooks src1.py", tmp_path)
    assert result.returncode == 0


def test_cp_clustered_short_flag_target_directory_blocks_source(tmp_path: Path) -> None:
    """Security-review regression: a clustered short option ending in `t`
    (e.g. `-rt`) is GNU's target-directory form too, not just bare `-t`."""
    result = _run("cp -rt plugins/dev-team/hooks src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_multiline_command_does_not_evade_cp_destination_check(tmp_path: Path) -> None:
    """Security-review regression: a multi-line command must not collapse
    into one shlex call, which would make positionals[-1] read the wrong
    (last, unrelated) command's last token instead of the cp destination."""
    result = _run("cp plugins/dev-team/hooks/evil.sh plugins/dev-team/hooks/dest.sh\necho done", tmp_path)
    assert result.returncode == 2


def test_single_ampersand_background_job_does_not_evade_cp_destination_check(
    tmp_path: Path,
) -> None:
    result = _run("cp plugins/dev-team/hooks/evil.sh plugins/dev-team/hooks/dest.sh & echo done", tmp_path)
    assert result.returncode == 2


# --- (#1904 item 12) cp/mv destination heuristic: redirects and quoting ----


def test_trailing_redirect_not_mistaken_for_cp_destination(tmp_path: Path) -> None:
    """(#1904 item 12a) A trailing `2>/dev/null` must not be treated as the
    cp destination — the real destination (`x.sh`) is still the correct
    hit."""
    result = _run("cp evil.sh plugins/dev-team/hooks/x.sh 2>/dev/null", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/x.sh" in result.stdout


def test_trailing_spaced_redirect_not_mistaken_for_cp_destination(tmp_path: Path) -> None:
    """(#1904 item 12a) Same as above, but with the redirect operator
    space-separated from its target (`> /dev/null`) rather than glued to
    it."""
    result = _run("cp evil.sh plugins/dev-team/hooks/x.sh > /dev/null", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/hooks/x.sh" in result.stdout


def test_trailing_redirect_alone_does_not_evade_legit_rename(tmp_path: Path) -> None:
    """(#1904 item 12a) Stripping the trailing redirect must not turn a
    legitimate remediation (renaming to `.py`) into a false positive."""
    result = _run(
        "mv plugins/dev-team/hooks/foo.sh plugins/dev-team/hooks/foo.py 2>/dev/null",
        tmp_path,
    )
    assert result.returncode == 0


def test_quoted_ampersand_in_cp_destination_does_not_desync_scan(tmp_path: Path) -> None:
    """(#1904 item 12b) A quoted `&` inside the destination filename must
    not desync a separator-based split — the previous raw-string
    `re.split` would break the quoted segment apart mid-token and silently
    drop it via the caught `ValueError`."""
    result = _run(
        'cp evil.sh "plugins/dev-team/hooks/a&b.sh"',
        tmp_path,
    )
    assert result.returncode == 2
    assert "a&b.sh" in result.stdout


def test_quoted_semicolon_in_cp_destination_does_not_desync_scan(tmp_path: Path) -> None:
    """(#1904 item 12b) Same as above, for a quoted `;`."""
    result = _run(
        'mv evil.sh "plugins/dev-team/hooks/a;b.sh"',
        tmp_path,
    )
    assert result.returncode == 2
    assert "a;b.sh" in result.stdout


# --- (#1904 item 13) attached/abbreviated target-directory forms -----------


def test_cp_attached_short_target_directory_blocks_source(tmp_path: Path) -> None:
    """(#1904 item 13) GNU's attached-value short form: `-tDIR`, value
    glued directly onto the flag with no space."""
    result = _run("cp -tplugins/dev-team/hooks/ src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_cp_attached_clustered_short_target_directory_blocks_source(tmp_path: Path) -> None:
    """(#1904 item 13) The attached form also works with other clustered
    flags in front of the `t` (`-rtDIR`)."""
    result = _run("cp -rtplugins/dev-team/hooks/ src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_cp_attached_short_target_directory_allows_python_source(tmp_path: Path) -> None:
    result = _run("cp -tplugins/dev-team/hooks/ src1.py", tmp_path)
    assert result.returncode == 0


def test_cp_abbreviated_long_target_directory_blocks_source(tmp_path: Path) -> None:
    """(#1904 item 13) `--target-dir=` is an unambiguous prefix-abbreviation
    of `--target-directory=` — cp/mv accept it via GNU getopt_long's own
    abbreviation rule."""
    result = _run("cp --target-dir=plugins/dev-team/hooks src1.sh", tmp_path)
    assert result.returncode == 2
    assert "src1.sh" in result.stdout


def test_cp_abbreviated_long_target_directory_allows_python_source(tmp_path: Path) -> None:
    result = _run("cp --target-dir=plugins/dev-team/hooks src1.py", tmp_path)
    assert result.returncode == 0


# --- (#1861) early-exit guard ------------------------------------------------


# --- (#1904 follow-up bypass) redirect operators beyond bare `>`/`>>` -----
#
# `_tokenize_command`'s shlex lexer groups a RUN of adjacent metacharacters
# into a single multi-character token — `&>`, `>&`, `>|`, and fd-duplication
# forms like `2>&1`/`1>&2` never match the exact `("\">\", \">>\")` check
# `_strip_redirects` used to make, so their operand (a real path or a bare
# fd number) survived into the positional list and could be picked as the
# cp/mv destination instead of the genuine one.


def test_ampersand_greater_redirect_does_not_evade_cp_destination_check(
    tmp_path: Path,
) -> None:
    """`&>` (bash: redirect both stdout+stderr) groups into one lexer
    token; unfixed code only recognized bare `>`/`>>`, so `/dev/null`
    became the destination heuristic's last positional and the real `cp`
    destination escaped detection."""
    result = _run("cp evil.sh plugins/dev-team/x.sh &> /dev/null", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/x.sh" in result.stdout


def test_output_duplication_redirect_does_not_evade_cp_destination_check(
    tmp_path: Path,
) -> None:
    """`>&2` (duplicate stdout onto fd 2) groups into `>&` + `2`; unfixed
    code stripped neither, so the bare `2` became the last positional."""
    result = _run("cp evil.sh plugins/dev-team/x.sh >&2", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/x.sh" in result.stdout


def test_fd_prefixed_duplication_redirect_does_not_evade_cp_destination_check(
    tmp_path: Path,
) -> None:
    """`1>&2` (fd-prefixed duplication, same family as `2>&1`) tokenizes as
    `1`, `>&`, `2` — the fd-digit branch only recognized a following
    literal `>`/`>>`, so it never consumed this operator+operand pair."""
    result = _run("cp evil.sh plugins/dev-team/x.sh 1>&2", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/x.sh" in result.stdout


def test_pipe_with_stderr_separator_segments_correctly(tmp_path: Path) -> None:
    """`|&` (bash shorthand for `2>&1 |`) is a command separator, not a
    redirect — unfixed code had it missing from `_COMMAND_SEPARATORS`, so
    the whole command stayed one un-split segment whose `prog` resolved to
    `true`, never reaching the cp/mv check at all."""
    result = _run("true |& cp evil.sh plugins/dev-team/x.sh", tmp_path)
    assert result.returncode == 2
    assert "plugins/dev-team/x.sh" in result.stdout


def test_force_overwrite_redirect_still_detected(tmp_path: Path) -> None:
    """`>|` (bash noclobber-override) sits outside `_REDIRECT_RE`'s
    capture-start character class (`|` is excluded), so the whole regex
    failed to match and the write escaped `_redirect_targets` entirely."""
    result = _run("echo hi >| plugins/dev-team/hooks/evil.sh", tmp_path)
    assert result.returncode == 2
    assert "evil.sh" in result.stdout


def test_quoted_semicolon_argument_known_limitation_evades_scan(tmp_path: Path) -> None:
    """KNOWN LIMITATION (see `_is_operator_token`'s docstring): a quoted
    `";"` argument normalizes to the identical token text as the real
    unquoted `;` separator after posix `shlex` processing, so `tee` is
    incorrectly split from its own literal destination argument and the
    destination evades detection. Documented as current (imperfect)
    behavior, not silently left unaddressed — see the docstring for the
    fix-cost rationale."""
    result = _run('tee ";" plugins/dev-team/hooks/evil.sh', tmp_path)
    assert result.returncode == 0


def test_missing_plugin_scope_dir_skips_scan(tmp_path_factory: pytest.TempPathFactory) -> None:
    """A downstream install with no plugins/dev-team/ tree on disk must not
    be scanned at all — even a command that would otherwise match a banned
    write pattern is allowed through. Uses its own directory (not the
    module's autouse `_plugin_scope_dir`-seeded `tmp_path`) so the guard's
    absence condition is genuinely exercised."""
    root = tmp_path_factory.mktemp("downstream-install")
    result = _run("echo hi > plugins/dev-team/hooks/foo.sh", root)
    assert result.returncode == 0
