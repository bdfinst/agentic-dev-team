"""Content guard for #1656: every `${CLAUDE_PLUGIN_ROOT}` expansion inside a
shell-flavored fenced code block must be quoted.

An unquoted `${CLAUDE_PLUGIN_ROOT}/scripts/x.py` breaks under word-splitting
the moment the plugin is installed under a path containing a space (the
default macOS `~/Library/Application Support/...` cache tree is exactly such
a path). #1656 swept every existing instance to `"${CLAUDE_PLUGIN_ROOT}/..."`
across 28 files; this guard is the regression test that keeps a future
SKILL.md/doc edit from reintroducing an unquoted one.

Scope is deliberately narrow: only `bash`/`sh`/`shell`/untagged fenced code
blocks are checked. A `${CLAUDE_PLUGIN_ROOT}` mention inside a `markdown`-
tagged illustrative block (e.g. `skills/pr/SKILL.md`'s own HTML-comment
example of what a rendered artifact looks like) or in prose outside any
fence is not a shell invocation and quoting it would be meaningless.

Fence tracking is per-line, matching this repo's own established lesson
(see `test_bare_invocation_wide_scan.py`'s docstring) that a blob-wide regex
can bridge a fence's own opening line with an unrelated line beyond it.

**Residual gap (ADR 0033's Consequences):** `_UNQUOTED_EXPANSION_RE` checks
for an OPENING quote only, not a balanced closing one — a malformed partial
form like `"${CLAUDE_PLUGIN_ROOT}"/scripts/x.py` is not distinguished from
the fully quoted form. Accepted: the uncaught shapes are either a visible
shell syntax error or already word-split-safe.

**Fences indented inside a list item are still fences.** A first draft of
this guard anchored the fence regex at column 0 (`^```...`), which made every
fence indented under a numbered/bulleted step — the majority shape in this
repo's own SKILL.md files, e.g. `skills/cost-report/SKILL.md`'s numbered
steps — invisible to the scanner: `in_fence` never flipped, so nothing
inside those blocks was ever checked. Verified against the real tree before
fixing (a gate that cannot fail is worse than no gate): several of the
lines #1656's own sweep quoted sit inside exactly such indented fences.
`_FENCE_RE` therefore allows arbitrary leading whitespace before the marker.

**Both the braced and unbraced spellings are in scope.** This repo's own
convention (ADR 0032) uses `${CLAUDE_PLUGIN_ROOT}` in most places but
`$CLAUDE_PLUGIN_ROOT` (no braces) in a few — both word-split identically
when unquoted, so `_UNQUOTED_EXPANSION_RE` matches either form.

**A fence's own marker length matters.** `skills/plan/references/plan-template.md`
wraps its whole example in a 4-backtick fence specifically so a real
3-backtick fence can appear, unescaped, as literal template content inside
it. Recognizing only exactly-3-backtick markers would mis-toggle on that
inner content, opening/closing "fences" that are actually just template
text. `_FENCE_RE` captures the marker's own backtick-run length, and a
candidate closer only closes the currently-open fence when its run is at
least as long as the opener's — shorter backtick runs nested inside a
longer-fenced block are literal content, not real delimiters.
"""

from __future__ import annotations

import re

import pytest

from _content_guard_scan import PLUGIN_MARKDOWN_SCAN_DIRS, scanned_markdown_files
from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
_SHELL_LANGS = {"", "bash", "sh", "shell"}

_FENCE_RE = re.compile(r"^\s*(`{3,})(\w*)\s*$")
_UNQUOTED_EXPANSION_RE = re.compile(r'(?<!")\$\{?CLAUDE_PLUGIN_ROOT\}?\b')

SCANNED_FILES = scanned_markdown_files(PLUGIN_ROOT, PLUGIN_MARKDOWN_SCAN_DIRS)
assert len(SCANNED_FILES) > 100, (
    f"only {len(SCANNED_FILES)} files found under {PLUGIN_MARKDOWN_SCAN_DIRS} — "
    "a typo'd or missing scan dir would silently disable this guard entirely"
)


def _unquoted_expansions(text: str):
    """[(lineno, line_text), ...] for every unquoted `${CLAUDE_PLUGIN_ROOT}`
    found inside a bash/sh/shell/untagged fenced code block in `text`."""
    lines = text.splitlines()
    hits = []
    in_fence = False
    lang = None
    opener_marker_len = 0
    for lineno, line in enumerate(lines, start=1):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker_len = len(fence_match.group(1))
            if in_fence:
                if marker_len >= opener_marker_len:
                    in_fence = False
                    lang = None
                    opener_marker_len = 0
                # A shorter run nested inside a longer-fenced block is
                # literal content (e.g. a 3-backtick example inside a
                # 4-backtick wrapper), not a real delimiter — fall through
                # without toggling.
            else:
                in_fence = True
                lang = fence_match.group(2).lower()
                opener_marker_len = marker_len
            continue
        if in_fence and lang in _SHELL_LANGS and _UNQUOTED_EXPANSION_RE.search(line):
            hits.append((lineno, line.strip()))
    return hits


@pytest.mark.parametrize("path", SCANNED_FILES, ids=lambda p: p.relative_to(PLUGIN_ROOT).as_posix())
def test_claude_plugin_root_is_quoted_in_shell_fences(path):
    rel = path.relative_to(PLUGIN_ROOT).as_posix()
    offenders = _unquoted_expansions(path.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{rel}: unquoted ${{CLAUDE_PLUGIN_ROOT}} inside a shell fenced code "
        'block — quote it as "${CLAUDE_PLUGIN_ROOT}/..." so the path survives '
        "word-splitting once installed under a space-containing path:\n  "
        + "\n  ".join(f"{lineno}: {line}" for lineno, line in offenders)
    )


class TestFenceScopingBehavior:
    """Synthetic fixtures proving the scanner flags unquoted expansions only
    inside shell-flavored fences, and never inside a non-shell fence or bare
    prose — mirroring the fence-boundary lesson from
    `test_bare_invocation_wide_scan.py`."""

    def test_unquoted_expansion_in_bash_fence_is_flagged(self):
        text = "```bash\npython3 ${CLAUDE_PLUGIN_ROOT}/scripts/x.py\n```\n"
        hits = _unquoted_expansions(text)
        assert len(hits) == 1
        assert hits[0][0] == 2

    def test_quoted_expansion_in_bash_fence_is_not_flagged(self):
        text = '```bash\npython3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"\n```\n'
        assert _unquoted_expansions(text) == []

    def test_untagged_fence_is_still_scanned(self):
        text = "```\npython3 ${CLAUDE_PLUGIN_ROOT}/scripts/x.py\n```\n"
        hits = _unquoted_expansions(text)
        assert len(hits) == 1

    def test_non_shell_fence_is_not_scanned(self):
        text = "```markdown\n<!-- Per ${CLAUDE_PLUGIN_ROOT}/knowledge/x.md -->\n```\n"
        assert _unquoted_expansions(text) == []

    def test_prose_outside_any_fence_is_not_scanned(self):
        text = "See ${CLAUDE_PLUGIN_ROOT}/scripts/x.py for details.\n"
        assert _unquoted_expansions(text) == []

    def test_fence_indented_inside_a_list_item_is_still_scanned(self):
        """Regression fixture: an earlier draft anchored `_FENCE_RE` at
        column 0, so a fence indented under a numbered/bulleted step (this
        repo's own dominant SKILL.md shape) was invisible — see module
        docstring."""
        text = (
            "1. Do the thing:\n\n"
            "   ```bash\n"
            "   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/x.py\n"
            "   ```\n"
        )
        hits = _unquoted_expansions(text)
        assert len(hits) == 1
        assert hits[0][0] == 4

    def test_unbraced_expansion_is_also_scanned(self):
        """`$CLAUDE_PLUGIN_ROOT/path` (no braces) word-splits identically to
        the braced form when unquoted — both spellings are in scope."""
        text = "```bash\npython3 $CLAUDE_PLUGIN_ROOT/scripts/x.py\n```\n"
        hits = _unquoted_expansions(text)
        assert len(hits) == 1

    def test_quoted_unbraced_expansion_is_not_flagged(self):
        text = '```bash\npython3 "$CLAUDE_PLUGIN_ROOT/scripts/x.py"\n```\n'
        assert _unquoted_expansions(text) == []

    def test_shorter_fence_nested_inside_a_longer_one_is_literal_content(self):
        """Regression fixture for `skills/plan/references/plan-template.md`'s
        shape: a 4-backtick outer fence wrapping a 3-backtick example as
        literal text. The inner ```-lines must not be mistaken for real
        fence delimiters, and content between them (still inside the outer
        `markdown`-tagged fence) must not be scanned."""
        text = (
            "````markdown\n"
            "Example:\n"
            "```bash\n"
            "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/x.py\n"
            "```\n"
            "````\n"
        )
        assert _unquoted_expansions(text) == []
