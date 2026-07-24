"""Enforcement anchor for evals/skills/multi-tool-code-intelligence-nudge/
slice-1-rename-generalize-the-nudge-hook-detection-and-message-composition.feature
(plan: plans/multi-tool-code-intelligence-nudge.md, issue #1368).

tests/repo/test_feature_spec_refs.py requires every `.feature` spec under
evals/skills/ to carry an `# Enforced by:` header naming a non-empty
`tests/skills/<name>.bats|.py` contract. This slice's actual, maintained
test suite is plugins/dev-team/tests/hooks/test_code_intelligence_nudge.py
(named explicitly in the plan's Step 1.1/1.2/1.3 Files lists) — duplicating
its assertions here would create a second copy to keep in sync. Instead,
this file re-runs that suite as a subprocess and fails loudly (with its
captured output) if it regresses, so the two locations can't silently
drift apart.
"""

from __future__ import annotations

import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK_TEST = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "tests"
    / "hooks"
    / "test_code_intelligence_nudge.py"
)


def test_code_intelligence_nudge_hook_suite_passes():
    assert _HOOK_TEST.is_file(), f"missing contract suite: {_HOOK_TEST}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_HOOK_TEST), "-q"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
