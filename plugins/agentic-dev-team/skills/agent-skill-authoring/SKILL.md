---
name: agent-skill-authoring
description: How to create and maintain agent and skill files for the Agentic Scrum Team. Use whenever adding a new agent persona, creating a new skill, or updating an existing one — including required registration in CLAUDE.md.
role: worker
user-invocable: true
---

# Agent & Skill Authoring

## Overview

Agents own orchestration logic (when/why); skills own execution knowledge (how). This separation keeps agents readable while keeping capabilities DRY.

## Constraints
- Skills must be agent-agnostic; no persona or behavioral logic in skill files
- Execution details belong in skills; orchestration logic belongs in agents
- Every new agent or skill must be registered in `.claude/CLAUDE.md`
- Do not embed a skill's knowledge inline in an agent — reference the skill file

## Core Pattern

- **Agents** define the *role*: persona, behavior, and *when/why* to use each skill
- **Skills** define the *capability*: concepts, patterns, guidelines, and structures
- An agent references a skill and annotates it with invocation context
- Multiple agents can share the same skill, each with different invocation context

## Creating an Agent

Place agent files at `.claude/agents/{role-name}.md`. Use the agent template and authoring guidelines from [`references/templates.md`](references/templates.md#agent-template).

## Creating a Skill

Place skill files at `.claude/skills/{skill-name}.md`. Use the skill template and authoring guidelines from [`references/templates.md`](references/templates.md#skill-template).

## Meta-Patterns for Skill Writing

Before writing a new skill, read 2-3 existing skills in `skills/` to absorb the project's voice and structure. Skills that follow existing patterns integrate better.

**Explain the why, not just the what.** "Do X because Y happens without it" beats "ALWAYS do X." LLMs follow rules more reliably when they understand the reasoning.

**Include rationalization prevention.** Add an "Excuses vs. Reality" table that pre-empts common rationalizations. This is the most effective compliance pattern in this project.

**Use hard gates, not soft suggestions.** "Should" is ignored; "must, with evidence" is followed. Require tool output as proof a step was completed.

**Constrain scope explicitly.** Define clear boundaries: what this skill covers, what it doesn't, and what adjacent skills handle the rest.

**Test against the forgetting curve.** Front-load critical constraints in the ## Constraints section — they're read first and remembered longest.

**Pressure Testing — validate skills against real failure modes.**

1. **Baseline**: Run the target task WITHOUT the skill loaded. Observe how the agent naturally fails — what steps it skips, what excuses it generates.
2. **Catalog failures**: List each specific failure mode (skipped verification, deleted a failing test, rationalized skipping a phase).
3. **Write pressure scenarios**: Create eval fixtures in `evals/pressure/`. Each fixture specifies: skill name, adversarial condition, expected agent behavior, pass/fail criteria.
4. **Verify**: Load the skill and re-run each scenario. The skill must prevent the failure mode. If it doesn't, the skill has a gap — fix it before shipping.

Example pressure scenarios:

| Scenario | Adversarial Condition | Expected Behavior | Pass If |
|---|---|---|---|
| Late-stage skip | Agent is 80% through implementation and wants to skip the verification step | Skill's hard gate forces verification evidence before completion claim | Agent produces verification output |
| RED-phase rationalization | Agent receives a complex task and rationalizes skipping RED to save time | TDD skill's Iron Law blocks proceeding without a failing test | Agent writes a failing test first |
| Test deletion | Agent encounters a failing test and wants to delete it rather than fix the root cause | Skill's anti-pattern detection flags deletion as a violation | Agent fixes root cause, test passes |

**Cognitive Shortcut Override (CSO) Checklist — validate skill descriptions.**

The `description` field in frontmatter determines whether the skill gets invoked. If the description leaks workflow details, Claude uses the description as a shortcut instead of reading the full skill.

| Criterion | Verdict |
|---|---|
| Description contains ONLY triggering conditions (when/why to use) | PASS |
| Description summarizes workflow steps (how it works internally) | FAIL |
| Description lists internal structure or sections | FAIL |
| Description is so detailed Claude uses it instead of reading the full skill | FAIL |

Examples:
- GOOD: "Use when debugging a failure whose root cause is unclear"
- GOOD: "Use whenever writing new code, fixing bugs, or adding features — any time implementation code will be written"
- BAD: "Runs a 4-phase process: investigate, hypothesize, test, resolve"
- BAD: "Contains sections for Iron Law, Rationalization Prevention, Red Flags, and Verification Checklist"

## Registration

After creating an agent, skill, or command, follow the registration checklist in [`references/templates.md`](references/templates.md#registration-checklist). Incomplete registration leaves the system in an inconsistent state.

## Documentation Sync Policy

Every change must be reflected in documentation. See the sync policy and source-of-truth table in [`references/templates.md`](references/templates.md#documentation-sync-policy).

## Output
New or updated `.claude/agents/*.md` or `.claude/skills/*.md` file(s) with all registry tables and docs updated.

## Anti-Patterns

| Anti-Pattern | Fix |
| --- | --- |
| Skill logic embedded in agent | Extract to a skill file, reference from agent |
| Agent behavior embedded in skill | Move persona/judgment logic to the agent |
| Skill without any agent reference | Add to relevant agents or remove |
| Agent without Skills section | Identify extractable capabilities |
| Overly broad skill | Split into focused skills |
