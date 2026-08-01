"""_bdd_markers — the shared per-language BDD pending-marker table.

Hoisted out of `gherkin_stub_gate.py` (issue #1421 bug 5): that module's
`_MARKERS_BY_EXT` used to be imported by `stub_extractors/__init__.py` via a
`sys.path` reach-up into the parent `scripts/` entry-point layer and a
leading-underscore "private" name — the only module under `scripts/lib/` in
the whole repo that imported from its own parent layer (every sibling lib
module, `_vendored_tree.py`/`_gherkin_text.py` included, is either
stdlib-only or imports lib siblings). This module is the shared home both
`gherkin_stub_gate.py` and `stub_extractors/__init__.py` import from instead,
under a public name.

Extension (lowercase) -> (language label, pending marker substrings).

Stdlib-only. (ADR 0014/0015).
"""

from __future__ import annotations

MARKERS_BY_EXT = {
    ".js": ("JS/TS", ("this.pending()",)),
    ".ts": ("JS/TS", ("this.pending()",)),
    ".mjs": ("JS/TS", ("this.pending()",)),
    ".cjs": ("JS/TS", ("this.pending()",)),
    ".java": ("Java", ("PendingException",)),
    ".cs": ("C#", ("PendingStepException", "StepIsPending()")),
    ".go": ("Go", ("godog.ErrPending",)),
}
