"""hooks/lib/review_gate_normalized_hash.py — normalization-invariant gate
hash for cosmetic-delta carry-forward (#1627).

`review_gate_hash()` hashes the raw staged patch bytes, so ANY re-stage after
the corroborating dispatches — a whitespace fix, a markdown edit alongside
code — voids the evidence and forces fresh dispatches purely to re-satisfy
the gate. Those dispatches review nothing new; they exist only to feed the
ledger. #1623 §2 records 4 of the last ~5 sessions hitting
`dispatch-evidence-different-content`/`stale` blocks this way.

This module computes a SECOND hash, invariant under changes that provably
cannot alter behavior, so `pre_commit_review.py` can carry corroboration
forward across such a re-stage — **without** any exemption event, hook
bypass, or self-asserted claim.

## Why this does not reopen #1461

The exemption is a **property of content, recomputed by the hook itself at
gate time** from `git diff --cached`. It is not a claim written by the gated
party. Contrast the doc-only exemption, which already needed hook-side
re-derivation precisely because the ledger event is a self-assertion
(`pre_commit_doc_classifier.py`'s docstring) — here the re-derivation IS the
mechanism; there is no assertion at all. Ledger events still originate only
from genuine PreToolUse dispatch recording, and the forgery surface named in
`agent_dispatch_ledger.py`'s KNOWN RESIDUAL GAP is unchanged in kind.

Kept as a sibling module rather than folded into `review_gate_hash.py`,
following the `review_gate_corroboration.py` precedent named in the issue:
`review_gate_hash.py` is deliberately a minimal pure hash function with no
doc-classification knowledge, and this module's normalization needs exactly
that knowledge.

## What v1 normalizes — and what it deliberately does not

**Dropped:** hunks whose file is doc-classified, reusing
`pre_commit_doc_classifier.is_doc_only_changeset` per file — the same STRICT
predicate the doc-only exemption uses, including its "functional Claude-config
markdown is never documentation" carve-out. A "cosmetic" edit to `agents/`,
`skills/`, `.claude/`, `CLAUDE.md`, or any other enforcement machinery can
therefore never ride the carry-forward.

**Collapsed:** leading/trailing whitespace on a changed line — but only when
BOTH of the following hold. Each is a place where the obvious rule is
unsound, so each is a hard precondition, not a refinement:

1. **The file's language does not make indentation significant.** In Python,
   YAML, Haskell, and friends, dedenting a line moves it out of its block:

       for x in items:          for x in items:
           total += x               total += x
           return total         return total     # <- different behavior

   Both `return total` lines strip to the same text. Treating that as
   cosmetic would let a genuine control-flow change carry corroboration
   forward. Files with an indentation-significant extension
   (`_INDENT_SIGNIFICANT_EXTENSIONS`) therefore get **byte-exact**
   comparison — no whitespace normalization at all. The default for an
   unknown extension is also byte-exact: an extension this module has never
   heard of is not one it can prove is brace-delimited.

2. **The line carries no quote character** (`"`, `'`, or a backtick).
   Whitespace inside a string literal is data. A multi-line string's
   indentation is part of its value, and `"a  b"` vs `"a b"` is a behavior
   change that would otherwise read as cosmetic. Without language awareness
   the only sound language-agnostic rule is to keep every quote-bearing line
   out of the cosmetic bucket entirely.

Interior whitespace is NEVER collapsed under any circumstances. All of this
errs closed: a Python reindent, or an indentation fix on a quoted line,
simply doesn't get carry-forward — costing one re-dispatch rather than
weakening the gate.

## Unquoted multi-line literal bodies (#1638, #1660, #1661, #1667)

The quote-character rule above is what keeps string DATA out of the cosmetic
bucket — but it only sees quote characters, and a whole family of multi-line
literal forms carries a data body with no quote character on its interior
lines: Ruby's `<<~SQL`, PHP's `<<<TXT`, Perl's `<<EOF`, Lua's `[[ ]]`,
PostgreSQL's `$$ $$`, Go raw strings and JS/TS template literals, C++'s
`R"( )"`, and PHP's inline-HTML region between `?>` and `<?`.
`_heredoc_body_marks` tracks each language's grammars per hunk side
(`_HEREDOC_GRAMMARS`, extension-keyed so PHP's three-angle-bracket form can
never cross-match Ruby/Perl's two-angle-bracket form) and forces every line
between an opener and its closer to byte-exact comparison, bypassing
`_canonical_line`'s collapsible/quote-char rules entirely.

Failing closed here means three things, all load-bearing:

- **An opener with no closer inside the visible hunk side marks every
  remaining line, not just up to end-of-context.** The true close may be
  outside what this hunk shows; the safe assumption is that it hasn't
  closed yet, so nothing after it is eligible for whitespace collapsing.
- **An opener could be invisible entirely** — above the first line this
  function ever sees. `normalized_gate_hash` narrows that gap at the source
  by requesting `--unified=100000` context, so for any realistically-sized
  file every hunk spans start-to-end.
- **That context request is a magic number, so it is checked rather than
  trusted (#1662).** A file longer than the window still yields a hunk that
  does not start at line 1, and an opener above it is invisible — the exact
  hazard the grammars close, reopened silently, and failing OPEN rather than
  closed. `normalize_patch` therefore reads the hunk's declared start lines
  and drops any grammared file's non-line-1 hunk to byte-exact comparison
  instead of believing the context flag did its job.

The same call is bounded in both directions (#1663): an explicit subprocess
timeout on the `git diff`, and a cap on the patch size accepted for
processing. Whole-file context means a one-line edit to a large tracked file
(a `.json` lockfile, a generated fixture) otherwise produces and canonicalizes
that entire file, several in-memory copies deep, synchronously inside a
PreToolUse hook on every commit.

## What the canonical form must contain to bind a subject (#1631 review)

The first draft of this module compared, per file, the flat list of removed
lines against the flat list of added lines, and parsed the patch by
dispatching on line prefixes. An adversarial pass found five distinct
collisions where behaviorally different changesets normalized identically,
each of which let unreviewed content ride a carry-forward. All five are
closed here, and each fix is a hard requirement rather than a refinement:

1. **Hunks are consumed by their declared line counts.** Dispatching on
   `--- `/`+++ ` prefixes while inside a hunk is parser confusion: a REMOVED
   source line beginning `-- ` (a SQL/Lua/Haskell comment) renders as
   `--- ...`, was read as a file header, and silently terminated the hunk —
   so every following line in it, including injected code, vanished from the
   digest. An added line beginning `++ ` did the same via `+++ `. A malformed
   or over-running hunk is a parse failure, and fails closed.

2. **The canonical form is per HUNK, comparing each hunk's whole old side
   against its whole new side, context lines included.** Flat per-file
   removed/added lists carry no position, so inserting the same line at two
   different places in a file — `+audit()` before vs. after a call — produced
   one digest. Context lines are what make an insertion point part of the
   subject. A hunk whose two sides canonicalize identically is the true
   definition of a cosmetic hunk, and only then is it dropped.

3. **The collapse is per hunk, never across hunks.** Whole-file
   removed-equals-added treated a line MOVED between two hunks (a
   `lock.acquire()` relocated across a function) as formatting, because the
   file's removed and added lists matched.

4. **Changes carried entirely by patch metadata are recorded, not skipped.**
   A mode flip (`chmod +x`), a rename, a binary-file replacement, and an
   empty new file all produce a diff with NO hunk body. They were therefore
   invisible: staging one on top of an already-corroborated changeset left
   the digest untouched. The earlier rationale — "a mode change is real, but
   it is carried by the raw-hash lens, which is still evaluated first and
   still authoritative" — does not hold, because this lens runs precisely
   when the raw lens has already rejected. Binary files bind their `index`
   blob SHAs, which is the only content signal a textual diff exposes.

5. **An empty canonical form is never a digest.** `sha256("")` is a CONSTANT
   shared by every fully-cosmetic changeset AND by every dispatch recorded
   while the index was clean — so two review dispatches made before anything
   was staged stamped exactly the value a later mode-only or rename-only
   stage recomputes, satisfying the `>= 2` floor with evidence from agents
   that reviewed nothing. `normalized_gate_hash` returns `None` for an empty
   normalization, exactly as it does for a git failure and for the same
   reason: this lens only means something when two parties independently
   arrive at the same NON-TRIVIAL value.

Fixes 2 and 3 cost some invariance — a whitespace fix close enough to a
reviewed change that git merges their hunks now shifts the digest, and the
carry-forward is lost. That is the correct direction for this trade: a lost
carry-forward costs one re-dispatch, a spurious one admits unreviewed code.

**Deferred to v2:** comment-only stripping. It needs language awareness, and
string literals containing comment markers are a known trap. Gated on the
measured residual gate-block rate from #1624's recidivism metric.

## Fail-closed

Any parse or normalization error returns `None`. `pre_commit_review.py` treats
`None` as "this lens is not decisive" and falls through to today's exact
behavior — never to a pass. Same posture as every other read-side check in
the gate path.

Stdlib only. Python 3.8+. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Callable, NamedTuple

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from git_safe_diff import run_safe_git_diff
from pre_commit_doc_classifier import is_doc_only_changeset

#: Characters whose presence on a changed line disqualifies it from
#: strip-equality. See the module docstring: string literals are behavior.
_QUOTE_CHARS = ("\"", "'", "`")

#: Extensions of languages where leading whitespace carries meaning, so a
#: changed line's indentation can never be normalized away. Deliberately
#: over-inclusive: an extension listed here in error costs a re-dispatch; one
#: missing lets a control-flow change look cosmetic. Unknown extensions get
#: the same byte-exact treatment (see `_whitespace_collapsible`) — this set
#: exists to document the known cases, not to define the safe default.
_INDENT_SIGNIFICANT_EXTENSIONS = frozenset(
    {
        ".py", ".pyi", ".pyx",
        ".yaml", ".yml",
        ".hs", ".lhs", ".elm", ".nim", ".cr",
        ".fs", ".fsx", ".fsi",
        ".coffee", ".pug", ".jade", ".haml", ".slim",
        ".sass", ".styl",
        ".md", ".mdx", ".markdown", ".rst", ".adoc",
        ".txt",
        # Markup whose rendered output preserves whitespace inside `<pre>`
        # and `<textarea>`. Not brace-delimited in any case (#1631 review).
        ".html", ".htm", ".vue", ".svelte",
    }
)

#: Extensions whose languages are brace/keyword-delimited, where leading and
#: trailing whitespace on a line is formatting only. Only these opt IN to
#: whitespace collapsing; everything else is compared byte-exactly.
_WHITESPACE_INSIGNIFICANT_EXTENSIONS = frozenset(
    {
        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts",
        ".java", ".kt", ".kts", ".scala", ".groovy",
        ".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".hxx",
        ".cs", ".go", ".rs", ".swift", ".m", ".mm",
        ".php", ".rb", ".pl", ".pm", ".lua", ".dart",
        ".css", ".scss", ".less",
        # `.xml` is deliberately ABSENT (#1660): element text and CDATA
        # sections preserve whitespace across most of a document, and no
        # per-delimiter grammar would mark meaningfully fewer lines than
        # "all of them". Falling back to the byte-exact default is both
        # cheaper and safer — it costs one re-dispatch, never a weakened
        # gate. See `_HEREDOC_GRAMMARS`' KNOWN RESIDUAL note.
        ".json", ".jsonc",
        ".sql", ".proto", ".tf", ".hcl",
    }
)

#: Shared by `_HEREDOC_GRAMMARS` below — see that mapping's own comment for
#: the grammar contract. Ruby's `<<~`/`<<-`/bare, HCL's `<<-`/bare, and Perl's
#: `<<~`/bare all share this exact closer rule.
def _bareish_heredoc_close(line: str, ident: str, modifier: str) -> bool:
    """Shared closer for grammars whose only modifier axis is "must the
    closing line sit in column 0". No modifier means the opener demands an
    unindented closer (`line == ident`); `~`/`-` means the closer may be
    indented (`line.lstrip() == ident`).

    Leading whitespace only — never `.strip()`. A real heredoc terminator
    (Ruby, Perl, HCL) is the identifier and nothing else on the line; text
    AFTER it, including trailing whitespace, means the line is not a
    terminator at all. Stripping trailing whitespace here would false-close
    on a body line like `"  SQL  "` (trailing spaces) and dump every
    subsequent body line back into whitespace collapsing — the "more body,
    never fewer" rule this grammar exists to uphold, breached by the exact
    kind of over-eager closer match that rule warns against."""
    return line == ident if modifier == "" else line.lstrip() == ident


def _line_terminated(predicate):
    """Adapt a whole-line closer predicate to the positional closer protocol.

    A heredoc terminator is a whole LINE, never a delimiter embedded in one.
    Returning `len(line)` on a match means "this region consumed the entire
    line", which is what stops the scanner re-scanning a terminator line for
    a fresh opener — sound only because every predicate used here requires
    the whole (stripped) line to equal the identifier, so a closing line can
    never also carry an opener. `from_pos > 0` only happens when an INLINE
    region already closed earlier on this line, and a heredoc terminator
    cannot begin mid-line, so that case correctly never matches.
    """

    def close(line: str, ident: str, modifier: str, from_pos: int):
        if from_pos:
            return None
        return len(line) if predicate(line, ident, modifier) else None

    return close


def _delimited(build_close):
    """Positional closer for an INLINE multi-line literal — one whose closing
    delimiter is embedded in a line rather than being the whole line (Go/JS
    backticks, Lua long brackets, SQL dollar-quoting, C++ raw strings, PHP's
    inline-HTML region).

    Returns the index just past the delimiter so the scanner can resume
    hunting for a fresh opener on the remainder of the SAME line. That
    resumption is what makes these forms safe to mix with heredocs: an inline
    form genuinely can close and re-open on one line, the case the pre-#1660
    scanner could not represent (and whose absence its own docstring flagged
    as the thing a "grammar with a looser closer" would need).
    """

    def close(line: str, ident: str, modifier: str, from_pos: int):
        needle = build_close(ident, modifier)
        index = line.find(needle, from_pos)
        return None if index < 0 else index + len(needle)

    return close


class _Grammar(NamedTuple):
    """One unquoted multi-line-literal form for one language family.

    `open_re` matches an opener anywhere on a line. Two OPTIONAL named groups
    carry what a closer needs: `ident` (the delimiter identifier — a heredoc
    tag, a Lua bracket level, a SQL dollar tag, a C++ raw-string delimiter)
    and `mod` (the modifier axis, e.g. Ruby's `~`/`-`). NAMED, not positional
    (#1665): the old convention lived only in a comment, and forced PHP's
    regex to carry a phantom empty capture group purely to keep `group(2)`
    aligned across grammars.

    `close(line, ident, mod, from_pos)` returns the index just past this
    region's terminator in `line`, or `None` if it does not terminate there.

    `inline` records where the body starts: `False` for heredocs (body starts
    on the line AFTER the opener, so an opener never closes itself), `True`
    for inline spans (body starts mid-line, and the region may open and close
    on one line).
    """

    open_re: re.Pattern
    close: Callable[[str, str, str, int], int | None]
    inline: bool


def _opener_parts(match) -> tuple[str, str]:
    """`(ident, modifier)` from an opener match, tolerating grammars that
    declare only some of the optional named groups.

    `qident` is the QUOTED-delimiter alternative, kept a separate group so the
    unquoted alternative can keep its `[A-Za-z_]` first-character rule — which
    is what stops Ruby/Perl's shovel operator (`x << 2`) reading as a heredoc
    opener — while a quoted delimiter may legally start with a digit
    (`<<~'1SQL'`) or be empty (Perl's blank-line-terminated `<<""`). Both are
    #1667. An empty `qident` is a real match, so the `is not None` test must
    not be shortened to a truthiness test.
    """
    groups = match.groupdict()
    quoted = groups.get("qident")
    ident = quoted if quoted is not None else (groups.get("ident") or "")
    return ident, (groups.get("mod") or "")


#: Ruby's `<<~SQL`/`<<-SQL`/`<<SQL`, plus its backtick command form
#: ``<<`EOC` `` (#1667). The alternation keeps the digit-permissive delimiter
#: behind a required quote — see `_opener_parts`.
_RUBY_HEREDOC = _Grammar(
    re.compile(
        r"<<(?P<mod>[~-]?)"
        r"(?:(?P<q>['\"`])(?P<qident>[A-Za-z0-9_]+)(?P=q)"
        r"|(?P<ident>[A-Za-z_][A-Za-z0-9_]*))"
    ),
    _line_terminated(_bareish_heredoc_close),
    inline=False,
)

#: Perl's `<<EOF`/`<<~EOF`, its spaced-quoted (`print << "EOF";`) and
#: backslash-quoted (`print <<\EOF;`) forms, and its empty-delimiter
#: blank-line-terminated form `print <<"";` (#1667 — `qident` uses `*`, not
#: `+`, and `_bareish_heredoc_close` then closes on a genuinely empty line).
_PERL_HEREDOC = _Grammar(
    re.compile(
        r"<<(?P<mod>~?)(?:\s+(?=['\"]))?"
        r"(?:(?P<q>['\"])(?P<qident>[A-Za-z0-9_]*)(?P=q)"
        r"|\\?(?P<ident>[A-Za-z_][A-Za-z0-9_]*))"
    ),
    _line_terminated(_bareish_heredoc_close),
    inline=False,
)

#: PHP's `<<<TXT` heredoc and `<<<'TXT'` nowdoc. The closer is `.lstrip()`
#: (never `.strip()` — see `_bareish_heredoc_close`) plus `.rstrip(";,)")`,
#: since a real PHP terminator may be trailed by a statement terminator, an
#: array-element comma, or a call-argument close-paren. Known, accepted
#: residual: that makes PHP's close check looser than the "more body, never
#: fewer" rule for trailing PUNCTUATION — a body line reading exactly `TXT)`
#: false-closes. Distinguishing it needs the real PHP closer grammar, not a
#: regex tweak.
_PHP_HEREDOC = _Grammar(
    re.compile(r"<<<\s*(?P<q>['\"]?)(?P<ident>[A-Za-z_][A-Za-z0-9_]*)(?P=q)"),
    _line_terminated(lambda line, ident, _mod: line.lstrip().rstrip(";,)") == ident),
    inline=False,
)

#: PHP's inline-HTML region: everything between a `?>` and the next `<?` is
#: emitted verbatim, so reindenting it changes program OUTPUT (#1660).
_PHP_INLINE_HTML = _Grammar(
    re.compile(r"\?>"),
    _delimited(lambda _ident, _mod: "<?"),
    inline=True,
)

#: Lua long brackets — `[[ ... ]]`, `[==[ ... ]==]` (#1660). `ident` is the
#: `=` run, so the closer is level-matched and a `]]` at a different level
#: cannot close it. Also covers long comments (`--[[ ... ]]`), which share
#: the bracket grammar.
_LUA_LONG_BRACKET = _Grammar(
    re.compile(r"\[(?P<ident>=*)\["),
    _delimited(lambda ident, _mod: f"]{ident}]"),
    inline=True,
)

#: PostgreSQL dollar-quoting — `$$ ... $$`, `$tag$ ... $tag$` (#1660). `ident`
#: is the tag (absent for the bare `$$` form), so the closer is tag-matched.
_SQL_DOLLAR_QUOTE = _Grammar(
    re.compile(r"\$(?P<ident>[A-Za-z_][A-Za-z0-9_]*)?\$"),
    _delimited(lambda ident, _mod: f"${ident}$"),
    inline=True,
)

#: Go raw strings and JS/TS template literals — both backtick-delimited
#: (#1661). The OPENER line is already byte-exact under `_canonical_line`'s
#: quote-character rule (a backtick is in `_QUOTE_CHARS`); the gap this
#: closes is the INTERIOR lines, which routinely carry no quote character at
#: all. Over-matching is safe and expected here: a lone backtick in a comment
#: opens a region that never closes, and an unclosed region marks the rest of
#: the hunk byte-exact — a lost carry-forward, never a weakened gate.
_BACKTICK_RAW_STRING = _Grammar(
    re.compile(r"`"),
    _delimited(lambda _ident, _mod: "`"),
    inline=True,
)

#: C++ raw string literals — `R"(...)"`, `R"delim(...)delim"` (#1661).
_CPP_RAW_STRING = _Grammar(
    re.compile(r'R"(?P<ident>[^()\\\s]{0,16})\('),
    _delimited(lambda ident, _mod: f'){ident}"'),
    inline=True,
)

#: Shared tuples, so the `is`-identity aliases below stay identity-equal.
_RUBY_FORMS = (_RUBY_HEREDOC,)
_PERL_FORMS = (_PERL_HEREDOC,)
_PHP_FORMS = (_PHP_HEREDOC, _PHP_INLINE_HTML)
_LUA_FORMS = (_LUA_LONG_BRACKET,)
_SQL_FORMS = (_SQL_DOLLAR_QUOTE,)
_BACKTICK_FORMS = (_BACKTICK_RAW_STRING,)
_CPP_FORMS = (_CPP_RAW_STRING,)

#: Per-language unquoted multi-line-literal grammars (#1638, extended by
#: #1660/#1661/#1667). The quote-character rule in `_canonical_line` is what
#: keeps string data out of the cosmetic bucket, and it does not see an
#: UNQUOTED body — Ruby's `<<~SQL`, PHP's `<<<TXT`, Perl's `<<EOF`, Lua's
#: `[[`, SQL's `$$`, Go/JS backticks, C++'s `R"(`. Reindenting a line inside
#: one is a data change this module would otherwise read as formatting.
#:
#: Deliberately erring toward MORE lines counting as body, never fewer — see
#: `_heredoc_body_marks`'s docstring for why the closing-match direction
#: matters (an early false close drops real body content back into whitespace
#: collapsing, the hazard this exists to close).
#:
#: Keyed by extension, not by one cross-language regex, so PHP's `<<<` and
#: Ruby/Perl's `<<` can never cross-match. `.tf`/`.hcl` alias `.rb`'s forms
#: rather than `.pl`'s: Terraform/HCL heredocs support the bare and dash
#: (`<<-EOT`) forms but not the squiggly one, and only `.rb`'s regex captures
#: a dash modifier — `.pl`'s does not, so it would silently fail to match
#: `<<-EOT` at all.
#:
#: A `MappingProxyType` (#1665): this table is safety-relevant, and it was
#: previously a plain dict mutated after construction, so any importer could
#: rewrite a language's grammar at runtime. Its sibling language tables
#: (`_INDENT_SIGNIFICANT_EXTENSIONS`, `_WHITESPACE_INSIGNIFICANT_EXTENSIONS`)
#: are already `frozenset` for the same reason.
#:
#: KNOWN RESIDUAL (restored per #1660 — #1638 replaced the original residual
#: note with the grammar dict, leaving this class recorded nowhere):
#: - A `.php` file's leading inline-HTML region, before the file's FIRST
#:   `<?php`, is not marked: `_PHP_INLINE_HTML` needs a `?>` to open, and
#:   the file itself opens in HTML mode with no such token. Reaching it also
#:   requires a hunk starting at line 1, which the #1662 guard below already
#:   constrains.
#: - `.cs` verbatim strings (`@"..."`) and `.py`-style triple-quoted forms in
#:   other whitespace-insignificant languages have no grammar. Triple-quoted
#:   forms are covered incidentally — their delimiter IS a quote character,
#:   so `_canonical_line` keeps those lines byte-exact — but only on lines
#:   that carry the quote, never on interior lines.
#: - `.xml` was DROPPED from `_WHITESPACE_INSIGNIFICANT_EXTENSIONS` instead
#:   of being given a grammar: element text and CDATA sections are
#:   whitespace-preserving over most of a document, so the fail-closed option
#:   #1660 offers is both cheaper and safer than a grammar that would have to
#:   mark nearly every line anyway.
#:
#: Ruby/Perl's bare `<<` is also their shift/append ("shovel") operator
#: (`arr << item`, `x << 2`), but every real style guide writes that with
#: spaces around it. A heredoc opener has no space before an UNQUOTED
#: delimiter, so the identifier group starting immediately after `<<` (no
#: `\s*`) structurally cannot match the idiomatic spaced operator form.
#: Verified directly: `arr << item` and `x << 2` do not match; only the
#: unidiomatic no-space `arr<<item` would, which costs a rare false-positive
#: carry-forward loss. This is also exactly why #1667's digit-permissive
#: delimiter sits behind a REQUIRED quote: allowing `[0-9]` to lead an
#: unquoted delimiter would make `x << 2` a heredoc opener. Perl's grammar
#: carries two further exceptions, both in the SAFE (over-detection, never
#: under-detection) direction:
#: - A space IS legal (and not deprecated) before a QUOTED delimiter
#:   (`print << "EOF";`), so `.pl`'s regex allows whitespace only when
#:   immediately followed by a quote character — never bare — keeping the
#:   shovel-operator distinction intact while still matching this real
#:   heredoc form.
#: - A backslash-quoted delimiter (`print <<\EOF;`, perlop's no-interpolation
#:   shorthand for `<<'EOF'`) is matched by an optional `\` before the
#:   unquoted alternative. Over-matching an opener costs at most a spurious
#:   carry-forward loss (marking replaces a line with itself, byte-exact,
#:   never creating a collision); missing one is the unsafe direction this
#:   whole grammar exists to close.
_HEREDOC_GRAMMARS = MappingProxyType(
    {
        ".rb": _RUBY_FORMS,
        ".tf": _RUBY_FORMS,
        ".hcl": _RUBY_FORMS,
        ".pl": _PERL_FORMS,
        ".pm": _PERL_FORMS,
        ".php": _PHP_FORMS,
        ".lua": _LUA_FORMS,
        ".sql": _SQL_FORMS,
        ".go": _BACKTICK_FORMS,
        ".js": _BACKTICK_FORMS,
        ".jsx": _BACKTICK_FORMS,
        ".mjs": _BACKTICK_FORMS,
        ".cjs": _BACKTICK_FORMS,
        ".ts": _BACKTICK_FORMS,
        ".tsx": _BACKTICK_FORMS,
        ".mts": _BACKTICK_FORMS,
        ".cts": _BACKTICK_FORMS,
        ".cc": _CPP_FORMS,
        ".cpp": _CPP_FORMS,
        ".cxx": _CPP_FORMS,
        ".hpp": _CPP_FORMS,
        ".hxx": _CPP_FORMS,
        ".h": _CPP_FORMS,
    }
)



def _heredoc_body_marks(lines: list, suffix: str) -> list:
    """Return one bool per entry in `lines`: True where the line is inside an
    unquoted heredoc body (or is an unresolved opener's tail — see below),
    and must therefore be compared byte-exact regardless of the
    collapsible/quote-char rules `_canonical_line` otherwise applies.

    Tracks a FIFO queue of pending `(ident, modifier)` pairs, not a single
    one: stacked openers on one line are ordinary idioms (Ruby
    `assert_equal(<<~A, <<~B)`, Perl `print <<A, <<B;`), and their bodies
    close in the same order the openers appeared. Marking only the first of
    several openers — losing the rest to ordinary whitespace collapsing —
    is exactly the hazard this function exists to close, so every opener
    found while the queue is empty is enqueued, not just the first match on
    the line.

    Fails closed on an unmatched opener: if a heredoc opens within `lines`
    but no closing delimiter is found before `lines` ends, every remaining
    line is marked True. The true close may lie outside what this hunk's
    side shows; the safe assumption is that it has not closed yet.
    `normalized_gate_hash` additionally requests full-file diff context (see
    its docstring) so that in real use an opener earlier in the same file is
    always part of the same hunk as any body line it covers — this function
    only needs to reason within one hunk side, never across hunks.

    A line that closes a heredoc is not re-scanned for a new opener of its
    own, because `_line_terminated` reports that the terminator consumed the
    whole line. That is sound only for grammars whose closer IS the entire
    (stripped) line. INLINE grammars (#1660/#1661 — Lua long brackets, SQL
    dollar-quoting, Go/JS backticks, C++ raw strings, PHP inline HTML) have a
    genuinely looser closer, so `_delimited` reports the position just past
    the delimiter and the scan resumes there — the "fresh opener on the
    closer's line" case this docstring previously recorded as a hazard a
    looser grammar would reopen.

    An opener line itself is never marked — evident intent, and it usually
    carries no body content (`sql = <<~SQL`) — only lines strictly after it,
    through and including whatever line closes it. For inline forms the
    opener line is additionally already byte-exact under `_canonical_line`'s
    quote-character rule wherever the delimiter is a quote character.
    """
    grammars = _HEREDOC_GRAMMARS.get(suffix)
    if not grammars:
        return [False] * len(lines)
    marks = [False] * len(lines)
    # FIFO of (ident, modifier, close); bodies close in the order opened.
    pending: list = []
    for index, line in enumerate(lines):
        position = 0
        if pending:
            marks[index] = True
            while pending:
                ident, modifier, close = pending[0]
                end = close(line, ident, modifier, position)
                if end is None:
                    break
                pending.pop(0)
                position = end
            if pending:
                continue
        _enqueue_openers(line, position, grammars, pending)
    return marks


def _enqueue_openers(line: str, position: int, grammars, pending: list) -> None:
    """Enqueue every region opened at or after `position` on `line`.

    Openers are consumed in POSITIONAL order across ALL of a language's
    grammars, not one grammar at a time, so a line mixing two forms (PHP's
    `<<<TXT` heredoc and its `?>` inline-HTML region) enqueues them in the
    order their bodies actually close. Scanning grammar-by-grammar would
    invert that order and pair a body with the wrong closer.

    An INLINE region that closes on its own line spills nothing into the
    following lines, so the scan simply resumes past it. One that does NOT
    close consumes the rest of the line by definition — no further opener can
    start inside it — so the scan stops. A heredoc opener never consumes its
    own line: stacked openers (`assert_equal(<<~A, <<~B)`) are ordinary
    idioms, and all of them must be enqueued.
    """
    while position <= len(line):
        best = None
        for grammar in grammars:
            match = grammar.open_re.search(line, position)
            if match is None:
                continue
            if best is None or match.start() < best[0].start():
                best = (match, grammar)
        if best is None:
            return
        match, grammar = best
        ident, modifier = _opener_parts(match)
        # Never let a zero-width match stall the scan.
        advanced = max(match.end(), match.start() + 1)
        if grammar.inline:
            closed_at = grammar.close(line, ident, modifier, match.end())
            if closed_at is not None:
                position = max(closed_at, advanced)
                continue
            pending.append((ident, modifier, grammar.close))
            return
        pending.append((ident, modifier, grammar.close))
        position = advanced


#: Field/record separators for the canonical serialization. Chosen from the
#: ASCII separator block because they are vanishingly rare in source, but NOT
#: relied on for unambiguity: every field is length-prefixed by `_encode`, so
#: a file that genuinely contains these bytes cannot forge a field boundary.
#: git treats any NUL-free blob as text, so "no source line contains \x1f" is
#: an assumption about content an attacker supplies (#1631 review).
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"

#: Bounds on the one caller that asks git for whole-file context (#1663).
#: Both are fail-closed: exceeding either returns `None`, which every caller
#: already treats as "this lens is not decisive", never as a pass.
#: `run_safe_git_diff` had no timeout at all, so a wedged or pathologically
#: slow `git diff` hung the `pre_commit_review.py` PreToolUse hook
#: indefinitely.
_GIT_DIFF_TIMEOUT_SECONDS = 30.0
_MAX_PATCH_BYTES = 8 * 1024 * 1024


def _encode(parts) -> str:
    """Length-prefix each field so the canonical form is unambiguous.

    Without this, two different changesets could serialize identically by
    embedding a separator byte in a source line — the standard delimiter-
    injection hazard, and a real one here because the digest's whole job is
    to be hard to collide with.
    """
    return _FIELD_SEP.join(f"{len(part)}:{part}" for part in parts)

#: Patch-metadata prefixes that carry a real change with no hunk body — a
#: mode flip, a rename, a copy, an empty new or deleted file. See fix 4 in
#: the module docstring: omitting these makes such a change invisible to the
#: digest, so it could be staged on top of already-corroborated content.
_STRUCTURAL_PREFIXES = (
    "old mode ",
    "new mode ",
    "new file mode ",
    "deleted file mode ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
)

#: `@@ -old_start[,old_count] +new_start[,new_count] @@[ section heading]`.
#: Start lines are captured but deliberately unused — they shift whenever an
#: earlier hunk gains or loses a line, while the counts are what bound the
#: body. The leading anchor rejects the combined-diff `@@@` form, which this
#: module never asks git to produce.
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _is_documentation(path: str) -> bool:
    """Per-file documentation predicate, delegating to the gate's own STRICT
    classifier. A single-element list is exactly the "is this one file
    provably documentation" question, so no second implementation exists."""
    return is_doc_only_changeset([path])


def _suffix(path: str) -> str | None:
    """Lowercased extension including the dot, or None for an extensionless
    file — shared by `_whitespace_collapsible` and the heredoc grammar
    lookup so the two never disagree about what a path's extension is."""
    name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "." not in name:
        return None
    return "." + name.rsplit(".", 1)[-1]


def _whitespace_collapsible(path: str) -> bool:
    """True only for extensions this module can prove are brace/keyword-
    delimited. Everything else — including every unknown extension and every
    extensionless file — is compared byte-exactly. Fail-closed by default:
    the safe answer to "is this language's indentation meaningless?" is no."""
    suffix = _suffix(path)
    if suffix is None or suffix in _INDENT_SIGNIFICANT_EXTENSIONS:
        return False
    return suffix in _WHITESPACE_INSIGNIFICANT_EXTENSIONS


def _canonical_line(line: str, collapsible: bool) -> str:
    """The form of a changed line the normalized hash is computed over.

    Strips leading/trailing whitespace ONLY when the file's language allows
    it AND the line carries no quote character. Both conditions are load
    bearing — see the module docstring.
    """
    if not collapsible:
        return line
    if any(q in line for q in _QUOTE_CHARS):
        return line
    return line.strip()


def _target_path(header: str) -> str | None:
    """Extract the new-side path from a `+++ ` header. `/dev/null` (a pure
    delete) has no new-side path; the old-side name is used by the caller."""
    target = header[4:].strip()
    if target == "/dev/null":
        return None
    return target[2:] if target.startswith("b/") else target


def _source_path(header: str) -> str | None:
    source = header[4:].strip()
    if source == "/dev/null":
        return None
    return source[2:] if source.startswith("a/") else source


def _structural_marker(raw: str) -> str | None:
    """A patch-metadata line that carries a real change with no hunk body.

    Everything matched here alters the committed tree without producing a
    single `+`/`-` line, so omitting it makes the change invisible to this
    digest — see fix 4 in the module docstring. `index` is deliberately NOT
    here: its blob SHAs move with every content edit, which would defeat the
    invariance this module exists for. It is picked up only for binary files
    (`_FileSection.binary`), where it is the sole content signal available.
    """
    for prefix in _STRUCTURAL_PREFIXES:
        if raw.startswith(prefix):
            return raw.strip()
    return None


class _FileSection:
    """Accumulator for one `diff --git` section."""

    __slots__ = ("binary", "fallback", "hunks", "index_line", "old_path", "path", "structural")

    def __init__(self, fallback: str) -> None:
        self.path: str | None = None
        self.old_path: str | None = None
        self.fallback = fallback
        self.structural: list = []
        self.hunks: list = []
        self.binary = False
        self.index_line: str | None = None

    @property
    def name(self) -> str:
        """The section's identity for sorting and doc classification."""
        return self.path or self.old_path or self.fallback

    @property
    def has_real_path(self) -> bool:
        """True when a `---`/`+++` header supplied a genuine path.

        A section identified only by its `diff --git` remainder (a pure
        rename, mode flip, or binary swap) is never doc-classified away: the
        fallback is not a path this module can hand to the STRICT classifier
        with confidence, and the safe answer to "may this be dropped?" is no.
        """
        return self.path is not None or self.old_path is not None


def _parse_hunk_header(raw: str) -> tuple[int, int, int, int] | None:
    """`(old_count, new_count, old_start, new_start)` from an `@@ -a,b +c,d @@`
    header.

    An omitted count means 1 (`@@ -1 +1 @@`). Returns `None` for anything
    that is not a well-formed unified-diff hunk header, including the
    combined `@@@` form, which this module never asks git to produce.

    The START lines were previously parsed and discarded, with a comment
    explaining that they shift whenever an earlier hunk gains or loses a line
    while the counts are what bound the body. That reasoning went stale in
    #1638: the heredoc grammars made "does this hunk begin at the top of the
    file" a question the digest depends on, because an opener above a hunk is
    only visible when the hunk reaches back to line 1. #1662 makes them
    load-bearing again — see `normalize_patch`.
    """
    match = _HUNK_HEADER_RE.match(raw)
    if match is None:
        return None
    old_start = int(match.group(1))
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_start = int(match.group(3))
    new_count = int(match.group(4)) if match.group(4) is not None else 1
    return old_count, new_count, old_start, new_start


def normalize_patch(patch_text: str) -> str | None:
    """Reduce a unified diff to its behavior-bearing content.

    Returns a canonical string, or `None` when the patch cannot be parsed
    (fail-closed — the caller must not treat `None` as "no changes"). An
    EMPTY string means "parsed fine, nothing behavior-bearing left"; it is a
    legitimate value here, and `normalized_gate_hash` is what refuses to turn
    it into a digest (fix 5 in the module docstring).

    Hunk bodies are consumed by the line counts in their own `@@` headers,
    never by dispatching on line prefixes, so a removed line that happens to
    start with `-- ` cannot masquerade as a file header. Each hunk is reduced
    to its canonicalized old side and new side, context lines included, so an
    insertion's position is part of the subject; a hunk whose two sides come
    out identical was purely formatting and is dropped. Files are emitted in
    sorted order so a re-stage that reorders git's own file output cannot
    change the digest.
    """
    if patch_text is None:
        return None

    sections: list = []
    current: _FileSection | None = None
    old_side: list = []
    new_side: list = []
    old_remaining = 0
    new_remaining = 0
    old_start = 0
    new_start = 0
    in_hunk = False

    def close_hunk() -> None:
        nonlocal old_side, new_side, in_hunk
        if in_hunk and current is not None:
            current.hunks.append((old_side, new_side, old_start, new_start))
        old_side, new_side = [], []
        in_hunk = False

    try:
        for raw in patch_text.splitlines():
            if in_hunk and (old_remaining > 0 or new_remaining > 0):
                # Inside a hunk body: the declared counts, not the line's
                # prefix, decide where the body ends.
                if raw.startswith("\\"):
                    # "\ No newline at end of file" — annotates the preceding
                    # line and consumes no budget on either side.
                    continue
                if raw.startswith("+"):
                    new_side.append(raw[1:])
                    new_remaining -= 1
                elif raw.startswith("-"):
                    old_side.append(raw[1:])
                    old_remaining -= 1
                elif raw.startswith(" ") or raw == "":
                    # Context. An empty line is a context line whose trailing
                    # space some tools strip.
                    body = raw[1:] if raw else ""
                    old_side.append(body)
                    new_side.append(body)
                    old_remaining -= 1
                    new_remaining -= 1
                else:
                    # A hunk body cannot contain anything else. Rather than
                    # guess, fail closed.
                    return None
                if old_remaining <= 0 and new_remaining <= 0:
                    close_hunk()
                continue

            if raw.startswith("diff --git "):
                close_hunk()
                current = _FileSection(raw[len("diff --git ") :].strip())
                sections.append(current)
                continue

            if current is None:
                # Diff output that never opened a section. Not something git
                # produces for the invocation this module makes; fail closed
                # rather than digest a shape we do not understand.
                return None

            if raw.startswith("--- "):
                close_hunk()
                current.old_path = _source_path(raw)
            elif raw.startswith("+++ "):
                close_hunk()
                current.path = _target_path(raw)
            elif raw.startswith("@@"):
                close_hunk()
                counts = _parse_hunk_header(raw)
                if counts is None:
                    return None
                old_remaining, new_remaining, old_start, new_start = counts
                in_hunk = True
                if old_remaining <= 0 and new_remaining <= 0:
                    # A degenerate `@@ -0,0 +0,0 @@`: nothing to consume.
                    close_hunk()
            elif raw.startswith("index "):
                current.index_line = raw.strip()
            elif raw.startswith(("Binary files ", "GIT binary patch")):
                current.binary = True
            else:
                marker = _structural_marker(raw)
                if marker is not None:
                    current.structural.append(marker)
        close_hunk()
    except Exception:  # noqa: BLE001 - fail closed, see module docstring
        return None

    records = []
    try:
        for section in sorted(sections, key=lambda s: s.name):
            name = section.name
            if section.has_real_path and _is_documentation(name):
                continue
            collapsible = _whitespace_collapsible(name)
            suffix = _suffix(name)
            parts = list(section.structural)
            if section.binary:
                # The blob SHAs are the only content signal a textual diff
                # exposes for a binary file, and without them any binary
                # replacement is invisible to this digest.
                parts.append(section.index_line or "binary")
            grammared = suffix in _HEREDOC_GRAMMARS
            for old_lines, new_lines, hunk_old_start, hunk_new_start in section.hunks:
                if grammared and (hunk_old_start > 1 or hunk_new_start > 1):
                    # #1662: `_heredoc_body_marks` can only see an opener that
                    # is inside the hunk it is given. `normalized_gate_hash`
                    # asks for `--unified=100000` so that in practice every
                    # hunk spans the whole file — but that is a magic number,
                    # not a guarantee. A file longer than that context window
                    # still yields a hunk starting partway down, and an opener
                    # ABOVE it is invisible: the exact hazard the grammars
                    # exist to close, silently reopened, and failing OPEN
                    # rather than closed. Rather than trust the number, detect
                    # the condition it is supposed to make impossible and fall
                    # back to byte-exact for this hunk. Costs a carry-forward
                    # on files past the window; costs nothing otherwise, since
                    # a whole-file hunk starts at line 1 by construction.
                    # A pure add/delete reports start 0 on its empty side, so
                    # `> 1` (not `!= 1`) is what keeps those on the fast path.
                    old_canon = list(old_lines)
                    new_canon = list(new_lines)
                    if old_canon == new_canon:
                        continue
                    parts.append("\n".join(old_canon))
                    parts.append("\n".join(new_canon))
                    continue
                old_heredoc = _heredoc_body_marks(old_lines, suffix)
                new_heredoc = _heredoc_body_marks(new_lines, suffix)
                old_canon = [
                    ln if marked else _canonical_line(ln, collapsible)
                    for ln, marked in zip(old_lines, old_heredoc)
                ]
                new_canon = [
                    ln if marked else _canonical_line(ln, collapsible)
                    for ln, marked in zip(new_lines, new_heredoc)
                ]
                if old_canon == new_canon:
                    # This hunk's two sides canonicalize identically — its
                    # whole delta was formatting.
                    continue
                parts.append("\n".join(old_canon))
                parts.append("\n".join(new_canon))
            if not parts:
                continue
            records.append(_encode([name] + parts))
    except Exception:  # noqa: BLE001 - fail closed, see module docstring
        return None
    return _RECORD_SEP.join(_encode([record]) for record in records)


def normalized_gate_hash(cwd=None, target: str = "--cached") -> str | None:
    """sha256 of the normalized staged patch, or `None` on any failure.

    Uses the same `git_safe_diff.run_safe_git_diff` invocation and the same
    `--no-color --no-ext-diff --no-textconv` pins as `review_gate_hash()`.
    Those flags are not optional here either: a `diff.external` driver would
    otherwise collapse this function's input to empty for every changeset,
    turning the normalized hash into a constant — the same subject-binding
    bypass `review_gate_hash()`'s docstring documents at length.

    Also passes `--unified=100000` (#1638): `_heredoc_body_marks` reasons
    only within one hunk side, never across hunks, so a heredoc opener more
    than the default 3 lines of context above a changed body line would
    otherwise be invisible to it — the exact "opened outside the visible
    hunk" hazard the heredoc handling has to fail closed against. Requesting
    enough context to cover any realistically-sized file makes each file's
    changes arrive as one hunk spanning start to end, so an opener anywhere
    earlier in the file is always part of the same hunk as any body line it
    covers. This is strictly safer than the default, never less: wider
    context only ever MERGES hunks, and a merged hunk whose two sides still
    canonicalize identically was purely formatting regardless of how many
    original hunks it absorbed (see the "costs some invariance, never
    safety" trade already accepted for fixes 2-3 in the module docstring).

    `target` mirrors `review_gate_hash()`/`working_tree_gate_hash()`'s split:
    `--cached` for an ordinary staged commit, `HEAD` for the `git commit
    -a`/pathspec form (#1476).

    Returns `None` — never a digest of empty input — when git fails, AND
    when the changeset normalizes to nothing at all. Both are the same
    hazard: `sha256("")` is a CONSTANT, shared by every broken-git
    invocation, every fully-cosmetic changeset, and every dispatch recorded
    while the index was still clean. Two review dispatches made before
    anything was staged would otherwise stamp precisely the value a later
    mode-only or rename-only stage recomputes, clearing the `>= 2` floor with
    evidence from agents that reviewed nothing. The whole point of this lens
    is that two parties independently arrive at the same NON-TRIVIAL value.

    A changeset with nothing behavior-bearing left therefore gets no
    carry-forward. It loses nothing real: a wholly doc-classified changeset
    is already served by the doc-only exemption lens, which re-derives its
    own predicate against the actual staged files.
    """
    try:
        completed = run_safe_git_diff(
            ["--no-color", "--no-ext-diff", "--no-textconv", "--unified=100000"],
            cwd=cwd,
            text=False,
            target=target,
            timeout=_GIT_DIFF_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        # `SubprocessError` covers `TimeoutExpired`, which is NOT an `OSError`
        # subclass. Fail closed, matching every other failure path here.
        return None

    if completed.returncode != 0:
        return None

    if len(completed.stdout) > _MAX_PATCH_BYTES:
        # #1663: `--unified=100000` turns a one-line edit to a large tracked
        # file into a whole-file diff, and `normalize_patch` holds several
        # full in-memory copies of it (split lines, per-hunk old/new sides,
        # canonicalized sides, joined strings, encoded records). `.json` is a
        # whitespace-insignificant extension, so an ordinary lockfile touch
        # hits this path on every commit. Refusing above the cap costs a
        # carry-forward on very large files; processing an unbounded payload
        # synchronously inside a PreToolUse hook costs the commit.
        return None

    try:
        patch_text = completed.stdout.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - fail closed
        return None

    normalized = normalize_patch(patch_text)
    if not normalized:
        # Covers both the parse failure (`None`) and the degenerate
        # empty-canonical-form case (`""`) — see the docstring above.
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _main() -> int:
    value = normalized_gate_hash()
    if value is None:
        return 1
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ("normalize_patch", "normalized_gate_hash")
