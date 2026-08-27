"""slug — shared repo-root slug derivation.

Single source of truth for the kebab-safe, lowercase slug both
`codebase_recon.py` (its `.claude/memory/recon-<slug>.json` artifact naming)
and `orchestrator.py` (its `_recon_artifact_path` lookup of that same
artifact) must agree on byte-for-byte — a drifted copy in either script
would silently compute the wrong artifact path. Promoted from two
hand-duplicated private copies (`codebase_recon.py::_derive_slug`,
`orchestrator.py::_derive_recon_slug`) per issue #2068, following this
directory's existing `from lib import ...` convention
(`codebase_recon.py` already imports `deterministic_recon` this way).
"""

from __future__ import annotations

import re
from pathlib import Path

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9._-]")
_REPEATED_DASHES = re.compile(r"-{2,}")


def derive_slug(root: Path) -> str:
    """Derive a kebab-safe, lowercase slug from `root`'s resolved directory name.

    Falls back to `"repo"` when the name has no slug-safe characters left
    after stripping (e.g. an all-punctuation directory name).
    """
    name = root.resolve().name.lower()
    name = _NON_SLUG_CHARS.sub("-", name)
    name = _REPEATED_DASHES.sub("-", name)
    name = name.strip("-")
    return name or "repo"
