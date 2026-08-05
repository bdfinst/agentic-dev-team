"""pre_commit_detect — shared `git commit` detection for PreToolUse:Bash hooks.

Python port of hooks/lib/pre-commit-detect.sh (#576 / #572 Cluster B).
Extended under #709 to recognize bare `-n` as a bypass flag identically to
`--no-verify` (parity fix — `hooks/telemetry.py`'s bypass detection already
matched bare `-n`; this detector did not).

Extended again (#1801, independent security-review finding surfaced during
#1761/#1762/#1763's Slice 3 build, then through THREE rounds of
correctness-review/security-review re-review before this version shipped):
the original detector only matched `git commit` at the very start of the
command string, so a handful of behaviorally-identical invocations skipped
the gate with no bypass-audit trail at all. Round 1 widened the match with
segment-split-then-regex-match; round 2 replaced that with per-segment
shlex tokenization; each round's attempt FAILED its own re-review and was
replaced rather than patched — regex-over-raw-text couldn't see through
shell quoting, per-segment tokenization still split on raw-string
separator characters BEFORE tokenizing (letting a quoted separator inside
a git-option value bisect the invocation), and neither modeled a
clustered shell flag (`bash -lc '...'`), a wrapper's own options
(`sudo -u <user>`), a path-qualified interpreter (`/bin/bash -c '...'`),
nested `<shell> -c` wrapping more than one level deep, or a bare newline
as a real statement separator without also breaking a multi-line quoted
value. This version:

  - masks every BARE (non-quoted) newline to `;` before tokenizing
    (`_mask_bare_newlines`, a small quote-tracking character scan — not a
    full shell parser, just enough to know "am I inside a quote right
    now") so a bare newline acts as a real statement separator while one
    embedded in a quoted value (a multi-line commit message) stays part
    of that value's own token instead of splitting it;
  - tokenizes the WHOLE (masked) command in ONE quote-aware
    `shlex.shlex(..., punctuation_chars=True)` pass with `commenters`
    explicitly cleared (`shlex.split`'s convenience wrapper clears this by
    default; constructing `shlex.shlex` directly does not, so an
    un-cleared `#` mid-line silently discarded the rest of that line and
    everything after it — a real regression the second round introduced
    and this version closes);
  - splits the resulting token list on separator TOKENS
    (`_split_on_separators`) rather than raw-string characters — a
    separator inside a quoted value is never a boundary — and further
    decomposes any token shlex glued into a run of adjacent control
    characters (`;(`, `)&&(`, `|&`) back into its constituent one/two-
    character operators (`_split_control_token`) so a separator directly
    adjacent to unrelated punctuation still creates a boundary;
  - recognizes a shell name (matched on basename, so `/bin/bash` and
    `bash` are treated alike) followed by a bare `-c` or a clustered
    short-flag group ending in `c` (`-lc`, `-ec`, `-ic`) and recurses
    GENUINELY into that argument's own segments — including any FURTHER
    nested `<shell> -c` wrapping inside it, up to a small depth bound
    (`_MAX_NEST_DEPTH`) as a defensive backstop, not a realistic ceiling;
  - walks git's OWN global-option grammar token-by-token
    (`_match_commit_tokens`) rather than enumerating every option's exact
    spelling in a regex — an unrecognized boolean option is still safely
    skipped (the "invert the allowlist" choice), and `git`/wrapper-word
    matching is basename-aware the same way shell-name matching is
    (`/usr/bin/git commit`, `/usr/bin/sudo git commit` both match);
  - skips a wrapper word's OWN options using a table KEYED BY WRAPPER
    (`_WRAPPER_VALUE_TAKING_OPTS`), not one flat set shared across all
    wrappers — `-n` takes a value for `nice` but is boolean for `sudo`,
    and a shared set would have misparsed `sudo -n git commit` by
    swallowing `git` as `-n`'s value;
  - resolved EVERY matching segment's `-C` chain independently (not just
    the first) via `resolve_commit_targets` (deleted #1904 — see "Exposes"
    above — once its sole caller, `pre_commit_review.py`'s per-target
    commit-gating, was retired to a no-op by #1886; this paragraph
    documents the #1801 hardening history, not current exposed surface),
    each segment falling back to
    the caller's own `payload_cwd` when it has no usable `-C` — this is
    what closes the decoy-redirection bypass without over-blocking the
    everyday single-segment case: a prepended `git -C <decoy> commit ...;
    git commit -m real` has a SECOND matching segment with no `-C` of its
    own, which resolves to `payload_cwd` on its own merits, so the payload
    repo's own review can no longer be skipped by a decoy elsewhere in the
    same command — while a lone `git -C <dir> commit` run from a
    `payload_cwd` that isn't a git repository at all (ordinary, legitimate
    `-C` usage) still resolves to `<dir>` alone, not a forced, failing
    check of an unrelated non-repo directory.

This is still a best-effort heuristic, not a real shell parser — see the
"KNOWN RESIDUAL GAPS" list in `hooks/pre_commit_review.py` for what remains
uncovered (a `git`/shell alias, a genuinely PATH-shadowed non-standard
binary named `git`/`bash`/etc — as opposed to the absolute-path spelling
of the REAL one, which this module now recognizes — `eval`, `xargs`,
compound-command keywords this module doesn't enumerate, `cd`/`pushd`
changing a LATER segment's effective target, a wrapper option taking a
separate-token value before `-c` this module doesn't model
(`bash -o pipefail -c '...'`), and a wrapper or git global option needing
a separate-token value and not enumerated here at all). Widening the match
can only make DETECTION more eager, never less — a segment that looks like
`git ... commit` inside an unrecognized wrapper's argument can
false-POSITIVE into "this is a commit", which is the safe direction for a
fail-closed gate; it can't false-negative a real commit a narrower matcher
would have caught. Target RESOLUTION was different: `resolve_commit_targets`
(deleted #1904) could only ADD targets to check per matching segment, never
remove a segment's own real target from the set that gets evaluated, including
the one disclosed exception (a `-C`
chain that can't be safely resolved falls back to `payload_cwd`, which can
under-cover a commit genuinely aimed elsewhere).

Imported by the Python sibling of its one remaining live caller:
  - hooks/pre_commit_knowledge_index.py (via `is_git_commit_invocation`)

`resolve_commit_targets()` (the multi-target `-C`/`--git-dir`/`--work-tree`
resolution this module used to expose) was deleted in #1904: its sole
caller, `hooks/pre_commit_review.py`'s per-target commit-gating, was
already retired to a no-op by #1886's PR-time gate migration (`gh pr
create` has no `-C`-shaped multi-repository ambiguity for
`hooks/pre_pr_review.py`, the successor hook, to resolve — see that
module's own docstring). Confirmed orphaned by repo-wide grep before
deletion, not merely unused by one caller.

Exposes:

  is_git_commit_command(cmd: str) -> bool
    True when `cmd` is a `git commit` invocation, regardless of any
    bypass flag. Callers that need to distinguish "gate-worthy commit"
    from "bypassed commit" should also consult `has_bypass_flag`.

  has_bypass_flag(cmd: str) -> bool
    True when `cmd` carries `--no-verify` or a bare `-n` argument — git's
    two spellings of "skip hooks". Substring/word-bounded match; does not
    require `cmd` to be a `git commit` invocation.

  bypass_flag_name(cmd: str) -> Optional[str]
    "--no-verify" or "-n" (whichever matched; `--no-verify` preferred when
    both are present), or None when `cmd` carries no bypass flag.

  is_git_commit_invocation(cmd: str) -> bool
    True when `cmd` is a `git commit` we should gate on (no bypass flag).
    Kept for backward compatibility with existing callers/tests.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import re
import shlex

# Recognized shell interpreters whose own `-c`/clustered-`-c` flag takes a
# nested command as its argument (`bash -c '...'`, `bash -lc '...'`).
# Matched on basename (see `_word`) so `/bin/bash` is recognized too.
_SHELL_NAMES = frozenset({"bash", "sh", "zsh", "dash", "ksh"})

# Token forms that separate one command from the next within a single
# already-tokenized command. `_tokenize_command` (via `punctuation_chars=
# True`) emits `&&`/`||` as single two-character tokens and `;`/`|`/`&` as
# single characters — never split out of a quoted value. A bare (non-
# quoted) newline is masked to `;` before tokenizing (`_mask_bare_
# newlines`) rather than relying on shlex's own newline handling, which
# treats every newline as plain whitespace regardless of quoting.
_SEPARATOR_TOKENS = frozenset({";", "&&", "||", "|", "&"})

# Characters shlex's `punctuation_chars` mode can glue into ONE token when
# they appear adjacent with no separating whitespace (`;(`, `)&&(`, `|&`).
# `_split_control_token` decomposes such a token back into its constituent
# one/two-character operators so a separator adjacent to unrelated
# punctuation still creates a segment boundary.
_CONTROL_CHARS = frozenset(";&|()<>")

# Leading shell "noise" tokens that can precede `git` without changing what
# it targets: command wrappers that just re-exec their remaining argv
# (`env`, `exec`, `command`, `nohup`, `time`, `nice`, `sudo`, `setsid`,
# `doas`), and compound-command keywords that can immediately precede a
# command word
# (`then`, `do`, `else`, `elif`) plus grouping/negation tokens (`!`, `(`,
# `{`) that tokenize as standalone tokens when space-separated.
_WRAPPER_WORDS = frozenset(
    {"env", "exec", "command", "nohup", "time", "nice", "sudo", "setsid", "doas"}
)
_LEADING_NOISE_TOKENS = frozenset({"then", "do", "else", "elif", "!", "(", "{"})

# Wrapper options that take a separate-token value, KEYED BY WRAPPER WORD
# rather than one flat set shared across all of them (#1801 third-round
# re-review): `-n` takes a value for `nice` but is boolean for `sudo`, and
# a shared set misparsed `sudo -n git commit` by swallowing `git` itself
# as `-n`'s value. A wrapper/option pair not listed here is safely
# boolean-skipped (same "invert the allowlist" choice as git's own
# options) — it only misparses if it ALSO takes a separate value this
# table doesn't know about.
_WRAPPER_VALUE_TAKING_OPTS: dict[str, frozenset[str]] = {
    "sudo": frozenset({"-u", "-g", "-p", "-h", "-C"}),
    "doas": frozenset({"-u", "-C", "-a"}),
    "nice": frozenset({"-n"}),
    "env": frozenset({"-u", "-C", "-S"}),
    "exec": frozenset({"-a"}),
    "time": frozenset({"-o", "-f", "--output", "--format"}),
}

# A bare `NAME=value` shell-assignment token — no `env` keyword required
# (an earlier version required it, missing the far more common bare
# `X=1 git commit` spelling — correctness/security re-review finding).
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# git global options that consume exactly one following token as their
# argument when not already attached via `=` in the same token (`-c` always
# consumes its next token even when valueless — `-c core.pager` sets a
# boolean true — matching git's own arg parser, not just the `name=value`
# case a fixed regex atom previously required).
_VALUE_TAKING_OPTS = frozenset(
    {"-c", "--namespace", "--super-prefix", "--exec-path", "--attr-source", "--config-env"}
)

# Defensive backstop for `<shell> -c`-wrapping nesting depth
# (`_all_segments`) — genuinely recursive, not a realistic ceiling on how
# deep real commands nest; just insurance against a pathological input.
_MAX_NEST_DEPTH = 4

# The documented bypass. Substring match (no word boundary) — mirrors the
# .sh's `grep -qE -- '--no-verify'` byte-for-byte: `--no-verifying`, though
# not a real git flag, also short-circuits under the .sh, so the port does
# the same. Byte-parity is the migration contract.
_NO_VERIFY_RE = re.compile(r"--no-verify")

# git's short-form bypass flag. Word-bounded (whitespace or string edges) so
# it doesn't false-positive inside `-nx` or `--number`. Mirrors
# `hooks/telemetry.py`'s `_NO_VERIFY_RE` pattern.
_BARE_N_RE = re.compile(r"(?:^|\s)-n(?:\s|$)")


def _mask_bare_newlines(cmd: str) -> str:
    """Replace every newline OUTSIDE a single/double-quoted region with
    `;` — a real statement separator, the same as what a shell itself
    treats a bare newline as — while a newline INSIDE a quoted region
    (a multi-line commit message) is left untouched so it stays part of
    that value's own token instead of being cut in half. A POSIX
    backslash-newline pair (a line continuation — `git add -A && \\`
    followed by a newline then `git commit -m x`) is DELETED entirely,
    matching what a real shell does with it, rather than preserved: an
    earlier version of this function treated `\\`+newline the same as any
    other escaped character (kept both, verbatim), which fed
    `_tokenize_command`'s shlex pass a literal embedded newline instead of
    nothing — silently gluing the following word onto the newline and
    hiding `git`/`commit` from every downstream check (#1801 fifth-round
    re-review).

    A small character-by-character quote-tracking scan, not a full shell
    parser: both backslash branches are gated on being OUTSIDE a quote
    (`quote is None`) — it performs no in-quote escape handling at all,
    while POSIX double-quote escaping is actually BROADER than this scan
    (`\\"`, `\\$`, `` \\` `` are all recognized escapes there this scan
    doesn't treat as such). That's exactly why a double-quoted string
    containing an escaped copy of its OWN quote character can end this
    scan's quote-tracking early — a known, disclosed limitation (see
    KNOWN RESIDUAL GAPS in hooks/pre_commit_review.py) rather than
    something this function claims to handle."""
    out = []
    quote: str | None = None
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if quote is None and ch == "\\" and i + 1 < n and cmd[i + 1] == "\n":
            i += 2  # line continuation: delete the pair, emit nothing
            continue
        if quote is None and ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(cmd[i + 1])
            i += 2
            continue
        if quote is not None and ch == quote:
            quote = None
            out.append(ch)
        elif quote is None and ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif quote is None and ch == "\n":
            out.append(";")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _tokenize_command(cmd: str) -> list[str]:
    """POSIX-shell-tokenize the WHOLE (newline-masked) `cmd` in one pass,
    resolving quotes/escapes the same way a real shell would — this is
    what closes the quoting-evasion class (`git "commit"`, `'git' commit`,
    `\\git commit`) a plain string search cannot, keeps a quoted value
    containing whitespace or a separator character (`git -C "/a b"
    commit`, `git -c user.name="A; B" commit`) as ONE token instead of
    splitting it, and — via `commenters = \"\"` — never discards the rest
    of a line at an unquoted `#` the way `shlex.shlex`'s default
    `commenters` would (`shlex.split`'s convenience wrapper clears this;
    constructing `shlex.shlex` directly does not, and an earlier version
    of this module didn't either — a real regression this version
    closes). Falls back to a naive whitespace split on unbalanced quotes
    — an edge case a real shell would itself reject as malformed, so
    treating it as "can't tokenize, don't try to guess" is the safe
    posture."""
    masked = _mask_bare_newlines(cmd)
    try:
        lex = shlex.shlex(masked, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return masked.split()


def _split_control_token(tok: str) -> list[str]:
    """Split a token shlex glued from adjacent control characters (`;(`,
    `)&&(`, `|&`) back into its constituent one- or two-character shell
    operators, greedily preferring the two-character forms (`&&`, `||`)
    — the operators a real shell lexer would recognize, just not glued in
    this token's raw form."""
    pieces = []
    i, n = 0, len(tok)
    while i < n:
        two = tok[i : i + 2]
        if two in ("&&", "||"):
            pieces.append(two)
            i += 2
        else:
            pieces.append(tok[i])
            i += 1
    return pieces


def _split_on_separators(tokens: list[str]) -> list[list[str]]:
    """Split an already-tokenized command into segments at
    `_SEPARATOR_TOKENS` boundaries, first decomposing any token composed
    entirely of `_CONTROL_CHARS` via `_split_control_token` so a
    separator glued to adjacent, unrelated punctuation (`;(`, `|&`) still
    creates a boundary. Empty segments (a leading/trailing/doubled
    separator) are dropped."""
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok and all(c in _CONTROL_CHARS for c in tok):
            pieces = _split_control_token(tok)
        else:
            pieces = [tok]
        for piece in pieces:
            if piece in _SEPARATOR_TOKENS:
                segments.append([])
            else:
                segments[-1].append(piece)
    return [segment for segment in segments if segment]


def _word(tok: str) -> str:
    """The basename of `tok` when it looks path-qualified, else `tok`
    itself — so `/bin/bash`, `/usr/bin/git`, and `/usr/bin/sudo` are
    recognized the same as their bare spellings (#1801 third-round
    re-review: exact-token comparisons elsewhere in this module used to
    miss every absolute-path spelling of the same binary)."""
    return tok.rsplit("/", 1)[-1]


def _extract_shell_dash_c_bodies(tokens: list[str]) -> list[str]:
    """Scan an already-tokenized segment for a recognized shell name
    (matched via `_word`, so path-qualified spellings count too) followed
    by a bare `-c` or a clustered short-flag group ENDING in `c`
    (`bash -lc '...'`, `sh -ec "..."`, `zsh -ic '...'`) and return each
    such argument string found — the nested command a real shell would
    separately execute. Best-effort: a wrapper option that itself takes a
    separate-token value before `-c` (`bash -o pipefail -c '...'`) is not
    modeled and remains a disclosed residual gap (see
    `pre_commit_review.py`'s KNOWN RESIDUAL GAPS) — modeling every shell's
    exact getopt grammar is out of scope for this heuristic."""
    bodies = []
    for i, tok in enumerate(tokens):
        if _word(tok) not in _SHELL_NAMES:
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):
            flag = tokens[j]
            if flag == "-c" or (len(flag) > 2 and flag[-1] == "c" and flag[1:-1].isalpha()):
                if j + 1 < len(tokens):
                    bodies.append(tokens[j + 1])
                break
            j += 1
    return bodies


def _all_segments(cmd: str, _depth: int = 0) -> list[list[str]]:
    """Every already-tokenized segment worth checking for a `git ...
    commit` match: `cmd` tokenized and split on separator tokens, plus the
    same treatment GENUINELY recursively applied to every `<shell> -c`/
    clustered-`-c` argument `_extract_shell_dash_c_bodies` finds within
    those segments — including further nesting inside THOSE bodies too,
    up to `_MAX_NEST_DEPTH` (a defensive backstop, not a realistic
    ceiling; an earlier version of this function only extracted one level
    despite its own docstring claiming otherwise — #1801 third-round
    re-review)."""
    if _depth > _MAX_NEST_DEPTH:
        return []
    segments = _split_on_separators(_tokenize_command(cmd))
    all_found = list(segments)
    for segment in segments:
        for body in _extract_shell_dash_c_bodies(segment):
            all_found.extend(_all_segments(body, _depth + 1))
    return all_found


def _advance_past_value(tokens: list[str], i: int, has_attached_value: bool) -> int:
    """Advance past the option token at `tokens[i]` and, unless its value
    was `=`-attached to the same token, past its separate-token value too
    (when one remains). Shared by the `--git-dir`/`--work-tree` and
    `_VALUE_TAKING_OPTS` branches of `_match_commit_tokens`, which
    otherwise repeat this exact sequence (structure-review + complexity-
    review both independently flagged the duplication, #1801 re-review).

    `has_attached_value` must reflect whether `=` was PRESENT in the
    token, not the truthiness of the value after it (#1801 sixth-round
    re-review: `tok.partition("=")`'s value is `""` for BOTH "no `=` at
    all" and "`=` present with an empty value", e.g. `--namespace=`; the
    caller must pass the separator's own truthiness, not the value's, or
    an option with a present-but-empty attached value gets treated as
    needing a separate-token value and wrongly consumes the next token —
    which, for the LAST option before `commit`, silently swallows
    `commit` itself)."""
    i += 1
    if not has_attached_value and i < len(tokens):
        i += 1
    return i


def _match_commit_tokens(tokens: list[str]) -> tuple[bool, list[str], bool]:
    """Return `(is_commit, dash_c_chain, has_repo_override)` for an
    already-tokenized command. `dash_c_chain` is every `-C` argument found,
    IN ORDER (git's own left-to-right `-C` chaining — NOT "last wins").
    `has_repo_override` is True when `--git-dir`/`--work-tree` also
    appeared. Both were consumed by the now-deleted `resolve_commit_targets()`
    (#1904, orphaned once `pre_commit_review.py`'s per-target commit-gating
    was retired) — `is_git_commit_command()` below only needs the boolean
    `is_commit` element, but the tuple shape is left unchanged rather than
    narrowed, since narrowing it is an unrelated refactor with no behavioral
    payoff for this module's one remaining consumer."""
    i, n = 0, len(tokens)
    while i < n:
        if _ASSIGNMENT_RE.match(tokens[i]) or tokens[i] in _LEADING_NOISE_TOKENS:
            i += 1
            continue
        wrapper = _word(tokens[i])
        if wrapper in _WRAPPER_WORDS:
            i += 1
            # Skip the wrapper's OWN options too (#1801 third-round
            # re-review) — `sudo -u dev`, `nice -n 10`, `env -i` used to
            # stop this loop one token early, leaving `git` unreachable.
            # The value-taking set is keyed by THIS wrapper specifically
            # (`-n` is nice's value-taking option, sudo's boolean one).
            value_opts = _WRAPPER_VALUE_TAKING_OPTS.get(wrapper, frozenset())
            while i < n and tokens[i].startswith("-"):
                if tokens[i] in value_opts and i + 1 < n:
                    i += 2
                else:
                    i += 1
            continue
        break
    if i >= n or _word(tokens[i]) != "git":
        return False, [], False
    i += 1
    dash_c_chain: list[str] = []
    has_repo_override = False
    while i < n:
        tok = tokens[i]
        if tok == "commit":
            return True, dash_c_chain, has_repo_override
        if not tok.startswith("-"):
            return False, [], False
        opt, sep, value = tok.partition("=")
        if opt == "-C":
            i += 1
            if sep:
                dash_c_chain.append(value)
            elif i < n:
                dash_c_chain.append(tokens[i])
                i += 1
            continue
        if opt in ("--git-dir", "--work-tree"):
            has_repo_override = True
            i = _advance_past_value(tokens, i, bool(sep))
            continue
        if opt in _VALUE_TAKING_OPTS:
            i = _advance_past_value(tokens, i, bool(sep))
            continue
        # Unknown or known-boolean `-`-prefixed token: skip it alone.
        # "Invert the allowlist" (#1801 re-review): an unrecognized FUTURE
        # git global option that takes no value is still safely skipped;
        # one that takes a separate-token value and isn't enumerated above
        # remains a disclosed residual gap.
        i += 1
    return False, [], False


def _all_commit_matches(cmd: str) -> list[tuple[list[str], bool]]:
    """Every matching segment's `(dash_c_chain, has_repo_override)` — ALL
    of them, not just the first (#1801 re-review: returning only the first
    match let a prepended decoy `-C` segment become the sole thing
    resolved — a concern for the now-deleted `resolve_commit_targets()`,
    #1904; `is_git_commit_command()` below only needs the length of this
    list, not which segment's `-C` chain "won")."""
    if not cmd:
        return []
    matches = []
    for segment in _all_segments(cmd):
        matched, dash_c_chain, has_repo_override = _match_commit_tokens(segment)
        if matched:
            matches.append((dash_c_chain, has_repo_override))
    return matches


def is_git_commit_command(cmd: str) -> bool:
    """Return True iff `cmd` is a `git commit` invocation (bypass or not)."""
    return bool(_all_commit_matches(cmd))


def has_bypass_flag(cmd: str) -> bool:
    """Return True iff `cmd` carries `--no-verify` or a bare `-n` flag."""
    return bypass_flag_name(cmd) is not None


def bypass_flag_name(cmd: str) -> str | None:
    """Return which bypass flag matched (`--no-verify` preferred), or None."""
    if not cmd:
        return None
    if _NO_VERIFY_RE.search(cmd):
        return "--no-verify"
    if _BARE_N_RE.search(cmd):
        return "-n"
    return None


def is_git_commit_invocation(cmd: str) -> bool:
    """Return True iff `cmd` is a gate-worthy `git commit` invocation."""
    if not is_git_commit_command(cmd):
        return False
    return not has_bypass_flag(cmd)


__all__ = (
    "bypass_flag_name",
    "has_bypass_flag",
    "is_git_commit_command",
    "is_git_commit_invocation",
)
