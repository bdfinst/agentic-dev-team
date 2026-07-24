"""Enforcement anchor for evals/skills/multi-tool-code-intelligence-nudge/
slice-3-refresh-docs-and-knowledge-doc-fix-stale-reference-test-fixtures.feature
(plan: plans/multi-tool-code-intelligence-nudge.md, issue #1368).

INTERIM reference (Step 1.1 scope-extension, ahead of Slice 3 itself):
Slice 3 (Step 3.2) extends tests/knowledge/test_codegraph_vs_graphify_doc.py
with the doc-drift regression tests named in the plan. Until that lands,
this file points at the pre-existing (not-yet-extended) suite so
tests/repo/test_feature_spec_refs.py's `# Enforced by:` check has a real,
non-empty target instead of a dangling reference. Slice 3 should confirm
this still points at the right file once its own edits land (the path
itself doesn't change, only the suite's contents grow).
"""

from __future__ import annotations

import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_DOC_TEST = _REPO_ROOT / "tests" / "knowledge" / "test_codegraph_vs_graphify_doc.py"


def test_codegraph_vs_graphify_doc_suite_passes():
    assert _DOC_TEST.is_file(), f"missing contract suite: {_DOC_TEST}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_DOC_TEST), "-q"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
