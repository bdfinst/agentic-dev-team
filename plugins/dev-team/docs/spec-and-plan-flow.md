# Specification and plan flow: how agents and the user define a spec

How a feature request becomes an approved specification and then an approved
plan. The pieces are two skills, `/specs` and `/plan`, and the agents they
dispatch. This document is the end-to-end flow that connects them and shows
where the user makes each decision.

> **Authoritative sources**: the skill specs at
> [`skills/specs/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/specs/SKILL.md)
> and
> [`skills/plan/SKILL.md`](https://github.com/bdfinst/agentic-dev-team/blob/main/plugins/dev-team/skills/plan/SKILL.md).
> This document is a reader-friendly walkthrough. Where it and a skill spec
> disagree, the spec wins.

**On this page**: [Who does what](#who-does-what) · [The flow at a glance](#the-flow-at-a-glance) · [The collaboration loop](#the-collaboration-loop-in-detail) · [Human decision points](#human-decision-points) · [Regenerating the diagrams](#regenerating-the-diagrams)

## Who does what

| Role | Owns | Does not do |
| --- | --- | --- |
| **User** | Every decision: the first draft of each artifact, accept/reject on each critique, answers to `requires-stakeholder-input` questions, scope splits, spec approval, plan approval. | Edge-case enumeration. The build cadence's per-behavior tests catch those. |
| **Orchestrator** (`/specs`, `/plan`) | Mode selection, the critique loop, the Ambiguity Resolution Protocol, the completeness sweep, the consistency gate, persistence, slicing, Gherkin authoring, reviewer dispatch. | Writing implementation code. Both skills stop before any code exists. |
| **Product Manager** agent | Leads the Intent Description and Acceptance Criteria stages. Screens the request against the decision-defaults axes and batches ambiguous ones into one question round. | Architecture constraints. |
| **Architect** agent | Leads the Architecture Specification stage and runs the cross-artifact consistency gate. | Intent and business priority. |
| **Plan-review critics** (`plan-review-acceptance`, `-design`, `-ux`, `-strategic`, `-parallelization`) | Adversarial review of the plan before the user sees it. The set scales to plan tier. `plan-review-acceptance` always runs. | Approval. A critic's `approve` verdict never replaces the human gate. |

## The flow at a glance

Two diagrams, one per skill. `/specs` ends where `/plan` begins.

![Flowchart of /specs: a feature request is classified by argument shape into authoring, validate, or refuse. Authoring checks for a scope split, then each of the three artifacts runs the loop: user drafts, agent critiques, user decides, agent refines, max two iterations. Every gap goes through the Ambiguity Resolution Protocol, where inferable items are logged and requires-stakeholder-input items are batched back to the user. A completeness sweep feeds the cross-artifact consistency gate; fail loops back to drafting, pass persists the spec and auto-invokes /plan in authoring mode only.](diagrams/spec-flow.svg)

![Flowchart of /plan: read the approved spec, decompose into vertical slices, author Gherkin per slice, derive the parallelization DAG with plan_waves.py, classify the plan tier, dispatch one, two to four, or all five plan-review critics, revise on needs-revision for at most two rounds, append the Plan Review Summary, then present to the user who approves or requests changes. Approval exports .feature files, offers slice issues, and hands off to /build.](diagrams/plan-flow.svg)

## The collaboration loop in detail

The flowchart shows the gates. The sequence below shows the conversation
between the user and the agents inside `/specs` and across the handoff to
`/plan`. The Product Manager leads the Intent and Acceptance Criteria stages.
The Architect leads the Architecture Specification stage and runs the
consistency gate.

![Sequence diagram between the User, the /specs orchestrator, the Product Manager, the Architect, the /plan orchestrator, and the plan-review critics. The user drafts Intent with the Product Manager, Architecture with the Architect, and Acceptance Criteria with the Product Manager, each critiqued and refined in at most two rounds. Before acceptance criteria, /specs batches every requires-stakeholder-input decision to the user. The Architect runs the consistency gate; on pass, /specs persists and auto-invokes /plan. /plan slices, authors Gherkin, dispatches tier-scaled critics, revises until they approve, then asks the user to approve or request changes.](diagrams/spec-plan-sequence.svg)

## Human decision points

Every decision in the flow belongs to the user. The agents narrow the
question. They never answer it on the user's behalf.

| Gate | Where | What the user decides |
| --- | --- | --- |
| Existing spec | `/specs` Step 1 | Regenerate an older-format spec, or update in place. |
| Scope split | `/specs` Scope Split Protocol | Approve splitting a bundled request into one spec per feature. |
| Critique decision | `/specs` collaboration loop, per artifact | Accept, reject, or modify each critique finding. Rejections are recorded with the reason. |
| Stakeholder input | `/specs` Ambiguity Resolution Protocol | Answer every `requires-stakeholder-input` item, presented as one batch. |
| Glossary | `/specs` Glossary | Confirm inferred definitions. Only a human can mark a term `verified`. |
| Consistency gate | `/specs` Cross-Artifact Consistency Gate | Hard stop. Nothing proceeds to `/plan` until every item passes. |
| Spec destination | `/specs` persistence | Overwrite or version an existing spec file, or update versus create a matching GitHub issue. |
| Plan approval | `/plan` Step 6 | Approve the plan or request changes. This is the Phase 2 to Phase 3 gate. `--yes` or no TTY auto-approves and records the bypass. |
| Slice issues | `/plan` post-approval | Opt in to one parent issue plus N slice issues. Default is No. |

What the flow does **not** do: synthesize edge cases. `/specs` resolves the
ambiguity a human must settle. The build cadence's per-behavior tests surface
the edge cases a spec implies but never lists.

## Regenerating the diagrams

The SVGs are rendered from the Mermaid sources beside them in
[`diagrams/`](diagrams/) (`spec-flow.mmd`, `plan-flow.mmd`,
`spec-plan-sequence.mmd`). Edit the `.mmd`, then re-render:

```bash
npx -y @mermaid-js/mermaid-cli -i plugins/dev-team/docs/diagrams/spec-flow.mmd -o plugins/dev-team/docs/diagrams/spec-flow.svg -b white
```

Repeat for the other two files. The `.mmd` is the source of truth. Never edit
the SVG by hand.
