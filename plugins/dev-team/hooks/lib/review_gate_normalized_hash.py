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
import sys
from pathlib import Path

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
        ".json", ".jsonc", ".xml",
        ".sql", ".proto", ".tf", ".hcl",
    }
)

#: KNOWN RESIDUAL (#1631 review). The quote-character rule in
#: `_canonical_line` is what keeps string data out of the cosmetic bucket,
#: and it does not see an unquoted heredoc body — Ruby's `<<~SQL`, PHP's
#: `<<<TXT`, Perl's `<<EOF`. Reindenting a line inside one is a data change
#: this module would read as formatting. Narrower than the indentation-
#: significance hazard (which moves code between blocks) and it needs the
#: same language awareness that defers comment stripping to v2, so it is
#: recorded here rather than papered over with a heuristic.

#: Field/record separators for the canonical serialization. Chosen from the
#: ASCII separator block because they are vanishingly rare in source, but NOT
#: relied on for unambiguity: every field is length-prefixed by `_encode`, so
#: a file that genuinely contains these bytes cannot forge a field boundary.
#: git treats any NUL-free blob as text, so "no source line contains \x1f" is
#: an assumption about content an attacker supplies (#1631 review).
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"


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


def _whitespace_collapsible(path: str) -> bool:
    """True only for extensions this module can prove are brace/keyword-
    delimited. Everything else — including every unknown extension and every
    extensionless file — is compared byte-exactly. Fail-closed by default:
    the safe answer to "is this language's indentation meaningless?" is no."""
    name = str(path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "." not in name:
        return False
    suffix = "." + name.rsplit(".", 1)[-1]
    if suffix in _INDENT_SIGNIFICANT_EXTENSIONS:
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


def _parse_hunk_header(raw: str) -> tuple[int, int] | None:
    """`(old_count, new_count)` from an `@@ -a,b +c,d @@` header.

    An omitted count means 1 (`@@ -1 +1 @@`). Returns `None` for anything
    that is not a well-formed unified-diff hunk header, including the
    combined `@@@` form, which this module never asks git to produce.
    """
    match = _HUNK_HEADER_RE.match(raw)
    if match is None:
        return None
    old_count = int(match.group(2)) if match.group(2) is not None else 1
    new_count = int(match.group(4)) if match.group(4) is not None else 1
    return old_count, new_count


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
    in_hunk = False

    def close_hunk() -> None:
        nonlocal old_side, new_side, in_hunk
        if in_hunk and current is not None:
            current.hunks.append((old_side, new_side))
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
                old_remaining, new_remaining = counts
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
    for section in sorted(sections, key=lambda s: s.name):
        name = section.name
        if section.has_real_path and _is_documentation(name):
            continue
        collapsible = _whitespace_collapsible(name)
        parts = list(section.structural)
        if section.binary:
            # The blob SHAs are the only content signal a textual diff
            # exposes for a binary file, and without them any binary
            # replacement is invisible to this digest.
            parts.append(section.index_line or "binary")
        for old_lines, new_lines in section.hunks:
            old_canon = [_canonical_line(ln, collapsible) for ln in old_lines]
            new_canon = [_canonical_line(ln, collapsible) for ln in new_lines]
            if old_canon == new_canon:
                # This hunk's two sides canonicalize identically — its whole
                # delta was formatting.
                continue
            parts.append("\n".join(old_canon))
            parts.append("\n".join(new_canon))
        if not parts:
            continue
        records.append(_encode([name] + parts))
    return _RECORD_SEP.join(_encode([record]) for record in records)


def normalized_gate_hash(cwd=None, target: str = "--cached") -> str | None:
    """sha256 of the normalized staged patch, or `None` on any failure.

    Uses the same `git_safe_diff.run_safe_git_diff` invocation and the same
    `--no-color --no-ext-diff --no-textconv` pins as `review_gate_hash()`.
    Those flags are not optional here either: a `diff.external` driver would
    otherwise collapse this function's input to empty for every changeset,
    turning the normalized hash into a constant — the same subject-binding
    bypass `review_gate_hash()`'s docstring documents at length.

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
            ["--no-color", "--no-ext-diff", "--no-textconv"],
            cwd=cwd,
            text=False,
            target=target,
        )
    except (FileNotFoundError, OSError):
        return None

    if completed.returncode != 0:
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
