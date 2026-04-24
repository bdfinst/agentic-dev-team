# Agents

Agents define **who does the work**. There are two categories: **team agents** (persona-driven roles that implement, design, and coordinate) and **review agents** (focused reviewers that inspect code quality during implementation).

## Team Agents

Each team agent file in `agents/` specifies a role's persona, behavior, collaboration style, and which skills it uses.

| Agent | File | Purpose |
| --- | --- | --- |
| Orchestrator | [`orchestrator.md`](../agents/orchestrator.md) | Routes tasks, assigns models, coordinates inline review loop |
| Software Engineer | [`software-engineer.md`](../agents/software-engineer.md) | Code generation, implementation, applies review corrections |
| QA/SQA Engineer | [`qa-engineer.md`](../agents/qa-engineer.md) | Test generation, automated testing, quality gates |
| UI/UX Designer | [`ui-ux-designer.md`](../agents/ui-ux-designer.md) | Interface design, UX flows, accessibility compliance |
| Architect | [`architect.md`](../agents/architect.md) | System design, tech decisions, scalability planning |
| Product Manager | [`product-manager.md`](../agents/product-manager.md) | Requirements clarification, prioritization, stakeholder alignment |
| Technical Writer | [`tech-writer.md`](../agents/tech-writer.md) | Documentation, terminology consistency, style enforcement |
| Security Engineer | [`security-engineer.md`](../agents/security-engineer.md) | Security analysis, threat modeling, compliance |
| DevOps/SRE Engineer | [`devops-sre-engineer.md`](../agents/devops-sre-engineer.md) | Pipeline, deployment, reliability, observability |
| ADR Author | [`adr.md`](../agents/adr.md) | Creates and manages Architecture Decision Records |
| Codebase Recon | [`codebase-recon.md`](../agents/codebase-recon.md) | Surveys a codebase's structure, entry points, dependencies, security surface, and git history; produces a RECON artifact in `memory/` that other agents consume |

## Review Agents

Review agents run as sub-agents during Phase 3 inline checkpoints and full `/code-review` runs. The Orchestrator selects and spawns them — they are never invoked directly by the user. Model assignment is controlled by the Orchestrator's routing table. For the full dispatch pipeline, see [Code Review Process](code-review-process.md).

| Agent | File | Model | What It Checks |
| --- | --- | --- | --- |
| `spec-compliance-review` | [`spec-compliance-review.md`](../agents/spec-compliance-review.md) | sonnet | Spec-to-code matching — first gate before quality review |
| `test-review` | [`test-review.md`](../agents/test-review.md) | sonnet | Coverage gaps, assertion quality, test hygiene |
| `security-review` | [`security-review.md`](../agents/security-review.md) | opus | Injection, auth, data exposure |
| `domain-review` | [`domain-review.md`](../agents/domain-review.md) | opus | Abstraction leaks, boundary violations |
| `structure-review` | [`structure-review.md`](../agents/structure-review.md) | sonnet | SRP, DRY, coupling, file organization |
| `complexity-review` | [`complexity-review.md`](../agents/complexity-review.md) | haiku | Function size, cyclomatic complexity, nesting |
| `naming-review` | [`naming-review.md`](../agents/naming-review.md) | haiku | Intent-revealing names, magic values |
| `js-fp-review` | [`js-fp-review.md`](../agents/js-fp-review.md) | sonnet | Array mutations, impure patterns (JS/TS) |
| `concurrency-review` | [`concurrency-review.md`](../agents/concurrency-review.md) | sonnet | Race conditions, async pitfalls |
| `a11y-review` | [`a11y-review.md`](../agents/a11y-review.md) | sonnet | WCAG 2.1 AA, ARIA, keyboard navigation |
| `performance-review` | [`performance-review.md`](../agents/performance-review.md) | haiku | Resource leaks, N+1 queries |
| `token-efficiency-review` | [`token-efficiency-review.md`](../agents/token-efficiency-review.md) | haiku | File size, LLM anti-patterns |
| `claude-setup-review` | [`claude-setup-review.md`](../agents/claude-setup-review.md) | haiku | CLAUDE.md completeness and accuracy |
| `doc-review` | [`doc-review.md`](../agents/doc-review.md) | sonnet | README accuracy, API doc alignment, comment drift |
| `arch-review` | [`arch-review.md`](../agents/arch-review.md) | opus | ADR compliance, layer violations, dependency direction |
| `svelte-review` | [`svelte-review.md`](../agents/svelte-review.md) | sonnet | Svelte reactivity, closure state leaks |
| `progress-guardian` | [`progress-guardian.md`](../agents/progress-guardian.md) | sonnet | Plan adherence, commit discipline, scope creep |
| `refactoring-review` | [`refactor-scan.md`](../agents/refactor-scan.md) | sonnet | Post-GREEN refactoring opportunities |
| `data-flow-tracer` | [`use-case-data-patterns.md`](../agents/use-case-data-patterns.md) | sonnet | Data flow tracing through architecture layers (analysis-only) |

To add a new review agent, use `/agent-add`. See [Add a Review Agent](#add-a-review-agent) below.

## Plan Review Personas

Plan review personas are subagent prompt templates that critically challenge implementation plans during Phase 2, before the human gate. Unlike review agents (which check code), these check the plan itself. See [Plan Review Personas in the architecture doc](agent-architecture.md#plan-review-personas) for the full persona table, model assignments, and revision loop.

## Persona Template

Every agent file follows this structure:

```markdown
# [Role Name] Agent

## Technical Responsibilities
- [Primary capabilities - what this agent delivers]

## Skills
- [Skill Name](../skills/{file}.md) - [when/why this agent uses it]

## Collaboration Protocols
### Primary Collaborators
- [Agent Name]: [What they exchange]

### Communication Style
- [Tone, detail level, update frequency]

## Behavioral Guidelines
### Decision Making
- Autonomy level: [High/Moderate/Low] for [what]
- Escalation criteria: [When to escalate]
- Human approval requirements: [What needs sign-off]

### Conflict Management
- [How disagreements are resolved]

## Psychological Profile
- Work style: [Preferences]
- Problem-solving approach: [Methods]
- Quality vs. speed trade-offs: [Tendencies]

## Success Metrics
- [Measurable KPIs]
```

The `## Skills` section is the bridge between agents and skills. The agent defines *when and why* to invoke a skill; the skill defines *how* to execute it.

## Add a Team Agent

1. Create `agents/{role-name}.md` using the template above
2. Add the agent to the Team Organization diagram in `docs/team-structure.md`
3. Add it to the Team Agents table in `CLAUDE.md`
4. Define collaboration protocols with existing agents
5. Reference any applicable skills in the `## Skills` section

See [Agent & Skill Authoring](../skills/agent-skill-authoring/SKILL.md) for detailed guidelines.

## Add a Review Agent

Use the `/agent-add` slash command — it scaffolds a compliant agent, checks for scope overlap with existing review agents, runs `/agent-audit` automatically, and registers the agent in `CLAUDE.md`.

```text
/agent-add "React hook violations" --tier mid --lang js,ts,jsx,tsx
```

Manual process:
1. Create `agents/{name}-review.md` using the review agent template (see any existing review agent for reference)
2. Run `/agent-audit agents/{name}-review.md --fix` to validate compliance
3. Add eval fixtures to `evals/fixtures/` and expected results to `evals/expected/`
4. Run `/agent-eval --agent {name}-review` to validate accuracy
5. Add a row to the Review Agents table in `CLAUDE.md`

## Add a Project-Specific Custom Agent

Custom agents extend the team with knowledge specific to your project — your domain model, internal frameworks, coding conventions, or tech stack. They live in your project's `agents/` directory alongside the standard team agents and are invisible to other projects.

**When to add a custom agent** (rather than relying on a standard agent):
- The agent needs deep knowledge of your domain that would bloat the standard agent's context
- The role is specific to your team's process (e.g., a `compliance-reviewer` for regulated industries)
- You want a review agent that enforces internal conventions the standard agents don't know about

**Steps**:

1. Create the agent file in your project's `agents/`:

   ```bash
   # In your project (not this repo)
   touch .claude/agents/django-review.md
   ```

2. Write the agent using the [persona template](#persona-template) above. For a review agent, copy an existing one (e.g., `agents/js-fp-review.md`) as a starting point.

3. Register it in your project's `CLAUDE.md` under the appropriate table (Team Agents or Review Agents).

4. If it's a review agent, add eval fixtures so you can validate its accuracy:
   ```
   .claude/evals/fixtures/django-review/     # sample code the agent should flag
   .claude/evals/expected/django-review.json # expected findings
   ```

5. Validate with `/agent-audit` and test with `/agent-eval --agent django-review`.

**Important**: Custom agents in your project's `.claude/` are *additive* — they extend the standard team without replacing it. The Orchestrator will route to them when appropriate based on the task.

## Install or Update the Plugin

The standard install path is `claude plugin install agentic-dev-team@bfinster` — see the [repository README](../../../README.md#installation) for the full procedure, including how to update to a newer version. Copying agent files by hand is not supported: the Orchestrator routes by marketplace registry, not by file scan.

To contribute a custom agent back upstream:

1. Ensure the agent file follows the standard template (run `/agent-audit` against it)
2. Add eval fixtures and expected outputs
3. Submit a PR to this repository with the agent file, fixtures, and a registry entry in `CLAUDE.md`

## Remove an Agent

1. Delete the agent file from `agents/`
2. Remove it from the organization diagram and registry in `CLAUDE.md`
3. Update other agents' collaboration protocols that referenced the removed agent
