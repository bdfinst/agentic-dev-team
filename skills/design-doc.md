---
name: design-doc
description: Produce a written design document in docs/specs/ with user approval before planning begins. Use this skill during the Research phase when a feature request, architectural change, or non-trivial task enters the pipeline. Ensures misunderstandings are caught before any planning or implementation work starts. Also use when the user says "brainstorm", "design", "spec", or "let's think through this".
role: worker
user-invocable: true
---

# Design Document

## Overview

The Research phase explores what exists. This skill adds a structured output: a design document that captures the proposed approach and gets human approval before the Plan phase begins. Misunderstandings caught at design time cost minutes; misunderstandings caught at implementation time cost hours.

## Constraints
- Do not begin Phase 2 (Plan) without an approved design doc for non-trivial features
- Do not treat the design doc as a plan — it captures intent and approach, not file-level changes
- Do not skip alternatives analysis — a design doc with one option isn't a design doc, it's a plan
- The human must explicitly approve the design doc before proceeding
- **Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action** until the design doc is approved. The design doc is a gate, not a suggestion.

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "This is too simple to need a design doc" | Simple projects harbor unexamined assumptions. The design doc will be short — just write it. |
| "I already know the approach" | Then it'll take 5 minutes to write down. And the human might disagree. |
| "Writing a spec slows us down" | Misunderstandings caught at design time cost minutes. Misunderstandings caught at implementation time cost hours. |
| "The requirements are clear enough" | Clear to you. The human may interpret them differently. Write it down and verify. |

## When to Produce a Design Doc

| Task Type | Design Doc Required? |
|-----------|---------------------|
| New feature | Yes |
| Architectural change | Yes |
| Cross-cutting refactor | Yes |
| API design or redesign | Yes |
| Bug fix | No (unless the fix requires design decisions) |
| Typo/config/doc fix | No |
| Single-file change | No (unless it changes behavior significantly) |

## Document Structure

Save to `docs/specs/{feature-name}.md`:

```markdown
# {Feature Name} — Design Document

## Problem Statement
What problem are we solving? Who experiences it? What happens if we don't solve it?

## Proposed Approach
High-level description of the solution. How does it work? What are the key components?

## Alternatives Considered
| Approach | Pros | Cons | Why rejected |
|----------|------|------|-------------|

At least two alternatives. "Do nothing" counts as one.

## Key Decisions
Decisions that constrain the Plan phase. For each:
- What was decided
- Why
- What trade-off was accepted

## Open Questions
Things that need answers before or during planning. Tag each with who should answer (human, architect, domain expert).

## Scope Boundaries
What's explicitly in scope and out of scope. This prevents scope creep during planning and implementation.

## Visual Artifacts (optional)
Diagrams, mockups, data flow sketches — anything that clarifies the design. Use Mermaid for diagrams when possible.
```

## Process

1. **Research**: Explore the codebase, understand the problem space
2. **Draft**: Write the design doc based on research findings
3. **Present**: Show the design doc to the human at the Research phase gate
4. **Approve/Revise**: Human approves, requests changes, or redirects
5. **Proceed**: Approved design doc feeds into Phase 2 (Plan) as input alongside the research progress file

## Integration with Phases
- **Phase 1 output**: Research progress file + approved design doc
- **Phase 2 input**: Design doc provides intent and constraints; Plan phase specifies exact file changes
- **Agent-Assisted Specification**: Design doc complements BDD scenarios — design doc captures the "why" and "how", scenarios capture the "what"

## Output
A design document at `docs/specs/{feature-name}.md` reviewed and approved by the human before the Plan phase begins.
