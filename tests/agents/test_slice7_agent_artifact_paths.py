"""Content-guard: codebase-recon.md, orchestrator.md, and progress-guardian.md
no longer describe bare project-scoped memory/ writer targets (Slice 7, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

These three agents are "Enforcement: script"-tagged and each cross-references
a root-level `scripts/<name>.py` helper used for /agent-eval style validation
against fixtures — that helper is repo-internal tooling, not shipped plugin
code, and is out of this sweep's scope. The agent's own prose is what a live
Claude Code session actually follows when dispatched against a downstream
project, so its `memory/` writer-target documentation must still reflect the
current `.claude/memory/` convention.

`plans/` references in these three files describe the operator-facing
implementation-plan-file convention (the same domain as /plan's own shipped
default, `plans/<slugified-task>.md`) — a different concept from this epic's
`.claude/plans/` runtime-state domain — and are deliberately left bare.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"

CODEBASE_RECON = (PLUGIN / "agents" / "codebase-recon.md").read_text(encoding="utf-8")
ORCHESTRATOR = (PLUGIN / "agents" / "orchestrator.md").read_text(encoding="utf-8")
PROGRESS_GUARDIAN = (PLUGIN / "agents" / "progress-guardian.md").read_text(
    encoding="utf-8"
)

_BARE_MEMORY_RE = re.compile(r"(?<!\.claude/)memory/")


def test_codebase_recon_has_no_bare_memory_reference() -> None:
    assert not _BARE_MEMORY_RE.search(CODEBASE_RECON)
    assert ".claude/memory/recon-<slug>.json" in CODEBASE_RECON
    assert ".claude/memory/recon-<slug>.md" in CODEBASE_RECON
    assert ".claude/memory/recon-<slug>.inventory.txt" in CODEBASE_RECON


def test_orchestrator_has_no_bare_memory_reference() -> None:
    # the one benign hit is the "performance-metrics/SKILL.md" link, which
    # contains "metrics/" not "memory/" — assert memory/ specifically.
    assert not _BARE_MEMORY_RE.search(ORCHESTRATOR)
    assert ".claude/memory/recon-<slug>.md" in ORCHESTRATOR


def test_progress_guardian_memory_reference_relocated_plans_stays_bare() -> None:
    assert not _BARE_MEMORY_RE.search(PROGRESS_GUARDIAN)
    assert 'Glob(".claude/memory/**")' in PROGRESS_GUARDIAN
    # the plan-file convention (a distinct, operator-facing domain) stays bare
    assert 'Glob("plans/**")' in PROGRESS_GUARDIAN
