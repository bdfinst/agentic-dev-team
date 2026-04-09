# Agents

Agents define **who does the work**. There are two categories: **team agents** (persona-driven roles that implement, design, and coordinate) and **review agents** (focused reviewers that inspect code quality during implementation).

## Team Agents

Each team agent file in `agents/` specifies a role's persona, behavior, collaboration style, and which skills it uses.

| Agent | File | Purpose |
| --- | --- | --- |
| Orchestrator | [`orchestrator.md`](../plugins/agentic-dev-team/agents/orchestrator.md) | Routes tasks, assigns models, coordinates inline review loop |
| Software Engineer | [`software-engineer.md`](../plugins/agentic-dev-team/agents/software-engineer.md) | Code generation, implementation, applies review corrections |
| Data Scientist | [`data-scientist.md`](../plugins/agentic-dev-team/agents/data-scientist.md) | ML models, data analysis, statistical validation |
| QA/SQA Engineer | [`qa-engineer.md`](../plugins/agentic-dev-team/agents/qa-engineer.md) | Test generation, automated testing, quality gates |
| UI/UX Designer | [`ui-ux-designer.md`](../plugins/agentic-dev-team/agents/ui-ux-designer.md) | Interface design, UX flows, accessibility compliance |
| Architect | [`architect.md`](../plugins/agentic-dev-team/agents/architect.md) | System design, tech decisions, scalability planning |
| Product Manager | [`product-manager.md`](../plugins/agentic-dev-team/agents/product-manager.md) | Requirements clarification, prioritization, stakeholder alignment |
| Technical Writer | [`tech-writer.md`](../plugins/agentic-dev-team/agents/tech-writer.md) | Documentation, terminology consistency, style enforcement |
| Security Engineer | [`security-engineer.md`](../plugins/agentic-dev-team/agents/security-engineer.md) | Security analysis, threat modeling, compliance |
| DevOps/SRE Engineer | [`devops-sre-engineer.md`](../plugins/agentic-dev-team/agents/devops-sre-engineer.md) | Pipeline, deployment, reliability, observability |
| ADR Author | [`adr.md`](../plugins/agentic-dev-team/agents/adr.md) | Creates and manages Architecture Decision Records |

## Review Agents

Review agents run as sub-agents during Phase 3 inline checkpoints and full `/code-review` runs. The Orchestrator selects and spawns them — they are never invoked directly by the user. Model assignment is controlled by the Orchestrator's routing table.

| Agent | File | Model | What It Checks |
| --- | --- | --- | --- |
| `spec-compliance-review` | [`spec-compliance-review.md`](../plugins/agentic-dev-team/agents/spec-compliance-review.md) | sonnet | Spec-to-code matching — first gate before quality review |
| `test-review` | [`test-review.md`](../plugins/agentic-dev-team/agents/test-review.md) | sonnet | Coverage gaps, assertion quality, test hygiene |
| `security-review` | [`security-review.md`](../plugins/agentic-dev-team/agents/security-review.md) | opus | Injection, auth, data exposure |
| `domain-review` | [`domain-review.md`](../plugins/agentic-dev-team/agents/domain-review.md) | opus | Abstraction leaks, boundary violations |
| `structure-review` | [`structure-review.md`](../plugins/agentic-dev-team/agents/structure-review.md) | sonnet | SRP, DRY, coupling, file organization |
| `complexity-review` | [`complexity-review.md`](../plugins/agentic-dev-team/agents/complexity-review.md) | haiku | Function size, cyclomatic complexity, nesting |
| `naming-review` | [`naming-review.md`](../plugins/agentic-dev-team/agents/naming-review.md) | haiku | Intent-revealing names, magic values |
| `js-fp-review` | [`js-fp-review.md`](../plugins/agentic-dev-team/agents/js-fp-review.md) | sonnet | Array mutations, impure patterns (JS/TS) |
| `concurrency-review` | [`concurrency-review.md`](../plugins/agentic-dev-team/agents/concurrency-review.md) | sonnet | Race conditions, async pitfalls |
| `a11y-review` | [`a11y-review.md`](../plugins/agentic-dev-team/agents/a11y-review.md) | sonnet | WCAG 2.1 AA, ARIA, keyboard navigation |
| `performance-review` | [`performance-review.md`](../plugins/agentic-dev-team/agents/performance-review.md) | haiku | Resource leaks, N+1 queries |
| `token-efficiency-review` | [`token-efficiency-review.md`](../plugins/agentic-dev-team/agents/token-efficiency-review.md) | haiku | File size, LLM anti-patterns |
| `claude-setup-review` | [`claude-setup-review.md`](../plugins/agentic-dev-team/agents/claude-setup-review.md) | haiku | CLAUDE.md completeness and accuracy |
| `doc-review` | [`doc-review.md`](../plugins/agentic-dev-team/agents/doc-review.md) | sonnet | README accuracy, API doc alignment, comment drift |
| `arch-review` | [`arch-review.md`](../plugins/agentic-dev-team/agents/arch-review.md) | opus | ADR compliance, layer violations, dependency direction |
| `svelte-review` | [`svelte-review.md`](../plugins/agentic-dev-team/agents/svelte-review.md) | sonnet | Svelte reactivity, closure state leaks |
| `progress-guardian` | [`progress-guardian.md`](../plugins/agentic-dev-team/agents/progress-guardian.md) | sonnet | Plan adherence, commit discipline, scope creep |
| `refactoring-review` | [`refactor-scan.md`](../plugins/agentic-dev-team/agents/refactor-scan.md) | sonnet | Post-GREEN refactoring opportunities |
| `data-flow-tracer` | [`use-case-data-patterns.md`](../plugins/agentic-dev-team/agents/use-case-data-patterns.md) | sonnet | Data flow tracing through architecture layers (analysis-only) |

To add a new review agent, use `/agent-add`. See [Add a Review Agent](#add-a-review-agent) below.

## Persona Template

Every agent file follows this structure:

```markdown
# [Role Name] Agent

## Technical Responsibilities
- [Primary capabilities - what this agent delivers]

## Skills
- [Skill Name](../plugins/agentic-dev-team/skills/{file}.md) - [when/why this agent uses it]

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

See [Agent & Skill Authoring](../plugins/agentic-dev-team/skills/agent-skill-authoring/SKILL.md) for detailed guidelines.

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

## Incorporate Agents from Another Repository

You can pull individual agents or the full team from any repository that follows this structure.

### Pull a single agent from another repo

```bash
# Copy a specific agent into your project
cp path/to/other-repo/.claude/agents/react-review.md .claude/agents/

# Register it in your CLAUDE.md under Review Agents
# Then validate:
claude -p "/agent-audit .claude/agents/react-review.md --fix"
```

Any agent file that follows the standard template will work. If the source repo has eval fixtures for the agent, copy those too:

```bash
cp -r path/to/other-repo/.claude/evals/fixtures/react-review .claude/evals/fixtures/
cp path/to/other-repo/.claude/evals/expected/react-review.json .claude/evals/expected/
```

### Pull the full team into your project

This is the standard installation path. Copy the entire `.claude/` directory:

```bash
git clone https://github.com/your-org/agentic-dev-team /tmp/adt
cp -r /tmp/adt/.claude/ /path/to/your-project/.claude/
```

If your project already has a `.claude/` directory, merge selectively:

```bash
# Merge only agents and skills, preserve your existing CLAUDE.md and settings
cp -r /tmp/adt/.claude/agents/ /path/to/your-project/.claude/agents/
cp -r /tmp/adt/.claude/skills/ /path/to/your-project/.claude/skills/
cp -r /tmp/adt/.claude/commands/ /path/to/your-project/.claude/commands/
# Then manually merge the registry tables from /tmp/adt/.claude/CLAUDE.md into yours
```

### Install a subset of agents

If you only need specific agents (e.g., only review agents, no team personas):

```bash
# Copy only review agents
cp /tmp/adt/.claude/agents/*-review.md .claude/agents/

# Copy only team agents you want
cp /tmp/adt/.claude/agents/software-engineer.md .claude/agents/
cp /tmp/adt/.claude/agents/architect.md .claude/agents/

# Copy all skills (agents reference them)
cp -r /tmp/adt/.claude/skills/ .claude/skills/
```

After selective installation, update your `CLAUDE.md` to register only the agents you copied. Agents not registered in `CLAUDE.md` will not be routed to by the Orchestrator.

### Merge agents from multiple sources

If you maintain custom agents and also use agents from this repo:

1. Keep this repo's agents under `agents/` (the standard set)
2. Add your custom agents to the same directory — they coexist with no conflict as long as filenames don't collide
3. Register all agents (standard + custom) in your `CLAUDE.md`
4. The Orchestrator discovers agents from the registry tables, not by file scan, so registration is what activates an agent

### Keep agents up to date with upstream

```bash
# Check what changed in the upstream repo
cd /tmp/adt && git pull && cd -

# Selectively apply updates
cp /tmp/adt/.claude/agents/security-review.md .claude/agents/
cp /tmp/adt/.claude/agents/arch-review.md .claude/agents/
```

Review the diff before copying — if you have local modifications to a standard agent file, merge them manually rather than overwriting.

### Contribute a custom agent back

If you've built a custom agent that would be useful to others:

1. Ensure the agent file follows the standard template (run `/agent-audit` against it)
2. Add eval fixtures and expected outputs
3. Submit a PR to this repository with the agent file, fixtures, and a registry entry in `CLAUDE.md`

## Remove an Agent

1. Delete the agent file from `agents/`
2. Remove it from the organization diagram and registry in `CLAUDE.md`
3. Update other agents' collaboration protocols that referenced the removed agent
