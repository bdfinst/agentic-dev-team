"""hooks/lib/doc_classification.py — shared documentation-classification
literal tables (#1477).

`hooks/pre_commit_review.py`'s doc-only exemption predicate
(`hooks/lib/pre_commit_doc_classifier.py` as of this same change) and
`skills/code-review/scripts/change_shape.py`'s low-yield-lens gate both
classify a changed file as "documentation" — but for different purposes and
at different strictness levels (see `pre_commit_doc_classifier.py`'s module
docstring: the pre-commit gate's predicate is a deliberate STRICT SUBSET of
`change_shape.py`'s, never a superset, so the two must never be forced into
lockstep). Prior to this module the two call sites hand-duplicated the same
literal word lists, kept in sync only by comment convention — exactly the
class of gap that needed fixing across four separate `pre_commit_review.py`
hardening rounds (#1461) without anything forcing the `change_shape.py`
sibling copy to be checked too.

This module carries ONLY the literal data that is actually identical between
the two call sites today, with one exception: `is_functional_config` below
(#1923's third caller, `scripts/select_lenses.py`) IS shared logic, not just
data — but only because `change_shape.py` and `select_lenses.py` want the
exact same predicate over the exact same composed segment set (the
`"templates"` addition included), with no matching-semantics divergence
between them the way `pre_commit_doc_classifier.py` has from both (see the
`CORE_FUNCTIONAL_CONFIG_SEGMENTS` comment below). `pre_commit_doc_classifier.py`
does NOT call this function — it keeps its own inline check reading the raw
`CORE_FUNCTIONAL_CONFIG_SEGMENTS`/`FUNCTIONAL_CONFIG_NAMES` constants
directly, staying the strict subset its own docstring requires. Every other
matching *logic* here (exact-name vs. prefix match for doc detection) stays
local to each caller by design — unifying THAT, not just the data, would
re-introduce the subset/superset coupling the pre-commit gate's docstring
explicitly warns against.

Location: `hooks/lib/` rather than a new top-level `shared/` directory.
There is no existing precedent in this repo for a module living outside
both `hooks/` and `skills/*/scripts/` that either side imports — grepping
found no prior cross-boundary shared-constant mechanism. `hooks/lib/`
already hosts several business-logic-free utility modules other packages
reach into (`artifact_paths.py`, `stdin_json.py`, `minimal_yaml.py`), so a
neutral, pure-data module fits the same convention; `change_shape.py`
reaches it via the identical `sys.path.insert` pattern
`hooks/pre_commit_review.py` already uses for its own `hooks/lib/` imports
(see that module's top-of-file import block). This is a one-line documented
choice, not an established repo-wide convention — revisit if a genuine
`shared/` location emerges later.

Stdlib only.
"""

from __future__ import annotations

from pathlib import PurePosixPath  # used by is_functional_config below

# Documentation extensions (lower-cased). Byte-identical set between
# `change_shape.py`'s `_DOC_EXTENSIONS` and
# `pre_commit_doc_classifier.py`'s `_DOC_EXTENSIONS` prior to this
# extraction.
DOC_EXTENSIONS = frozenset({".md", ".mdx", ".markdown", ".rst", ".txt", ".adoc"})

# Documentation root-file word list (lower-cased), identical set of 7 words
# between both call sites. NOTE: the two callers apply DIFFERENT matching
# semantics on top of this SAME word list, by deliberate design —
# `change_shape.py` does a stem PREFIX match (`stem.startswith(word)`,
# appropriate for its own lower-stakes lens-narrowing purpose);
# `pre_commit_doc_classifier.py` does an EXACT match (`stem in
# frozenset(DOC_ROOT_WORDS)`, required because it is the sole gate deciding
# a zero-dispatch-evidence exemption — see that module's docstring for why
# prefix matching was exploitable there). This module carries only the
# shared words; each caller keeps its own matching logic.
DOC_ROOT_WORDS = (
    "readme",
    "changelog",
    "contributing",
    "license",
    "notice",
    "authors",
    "code_of_conduct",
)

# Functional-config filenames anywhere in the tree. Byte-identical set
# between both call sites.
FUNCTIONAL_CONFIG_NAMES = frozenset({"claude.md", "agents.md"})

# Functional-config path segments COMMON to both call sites. `change_shape.py`
# additionally treats "templates" as functional-config (its own
# `_FUNCTIONAL_CONFIG_SEGMENTS` adds it on top of this core set);
# `pre_commit_doc_classifier.py` deliberately does not (staying the strict
# subset its docstring requires). That one-item divergence predates this
# extraction and is preserved exactly as it was — not resolved — here; each
# caller layers its own additions on top of this shared core.
CORE_FUNCTIONAL_CONFIG_SEGMENTS = frozenset({".claude", "agents", "skills", "prompts", "knowledge"})

# `change_shape.py`'s own "templates" addition, baked in here because
# `select_lenses.py` wants the identical composed set — see `is_functional_config`.
_FUNCTIONAL_CONFIG_SEGMENTS_WITH_TEMPLATES = CORE_FUNCTIONAL_CONFIG_SEGMENTS | {"templates"}


def is_functional_config(file_path: str) -> bool:
    """True when ``file_path`` drives agent/skill/command behavior and must
    never be treated as inert documentation/config regardless of extension.
    Shared by `change_shape.py` and `select_lenses.py` (#1923) — see this
    module's docstring for why this one predicate is shared logic, not just
    data, and why `pre_commit_doc_classifier.py` deliberately does not call
    it."""
    path = PurePosixPath(file_path)
    if path.name.lower() in FUNCTIONAL_CONFIG_NAMES:
        return True
    return any(seg in _FUNCTIONAL_CONFIG_SEGMENTS_WITH_TEMPLATES for seg in path.parts)


__all__ = (
    "CORE_FUNCTIONAL_CONFIG_SEGMENTS",
    "DOC_EXTENSIONS",
    "DOC_ROOT_WORDS",
    "FUNCTIONAL_CONFIG_NAMES",
    "is_functional_config",
)
