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
        ".json", ".jsonc", ".xml", ".html", ".htm", ".vue", ".svelte",
        ".sql", ".proto", ".tf", ".hcl",
    }
)

#: Field/record separators for the canonical serialization. Chosen from the
#: ASCII separator block so they cannot occur in a source line git emits.
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"


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


def normalize_patch(patch_text: str) -> str | None:
    """Reduce a unified diff to its behavior-bearing content.

    Returns a canonical string, or `None` when the patch cannot be parsed
    (fail-closed — the caller must not treat `None` as "no changes").

    The canonical form deliberately excludes hunk headers: line numbers shift
    whenever an earlier doc hunk is dropped or an indentation fix lands, and
    including them would defeat the invariance this function exists to
    provide. Files are emitted in sorted order so a re-stage that reorders
    git's own file output cannot change the digest.
    """
    if patch_text is None:
        return None

    per_file: dict = {}
    path: str | None = None
    old_path: str | None = None
    removed: list = []
    added: list = []
    in_hunk = False

    def flush() -> None:
        nonlocal removed, added
        name = path or old_path
        if name is not None and (removed or added):
            entry = per_file.setdefault(name, {"removed": [], "added": []})
            entry["removed"].extend(removed)
            entry["added"].extend(added)
        removed, added = [], []

    try:
        for raw in patch_text.splitlines():
            if raw.startswith("diff --git "):
                flush()
                path = old_path = None
                in_hunk = False
            elif raw.startswith("--- "):
                flush()
                old_path = _source_path(raw)
                in_hunk = False
            elif raw.startswith("+++ "):
                flush()
                path = _target_path(raw)
                in_hunk = False
            elif raw.startswith("@@"):
                flush()
                in_hunk = True
            elif not in_hunk:
                # File-mode lines, `index` lines, `similarity index`, and any
                # other pre-hunk metadata. Excluded deliberately: a mode
                # change is real, but it is carried by the raw-hash lens,
                # which is still evaluated first and still authoritative.
                continue
            elif raw.startswith("+"):
                added.append(raw[1:])
            elif raw.startswith("-"):
                removed.append(raw[1:])
            elif raw.startswith("\\"):
                continue
        flush()
    except Exception:  # noqa: BLE001 - fail closed, see module docstring
        return None

    records = []
    for name in sorted(per_file):
        if _is_documentation(name):
            continue
        entry = per_file[name]
        collapsible = _whitespace_collapsible(name)
        rem = [_canonical_line(ln, collapsible) for ln in entry["removed"]]
        add = [_canonical_line(ln, collapsible) for ln in entry["added"]]
        if rem == add:
            # Every changed line in this file canonicalizes identically —
            # the file's whole delta was formatting.
            continue
        records.append(_FIELD_SEP.join([name, "\n".join(rem), "\n".join(add)]))
    return _RECORD_SEP.join(records)


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

    Returns `None` — never a digest of empty input — when git fails. An
    empty-input digest would be a CONSTANT across every broken-git
    invocation, and the whole point of this lens is that two parties must
    independently arrive at the same non-trivial value.
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
    if normalized is None:
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
