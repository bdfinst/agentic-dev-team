# 33. Quote every `${CLAUDE_PLUGIN_ROOT}` expansion in a shell fence

Date: 2026-08-01

## Status

Accepted

## Context

ADR 0032 names the house style for a shipped-and-portable script reference —
`${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`, or its quoted equivalent,
`"$CLAUDE_PLUGIN_ROOT/scripts/<name>.py"`. Its category-1 text originally
deferred the quoting half of that sentence to a then-pending ADR for #1656
("house style per ADR-pending #1656"); this ADR is that destination, and
ADR 0032 now points here instead.

An unquoted `${CLAUDE_PLUGIN_ROOT}/scripts/x.py` word-splits the moment the
plugin is installed under a path containing a space — the default macOS
`~/Library/Application Support/...` cache tree is exactly such a path. Bash
does not word-split inside double quotes, so `"${CLAUDE_PLUGIN_ROOT}/scripts/
x.py"` is safe regardless of what the variable expands to.

#1656 found 77 unquoted instances across 28 shipped `SKILL.md`/docs/knowledge
files and swept every one to the quoted form. A regression guard
(`tests/repo/test_claude_plugin_root_quoting.py`) was added in the same
change so a future edit can't reintroduce an unquoted expansion silently.

## Decision

Every `${CLAUDE_PLUGIN_ROOT}` (braced) or `$CLAUDE_PLUGIN_ROOT` (unbraced)
expansion inside a `bash`/`sh`/`shell`/untagged fenced code block in a
shipped `plugins/dev-team/{skills,docs,knowledge,agents}/**/*.md` file must
be quoted — the whole path token, not just the variable
(`"${CLAUDE_PLUGIN_ROOT}/scripts/x.py"`, not `${CLAUDE_PLUGIN_ROOT}"/scripts/
x.py"` or similar partial forms).

Both spellings — braced and unbraced — are in scope; this repo uses the
braced form in most places and the unbraced form in a few (e.g.
`sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" ...`), and both word-split identically
when unquoted.

A mention of `${CLAUDE_PLUGIN_ROOT}` outside any fence (prose, an HTML
comment illustrating rendered output) or inside a non-shell-flavored fence
(e.g. a `markdown`-tagged illustrative block) is not a shell invocation and
quoting it would be meaningless — out of this decision's scope.

Enforced by `tests/repo/test_claude_plugin_root_quoting.py`, which tracks
fence state per-line (open/close toggled by the marker's own backtick-run
length, so a shorter run nested inside a longer-fenced block — e.g.
`skills/plan/references/plan-template.md`'s 4-backtick wrapper around a
3-backtick example — is treated as literal content, not a real delimiter)
and allows arbitrary leading whitespace before a fence marker, so a fence
indented under a numbered/bulleted step (this repo's own dominant SKILL.md
shape) is still recognized.

## Consequences

- ADR 0032's category-1 forward reference now resolves to something.
- A future SKILL.md/doc edit that introduces a new, unquoted
  `${CLAUDE_PLUGIN_ROOT}`/`$CLAUDE_PLUGIN_ROOT` reference inside a shell
  fence fails CI rather than shipping silently.
- Does not cover a `${CLAUDE_PLUGIN_ROOT}` reference inside a shipped `.py`
  script's own string literals (e.g. a printed remediation hint) — those are
  reviewed case by case against ADR 0032's taxonomy instead, since a
  script's own working directory and mutation target (not word-splitting
  safety) is usually the more load-bearing question there.
- The guard tracks the closing quote, not just the opening one: a quote that
  closes partway through the token — `"${CLAUDE_PLUGIN_ROOT}"/scripts/x.py`,
  leaving `/scripts/x.py` outside the quotes — is distinguished from the
  fully quoted `"${CLAUDE_PLUGIN_ROOT}/scripts/x.py"` and flagged as a
  partial form. Trailing shell syntax with no space before the close (a
  command substitution's `)`, `;`, a backtick, a pipe/redirect) is not part
  of the path token and does not trigger a false positive.

## References

- Issue #1656 — this ADR's originating issue
- ADR 0032 — the shipped-script path-resolution taxonomy this decision's
  house style extends
- `tests/repo/test_claude_plugin_root_quoting.py` — the enforcement
