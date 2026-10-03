# Agents

Agents define **who does the work**. There are two categories. **Team agents** are persona-driven roles that implement, design, and coordinate. **Review agents** are focused reviewers that inspect code quality during implementation.

## Team agents

Each team agent file in `agents/` specifies a role's persona, behavior, collaboration style, and skills.

| Agent | File | Purpose |
| --- | --- | --- |
| ADR Author | [`adr-author.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/adr-author.md) | Creates and manages Architecture Decision Records |
| Architect | [`architect.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/architect.md) | System design, tech decisions, scalability planning |
| Codebase Recon | [`codebase-recon.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/codebase-recon.md) | Surveys a codebase's structure, entry points, dependencies, security surface, and git history; produces a RECON artifact in `.claude/memory/` that other agents consume |
| Orchestrator | [`orchestrator.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/orchestrator.md) | Routes tasks, assigns models, coordinates inline review loop |
| Platform Engineer | [`platform-engineer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/platform-engineer.md) | Pipeline, deployment, reliability, observability |
| Product Manager | [`product-manager.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/product-manager.md) | Requirements clarification, prioritization, stakeholder alignment |
| QA/SQA Engineer | [`qa-engineer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/qa-engineer.md) | Test generation, automated testing, quality gates |
| Security Engineer | [`security-engineer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/security-engineer.md) | Security analysis, threat modeling, compliance |
| Software Engineer | [`software-engineer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/software-engineer.md) | Code generation, implementation, applies review corrections |
| Technical Writer | [`tech-writer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/tech-writer.md) | Documentation, terminology consistency, style enforcement |
| UI/UX Designer | [`ui-ux-designer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/ui-ux-designer.md) | Interface design, UX flows, accessibility compliance |

## Review agents

Review agents run as sub-agents during Phase 3 inline checkpoints and full `/code-review` runs. The Orchestrator selects and spawns them. You never invoke them directly. Each agent declares its own `model:`/`effort:` frontmatter, which is the native Claude Code sub-agent contract. The harness resolves it (see Model/Effort Resolution in `agents/orchestrator.md`). For the full dispatch pipeline, see [Code review process](code-review-process.md).

| Agent | File | Model | What It Checks |
| --- | --- | --- | --- |
| `a11y-review` | [`a11y-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/a11y-review.md) | sonnet | WCAG 2.1 AA, ARIA, keyboard navigation |
| `ai-provenance-review` | [`ai-provenance-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/ai-provenance-review.md) | opus | AI-authored test assertion verification debt, regeneration-risk candidates |
| `angular-reactivity-review` | [`angular-reactivity-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/angular-reactivity-review.md) | sonnet | Angular Zone.js pitfalls, OnPush violations, RxJS subscription leaks |
| `arch-review` | [`arch-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/arch-review.md) | opus | ADR compliance, layer violations, dependency direction |
| `claude-setup-review` | [`claude-setup-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/claude-setup-review.md) | haiku | CLAUDE.md completeness and accuracy |
| `component-architecture-review` | [`component-architecture-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/component-architecture-review.md) | sonnet | Reusable component extraction, UI duplication, prop drilling, component APIs |
| `concurrency-review` | [`concurrency-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/concurrency-review.md) | sonnet | Race conditions, async pitfalls |
| `correctness-review` | [`correctness-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/correctness-review.md) | opus | Functional/behavioral defects — implementation diverges from evident intent |
| `data-flow-tracer` | [`data-flow-tracer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/data-flow-tracer.md) | sonnet | Data flow tracing through architecture layers (analysis-only) |
| `doc-review` | [`doc-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/doc-review.md) | sonnet | README accuracy, API doc alignment, comment drift |
| `domain-review` | [`domain-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/domain-review.md) | opus | Abstraction leaks, boundary violations |
| `js-fp-review` | [`js-fp-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/js-fp-review.md) | haiku | Array mutations, impure patterns, global state, point-free/composition opportunities (JS/TS) |
| `mutation-kill` | [`mutation-kill.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/mutation-kill.md) | opus | Autonomous survivor-reduction loop — generates targeted tests, verifies, commits, repeats; not a reviewer, invoked per Story by `/test-improve` Phase 5 or directly |
| `naming-review` | [`naming-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/naming-review.md) | haiku | Intent-revealing names, magic values |
| `performance-review` | [`performance-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/performance-review.md) | haiku | Resource leaks, N+1 queries |
| `progress-guardian` | [`progress-guardian.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/progress-guardian.md) | sonnet | Plan adherence, commit discipline, scope creep |
| `quality-reviewer` | [`quality-reviewer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/quality-reviewer.md) | sonnet | Coordinates the Inline Review Checkpoint's review agents and drives the fix loop — Stage 2 of the three-stage inline review |
| `react-reactivity-review` | [`react-reactivity-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/react-reactivity-review.md) | sonnet | React hook violations, stale closures, missing deps, subscription leaks |
| `refactor-opportunity-review` | [`refactor-opportunity-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/refactor-opportunity-review.md) | sonnet | Post-GREEN refactoring opportunities |
| `security-review` | [`security-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/security-review.md) | opus | Injection, auth, data exposure |
| `session-analysis` | [`session-analysis.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/session-analysis.md) | sonnet | Maps an aggregated session digest to probable plugin causes and ranked, tagged improvement suggestions (analysis-only) |
| `spec-compliance-review` | [`spec-compliance-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/spec-compliance-review.md) | sonnet | Spec-to-code matching — general first gate before quality review (final `/code-review` gate; pre-build and batched/complex-slice checkpoints in `/build`) |
| `spec-reviewer` | [`spec-reviewer.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/spec-reviewer.md) | haiku | Spec-to-diff matching for a single freshly-implemented unit — Stage 1 of the three-stage inline review |
| `structure-review` | [`structure-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/structure-review.md) | sonnet | SRP, DRY, coupling, file organization, nesting depth, cognitive load, async-pattern judgment |
| `test-review` | [`test-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/test-review.md) | sonnet | Coverage gaps, assertion quality, test hygiene |
| `test-smell-review` | [`test-smell-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/test-smell-review.md) | sonnet | xUnit test smells, test-double selection, pyramid placement |
| `token-efficiency-review` | [`token-efficiency-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/token-efficiency-review.md) | haiku | File size, LLM anti-patterns |
| `vue-reactivity-review` | [`vue-reactivity-review.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/agents/vue-reactivity-review.md) | sonnet | Vue ref/reactive pitfalls, watchEffect tracking, proxy escapes, subscription leaks |

To add a new review agent, use `/agent-add`. See [Add a review agent](#add-a-review-agent) below.

## Plan review personas

Plan review personas are registered agents (`agents/plan-review-*.md`) that critically challenge implementation plans during Phase 2, before the human gate. Review agents check code. These personas check the plan itself. See [Plan review personas in the architecture doc](agent-architecture.md#plan-review-personas) for the full persona table and revision loop.

## Persona template

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

The `## Skills` section is the bridge between agents and skills. The agent defines *when and why* to invoke a skill. The skill defines *how* to execute it.

## Non-standard body declarations

Several `Key: value` lines appear in some agents' **bodies**, not their frontmatter. They are intentional internal tooling metadata. They stay out of frontmatter because none of them are part of the official Claude Code sub-agent contract (`plugins/marketplace-dev/knowledge/agent-contract.json`). Frontmatter is reserved for that contract (issue #1333).

- **`Cites: [...]`** — a list of canonical skill and knowledge-file sources. An agent's normative rules (MUST/SHOULD/SHALL thresholds) derive from these sources, for example `Cites: [owasp-detection, accepted-risks-schema]`.
  - `scripts/citation_lint.py` reads this list. It warns when a stated numeric threshold does not appear in any cited source.
  - This catches silent drift when a canonical file changes but a reviewer agent's inline rule does not.
  - See the script's module docstring for the full contract.
  - See `tests/repo/test_citation_lint_corpus.py` for the regression guard over the real corpus.
- **`Scope: always` / `Scope:` (glob list) / `Scope: added-only` (glob list) / `Scope: on-demand`** — declares which files an agent is eligible to review. The `/code-review` dispatch step reads it (`skills/code-review/SKILL.md`).
  - `scripts/check_agent_scope.py` only validates that *some* `Scope:` line is present. It does not check which of the four forms the line takes, or that the value parses.
  - A misspelled sentinel (for example `Scope: added_only`) passes that check silently. It then falls through to `parse_scope` in `select_lenses.py`, which fails open (include-biased, and warned) on an unrecognized value.
  - `added-only` (#1733) narrows the glob-list form to files that are newly *added* (git change-type `A`), not merely modified.
  - `on-demand` (#1733's closing-pass follow-up) is a bare declaration with no bullet block. It means the agent is a genuine review agent whose findings are whole-repository properties. The per-diff resolver never dispatches it (`claude-setup-review`, `token-efficiency-review`, `ai-provenance-review`). See the docstring of `scripts/lib/review_roster.py` for why this replaced listing them in `NON_REVIEW_AGENTS`.
  - `parse_scope` treats the **first** `Scope:` line as authoritative. Keep the machine-readable form (`added-only`/`on-demand`/plain glob-list) above any later free-text `Scope:` prose in the same body. Otherwise the declaration a reader sees first is not the one the resolver reads.
- **`Verify-model:` / `Verify-effort:`** — a review agent's optional opt-in to a cheaper model/effort tier for **fix-verification** re-dispatches only. Discovery dispatches are unaffected.
  - Absent means "same tier as discovery". This is the deliberate default, because #1619 showed some confirmations genuinely need top-tier judgment.
  - `scripts/verify_tier.py` resolves these values. It validates each value against the same closed enums the official contract declares for `model:`/`effort:`.
  - On a typo, it falls back to the discovery tier. It fails toward the more expensive tier, never the cheaper one.
  - Full contract: [`knowledge/verification-mode.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/knowledge/verification-mode.md) (#1628).
- **`Enforcement: script`** — marks an agent whose behavior a script implements deterministically, rather than free-form LLM reasoning from the persona prose alone. Agents with this declaration also carry a `> **Implemented by:** ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py` blockquote near the top of the file. The blockquote points at that implementation (for example `orchestrator.md` → `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py`, `codebase-recon.md` → `${CLAUDE_PLUGIN_ROOT}/scripts/codebase_recon.py`).

## Add a team agent

1. Create `agents/{role-name}.md` using the template above.
2. Add the agent to the Team Organization diagram in `docs/team-structure.md`.
3. Add the agent to the Team Agents table in `CLAUDE.md`.
4. Define collaboration protocols with existing agents.
5. Reference any applicable skills in the `## Skills` section.

See the `marketplace-dev` plugin's `agent-skill-authoring` guidance for detailed authoring conventions.

## Add a review agent

Use the `/agent-add` slash command. It scaffolds a compliant agent and checks for scope overlap with existing review agents. It also runs `/agent-audit` automatically and registers the agent in `CLAUDE.md`.

```text
/agent-add "React hook violations" --tier mid --lang js,ts,jsx,tsx
```

Manual process:

1. Create `agents/{name}-review.md` using the review agent template (see any existing review agent for reference).
2. Run `/agent-audit agents/{name}-review.md --fix` to validate compliance.
3. Add eval fixtures to `evals/fixtures/` and expected results to `evals/expected/`.
4. Run `/agent-eval --agent {name}-review` to validate accuracy.
5. Add a row to the Review Agents table in `CLAUDE.md`.

## Add a project-specific custom agent

Custom agents extend the team with knowledge specific to your project. Examples include your domain model, internal frameworks, coding conventions, or tech stack. They live in your project's `agents/` directory alongside the standard team agents. Other projects cannot see them.

**When to add a custom agent** (rather than relying on a standard agent):

- The agent needs deep knowledge of your domain that would bloat the standard agent's context.
- The role is specific to your team's process (for example, a `compliance-reviewer` for regulated industries).
- You want a review agent that enforces internal conventions the standard agents do not know about.

**Steps**:

1. Create the agent file in your project's `agents/`:

   ```bash
   # In your project (not this repo)
   touch .claude/agents/django-review.md
   ```

2. Write the agent using the [persona template](#persona-template) above. For a review agent, copy an existing one (for example, `agents/js-fp-review.md`) as a starting point.

3. Register the agent in your project's `CLAUDE.md` under the appropriate table (Team Agents or Review Agents).

4. If the agent is a review agent, add eval fixtures so you can validate its accuracy:

   ```
   .claude/evals/fixtures/django-review/     # sample code the agent should flag
   .claude/evals/expected/django-review.json # expected findings
   ```

5. Validate with `/agent-audit` and test with `/agent-eval --agent django-review`.

**Important**: Custom agents in your project's `.claude/` are *additive*. They extend the standard team without replacing it. The Orchestrator routes to them when appropriate based on the task.

## Install or update the plugin

The standard install path is `claude plugin install dev-team@bfinster`. See the [repository README](../../../README.md#getting-started) for the full procedure, including how to update to a newer version. Copying agent files by hand is not supported. The Orchestrator routes by marketplace registry, not by file scan.

To contribute a custom agent back upstream:

1. Ensure the agent file follows the standard template (run `/agent-audit` against it).
2. Add eval fixtures and expected outputs.
3. Submit a PR to this repository with the agent file, fixtures, and a registry entry in `CLAUDE.md`.

## Remove an agent

1. Delete the agent file from `agents/`.
2. Remove the agent from the organization diagram and registry in `CLAUDE.md`.
3. Update the collaboration protocols of other agents that referenced the removed agent.
