---
name: human-oversight-protocol
description: Approval gates, intervention commands, and transparency requirements. Use to classify any agent action as autonomous/notify/approve, respond to override/pause/stop commands, or structure a plan review before the implementation phase begins.
role: orchestrator
user-invocable: true
---

# Human Oversight Protocol

## Constraints

- Approval gates cannot be skipped; do not proceed past a gate without explicit human sign-off.
- Ethical concerns are never auto-resolved; always escalate.
- Intervention commands (`override`, `pause`, `stop`) take immediate effect with no debate.
- Overrides accumulate; 3+ overrides on the same topic must trigger a config amend.

## Plan Review as Primary Quality Gate

The implementation plan is the primary review artifact, not the code. Traditional line-by-line code review is replaced by plan review for AI-generated work — 200 lines of plan is far more reviewable than 2,000 lines of generated code, and if the plan is correct and tests pass, the code is trustworthy.

### Plan review checklist

1. Does the research accurately describe how the system works? (File paths, data flows, dependencies)
2. Does the plan address the right problem?
3. Are the specified changes complete — no missing files or edge cases?
4. Is the test strategy sufficient to verify correctness?
5. Are there architectural concerns the plan missed?

### When to still review code

- Security-sensitive paths (authentication, authorization, crypto)
- Performance-critical paths
- When tests are insufficient to verify correctness
- When the plan was ambiguous about implementation details

## Approval Gates

### Gate classification

Every agent action falls into one of three categories:

| Category | Description | Human involvement |
|---|---|---|
| **Autonomous** | Routine work within agent's defined scope | None — deliver output directly |
| **Notify** | Significant but within scope; human should be aware | Deliver output + flag what was decided and why |
| **Approve** | Outside routine scope or high-impact; human must sign off | Present proposal, wait for explicit approval |

### Standard approval gates

These actions always require human approval. Every gate below writes an
`approval` entry to `metrics/config-changelog.jsonl` per the [Audit trail](#audit-trail)
schema — `proposed`, `evidence_shown`, and `risks_surfaced` included.

| Action | Rationale |
|---|---|
| Research findings (Phase 1 → 2) | Misunderstanding cascades into bad plans and bad code |
| Implementation plan (Phase 2 → 3) | Plan correctness determines code correctness |
| Production deployment | Irreversible, affects users |
| Architecture change | High-impact, hard to reverse |
| Database schema migration | Data integrity risk |
| Security-sensitive code | Vulnerability risk |
| Scope change | May affect timeline/budget |
| Add a *new* external dependency (a package not already in the project) | Supply chain risk — a genuinely new package. A reversible minor/patch version **bump of an existing** dependency is **Medium** (decide-and-proceed), not this gate — see Escalation Paths. |
| Delete files or data | Potentially irreversible |
| Team structure change | Affects all agents |

### Agent-specific gates

Each agent defines additional gates in its `## Behavioral Guidelines > Decision Making` section. The Orchestrator consolidates these when coordinating multi-agent tasks.

## Intervention Mechanisms

### 1. Feedback (real-time correction)

```
amend: [modify existing behavior]
learn: [teach something new]
remember: [persist a preference]
forget: [remove a preference]
```

- Does NOT stop the current task
- Agent incorporates the feedback and continues
- Full procedure: [Feedback & Learning](../feedback-learning/SKILL.md)

### 2. Override (decision reversal)

```
override: [what was decided] → [what should be done instead]
```

- Stops the current approach; agent adopts the human's decision without debate
- Logged as `override` in the [audit trail](#audit-trail) — `proposed` records the rejected proposal, `description` records the substituted decision, `evidence_shown`/`risks_surfaced` required
- 3+ overrides on the same topic should trigger a config amend

### 3. Pause (temporary halt)

```
pause
```

- Agent stops and presents current state
- Human reviews and either resumes or redirects
- No output is discarded

### 4. Stop (emergency halt)

```
stop
```

- All agents halt immediately
- Current output preserved but not delivered
- Orchestrator presents a summary of what was in progress
- Human decides: resume, redirect, or abandon

## Transparency Requirements

### Decision logging

| Log entry | Where | When |
|---|---|---|
| Agent selected for task | Task metrics entry | At task start |
| Routing rationale | Orchestrator metrics entry | At task start |
| Approval gate triggered | Task metrics entry | When gate fires |
| Human approval/rejection | Config changelog — [`proposed`/`evidence_shown`/`risks_surfaced` required](#audit-trail) | When human responds |
| Override applied | Config changelog — [`proposed`/`evidence_shown`/`risks_surfaced` required](#audit-trail) | When override issued |

### Decision visibility (Notify level)

```
Decision: [what was decided]
Rationale: [why]
Alternatives considered: [what else was evaluated]
```

### Audit trail

**Canonical schema.** This section is the single canonical definition of the
gate-decision audit entry — [Governance & Compliance](../governance-compliance/SKILL.md)
and [Feedback & Learning](../feedback-learning/SKILL.md) reference it rather than
restating the field definitions.

All oversight events are appended to `metrics/config-changelog.jsonl` (one JSON
object per line, append-only — existing entries are never modified, deleted, or
migrated) with:

| Field | Required for | Type | Rule |
|---|---|---|---|
| `type` | all | string | `approval` \| `override` \| `pause` \| `stop` |
| `trigger` | all | string | `user` |
| `description` | all | string | What happened and why. For `override`, this is the human's substituted decision (see below) |
| `proposed` | `approval`, `override` — optional for `pause`/`stop` | string | One-line statement of what was put before the human — or, for `override`, what the agent had decided before the human reversed it |
| `evidence_shown` | `approval`, `override` — optional for `pause`/`stop` | array of strings | **Artifact pointers only, never prose.** Each element is a repo-relative file path (e.g. `plans/<slug>.md`), `commit:<sha>`, `issue:#N` / `pr:#N`, or `metrics/<file>.jsonl@<line-or-timestamp>`. Every pointer must resolve to something that still exists after the session ends — never a chat transcript or ephemeral build/console output. If the evidence exists only as prose, write it to `memory/` first and point at that file. |
| `risks_surfaced` | `approval`, `override` — optional for `pause`/`stop` | array of strings | Risks stated at the gate. `[]` is valid and explicit — it means "no risks were surfaced," distinguishing a reviewed-and-clear gate from a pre-change entry that omits the field entirely. |

**Required for `approval` and `override`.** Optional for `pause`/`stop` — those
record an interruption of state, not a decision over a proposal, so there is
often nothing "proposed" or "shown" to record.

**For `override` entries**: `proposed` records the rejected proposal — what the
agent had decided; `description` records the human's substituted decision,
matching the existing `override: [what was decided] → [what should be done
instead]` grammar. Both fields must be reconstructable from the entry alone.

**Non-interactive gates write identically.** When a gate auto-proceeds (`--yes`,
`DEV_TEAM_AUTO_APPROVE=1`, or no TTY — see `/plan` and `/build`), the entry
carries the same three fields; only `description`/`trigger` reflect the bypass
(e.g. `"description": "Auto-approved (non-interactive) — no human gate"`).
Unattended approvals are exactly where after-the-fact audit matters most.

**Backward compatible, never migrated.** Entries written before this schema
existed have no `proposed` / `evidence_shown` / `risks_surfaced` fields and
remain valid — the changelog is append-only. Every consumer (feedback-learning's
rollback lookup, governance-compliance's compliance queries and periodic
checklist) must tolerate both shapes: an absent field means "written before
this schema," not "malformed."

**Example — phase-gate approval:**

```json
{
  "timestamp": "2026-07-05T18:02:11Z",
  "type": "approval",
  "trigger": "user",
  "description": "Plan approved for issue #867 (gate-decision audit fields)",
  "proposed": "Implement the gate-decision schema extension per plans/issue-867-gate-decision-audit.md",
  "evidence_shown": ["plans/issue-867-gate-decision-audit.md", "issue:#867"],
  "risks_surfaced": []
}
```

**Example — override:**

```json
{
  "timestamp": "2026-07-05T18:10:44Z",
  "type": "override",
  "trigger": "user",
  "description": "override: run the migration script → apply the schema change by hand-editing the two SKILL.md files",
  "proposed": "Agent proposed running scripts/migrate_schema.py to apply the change",
  "evidence_shown": ["memory/build-issue-867.md"],
  "risks_surfaced": ["Hand-editing risks missing a write site the script would have covered"]
}
```

## Output

Gate classification (autonomous / notify / approve) with rationale, or escalation summary with severity and recommended action. One decision per output; no restating of protocol rules.

## Escalation Paths

```
Agent → Orchestrator → Human
```

1. Agent identifies the issue and flags it to the Orchestrator.
2. **Absorb the uncertainty before escalating it.** Investigate within the codebase, run the relevant check, or dispatch the agent best placed to resolve it. Escalate only what investigation cannot settle — a raw unknown is not yet an escalation.
3. Orchestrator classifies severity:
   - **Low**: route to another agent with appropriate expertise; do not involve the human.
   - **Medium** — reversible, low-blast-radius, and *not* one of the Standard approval gates above: **decide and proceed.** Commit to one path, state the rationale, act, and surface an explicit override — e.g. "Taking X because Y; reply `override` to change course." Do not hand the human a menu for a decision the agent can own and reverse. A **reversible minor/patch version bump of an existing dependency** (e.g. to pull a bug fix) is Medium: absorb the uncertainty first (read the changelog delta, run the suite against the bump), then **decide and proceed with an override affordance** — do not escalate it as a no-recommendation menu. It is distinct from *adding* a new package, which is the Standard gate below. (The Standard approval gates — *adding* a new external dependency, schema migration, scope change, deletes, etc. — are never downgraded to Medium; they remain Approve. A major-version bump, or one that pulls a genuinely new transitive package, leans Approve too.)
   - **High** — irreversible or high-blast-radius: present to the human with full context, **no recommendation** (avoid anchoring), and wait. Reserved for genuinely human-only calls: the standard approval gates, ethical concerns, and anything hard to reverse.
4. Human decides at the High tier (or when a committed Medium decision is overridden).
5. The decision — or the committed Medium path plus any override — is logged and fed back to the requesting agent.
