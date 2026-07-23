"""Enforcement anchor for evals/skills/multi-tool-code-intelligence-nudge/
slice-2-extend-the-turn-mark-sentinel-to-repowise-list-based-schema.feature
(plan: plans/multi-tool-code-intelligence-nudge.md, issue #1368).

INTERIM reference (Step 1.1 scope-extension, ahead of Slice 2 itself):
Slice 2 (Step 2.1) renames plugins/dev-team/hooks/codegraph_turn_mark.py ->
code_intelligence_turn_mark.py and its test file. Until that lands, this
file points at the pre-rename suite
(plugins/dev-team/tests/hooks/test_codegraph_turn_mark.py) so
tests/repo/test_feature_spec_refs.py's `# Enforced by:` check has a real,
non-empty target instead of a dangling reference. Slice 2 MUST update the
path below (and this file's docstring) to the renamed test file once it
lands — do not let this go stale.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_TEST = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "tests"
    / "hooks"
    / "test_codegraph_turn_mark.py"
)


def test_turn_mark_hook_suite_passes():
    assert _HOOK_TEST.is_file(), f"missing contract suite: {_HOOK_TEST}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_HOOK_TEST), "-q"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
