r"""#2036 — the commit-bypass gate signal must scope to the git-commit argv,
not search the raw command string.

Both session-report extractors independently carried the identical bug:
`_COMMIT_RE = re.compile(r"\bgit\s+commit\b")` /
`_BYPASS_RE = re.compile(r"--no-verify|(^|\s)-n(\s|$)")`, searched against the
WHOLE command string. Neither pattern was anchored to an actual `git commit`
invocation, so any `-n` anywhere in a compound Bash call counted as a
review-gate bypass — `grep -n`, `rg -n`, `ls -n` are routine — and
`_COMMIT_RE` matched the substring "git commit" even inside an unrelated
string (`echo "git commit"`). #2036 found an unknown share of the reported
13.5% bypass rate across 33 projects was this noise, not real bypasses.

This module drives the table from the issue directly against
`session_log.signals.track_bash` — the single shared implementation both
`session_report.py` profiles now alias (epic #2040 unified what were, at
#2036's time, two independently-drifting copies; see ADR 0036, superseded).
"""

from __future__ import annotations

from collections import Counter

import pytest

from _repo_root import REPO_ROOT

# --- the table from #2036 (plus the three new argv-shaped cases) ----------
# (command, expect_attempt, expect_bypass)
CASES = [
    pytest.param('git commit -m "fix"', True, False, id="plain-commit"),
    pytest.param(
        "git commit --no-verify -m x", True, True, id="explicit-no-verify"
    ),
    pytest.param(
        'git commit -m "fix" && grep -n TODO src/',
        True,
        False,
        id="compound-grep-n-not-a-bypass",
    ),
    pytest.param(
        "git commit -m x; rg -n foo", True, False, id="compound-rg-n-not-a-bypass"
    ),
    pytest.param(
        'echo "git commit" && ls -n',
        False,
        False,
        id="commit-substring-inside-echo-is-not-an-attempt",
    ),
    pytest.param("git commit -n", True, True, id="bare-n-flag-is-a-bypass"),
    pytest.param(
        "git -C path commit -n",
        True,
        True,
        id="global-option-with-arg-before-subcommand",
    ),
    pytest.param(
        'git commit -m "pass -n to grep"',
        True,
        False,
        id="quoted--n-inside-commit-message-is-not-a-bypass",
    ),
    pytest.param(
        'git commit -m "line one\nline two"',
        True,
        False,
        id="unquoted-vs-quoted-newline-embedded-message-not-split",
    ),
]


def _session_log_signals(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(
        str(REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib")
    )
    from session_log import signals

    return signals


@pytest.mark.parametrize("cmd,expect_attempt,expect_bypass", CASES)
def test_track_bash_commit_bypass_scoping(
    cmd, expect_attempt, expect_bypass, monkeypatch: pytest.MonkeyPatch
) -> None:
    signals = _session_log_signals(monkeypatch)
    block = {"name": "Bash", "input": {"command": cmd}}
    counts = Counter()
    signals.track_bash(block, counts, signals.new_thread())
    assert counts["commit_attempts"] == (1 if expect_attempt else 0)
    assert counts["commit_bypasses"] == (1 if expect_bypass else 0)


# --- a real invocation still counts once per real git-commit segment -------


def test_two_real_commits_in_one_bash_call_count_as_two_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deliberate behavior change from the pre-#2036 whole-string search,
    which could only ever detect one attempt per Bash call regardless of how
    many `git commit`s it chained. Segmenting by shell operator means each
    real invocation is counted — strictly more correct, and worth pinning
    explicitly since it changes what the raw counter means."""
    signals = _session_log_signals(monkeypatch)
    block = {
        "name": "Bash",
        "input": {"command": 'git commit -m a && git commit -m b --no-verify'},
    }
    counts = Counter()
    signals.track_bash(block, counts, signals.new_thread())
    assert counts["commit_attempts"] == 2
    assert counts["commit_bypasses"] == 1
