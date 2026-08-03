"""Shared review-agent roster boundary (#1516).

``NON_REVIEW_AGENTS`` names the agents that are **not** dispatchable
code-review lenses. Two consumers share the set, for two related reasons —
keep them together so an agent added for one reason is handled by both:

- ``check_agent_scope.py`` — these are **exempt** from the ``Scope:`` body
  declaration requirement (they are not review lenses, so they need no
  per-file scope).
- ``select_lenses.py`` — these are **excluded** from the dispatchable-lens
  roster (they never run as a ``/build`` or ``/code-review`` lens).

Members fall into two groups, both excluded from this module's remit for
different reasons: (1) agents with no per-file review scope at all — the team
agents, the analysis-only agents, and the orchestrator-dispatched
coordinators/gates (``quality-reviewer``, ``spec-reviewer``) that the
registry's Review Agents table lists but which are never dispatched as
standalone lenses; and (2) genuine review agents (``claude-setup-review``,
``token-efficiency-review``, ``ai-provenance-review``) whose findings are
properties of the whole repository rather than any one diff, so they are
excluded from the per-diff resolver and dispatched instead by the whole-tree
``/repo-review`` skill (#1735) — see each one's own comment below.

Stdlib-only.
"""

from __future__ import annotations

NON_REVIEW_AGENTS = frozenset({
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
    # Reviews the *harness* (CLAUDE.md, rules, skills, agent frontmatter), not the
    # changeset — so it has nothing to say about a diff and was firing on every
    # code review as dead weight. `Scope: always` put it in an 18-lens panel for a
    # two-file JS change in a project with no Claude config at all. Now dispatched
    # by both the user-invocable `/claude-setup-review` skill (on-demand) and the
    # whole-tree `/repo-review` skill (#1735) — never automatically by /code-review.
    "claude-setup-review",
    # Repo-wide drift/trend metrics, not per-diff correctness gates (#1733): a
    # diff-scoped review of a small PR can't even see the pattern either agent
    # exists to catch (a file that crept past a size threshold over many small
    # PRs; accumulating verification debt across the whole codebase). Both now
    # run only in the whole-tree, on-demand `/repo-review` skill (#1735), same
    # reasoning and same treatment as `claude-setup-review` above.
    "token-efficiency-review",
    "ai-provenance-review",
    # Plan/Gherkin critics dispatched by /plan and /gherkin-derive — not code-review
    # lenses, so no per-file Scope (closes #1525: check_agent_scope was red for these).
    "gherkin-quality-critic",
    "plan-review-acceptance",
    "plan-review-design",
    "plan-review-parallelization",
    "plan-review-strategic",
    "plan-review-ux",
})
