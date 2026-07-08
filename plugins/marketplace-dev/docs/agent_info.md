# Agents

`marketplace-dev` ships one **review agent**. It runs read-only and produces structured JSON findings — it is never invoked directly by the user, only by the `/plugin-audit` orchestrator command.

## Review agent

| Agent | File | Purpose |
| --- | --- | --- |
| `plugin-best-practices-review` | [`agents/plugin-best-practices-review.md`](../agents/plugin-best-practices-review.md) | Structural compliance review for any Claude Code plugin. Checks: agent type appropriateness (markdown vs. script, per rules R1–R10), frontmatter compliance, eval-coverage presence, and body line-count budgets. Produces JSON output. Does **not** evaluate detection-logic quality — that belongs to the plugin's own `agent-eval`. |

## Dispatch model

`plugin-best-practices-review` is dispatched by `/plugin-audit` for every agent and skill file in the target plugin directory. It runs read-only (Glob, Grep, Read tools only) and emits a `findings` array in JSON. Pass `--fix` to `/plugin-audit` to apply auto-correctable findings after the review pass.

## Knowledge shared with the agent

The agent reads [`knowledge/agent-type-decision-rules.md`](../knowledge/agent-type-decision-rules.md) — the markdown-vs-script decision matrix (rules R1–R10). This is the **single source of truth** shared by `/agent-type-advisor` (forward-looking) and `plugin-best-practices-review` (retrospective). Rule IDs are cited in findings; the full rationale lives in the knowledge file.
