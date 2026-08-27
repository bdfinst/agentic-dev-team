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

This module drives the table from the issue directly against both
extractors' `_track_bash`, parametrized so a regression in either copy is
caught — the two are deliberately still separate implementations (their
unification is epic #2040's job, not this fix's), so nothing but an identical
test run twice keeps them in agreement.
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


def _session_extract(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts"))
    import session_extract

    return session_extract


def _extract_session_report(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(
        str(REPO_ROOT / "plugins" / "dev-team" / "scripts")
    )
    import extract_session_report

    return extract_session_report


@pytest.mark.parametrize("cmd,expect_attempt,expect_bypass", CASES)
def test_session_extract_commit_bypass_scoping(
    cmd, expect_attempt, expect_bypass, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _session_extract(monkeypatch)
    block = {"name": "Bash", "input": {"command": cmd}}
    bash_commands = Counter()
    signals = Counter()
    mod._track_bash(block, "sid-1", bash_commands, signals, {}, {})
    assert signals["commit_attempts"] == (1 if expect_attempt else 0)
    assert signals["commit_bypasses"] == (1 if expect_bypass else 0)


@pytest.mark.parametrize("cmd,expect_attempt,expect_bypass", CASES)
def test_extract_session_report_commit_bypass_scoping(
    cmd, expect_attempt, expect_bypass, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _extract_session_report(monkeypatch)
    block = {"name": "Bash", "input": {"command": cmd}}
    thread = mod._new_thread()
    signals = Counter()
    mod._track_bash(block, signals, thread)
    assert signals["commit_attempts"] == (1 if expect_attempt else 0)
    assert signals["commit_bypasses"] == (1 if expect_bypass else 0)


# --- both extractors must agree on the same input, per #2036's acceptance --


@pytest.mark.parametrize("cmd,expect_attempt,expect_bypass", CASES)
def test_both_extractors_agree(
    cmd, expect_attempt, expect_bypass, monkeypatch: pytest.MonkeyPatch
) -> None:
    se = _session_extract(monkeypatch)
    esr = _extract_session_report(monkeypatch)

    block = {"name": "Bash", "input": {"command": cmd}}

    se_signals = Counter()
    se._track_bash(block, "sid-1", Counter(), se_signals, {}, {})

    esr_signals = Counter()
    esr._track_bash(block, esr_signals, esr._new_thread())

    assert se_signals["commit_attempts"] == esr_signals["commit_attempts"]
    assert se_signals["commit_bypasses"] == esr_signals["commit_bypasses"]


# --- a real invocation still counts once per real git-commit segment -------


def test_two_real_commits_in_one_bash_call_count_as_two_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deliberate behavior change from the pre-#2036 whole-string search,
    which could only ever detect one attempt per Bash call regardless of how
    many `git commit`s it chained. Segmenting by shell operator means each
    real invocation is counted — strictly more correct, and worth pinning
    explicitly since it changes what the raw counter means."""
    mod = _session_extract(monkeypatch)
    block = {
        "name": "Bash",
        "input": {"command": 'git commit -m a && git commit -m b --no-verify'},
    }
    signals = Counter()
    mod._track_bash(block, "sid-1", Counter(), signals, {}, {})
    assert signals["commit_attempts"] == 2
    assert signals["commit_bypasses"] == 1
