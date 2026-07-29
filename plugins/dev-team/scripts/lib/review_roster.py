"""Shared review-agent roster boundary (#1516).

``NON_REVIEW_AGENTS`` names the agents that are **not** dispatchable
code-review lenses. Two consumers share the set, for two related reasons —
keep them together so an agent added for one reason is handled by both:

- ``check_agent_scope.py`` — these are **exempt** from the ``Scope:`` body
  declaration requirement (they are not review lenses, so they need no
  per-file scope).
- ``select_lenses.py`` — these are **excluded** from the dispatchable-lens
  roster (they never run as a ``/build`` or ``/code-review`` lens).

Members are agents with no per-file review scope: the team agents, the
analysis-only agents, and the orchestrator-dispatched coordinators/gates
(``quality-reviewer``, ``spec-reviewer``) that the registry's Review Agents
table lists but which are never dispatched as standalone lenses.

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

NON_REVIEW_AGENTS = {
    "adr-author",
    "architect",
    "codebase-recon",
    "data-flow-tracer",
    "mutation-kill",
    "orchestrator",
    "platform-engineer",
    "product-manager",
    "progress-guardian",
    "qa-engineer",
    "quality-reviewer",  # Stage-2 coordinator, orchestrator-dispatched — not a lens
    "security-engineer",
    "session-analysis",
    "software-engineer",
    "spec-reviewer",  # Stage-1 spec gate, orchestrator-dispatched — not a lens
    "tech-writer",
    "ui-ux-designer",
}
