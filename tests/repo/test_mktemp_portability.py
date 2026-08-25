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

#: A `mktemp` invocation carrying a `-t` flag anywhere in its arguments —
#: including after the template (`mktemp foo-XXXXXX -t`), which a
#: flag-adjacency pattern would miss. Applied to comment-stripped,
#: continuation-joined logical lines (see _logical_lines).
_MKTEMP_T_RE = re.compile(r"\bmktemp\b[^\n]*?(?:\s|^)-[A-Za-z]*t\b")

#: Extensions worth scanning. Shell is where `mktemp` is invoked.
_SHELL_SUFFIXES = (".sh", ".bash", ".bats", ".zsh")

#: Prose is allowed to NAME the banned form only where it exists to ban it —
#: same "accounted for, or excluded WITH a reason" convention as
#: test_python_floor.py's SLICE_EXCLUSIONS. Anything else teaching the form is
#: a finding, because a README example is how it gets copied back into a script.
_DOCS_THAT_MAY_NAME_THE_BANNED_FORM = {
    "CLAUDE.md": "records the #1993 lesson alongside the Python floor/ceiling story",
}


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    return [f for f in out.split("\0") if f]


def _is_shell(path: str) -> bool:
    if path.endswith(_SHELL_SUFFIXES):
        return True
    # GitHub Actions `run:` blocks are shell, in a file named .yml. Scanning the
    # raw YAML is coarse but errs toward catching a real reintroduction.
    if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
        return True
    # Extensionless hooks (.husky/pre-push, .husky/post-commit, ...) are shell.
    return path.startswith(".husky/") and "." not in path.rsplit("/", 1)[-1]


def _logical_lines(text: str):
    """(lineno, code) pairs with continuations joined and comments stripped.

    Both matter to a per-line grep: an invocation split over `mktemp \\` +
    `  -t foo-XXXXXX` has the command and the flag on different physical lines,
    and a trailing `# ... mktemp -t ...` comment is prose, not a use.
    """
    buf, start = "", 1
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not buf:
            start = lineno
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
            continue
        line = buf + raw
        buf = ""
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue  # prose about the banned form, not a use of it
        # Drop a trailing comment, but only outside quotes.
        code, quote = [], None
        for ch in line:
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                break
            code.append(ch)
        yield start, "".join(code)
    if buf:
        yield start, buf


def _offenders(paths: list[str]) -> list[str]:
    hits = []
    for rel in paths:
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except (OSError, IsADirectoryError):
            continue
        for lineno, code in _logical_lines(text):
            if _MKTEMP_T_RE.search(code):
                hits.append(f"{rel}:{lineno}: {code.strip()}")
    return hits


#: A quoted or bare `mktemp` argument containing a run of Xs — the template.
_TEMPLATE_ARG_RE = re.compile(r"""(?:"([^"]*XXX+[^"]*)"|'([^']*XXX+[^']*)'|(\S*XXX+\S*))""")


def _template_args(line: str) -> list[str]:
    """Every `mktemp` template argument on one line, quotes stripped."""
    if "mktemp" not in line:
        return []
    after = line[line.index("mktemp") + len("mktemp"):]
    return [next(g for g in m.groups() if g) for m in _TEMPLATE_ARG_RE.finditer(after)]


#: Files that COMPOSE shell rather than being shell — a hook building a
#: command string is just as able to ship a broken template, and neither the
#: shell-suffix filter nor a `-t` regex would ever look at it. Found the hard
#: way: session_learning_trigger.py shipped this exact defect.
_SHELL_COMPOSING_SUFFIXES = (".py", ".js", ".mjs", ".ts")


#: This file names every banned shape on purpose, in prose and in fixtures.
_SELF = "tests/repo/test_mktemp_portability.py"


def _shell_bearing_files() -> list[str]:
    """Shell files plus any file whose text invokes `mktemp`."""
    out = []
    for rel in _tracked_files():
        if rel == _SELF:
            continue
        if _is_shell(rel):
            out.append(rel)
        elif rel.endswith(_SHELL_COMPOSING_SUFFIXES):
            try:
                if "mktemp" in (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace"):
                    out.append(rel)
            except (OSError, IsADirectoryError):
                continue
    return out


def test_no_mktemp_template_puts_characters_after_the_xs():
    """BSD mktemp substitutes only a TRAILING run of Xs.

    `mktemp "$TMPDIR/foo-XXXXXX.log"` therefore creates a file named literally
    `foo-XXXXXX.log` — a fixed, predictable path — and the NEXT call fails with
    "File exists". Verified on macOS. GNU substitutes it, so this is another
    silent GNU/BSD split, and it is the trap the #1993 fix itself first fell
    into while removing the `-t` one.
    """
    offenders = []
    for rel in _shell_bearing_files():
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except (OSError, IsADirectoryError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for template in _template_args(line):
                if not re.search(r"XXX+$", template):
                    offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "A mktemp template must END with its Xs — BSD substitutes only a "
        "trailing run, so anything after them is taken literally and the "
        "resulting fixed path collides on the next call (issue #1993):\n"
        '    mktemp "${TMPDIR:-/tmp}/foo-XXXXXX"        # correct\n'
        '    mktemp "${TMPDIR:-/tmp}/foo-XXXXXX.log"    # fixed name, then EEXIST\n\n'
        + "\n".join(offenders)
    )


def test_the_shell_file_enumeration_actually_finds_files():
    """The sweep below asserts an EMPTY list, which a broken enumeration
    satisfies just as well as a clean repo.

    If `git ls-files` regressed, `REPO_ROOT` drifted, or `_is_shell` were
    narrowed, every offender check here would go quietly green — "a gate that
    cannot fail is worse than no gate" (CLAUDE.md). Anchor it on files that
    must exist.
    """
    shell_files = [p for p in _tracked_files() if _is_shell(p)]
    assert ".husky/pre-push" in shell_files
    assert "scripts/ci-local.sh" in shell_files
    assert len(shell_files) > 20, f"suspiciously few shell files: {len(shell_files)}"

    docs = [p for p in _tracked_files() if p.endswith((".md", ".mdx"))]
    assert "CLAUDE.md" in docs
    assert len(docs) > 20, f"suspiciously few markdown files: {len(docs)}"


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


def test_no_documentation_teaches_the_non_portable_form():
    """Docs are how the next contributor learns the form.

    A guard over shell files alone lets `mktemp -t` live on in a README or a
    skill's instructions, from where it gets copied back into a script — so
    the prose is swept too. Fenced shell examples are the realistic vector.
    """
    docs = [p for p in _tracked_files() if p.endswith((".md", ".mdx"))]
    offenders = [
        o for o in _offenders(docs)
        if o.split(":", 1)[0] not in _DOCS_THAT_MAY_NAME_THE_BANNED_FORM
    ]
    assert not offenders, (
        "Documentation teaches `mktemp -t`, which is not portable (issue "
        "#1993). Use `mktemp \"${TMPDIR:-/tmp}/prefix-XXXXXX\"` in examples:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    "command",
    [
        'mktemp -t foo-XXXXXX',
        'mktemp -d -t foo-XXXXXX',
        'x="$(mktemp -t foo.XXXXXX)"',
        'mktemp -q -t foo-XXXXXX',
        'mktemp foo-XXXXXX -t',
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


def test_a_trailing_comment_naming_the_form_is_not_a_finding(tmp_path):
    """Prose on a code line is prose. Scanning the raw line flagged it."""
    lines = list(_logical_lines('echo hi  # never use mktemp -t here\n'))
    assert not any(_MKTEMP_T_RE.search(code) for _, code in lines), lines


def test_a_continuation_split_invocation_is_still_a_finding():
    """`mktemp \\` + `  -t foo` puts the command and the flag on different
    physical lines, so a per-line grep sees neither."""
    text = 'LOG=$(mktemp \\\n  -t foo-XXXXXX)\n'
    assert any(_MKTEMP_T_RE.search(code) for _, code in _logical_lines(text)), \
        list(_logical_lines(text))


def test_a_hash_inside_quotes_is_not_treated_as_a_comment():
    """Stripping at the first `#` regardless of quoting would truncate a real
    command and hide a `-t` after it."""
    text = 'mktemp "pre#fix-XXXXXX" -t\n'
    assert any(_MKTEMP_T_RE.search(code) for _, code in _logical_lines(text)), \
        list(_logical_lines(text))
