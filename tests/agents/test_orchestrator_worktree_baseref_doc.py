"""Slice 3 / Step 3.1 — documentation gate for the worktree.baseRef=head
settings-scope constraint from issue #553.

Scenarios (from plans/build-worktree-inherits-caller-head.md Slice 3):

  Scenario: orchestrator agent describes the required user action
    Given plugins/dev-team/agents/orchestrator.md
    When I read the Wave-Aware Build Dispatch section
    Then it names "worktree.baseRef" and points at the knowledge section
      stating that users must set it in `.claude/settings.json` or
      `~/.claude/settings.json`

#2011 moved the wave mechanics out of the always-on agent body and behind the
knowledge index; the settings-scope detail and the spike link now live in
`knowledge/three-phase-workflow.md` § Wave-aware build dispatch. The orchestrator
keeps the `worktree.baseRef` name and the anchor that reaches the detail, so the
prerequisite is still visible to a session reading only the agent body.

  Scenario: request-processing-flow references the constraint
    Given plugins/dev-team/knowledge/request-processing-flow.md
    When I read the Implement step
    Then it references worktree.baseRef and the settings file the user
      is expected to edit

Hermetic: this suite is a read-only check against checked-in files; no git
ops, no fs mutation.

Ported from tests/agents/orchestrator_worktree_baseref_doc_tests.bats
(issue #675: bats -> pytest).
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

ORCH = REPO_ROOT / "plugins" / "dev-team" / "agents" / "orchestrator.md"
FLOW_DOC = (
    REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "request-processing-flow.md"
)
PHASES = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "three-phase-workflow.md"
WAVE_ANCHOR = (
    "${CLAUDE_PLUGIN_ROOT}/knowledge/three-phase-workflow.md#wave-aware-build-dispatch"
)

SETTINGS_FILE_RE = re.compile(r"(\.claude/settings\.json|~/\.claude/settings\.json)")


def test_orchestrator_documents_worktree_baseref() -> None:
    text = ORCH.read_text(encoding="utf-8")
    assert "worktree.baseRef" in text


def test_orchestrator_points_at_the_wave_section_carrying_the_detail() -> None:
    # The on-demand path: the always-on agent body names the exact anchor a
    # session resolves to reach the settings-scope detail below.
    text = ORCH.read_text(encoding="utf-8")
    assert WAVE_ANCHOR in text


def test_phase_reference_names_settings_file_user_must_edit() -> None:
    # Either project-level or user-level .claude/settings.json — the two
    # scopes the Slice 0 spike proved are honored.
    text = PHASES.read_text(encoding="utf-8")
    assert SETTINGS_FILE_RE.search(text)


def test_phase_reference_points_at_spike_audit_trail() -> None:
    # Non-blocking discoverability — the doc should link to the spike so a
    # reader can trace *why* only certain scopes are honored.
    text = PHASES.read_text(encoding="utf-8")
    assert "worktree-baseref-head-spike" in text


def test_request_processing_flow_documents_worktree_baseref() -> None:
    text = FLOW_DOC.read_text(encoding="utf-8")
    assert "worktree.baseRef" in text


def test_request_processing_flow_names_settings_file() -> None:
    text = FLOW_DOC.read_text(encoding="utf-8")
    assert SETTINGS_FILE_RE.search(text)


def test_request_processing_flow_points_at_spike_audit_trail() -> None:
    # Parity with orchestrator.md — spec AC6 requires all three doc
    # locations to link the spike file explicitly.
    text = FLOW_DOC.read_text(encoding="utf-8")
    assert "worktree-baseref-head-spike" in text
