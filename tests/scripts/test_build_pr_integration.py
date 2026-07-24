"""Pins build/pr SKILL.md wiring to progress_guardian.py, not the retired
agent-dispatch pattern.

Ported from tests/scripts/build_pr_integration_tests.bats (issue #676).
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

BUILD_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"
PR_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "pr" / "SKILL.md"


def test_build_skill_references_progress_guardian_py() -> None:
    assert "scripts/progress_guardian.py" in BUILD_SKILL.read_text()


def test_build_skill_does_not_dispatch_progress_guardian_agent() -> None:
    assert not re.search(
        r"(dispatch|Agent:)\s+progress-guardian", BUILD_SKILL.read_text()
    )


def test_pr_skill_references_progress_guardian_py_pre_pr() -> None:
    assert "scripts/progress_guardian.py --pre-pr" in PR_SKILL.read_text()


def test_pr_skill_does_not_dispatch_progress_guardian_agent() -> None:
    assert not re.search(r"(dispatch|Agent:)\s+progress-guardian", PR_SKILL.read_text())
