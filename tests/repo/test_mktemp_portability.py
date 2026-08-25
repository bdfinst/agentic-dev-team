"""`mktemp -t` is not portable, and it fails silently (issue #1993).

GNU coreutils treats the argument to `-t` as a template and honors `$TMPDIR`.
BSD/macOS treats it as a literal *prefix*, ignores `$TMPDIR` entirely, and
resolves the per-user temp directory via `confstr(_CS_DARWIN_USER_TEMP_DIR)`:

    $ export TMPDIR=/tmp/scratch
    $ mktemp -t prepush-worktree-paths-pre-XXXXXX
    /var/folders/k7/tfy.../T/prepush-worktree-paths-pre-XXXXXX.DygvyYDoaU

Note the file is not under `$TMPDIR`, and `XXXXXX` survives literally with a
BSD-chosen suffix appended.

That is not a style preference. `.husky/pre-push` writes a worktree-path
snapshot that `tests/repo/test_pre_push_ref_guard.py` locates by pointing
`$TMPDIR` at a test-controlled directory — so on macOS the snapshot went
somewhere the test could not see it, two tests failed, and because the
`pre-push` hook runs the full `ci-local.sh`, **every local push from a Mac was
blocked**. It passed on Ubuntu CI the whole time. Every maintainer here
develops on macOS; every gate runs on Ubuntu.

`mktemp "${TMPDIR:-/tmp}/prefix-XXXXXX"` behaves identically on both.

This is the same shape as the Python floor/ceiling gates that CLAUDE.md
records: a gate bounds only the platform it can observe, and the unobserved
end is where the bug lives. Until a macOS CI leg exists (issue #1993 item 3,
still open), this grep is the mechanism keeping the class out.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from _repo_root import REPO_ROOT

#: `mktemp -t` / `mktemp -d -t`, with the flags in either order.
_MKTEMP_T_RE = re.compile(r"\bmktemp\b(?:\s+-[A-Za-z]+)*\s+-[A-Za-z]*t\b")

#: Extensions worth scanning. Shell is where `mktemp` is invoked; the markdown
#: sweep keeps documentation from teaching the non-portable form back in.
_SHELL_SUFFIXES = (".sh", ".bash", ".bats", ".zsh")


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    return [f for f in out.split("\0") if f]


def _is_shell(path: str) -> bool:
    if path.endswith(_SHELL_SUFFIXES):
        return True
    # Extensionless hooks (.husky/pre-push, .husky/post-commit, ...) are shell.
    return path.startswith(".husky/") and "." not in path.rsplit("/", 1)[-1]


def _offenders(paths: list[str]) -> list[str]:
    hits = []
    for rel in paths:
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except (OSError, IsADirectoryError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue  # prose about the banned form, not a use of it
            if _MKTEMP_T_RE.search(line):
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def test_no_shell_script_uses_the_non_portable_mktemp_t_form():
    offenders = _offenders([p for p in _tracked_files() if _is_shell(p)])
    assert not offenders, (
        "`mktemp -t` is not portable: BSD/macOS ignores $TMPDIR and treats the "
        "argument as a literal prefix, so the file does not land where the "
        "caller asked (issue #1993). Use a full template path instead:\n"
        '    mktemp "${TMPDIR:-/tmp}/my-prefix-XXXXXX"\n'
        '    mktemp -d "${TMPDIR:-/tmp}/my-prefix-XXXXXX"\n\n'
        + "\n".join(offenders)
    )


def test_the_pre_push_hook_places_its_temp_files_under_tmpdir():
    """The specific regression: the hook's snapshot must honor $TMPDIR.

    Asserted on the hook's own text rather than by running it, because the
    surrounding suite already executes the hook — what is pinned here is that
    every one of its temp files is created the portable way, including any
    added later.
    """
    hook = (REPO_ROOT / ".husky" / "pre-push").read_text(encoding="utf-8")
    # Match the `mktemp` COMMAND, not the substring: the hook's own helper is
    # named `_prepush_mktemp`, and every call site would otherwise look like a
    # bare invocation missing its template.
    invocation = re.compile(r"(?:^|[;&|(`$\s])mktemp\b")
    mktemp_lines = [
        ln.strip()
        for ln in hook.splitlines()
        if invocation.search(ln) and not ln.strip().startswith("#")
    ]
    assert mktemp_lines, "expected .husky/pre-push to create temp files"
    for line in mktemp_lines:
        assert "${TMPDIR:-" in line, (
            f"pre-push creates a temp file without an explicit $TMPDIR-rooted "
            f"template, so it will not land under $TMPDIR on macOS: {line}"
        )


@pytest.mark.parametrize(
    "command",
    [
        'mktemp -t foo-XXXXXX',
        'mktemp -d -t foo-XXXXXX',
        'x="$(mktemp -t foo.XXXXXX)"',
        'mktemp -q -t foo-XXXXXX',
    ],
)
def test_the_detector_matches_the_forms_it_claims_to(command, tmp_path):
    """A guard that cannot fail is worse than no gate (CLAUDE.md).

    These are the shapes the repo has actually used, plus the flag-order and
    flag-combination variants a future edit could reach for.
    """
    assert _MKTEMP_T_RE.search(command), command


@pytest.mark.parametrize(
    "command",
    [
        'mktemp "${TMPDIR:-/tmp}/foo-XXXXXX"',
        'mktemp -d "${TMPDIR:-/tmp}/foo-XXXXXX"',
        'mktemp -d',
        'mktemp',
        'echo "use mktemp with a template"',
    ],
)
def test_the_detector_does_not_match_portable_forms(command):
    assert not _MKTEMP_T_RE.search(command), command
