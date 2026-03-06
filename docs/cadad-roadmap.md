# C-DAD Alignment Roadmap

This project was compared against the **Contract-Driven AI Development (C-DAD)** white paper (Enrico Piovesan, October 2025), which argues that AI-native software requires formal, versioned, machine-readable contracts as the shared foundation between humans, AI agents, and runtimes.

The comparison found strong philosophical alignment but several structural gaps. This document tracks the gaps as an actionable backlog, ordered by implementation value.

## Background

C-DAD's core argument: for AI to function as a dependable collaborator, software must be *self-describing* — portable across tools, verifiable throughout its lifecycle, and resilient over time. Contracts are the mechanism: structured artifacts that encode capabilities, rationale, policy, and lifecycle state in a language understandable by both humans and AI.

**What this project already does well** relative to C-DAD:
- Agent and skill files function as behavioral contracts — structured specs consumed by AI agents
- CLAUDE.md is the shared collaboration surface for humans and AI
- ATDD (Gherkin feature files) implements contract-first delivery at the behavior level
- Three human review gates mirror C-DAD's human-in-the-loop governance model
- `config-changelog.jsonl` provides an audit trail
- Review agents validate code against defined standards (AI as contract enforcer)
- Feedback-learning skill implements C-DAD's governance feedback loop
- `memory/` files + doc-sync policy implement C-DAD's living documentation model

**What is missing** is the formal, machine-readable scaffolding that makes contracts enforceable at scale.

---

## Todo List

### Priority 1 — Contract Registry

**C-DAD gap**: No central registry. Agent and skill files are discovered by file-path convention, not registered with machine-readable metadata. There is no way for tooling, CI, or other repositories to discover available agents programmatically.

**Tasks**:

- [ ] Create `registry/` directory at repo root
- [ ] Define a JSON schema for agent/skill manifests (`registry/schema.json`) with required fields:
  - `id` — kebab-case unique identifier (e.g., `agents/security-review`)
  - `version` — semantic version (e.g., `1.2.0`)
  - `lifecycle` — one of `draft | active | deprecated | retired`
  - `type` — one of `team-agent | review-agent | skill | command`
  - `model` — assigned model tier (`haiku | sonnet | opus`)
  - `artifacts` — paths to agent/skill file, evals, expected outputs
  - `description` — one-line summary of what it does
  - `owners` — team or individual responsible for maintaining it
- [ ] Generate initial manifests for all existing agents and skills
- [ ] Update `/agent-add` and `/agent-remove` commands to maintain the registry automatically
- [ ] Update `/eval-audit` to validate that all agents in `.claude/agents/` have corresponding registry entries
- [ ] Add a registry validation step to the `eval-compliance-check.sh` hook

**Example manifest** (`registry/agents/security-review.json`):
```json
{
  "id": "agents/security-review",
  "version": "1.0.0",
  "lifecycle": "active",
  "type": "review-agent",
  "model": "opus",
  "artifacts": {
    "agent": ".claude/agents/security-review.md",
    "evals": ".claude/evals/fixtures/security-review/",
    "expected": ".claude/evals/expected/security-review.json"
  },
  "description": "Detects injection vulnerabilities, auth/authz flaws, data exposure, and crypto misuse",
  "owners": ["security-team"]
}
```

---

### Priority 2 — Lifecycle State Management

**C-DAD gap**: Agent files have no lifecycle metadata. There is no way to distinguish experimental agents from stable ones, or to deprecate an agent without deleting it. `/agent-remove` deletes rather than deprecates, permanently destroying history.

**Tasks**:

- [ ] Add `status:` field to agent and skill frontmatter: `draft | active | deprecated | retired`
- [ ] Set all existing agents to `status: active`
- [ ] Update the agent template in `docs/agent_info.md` and `skills/agent-skill-authoring.md` to require `status:` in frontmatter
- [ ] Update `/agent-add` to default new agents to `status: draft` with a note to promote to `active` after eval validation passes
- [ ] Update `/agent-remove` to offer deprecation as an alternative to deletion:
  - Deprecation sets `status: deprecated` in frontmatter and registry, adds a `deprecated-by:` link if a replacement exists, and removes the agent from active routing without deleting the file
  - Deletion remains available but requires explicit confirmation
- [ ] Update the Orchestrator's routing logic to skip agents with `status: deprecated` or `status: retired`
- [ ] Update `/eval-audit` to flag `draft` agents that have no eval fixtures

---

### Priority 3 — Semantic Versioning on Agent and Skill Files

**C-DAD gap**: Agent and skill files change via git commits but have no version numbers. Breaking changes (e.g., changing an agent's output format or eval contract) are invisible to consumers until something breaks.

**Tasks**:

- [ ] Add `version:` field to all agent and skill frontmatter (start everything at `1.0.0`)
- [ ] Define versioning rules in `skills/agent-skill-authoring.md`:
  - **Patch** (`x.x.1`): clarifications, typo fixes, no behavioral change
  - **Minor** (`x.1.0`): new capability added, backwards-compatible
  - **Major** (`2.0.0`): output format changes, required section changes, breaking behavioral change
- [ ] Update `/agent-add` scaffolding to start new agents at `0.1.0` (draft) or `1.0.0` (active)
- [ ] Add a version bump step to the `/apply-fixes` workflow when corrections change agent behavior
- [ ] Update the registry manifest to mirror the version from frontmatter (single source of truth: frontmatter; registry reflects it)

---

### Priority 4 — Embedded Provenance in Agent and Skill Changes

**C-DAD gap**: The `config-changelog.jsonl` captures user-triggered config changes (via `amend`/`learn`/`remember`) but agent and skill file edits have no embedded provenance. There is no record of *why* an agent was changed, who approved it, or what triggered the change.

**Tasks**:

- [ ] Extend `metrics/config-changelog.jsonl` schema to cover agent and skill file changes (not just config), with fields:
  - `artifact` — path to the changed file
  - `version-before` / `version-after`
  - `change-type` — `patch | minor | major`
  - `rationale` — why the change was made
  - `triggered-by` — user request, eval failure, feedback keyword, or ADR reference
  - `approved-by` — human who reviewed (if applicable)
- [ ] Update `eval-compliance-check.sh` hook: when an agent or skill file is edited, emit a prompt asking the agent to log the change to the changelog with rationale
- [ ] Update `skills/agent-skill-authoring.md` to require a changelog entry for every agent/skill modification
- [ ] Add an `adr-links:` optional frontmatter field so agents can reference the ADR that motivated their design

---

### Priority 5 — Formal Policy Inheritance

**C-DAD gap**: Governance principles exist in `CLAUDE.md` and `governance-compliance.md` but there is no formal cascade. A new agent can be created without explicitly declaring its compliance posture or inheriting org-level policies.

**Tasks**:

- [ ] Define a three-level policy hierarchy in `skills/governance-compliance.md`:
  - **Org level** — applies to all agents (data handling, audit requirements, ethics constraints)
  - **Domain level** — applies to agent categories (review agents, team agents, skills)
  - **Contract level** — agent-specific overrides or exemptions
- [ ] Add a `policy:` block to agent frontmatter for contract-level overrides:
  ```yaml
  policy:
    audit: true
    data-retention: session-only
    exemptions: []
  ```
- [ ] Update `/eval-audit` to check that agents do not implicitly violate org-level policies
- [ ] Document the exemption process: any `exemptions:` entry must include a rationale and an approver reference

---

### Priority 6 — Machine-Readable Manifests Alongside Markdown

**C-DAD gap**: All contracts are markdown-only. There are no parseable manifests that CI pipelines, external tooling, or other repositories could consume without parsing prose.

**Tasks**:

- [ ] For each agent and skill, the registry manifest (Priority 1) serves as the machine-readable layer. Ensure manifests are kept in sync with markdown files.
- [ ] Add a GitHub Actions workflow (or hook) that validates registry manifests on every PR:
  - All agents in `.claude/agents/` have a registry entry
  - Registry `version` matches frontmatter `version`
  - Registry `lifecycle` matches frontmatter `status`
  - All `artifacts` paths in manifests resolve to real files
- [ ] Generate a machine-readable index at `registry/index.json` — a flat list of all active agents and skills with their key metadata — suitable for consumption by external tools and other repositories

---

### Priority 7 — Dependency Graph Between Agents and Skills

**C-DAD gap**: There is no cross-agent dependency graph. If the Orchestrator's output format changes, dependent skills and review agents have no way to detect the impact. Skills that reference each other create invisible coupling.

**Tasks**:

- [ ] Add a `depends-on:` optional frontmatter field to agent and skill files listing their explicit dependencies:
  ```yaml
  depends-on:
    - skills/accuracy-validation
    - skills/governance-compliance
  ```
- [ ] Add a `used-by:` field (inverse index) to the registry manifest, populated automatically from `depends-on` entries
- [ ] Create a script (`scripts/dependency-graph.sh`) that reads all manifests and emits a DOT or Mermaid dependency graph
- [ ] Update `/eval-audit` to flag circular dependencies and orphaned skills (skills with no `used-by` entries)
- [ ] Add a breaking-change check: when an agent or skill with `change-type: major` is modified, identify all dependents from the registry and include them in the review scope

---

### Priority 8 — Runtime Enforcement (Future / Advanced)

**C-DAD gap**: Enforcement is CI-time only (hooks, review agents). C-DAD envisions contracts enforced at runtime — deployments blocked when deprecated contracts are invoked, policies validated before agent execution begins.

**Tasks** (longer-term):

- [ ] Define a pre-execution contract validation step in the Orchestrator: before spawning any agent, verify the agent's registry entry is `active` and its version is compatible with the current system version
- [ ] Add a runtime policy check: when the Orchestrator routes a task, validate that the selected agent's policy block is compatible with the task's data sensitivity classification
- [ ] Emit a structured event log entry for every agent invocation (agent id, version, model, task id, timestamp) to `metrics/invocation-log.jsonl` — this creates the runtime audit trail C-DAD requires
- [ ] Define a compatibility matrix: which versions of each agent are compatible with which versions of dependent skills

---

## Summary

| Todo | C-DAD Chapter | Effort | Value |
|------|--------------|--------|-------|
| Contract registry | Ch. 4 — Shared Collaboration Surfaces | Medium | High — enables cross-repo sharing and tooling |
| Lifecycle state management | Ch. 5 — Lifecycle of a Contract | Low | High — prevents using stale/experimental agents |
| Semantic versioning | Ch. 6 — Authoring & Representation | Low | Medium — makes breaking changes visible |
| Embedded provenance | Ch. 3 — Rationale and Provenance | Medium | Medium — audit trail completeness |
| Policy inheritance | Ch. 7 — Governance & Policy | Medium | Medium — formal compliance posture |
| Machine-readable manifests | Ch. 6 — Authoring & Representation | Low (follows registry) | High — cross-repo and tooling integration |
| Dependency graph | Ch. 11 — Dependency & Distribution | Medium | Medium — impact analysis for changes |
| Runtime enforcement | Ch. 9 — Automation and Pipelines | High | Future — production-grade enforcement |
