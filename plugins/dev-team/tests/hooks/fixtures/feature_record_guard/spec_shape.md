# Spec: Lanes

<!-- Template note: fill each section. Delete comments before approval. -->

## Intent Description

Build lanes run in isolated worktrees so a failed lane cannot corrupt the
others. The goal is a faster build with the same integration order.

## Architecture Specification

- A lane is one worktree and one branch.
- Composition merges lane results in plan order.

## Acceptance Criteria

- [ ] AC1 A lane opens in its own worktree.
- [ ] AC2 Composed lanes integrate once, in plan order.

## Out of scope

Remote execution.
