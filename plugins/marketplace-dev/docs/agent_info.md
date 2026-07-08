# Agents

The `marketplace-dev` plugin ships one review agent. It is dispatched by `/plugin-audit` and is
not directly user-invocable.

## Review Agents

| Agent | File | Purpose | Invocation |
| --- | --- | --- | --- |
| plugin-best-practices-review | [`plugin-best-practices-review.md`](../agents/plugin-best-practices-review.md) | Structural findings for any plugin — agent type appropriateness (markdown vs script), frontmatter compliance, eval-coverage presence, and body line-count budgets. Read-only; JSON output. Does not evaluate detection-logic quality. | Dispatched by `/plugin-audit` |
