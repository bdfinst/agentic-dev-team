# Agents

Agents define **who does the work**. There are two categories: **team agents** (persona-driven roles that implement, design, and coordinate) and **review agents** (focused reviewers that inspect code quality during implementation).

## Team Agents

Each team agent file in `agents/` specifies a role's persona, behavior, collaboration style, and which skills it uses.

| Agent | File | Purpose |
| --- | --- | --- |
| ADR Author | [`adr-author.md`](../agents/adr-author.md) | Creates and manages Architecture Decision Records |
| Architect | [`architect.md`](../agents/architect.md) | System design, tech decisions, scalability planning |
| Codebase Recon | [`codebase-recon.md`](../agents/codebase-recon.md) | Surveys a codebase's structure, entry points, dependencies, security surface, and git history; produces a RECON artifact in `.claude/memory/` that other agents consume |
| Orchestrator | [`orchestrator.md`](../agents/orchestrator.md) | Routes tasks, assigns models, coordinates inline review loop |
| Platform Engineer | [`platform-engineer.md`](../agents/platform-engineer.md) | Pipeline, deployment, reliability, observability |
| Product Manager | [`product-manager.md`](../agents/product-manager.md) | Requirements clarification, prioritization, stakeholder alignment |
| QA/SQA Engineer | [`qa-engineer.md`](../agents/qa-engineer.md) | Test generation, automated testing, quality gates |
| Security Engineer | [`security-engineer.md`](../agents/security-engineer.md) | Security analysis, threat modeling, compliance |
| Software Engineer | [`software-engineer.md`](../agents/software-engineer.md) | Code generation, implementation, applies review corrections |
| Technical Writer | [`tech-writer.md`](../agents/tech-writer.md) | Documentation, terminology consistency, style enforcement |
| UI/UX Designer | [`ui-ux-designer.md`](../agents/ui-ux-designer.md) | Interface design, UX flows, accessibility compliance |

## Review Agents

Review agents run as sub-agents during Phase 3 inline checkpoints and full `/code-review` runs. The Orchestrator selects and spawns them — they are never invoked directly by the user. Each agent declares its own `model:`/`effort:` frontmatter — the native Claude Code sub-agent contract, resolved by the harness itself (see Model/Effort Resolution in `agents/orchestrator.md`). For the full dispatch pipeline, see [Code Review Process](code-review-process.md).

| Agent | File | Model | What It Checks |
| --- | --- | --- | --- |
| `a11y-review` | [`a11y-review.md`](../agents/a11y-review.md) | sonnet | WCAG 2.1 AA, ARIA, keyboard navigation |
| `ai-provenance-review` | [`ai-provenance-review.md`](../agents/ai-provenance-review.md) | opus | AI-authored test assertion verification debt, regeneration-risk candidates |
| `angular-reactivity-review` | [`angular-reactivity-review.md`](../agents/angular-reactivity-review.md) | sonnet | Angular Zone.js pitfalls, OnPush violations, RxJS subscription leaks |
| `arch-review` | [`arch-review.md`](../agents/arch-review.md) | opus | ADR compliance, layer violations, dependency direction |
| `claude-setup-review` | [`claude-setup-review.md`](../agents/claude-setup-review.md) | haiku | CLAUDE.md completeness and accuracy |
| `complexity-review` | [`complexity-review.md`](../agents/complexity-review.md) | haiku | Function size, cyclomatic complexity, nesting |
| `component-architecture-review` | [`component-architecture-review.md`](../agents/component-architecture-review.md) | sonnet | Reusable component extraction, UI duplication, prop drilling, component APIs |
| `concurrency-review` | [`concurrency-review.md`](../agents/concurrency-review.md) | sonnet | Race conditions, async pitfalls |
| `correctness-review` | [`correctness-review.md`](../agents/correctness-review.md) | opus | Functional/behavioral defects — implementation diverges from evident intent |
| `data-flow-tracer` | [`data-flow-tracer.md`](../agents/data-flow-tracer.md) | sonnet | Data flow tracing through architecture layers (analysis-only) |
| `doc-review` | [`doc-review.md`](../agents/doc-review.md) | sonnet | README accuracy, API doc alignment, comment drift |
| `domain-review` | [`domain-review.md`](../agents/domain-review.md) | opus | Abstraction leaks, boundary violations |
| `js-fp-review` | [`js-fp-review.md`](../agents/js-fp-review.md) | haiku | Array mutations, impure patterns, global state, point-free/composition opportunities (JS/TS) |
| `mutation-kill` | [`mutation-kill.md`](../agents/mutation-kill.md) | opus | Autonomous survivor-reduction loop — generates targeted tests, verifies, commits, repeats; not a reviewer, invoked per Story by `/test-improve` Phase 5 or directly |
| `naming-review` | [`naming-review.md`](../agents/naming-review.md) | haiku | Intent-revealing names, magic values |
| `performance-review` | [`performance-review.md`](../agents/performance-review.md) | haiku | Resource leaks, N+1 queries |
| `progress-guardian` | [`progress-guardian.md`](../agents/progress-guardian.md) | sonnet | Plan adherence, commit discipline, scope creep |
| `quality-reviewer` | [`quality-reviewer.md`](../agents/quality-reviewer.md) | sonnet | Coordinates the Inline Review Checkpoint's review agents and drives the fix loop — Stage 2 of the three-stage inline review |
| `react-reactivity-review` | [`react-reactivity-review.md`](../agents/react-reactivity-review.md) | sonnet | React hook violations, stale closures, missing deps, subscription leaks |
| `refactor-opportunity-review` | [`refactor-opportunity-review.md`](../agents/refactor-opportunity-review.md) | sonnet | Post-GREEN refactoring opportunities |
| `security-review` | [`security-review.md`](../agents/security-review.md) | opus | Injection, auth, data exposure |
| `session-analysis` | [`session-analysis.md`](../agents/session-analysis.md) | sonnet | Maps an aggregated session digest to probable plugin causes and ranked, tagged improvement suggestions (analysis-only) |
| `spec-compliance-review` | [`spec-compliance-review.md`](../agents/spec-compliance-review.md) | sonnet | Spec-to-code matching — general first gate before quality review (final `/code-review` gate; pre-build and batched/complex-slice checkpoints in `/build`) |
| `spec-reviewer` | [`spec-reviewer.md`](../agents/spec-reviewer.md) | haiku | Spec-to-diff matching for a single freshly-implemented unit — Stage 1 of the three-stage inline review |
| `structure-review` | [`structure-review.md`](../agents/structure-review.md) | sonnet | SRP, DRY, coupling, file organization |
| `test-review` | [`test-review.md`](../agents/test-review.md) | sonnet | Coverage gaps, assertion quality, test hygiene |
| `test-smell-review` | [`test-smell-review.md`](../agents/test-smell-review.md) | sonnet | xUnit test smells, test-double selection, pyramid placement |
| `token-efficiency-review` | [`token-efficiency-review.md`](../agents/token-efficiency-review.md) | haiku | File size, LLM anti-patterns |
| `vue-reactivity-review` | [`vue-reactivity-review.md`](../agents/vue-reactivity-review.md) | sonnet | Vue ref/reactive pitfalls, watchEffect tracking, proxy escapes, subscription leaks |

To add a new review agent, use `/agent-add`. See [Add a Review Agent](#add-a-review-agent) below.

## Plan Review Personas

Plan review personas are registered agents (`agents/plan-review-*.md`) that critically challenge implementation plans during Phase 2, before the human gate. Unlike review agents (which check code), these check the plan itself. See [Plan Review Personas in the architecture doc](agent-architecture.md#plan-review-personas) for the full persona table and revision loop.

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

## Non-standard body declarations

Several `Key: value` lines appear in some agents' **bodies**, not their frontmatter — they are intentional internal tooling metadata, deliberately kept out of frontmatter because none of them are part of the official Claude Code sub-agent contract (`plugins/marketplace-dev/knowledge/agent-contract.json`); frontmatter is reserved for that contract (issue #1333).

- **`Cites: [...]`** — a list of canonical skill/knowledge-file sources an agent's normative rules (MUST/SHOULD/SHALL thresholds) derive from, e.g. `Cites: [owasp-detection, accepted-risks-schema]`. `scripts/citation_lint.py` reads this list and flags a warning when a stated numeric threshold doesn't appear in any cited source — catching silent drift when a canonical file changes but a reviewer agent's inline rule doesn't. See the script's module docstring for the full contract. See `tests/repo/test_citation_lint_corpus.py` for the regression guard over the real corpus.
- **`Scope: always` / `Scope:` (glob list) / `Scope: added-only` (glob list)** — self-declares which files an agent is eligible to review; read by `/code-review`'s dispatch step (`skills/code-review/SKILL.md`). `scripts/check_agent_scope.py` only validates that *some* `Scope:` line is present, not which of the three forms it takes or that the value parses — a misspelled sentinel (e.g. `Scope: added_only`) passes that check silently, then falls through to `select_lenses.py`'s `parse_scope`, which fails open (include-biased, and warned) on an unrecognized value. `added-only` (#1733) narrows the glob-list form to only files that are newly *added* (git change-type `A`), not merely modified — `parse_scope` treats the **first** `Scope:` line as authoritative, so the `added-only` (or plain glob-list) line must stay above any later free-text `Scope:` prose in the same body, or the machine-readable declaration is not the one a reader sees first.
- **`Verify-model:` / `Verify-effort:`** — a review agent's optional opt-in to a cheaper model/effort tier for **fix-verification** re-dispatches only; discovery dispatches are unaffected. Absent means "same tier as discovery" — the deliberate default, since #1619 showed some confirmations genuinely need top-tier judgment. Resolved by `scripts/verify_tier.py`, which validates each value against the same closed enums the official contract declares for `model:`/`effort:` and falls back to the discovery tier on a typo (failing toward the more expensive tier, never the cheaper one). Full contract: [`knowledge/verification-mode.md`](../knowledge/verification-mode.md) (#1628).
- **`Enforcement: script`** — marks an agent whose behavior is deterministically implemented by a script rather than driven by free-form LLM reasoning from the persona prose alone. Agents carrying this declaration also carry a `> **Implemented by:** ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py` blockquote near the top of the file pointing at that implementation (e.g. `orchestrator.md` → `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py`, `codebase-recon.md` → `${CLAUDE_PLUGIN_ROOT}/scripts/codebase_recon.py`).

## Add a Team Agent

1. Create `agents/{role-name}.md` using the template above
2. Add the agent to the Team Organization diagram in `docs/team-structure.md`
3. Add it to the Team Agents table in `CLAUDE.md`
4. Define collaboration protocols with existing agents
5. Reference any applicable skills in the `## Skills` section

See the `marketplace-dev` plugin's `agent-skill-authoring` guidance for detailed authoring conventions.

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

The standard install path is `claude plugin install dev-team@bfinster` — see the [repository README](../../../README.md#installation) for the full procedure, including how to update to a newer version. Copying agent files by hand is not supported: the Orchestrator routes by marketplace registry, not by file scan.

To contribute a custom agent back upstream:

1. Ensure the agent file follows the standard template (run `/agent-audit` against it)
2. Add eval fixtures and expected outputs
3. Submit a PR to this repository with the agent file, fixtures, and a registry entry in `CLAUDE.md`

## Remove an Agent

1. Delete the agent file from `agents/`
2. Remove it from the organization diagram and registry in `CLAUDE.md`
3. Update other agents' collaboration protocols that referenced the removed agent
