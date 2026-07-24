"""Pins extract()'s Skill/Agent tool_use detection and gate (commit-bypass,
#111) signals — output shapes not covered by the primary fixture in
test_session_extract.py. Added ahead of the extract() concern-splitting
refactor (Medium complexity finding) so the refactor stays behavior-preserving.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "scripts" / "session_extract.py"
FIX = (
    REPO_ROOT / "tests" / "fixtures" / "session-review" / "sample-transcript-gate.jsonl"
)
PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _digest() -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT),
            "--transcript",
            str(FIX),
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_extract_detects_skill_and_agent_tool_use_invocations() -> None:
    digest = _digest()
    utilization = digest["utilization"]
    # namespace prefixes ("dev-team:", "agentic-dev-team:") are stripped so
    # invoked names match the bare registry ids.
    assert utilization["skills_invoked"] == {"code-review": 1}
    assert utilization["agents_invoked"] == {
        "explore-agent": 1,
        "triage-agent": 1,
    }


def test_extract_detects_commit_attempts_and_review_gate_bypasses() -> None:
    digest = _digest()
    gate = digest["gate"]
    assert gate["commit_attempts"] == 2
    assert gate["commit_bypasses"] == 1
    assert gate["bypass_rate"] == 0.5
