---
name: design-interrogation
description: >-
  Relentlessly interview the user about a plan, design, or feature spec to
  surface unresolved decisions, hidden assumptions, and edge cases. Use when
  the user says "grill me", "stress-test this plan", "poke holes in my design",
  "what am I missing", or before committing to a plan that feels under-examined.
  Unlike /specs (which produces artifacts) this skill produces clarity — it's a
  thinking tool. Also use proactively in the Research phase when a design doc
  has implicit decisions that need to be made explicit.
role: worker
user-invocable: true
---

# Design Interrogation

## Overview

Walk every branch of a decision tree until all decisions are resolved. The goal is not to produce an artifact — it's to force the developer to think through decisions they'd otherwise skip. Good designs fail not from what was considered, but from what wasn't.

## When to Use

- Before committing to a plan (Research phase, before `/plan`)
- After a design doc is drafted but before implementation
- When the user says "grill me" or "stress-test this"
- When a plan has implicit assumptions that need to be surfaced

## How It Works

### 1. Identify the Decision Surface

Read the plan, design doc, spec, or description. Identify every decision point — explicit ones the user already made, and implicit ones hiding behind assumptions. Look for:

- **Unstated assumptions**: "We'll use X" without explaining why not Y
- **Vague scope boundaries**: "We'll handle that later" — when is later?
- **Missing error paths**: What happens when the happy path breaks?
- **Integration seams**: Where does this design touch other systems?
- **Scale implications**: Does this work for 10 users? 10,000? 10 million?
- **Migration paths**: How do you get from the current state to the proposed state?

### 2. Walk the Decision Tree

Ask questions **one at a time**. For each question:

1. State the decision that needs to be made
2. Provide your recommended answer with reasoning
3. If the question can be answered by exploring the codebase, explore it yourself instead of asking the user
4. Wait for the user's response before moving to the next question

Follow dependency order — resolve foundational decisions before asking about things that depend on them. If an answer to one question invalidates a previous decision, flag it.

### 3. Go Deep, Not Wide

Don't ask surface-level questions. Push into the uncomfortable territory:

- "You said you'd use a queue here — what happens when the queue fills up?"
- "This assumes the API is always available. What's the degradation strategy?"
- "You've designed for creation but not deletion. Is that intentional?"
- "Three services share this model. Who owns the schema?"

If the user gives a hand-wavy answer, push back: "That's a direction, not a decision. What specifically would you build?"

### 4. Know When to Stop

Stop when:
- Every branch of the decision tree has a concrete answer
- The user says "that's enough" or "I'm confident now"
- You've circled back to the same questions — all paths are resolved

### 5. Summarize

After the interrogation, provide a brief summary:
- **Decisions made**: numbered list of resolved decisions
- **Open items**: anything the user explicitly deferred (with the reason)
- **Risks identified**: concerns that surfaced during questioning

This summary can feed directly into `/plan` or a design doc.

## Tone

Be direct and constructive, not adversarial. The goal is partnership in finding gaps, not scoring points. Think of a senior engineer doing a design review — rigorous but respectful. Provide your own recommended answer for every question so the user has something to react to, not just a blank to fill.

## Anti-Patterns

- Don't ask questions you could answer by reading the codebase
- Don't ask rhetorical questions — every question should need a decision
- Don't ask more than one question at a time
- Don't accept "we'll figure it out later" without pressing for when and how
- Don't turn this into a requirements document — that's what `/specs` does
