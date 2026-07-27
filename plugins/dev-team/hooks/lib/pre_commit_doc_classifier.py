"""hooks/lib/pre_commit_doc_classifier.py — the `.review-passed` gate's
doc-only exemption predicate (#1461, extracted from `pre_commit_review.py`
under #1477).

Moved out of `pre_commit_review.py` (which had grown to ~759 lines, mixing
the hook stdin/exit-code contract, git querying, plugin-version resolution,
bypass-audit recording, boundary-event emission, doc-only classification,
and the gate-verdict decision engine all in one file) so that module can
stay to hook-contract plumbing and wiring, with this predicate as its own
independently testable, independently reviewable unit.

Re-derives the doc-only exemption's OWN predicate (#1461 security review)
rather than trusting the claim in the ledger event: `--event doc-only`
(`boundary_events.py`) is written by the SAME untrusted party this gate
exists to constrain, so an unconditional "the event exists, therefore trust
it" check is the classic trust-the-client pattern — nothing previously
verified the exempted diff was actually documentation.

Deliberately a TIGHTER re-implementation of `code-review/SKILL.md`'s
doc-only short-circuit and `skills/code-review/scripts/change_shape.py`'s
`_is_documentation` (built on `hooks/lib/doc_classification.py`'s SHARED
literal tables, but not a lockstep copy of `change_shape.py`'s matching
logic — #1461 second security re-review found the original copy
exploitable): those two only ever ADD a review lens or skip everything on
already-honest input; this function is the sole gate deciding whether a
"record zero dispatch evidence" exemption is honored at all, so it must be
a STRICT SUBSET of what SKILL.md/change_shape.py would call documentation,
never a superset. Concretely: (1) a root-doc EXACT NAME (README, LICENSE,
...) only counts at the repository root (`len(parts) == 1`) AND only when
the stem carries NO extension at all — `license_manager.py` staged at the
repo root must never match merely because its basename starts with
"license", and (#1461 FOURTH security re-review) `license-check` or
`readme-lint` must never match either, despite also being extensionless: an
earlier fix used `stem.startswith(prefix)`, which still admitted any
extensionless name merely beginning with a root-doc prefix. Exact
membership in the doc-root word set is the only form that matches this
comment's own stated intent ("the genuinely extensionless case: LICENSE,
NOTICE, AUTHORS") — a `README.txt`-shaped file is already covered by the
`DOC_EXTENSIONS` branch above, so this branch exists ONLY for those exact
extensionless root docs, nothing glob-shaped; (2) a `docs/` directory
membership alone is NOT sufficient — a doc extension is still required,
since `docs/conf.py` or a doc-site build script is executable code that
happens to live under `docs/`. Path segments are lower-cased once, matching
the stem, so a case-insensitive checkout (`Agents/foo.md`, `.Claude/x.md`)
can't escape the functional-config exclusion below by case alone.
`CORE_FUNCTIONAL_CONFIG_SEGMENTS`'s bare `"agents"` entry already matches
`templates/agents/`, and any other `.../agents/...` path, exactly per
`code-review/SKILL.md`'s literal stated rule — no separate
templates-specific helper is needed. If this rule ever needs to change,
change it here first and only loosen the lens-narrowing siblings to
match — never the reverse.

Stdlib only. Python 3.8+.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from doc_classification import (  # noqa: E402
    CORE_FUNCTIONAL_CONFIG_SEGMENTS,
    DOC_EXTENSIONS,
    DOC_ROOT_WORDS,
    FUNCTIONAL_CONFIG_NAMES,
)

_DOC_ROOT_NAMES = frozenset(DOC_ROOT_WORDS)

# `.txt` is in `DOC_EXTENSIONS` for real plain-text docs (README.txt), but a
# `.txt`/`.md`-shaped dependency manifest or build file is executable/
# supply-chain surface, not documentation (#1461 fourth security re-review) —
# denylisted by exact name regardless of matching a doc extension above.
_NON_DOC_NAMES_DESPITE_EXTENSION = {
    "requirements.txt", "requirements-dev.txt", "constraints.txt",
    "cmakelists.txt",
}
# Same denylist, by directory instead of exact basename (#1461 fifth
# security re-review): the common multi-file pip layout
# (`requirements/base.txt`, `constraints/pins.txt`) escapes the exact-name
# check above while still matching `DOC_EXTENSIONS`.
_NON_DOC_DIR_SEGMENTS = {"requirements", "constraints"}


def is_doc_only_changeset(files: list[str]) -> bool:
    """True only when EVERY given path is provably documentation and none is
    functional Claude-config markdown. An empty list — or a list whose every
    entry is blank/unusable — is not doc-only: there is nothing to exempt,
    so this must never vacuously pass."""
    saw_any = False
    for raw in files:
        name = raw.strip()
        if not name:
            continue
        parts = [p.lower() for p in name.replace("\\", "/").split("/") if p]
        if not parts:
            continue
        saw_any = True
        stem = parts[-1]
        suffix = "." + stem.rsplit(".", 1)[-1] if "." in stem else ""
        in_non_doc_dir = suffix in DOC_EXTENSIONS and any(
            seg in _NON_DOC_DIR_SEGMENTS for seg in parts[:-1]
        )
        if (
            stem in FUNCTIONAL_CONFIG_NAMES
            or stem in _NON_DOC_NAMES_DESPITE_EXTENSION
            or in_non_doc_dir
            or any(seg in CORE_FUNCTIONAL_CONFIG_SEGMENTS for seg in parts)
        ):
            return False
        if suffix in DOC_EXTENSIONS:
            continue
        # A root-doc EXACT NAME (README, LICENSE, ...) only counts at the
        # repo root — never at any depth, never with an extension, and
        # never merely as a name PREFIX (`license-check` is not "license").
        if len(parts) == 1 and stem in _DOC_ROOT_NAMES:
            continue
        return False
    return saw_any


__all__ = ("is_doc_only_changeset",)
