"""Shared review-agent roster boundary (#1516).

``NON_REVIEW_AGENTS`` names the agents that are **not** dispatchable
code-review lenses — they have no per-file review scope at all: the team
agents, the analysis-only agents, and the orchestrator-dispatched
coordinators/gates (``quality-reviewer``, ``spec-reviewer``) that the
registry's Review Agents table lists but which are never dispatched as
standalone lenses. Two consumers share the set, for two related reasons —
keep them together so an agent added for one reason is handled by both:

- ``check_agent_scope.py`` — these are **exempt** from the ``Scope:`` body
  declaration requirement (they are not review lenses, so they need no
  per-file scope).
- ``select_lenses.py`` — these are **excluded** from the dispatchable-lens
  roster (they never run as a ``/build`` or ``/code-review`` lens).

Genuine review agents whose findings are properties of the whole repository
rather than any one diff (``claude-setup-review``, ``token-efficiency-review``,
``ai-provenance-review``) are **not** members here — they declare their own
exclusion directly in their body via ``Scope: on-demand``
(``select_lenses.SCOPE_ON_DEMAND``), which the resolver reads and never
selects for the per-diff roster. That is the single-source-of-truth
mechanism ``select_lenses.py``'s own docstring already promises for every
other ``Scope:`` kind — putting these three agents in this set instead would
be a second, competing mechanism for the same fact, and would also (wrongly)
exempt them from the ``Scope:`` declaration requirement they actually
satisfy. See each agent's own comment for why it is whole-tree, not
per-diff, and ``/repo-review``'s fixed roster (#1735) for where it runs
instead.

``SCOPE_LINE_RE`` is the shared ``Scope:`` body-declaration pattern —
``select_lenses.py`` and ``check_agent_scope.py`` both parsed the
byte-identical regex independently before this; kept here so a future
change to the declaration grammar has one definition to update.

Stdlib-only.
"""

from __future__ import annotations

import re

#: A body-level ``Scope: <value>`` line. Not frontmatter — see
#: ``plugins/marketplace-dev/knowledge/agent-contract.json`` (issue #1333).
#: Exposed as a raw pattern string too, so a consumer needing different
#: compile-time flags (e.g. ``re.MULTILINE`` for a whole-body ``.search()``
#: instead of a per-line ``.match()``) shares the same grammar without a
#: second, independently-typed copy of it.
SCOPE_LINE_PATTERN = r"^\s*Scope\s*:\s*(.*)$"
SCOPE_LINE_RE = re.compile(SCOPE_LINE_PATTERN)

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
    # `claude-setup-review`, `token-efficiency-review`, and `ai-provenance-review`
    # are deliberately NOT here — they are genuine review agents that declare
    # `Scope: on-demand` directly in their own body, which select_lenses.py's
    # resolver reads and excludes on its own. See this module's docstring.
    # Plan/Gherkin critics dispatched by /plan and /gherkin-derive — not code-review
    # lenses, so no per-file Scope (closes #1525: check_agent_scope was red for these).
    "gherkin-quality-critic",
    "plan-review-acceptance",
    "plan-review-design",
    "plan-review-parallelization",
    "plan-review-strategic",
    "plan-review-ux",
})
