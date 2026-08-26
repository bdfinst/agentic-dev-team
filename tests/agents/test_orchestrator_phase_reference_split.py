"""#2011 — the orchestrator's per-phase detail is reachable on demand.

`agents/orchestrator.md` is a main-loop role, not a dispatch target: nothing
spawns `orchestrator` as a subagent, so its whole body is always-on context paid
by every session before any work happens. #2011 moved the part that is only
needed *once a phase is actually running* — persona rosters, the conditional
Codebase Recon / Security Engineer dispatch rules, wave mechanics, the inline
review checkpoints and the review loop — into two knowledge files, leaving the
routing tables and the cross-phase invariants always on.

That trade is only safe if the on-demand path actually resolves. These checks are
the mechanism for that, and they are deterministic — an anchor either exists in
`knowledge/index.json` or it does not:

1. Every phase has BOTH a policy section (`three-phase-workflow.md`) and a
   companion script-behavior section (`orchestrator-script-implementation.md`),
   registered in the index under the anchor the orchestrator cites.
2. The orchestrator names both anchors for every phase, so a session reading only
   the always-on body can reach either.
3. The relocated detail is not silently re-inlined into the always-on body —
   the ratchet that keeps the footprint from creeping back.

The token figure itself is pinned separately and mechanically by
`knowledge/agent-registry.md`'s `~Tokens` column, verified by
`scripts/measure_tokens.py --verify`.
"""

from __future__ import annotations

import json
import re

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
ORCH = PLUGIN / "agents" / "orchestrator.md"
INDEX = PLUGIN / "knowledge" / "index.json"

PHASES_KEY = "plugins/dev-team/knowledge/three-phase-workflow.md"
SCRIPT_KEY = "plugins/dev-team/knowledge/orchestrator-script-implementation.md"

PHASE_ANCHORS = ("phase-1-research", "phase-2-plan", "phase-3-implement")

# Sections the orchestrator points at that are not per-phase.
OTHER_PHASE_FILE_ANCHORS = (
    "wave-aware-build-dispatch",
    "phase-transitions",
)

# Distinctive strings from the relocated sections. Each one appearing in the
# always-on body again means the detail was re-inlined rather than referenced.
RELOCATED_MARKERS = (
    "RESEARCH_PERSONAS",
    "PLAN_CORE_PERSONAS",
    "SOFTWARE_ENGINEER_PERSONA",
    "_default_phase_research",
    "_default_phase_plan",
    "_dispatch_implement_wave",
    "DEV_TEAM_WORKTREE_BASE_FRESH",
)


def _index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def _anchors(key: str) -> set[str]:
    return {entry.get("anchor") for entry in _index().get(key, {}).values()}


def _orch_text() -> str:
    return ORCH.read_text(encoding="utf-8")


def test_phase_policy_sections_are_registered_in_the_knowledge_index() -> None:
    anchors = _anchors(PHASES_KEY)
    missing = [a for a in PHASE_ANCHORS + OTHER_PHASE_FILE_ANCHORS if a not in anchors]
    assert not missing, (
        f"{PHASES_KEY} is missing index anchors {missing}. Rebuild with "
        "`python3 plugins/dev-team/hooks/lib/build_knowledge_index.py` after "
        "renaming a heading — a citation the index cannot resolve is a dead "
        "on-demand path."
    )


def test_phase_script_behavior_sections_are_registered_in_the_knowledge_index() -> None:
    anchors = _anchors(SCRIPT_KEY)
    missing = [a for a in PHASE_ANCHORS if a not in anchors]
    assert not missing, f"{SCRIPT_KEY} is missing index anchors {missing}"


def test_orchestrator_cites_both_anchors_for_every_phase() -> None:
    text = _orch_text()
    missing = [
        ref
        for anchor in PHASE_ANCHORS
        for ref in (
            f"${{CLAUDE_PLUGIN_ROOT}}/knowledge/three-phase-workflow.md#{anchor}",
            f"${{CLAUDE_PLUGIN_ROOT}}/knowledge/orchestrator-script-implementation.md#{anchor}",
        )
        if ref not in text
    ]
    assert not missing, (
        "agents/orchestrator.md must name the runtime-resolvable anchor for "
        "each phase's policy AND its script-behavior companion, or a session "
        f"reading only the always-on body cannot reach them. Missing: {missing}"
    )


def test_every_knowledge_anchor_the_orchestrator_cites_exists() -> None:
    text = _orch_text()
    ref_re = re.compile(
        r"\$\{CLAUDE_PLUGIN_ROOT\}/(knowledge/[a-z0-9-]+\.md)#([a-z0-9-]+)"
    )
    index = _index()
    dangling = [
        f"{path}#{anchor}"
        for path, anchor in ref_re.findall(text)
        if anchor
        not in {
            e.get("anchor") for e in index.get(f"plugins/dev-team/{path}", {}).values()
        }
    ]
    assert not dangling, (
        "agents/orchestrator.md cites knowledge anchors that do not resolve "
        f"through knowledge/index.json: {dangling}"
    )


def test_relocated_detail_is_not_re_inlined_into_the_always_on_body() -> None:
    text = _orch_text()
    offenders = [marker for marker in RELOCATED_MARKERS if marker in text]
    assert not offenders, (
        "Per-phase detail moved to knowledge/ by #2011 has been re-inlined into "
        "agents/orchestrator.md, which is always-on context. Cite the knowledge "
        f"anchor instead. Found: {offenders}"
    )
