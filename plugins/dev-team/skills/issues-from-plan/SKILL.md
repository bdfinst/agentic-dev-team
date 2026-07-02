---
name: issues-from-plan
description: >-
  Break a plan into independently-grabbable GitHub issues. Use when the user
  says "create issues from this plan", "break this into tickets", "file issues",
  or wants to distribute plan steps across a team.
argument-hint: "[plan file path]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Issues from Plan

Role: orchestrator.

Break an implementation plan into GitHub issues that can be worked independently.

## Orchestrator constraints

1. Decompose the plan into issues; do not implement.
2. Preserve plan ordering and dependencies as issue links.
3. **Be concise.** Report created issue numbers, no narration.

## Process

### 1. Find the Plan

If a path is provided in arguments, read that file. Otherwise, look for the most recent plan in:

- Active plan in conversation context
- `memory/` directory (phase progress files)
- `plans/` directory

Arguments: $ARGUMENTS

If no plan is found, ask the user to point you to one.

### 2. Analyze the Plan

Read the plan and identify each **slice** (`### Slice <id>:`), its acceptance criteria, and the shared architectural decisions. Derive the dependency links from the **DAG, not file order** — do not hand-infer them:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/issue_deps.py <plan-file>
```

This returns `{ "<slice>": ["<dep slice>", ...] }` — each slice's direct predecessors. A slice listed earlier in the file carries **no** dependency on a later one unless the DAG says so.

Then locate the plan's **spec** (the linked spec artifact or `docs/specs/<...>.md`); it becomes the **parent** issue. **If the plan has no associated spec, report that and create no parent issue** (and no children) — stop here.

### 3. Draft Issues

For each unit of work, draft an issue with:

- **Title**: Short, action-oriented (e.g., "Add user authentication endpoint")
- **Body**:
  - What to build (behavior description, not implementation details)
  - Acceptance criteria as checkboxes
  - Dependencies on other issues (by title reference)
  - Relevant architectural decisions from the plan
  - Testing approach
- **Labels**: suggest appropriate labels if the repo uses them

### 4. Review with User

Present the issue list as a numbered summary:

```
1. [Title] — [one-line description] (depends on: none)
2. [Title] — [one-line description] (depends on: #1)
3. [Title] — [one-line description] (depends on: #1)
...
```

Ask: "Does this breakdown look right? Should any issues be merged or split?"

Wait for approval before creating.

### 5. Create Issues (parent spec, then slice children)

Create the **parent** issue from the spec first, then one **child** issue per slice linked to it, then backfill the sibling `depends on #N` links from the `scripts/issue_deps.py` map:

1. **Parent (spec):** `gh issue create` from the spec (intent + acceptance summary); capture its number as `$PARENT`. If step 2 found no spec, skip everything — no parent, no children.
2. **Children (slices):** for each slice, `gh issue create` with `Part of #$PARENT` in the body. Record the **slice-id → issue-number** mapping as you go.
3. **DAG links:** for each slice, look up its predecessors from the `scripts/issue_deps.py` map, translate them to the child issue numbers, and set the child's `## Depends On` to `depends on #N` for each (a slice with no predecessors says "none"). Links come from the DAG map, never from file order.
4. **Partial-failure safety:** if any `gh` call fails partway, do **not** abort silently — report which issues were created (with numbers) and which were not, then let the plan flow continue. Never leave a half-created state unreported.

```bash
gh issue create --title "Issue title" --body "$(cat <<'EOF'
## What to Build

[Behavior description — what this slice delivers end-to-end]

Part of #<parent>

## Depends On

- #<number>: [brief reason]   <!-- from scripts/issue_deps.py; "none" if no predecessors -->

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] All tests pass

## Architectural Context

[Relevant decisions from the plan that apply to this issue]

## Testing Approach

[What to test and how — behavior-level, not implementation-level]
EOF
)"
```

### 6. Present Results

List all created issue URLs with their titles. Note the dependency graph.
