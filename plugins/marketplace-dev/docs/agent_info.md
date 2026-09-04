# Agents

The `marketplace-dev` plugin ships one review agent. It is dispatched by the
`plugin-audit` skill (itself agent-loaded, not a slash command) and is not
directly user-invocable.

## Review Agents

| Agent | File | Purpose | Invocation |
| --- | --- | --- | --- |
| plugin-best-practices-review | [`plugin-best-practices-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/marketplace-dev/agents/plugin-best-practices-review.md) | Structural findings for any plugin — agent type appropriateness (markdown vs script), frontmatter compliance, eval-coverage presence, and body line-count budgets. Read-only; JSON output. Does not evaluate detection-logic quality. | Dispatched by the `plugin-audit` skill |

The markdown-vs-script judgment this agent applies is the decision matrix in
[`agent-type-decision-rules.md`](../knowledge/agent-type-decision-rules.md)
(rules R1–R10). See also the [Skills catalog](skills.md) and [Workflows](workflows.md).
