"""knowledge_index_paths — single source of truth for the indexed corpus.

Python port of hooks/lib/knowledge-index-paths.sh (#575 / #572 Cluster A).

Imported (not executed) by the Python siblings of the three .sh callers:
  - hooks/knowledge-index.py                   (PostToolUse regenerator)
  - hooks/pre-commit-knowledge-index.py        (pre-commit freshness gate)
  - tests/agents/… anchor-citation gate        (still bats today; the .py
                                                port will import this module)

The corpus is:
  - plugins/dev-team/knowledge/*.md         (top-level .md only)
  - plugins/dev-team/skills/<name>/SKILL.md

Excluded:
  - plugins/dev-team/knowledge/schemas/**   (json schemas, not docs)
  - everything else (agents/, commands/, docs/, README.md, …)

Anchor: top-level knowledge .md OR <skills-dir>/<one segment>/SKILL.md.
A leading `(^|/)` allows repo-relative or absolute paths.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Regex matching corpus paths (POSIX ERE from the .sh sibling, ported to
# Python re syntax). Anchor: end-of-string; a leading segment is optional so
# absolute and repo-relative inputs both match. Alternation covers the two
# corpus shapes: top-level knowledge markdown, and per-skill SKILL.md.
CORPUS_REGEX: str = (
    r"(^|/)plugins/dev-team/(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md)$"
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
