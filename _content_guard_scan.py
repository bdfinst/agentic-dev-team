"""Shared file-discovery helper for the plugin-markdown content-guard tests.

`tests/repo/test_bare_invocation_wide_scan.py` and
`tests/repo/test_claude_plugin_root_quoting.py` each scan a subset of
`plugins/dev-team/`'s markdown tree, differing only in *which*
subdirectories they include — this is the one piece those two guards
genuinely share (flagged by structure-review during #1655/#1656's own code
review as duplicated verbatim); every other part of each guard (the regex
grammar, the fence-state tracking, the exemption registry) is
lens-specific and stays in its own file.

Scoped to the repo root via the ``pythonpath = .`` entry in ``pytest.ini``,
matching ``_repo_root.py``'s own convention (see that module's docstring),
rather than living inside ``tests/repo/`` where ``--import-mode=importlib``
would not make it importable by bare name.
"""

from __future__ import annotations

from pathlib import Path

#: The one scan surface both content guards share. Declared once here so the
#: two guards can no longer silently diverge the way they did before
#: (`test_bare_invocation_wide_scan.py` once omitted `"agents"` while its
#: sibling included it) — `scanned_markdown_files` still takes `scan_dirs` as
#: an explicit parameter rather than defaulting to this constant, so a
#: future guard with a genuinely narrower surface isn't forced to match it.
PLUGIN_MARKDOWN_SCAN_DIRS = ("skills", "docs", "knowledge", "agents")


def scanned_markdown_files(plugin_root: Path, scan_dirs: tuple) -> list:
    """Every `**/*.md` file under `plugin_root / sub` for each `sub` in
    `scan_dirs` that exists, sorted within each subdirectory."""
    files = []
    for sub in scan_dirs:
        root = plugin_root / sub
        if root.is_dir():
            files.extend(sorted(root.glob("**/*.md")))
    return files
