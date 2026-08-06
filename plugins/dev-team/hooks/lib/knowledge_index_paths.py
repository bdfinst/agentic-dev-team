"""knowledge_index_paths — single source of truth for which path edits must
trigger an index rebuild/freshness check.

Python port of hooks/lib/knowledge-index-paths.sh (#575 / #572 Cluster A).

Imported (not executed) by the Python siblings of the three .sh callers:
  - hooks/knowledge-index.py                   (PostToolUse regenerator)
  - hooks/pre-commit-knowledge-index.py        (pre-commit freshness gate)
  - tests/agents/… anchor-citation gate        (still bats today; the .py
                                                port will import this module)

`is_corpus_path()` answers "does an edit here change indexed content and
need a rebuild" — that is a broader set than "is this file a top-level
index entry" (owned by build_knowledge_index.py's `discover_files()`, which
walks only the first two shapes below). Deliberately two different
questions, not two copies of one: a references/*.md file is never itself an
index entry, but editing it changes the *summary* of the SKILL.md section
that includes it, so it must trigger the same rebuild as editing that
SKILL.md directly.

Rebuild triggers:
  - plugins/dev-team/knowledge/*.md                    (top-level .md only;
                                                        also an index entry)
  - plugins/dev-team/skills/<name>/SKILL.md            (also an index entry)
  - plugins/dev-team/skills/<name>/references/*.md     (NOT an index entry —
                                                        only feeds another
                                                        entry's summary, via
                                                        build_knowledge_index.py's
                                                        `<!-- include:
                                                        references/<name>.md
                                                        -->` marker
                                                        resolution, Step 1.1
                                                        of plans/
                                                        test-improve-context-loading-strategy.md)

Excluded:
  - plugins/dev-team/knowledge/schemas/**   (json schemas, not docs)
  - everything else (agents/, commands/, docs/, README.md, …)

Anchor: top-level knowledge .md, <skills-dir>/<one segment>/SKILL.md, OR
<skills-dir>/<one segment>/references/<one segment>.md. A leading `(^|/)`
allows repo-relative or absolute paths.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Regex matching corpus paths (POSIX ERE from the .sh sibling, ported to
# Python re syntax). Anchor: end-of-string; a leading segment is optional so
# absolute and repo-relative inputs both match. Alternation covers the three
# corpus shapes: top-level knowledge markdown, per-skill SKILL.md, and
# per-skill references/*.md (spliced into a SKILL.md summary via include
# markers — see the module docstring above).
CORPUS_REGEX: str = (
    r"(^|/)plugins/dev-team/"
    r"(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md|skills/[^/]+/references/[^/]+\.md)$"
)

_CORPUS_RE = re.compile(CORPUS_REGEX)


def is_corpus_path(path: str) -> bool:
    """Return True iff `path` is part of the indexed corpus.

    Byte-parity with the .sh's `_is_corpus_path`. Windows backslash paths
    do NOT match — the corpus is a forward-slash convention and Git Bash
    surfaces forward slashes even on Windows.
    """
    if not path:
        return False
    return _CORPUS_RE.search(path) is not None


def filter_corpus_paths(paths: Iterable[str]) -> list[str]:
    """Return the input list filtered to corpus paths, preserving order.

    Convenience for hook callers that receive a batch of changed files and
    want only the ones the index cares about. Order-preserving because
    downstream builds are order-sensitive (see build_knowledge_index.py).
    """
    return [p for p in paths if is_corpus_path(p)]


__all__ = ("CORPUS_REGEX", "filter_corpus_paths", "is_corpus_path")
