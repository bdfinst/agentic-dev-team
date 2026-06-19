---
name: agent-create
description: >-
  Create new Claude Code sub-agent files following the official schema and
  token-efficiency budgets. Handles both review agents (JSON output, read-only
  tools, ≤ 40-line body) and team agents (prose output, action tools, ≤ 75-line
  body). Use when the user says "add an agent", "create a reviewer for X",
  "new team agent for Y", or when /agent-add is invoked. Validates against
  /agent-audit before writing. Updates the agent registry and CLAUDE.md after
  success.
role: worker
user-invocable: true
---

# Agent Create

Automates production of Claude Code sub-agent files that pass schema validation
and stay within token-efficiency budgets. For conventions, anti-patterns, and
registration checklists, see `skills/agent-skill-authoring/SKILL.md`.

## Constraints

- Do not write any file until validation passes and the user confirms the draft
- Name validation is a hard gate — exit immediately if the name is invalid
- Never include `hooks`, `mcpServers`, or `permissionMode` without explicit user
  confirmation after the plugin warning
- Body line budgets are hard limits enforced at generation time; trim content is
  shown to the user before any file is written
- Registry and CLAUDE.md updates are append-only; never edit existing rows

---

## Step 1 — Parse Arguments

Accept these inputs (from arguments or interactive prompts):

| Input | Required | Notes |
|-------|----------|-------|
| `name` | yes | file stem of the new agent |
| `type` | yes | `review` or `team` |
| `description` | yes | one-line summary for frontmatter |
| `tools` | no | comma-separated tool list |
| `model` | no | haiku \| sonnet \| opus \| inherit |
| `--tier small\|mid\|frontier` | no | maps to model: small→haiku, mid→sonnet, frontier→opus |
| `--context diff-only\|full-file\|project-structure` | no | sets `Context needs:` field in review body |
| `--lang <exts>` | no | adds language scope line to review body (e.g. `Scope: .ts, .tsx files only`) |
| `--dry` | no | display generated content without writing file or updating registry |

If `--tier` was provided, map to model: `small` → `haiku`, `mid` → `sonnet`, `frontier` → `opus`. This overrides any explicit `model` argument.

---

## Step 2 — Validate Name (hard gate)

The name must match `^[a-z][a-z0-9-]*$` exactly.

If it does not:

1. Emit: `Name must match ^[a-z][a-z0-9-]*$ — use lowercase letters, digits, and hyphens only`
2. Compute a kebab-case correction:
   - Lowercase all characters
   - Replace runs of non-alphanumeric characters with a single hyphen
   - Strip leading/trailing hyphens
   - If result starts with a digit: strip leading digits and any adjacent hyphens from the front; if the result is then valid, use it; if empty or still invalid, skip the suggestion
3. If a valid correction exists, emit: `Did you mean: <corrected-name>?`
4. **Stop immediately. Do not write any file.**

---

## Step 3 — Detect Agent Type

If `type` was not provided:

- Scan `description` for keywords:
  - `review`, `audit`, `check`, `validate`, `detect`, `scan`, `lint` → infer `review`
  - `engineer`, `architect`, `manager`, `writer`, `planner`, `designer`, `specialist` → infer `team`
- If inference is confident, state the inferred type and continue
- If ambiguous or no keywords match, ask: `Agent type: review or team?`

---

## Step 4 — Prompt for Missing Tools

If `tools` was not provided, emit exactly:

```
Which tools does this agent need?
  Read, Grep, Glob (read-only) | add Edit, Write (file changes) | add Bash (shell) | add Skill (skill invocation) | add Agent (spawn subagents)
```

Wait for the user's selection before continuing.

If tools were provided, validate each against known Claude Code tool names
(`Read`, `Grep`, `Glob`, `Bash`, `Edit`, `Write`, `Agent`, `Skill`,
`WebFetch`, `WebSearch`, `NotebookRead`, `NotebookEdit`). Flag unknown names
as a warning (not an error — custom tools are allowed).

---

## Step 5 — Apply Defaults

| Setting | Review default | Team default |
|---------|---------------|-------------|
| `tools` | `Read, Grep, Glob` | (whatever user specified) |
| `model` | `haiku` | `sonnet` |

Only apply a default when the value was not specified by the user.

---

## Step 6 — Check for Existing File

Glob `plugins/dev-team/agents/<name>.md`.

If the file exists:

1. Read its `description` frontmatter field
2. Emit: `plugins/dev-team/agents/<name>.md already exists (description: <existing-description>)`
3. Ask: `Overwrite? (yes/no)`
4. On `no`: emit `Cancelled. Existing agent: plugins/dev-team/agents/<name>.md — <existing-description>` and **stop with no changes**
5. On `yes`: continue

---

## Step 7 — Check Scope Overlap (Review Agents Only)

For review agents, scan existing agents for topical overlap:

1. Read `description` frontmatter of all files in `plugins/dev-team/agents/`
2. For each existing agent, also read the first 20 lines of its `## Detect` section if present
3. If the LLM judges ≥ 60% topical overlap between the new description and an existing agent's scope, emit:

   `Possible overlap with <agent-name>: <one-sentence description of shared concept>. Continue anyway? (yes/no)`

4. On `no`: stop with no changes
5. On `yes`: continue
6. This check is advisory — the user can always continue

For team agents: compare descriptions only (no `## Detect` scan).

---

## Step 8 — Handle Plugin-Unsupported Fields

If the user has requested `hooks`, `mcpServers`, or `permissionMode`, emit:

```
hooks/mcpServers/permissionMode are silently ignored for plugin agents — move the file to .claude/agents/ if you need them to take effect
```

Then ask: `Include anyway? (yes/no)`

- On `no`: omit the field from generated frontmatter
- On `yes`: include the field as requested

Do not emit this warning for fields the user did not request.

---

## Step 9 — Generate Frontmatter

Emit only official fields with non-empty values. Use this structure:

```yaml
---
name: <name>
description: <description>
tools: <comma-separated tool list>
model: <model>
[any additional fields the user requested and confirmed]
---
```

Do not include `hooks`, `mcpServers`, or `permissionMode` unless the user
confirmed their inclusion in Step 8.

#### `cites:` (citation drift defense, #312)

When a review agent inlines normative **numeric thresholds** (e.g. "functions
MUST be under 50 lines", "coverage SHOULD reach 80%") that are owned by a
canonical skill or knowledge file, declare those sources with a `cites:` list so
`/agent-audit`'s citation lint can detect drift between the agent and its source:

```yaml
cites: [complexity, object-calisthenics]   # skill names or knowledge file stems
```

Each entry resolves to `skills/<name>/SKILL.md` or `knowledge/<name>.md`. The lint
(`scripts/citation_lint.py`) flags any threshold the agent states on an RFC-2119
line that is absent from every cited source. The lint is advisory (Phase 1,
non-blocking) either way.

**Pre-write check.** After Step 10 generates the body, before Step 11 writes
the file:

1. Scan the generated body for **threshold-bearing RFC-2119 lines** — any
   line carrying `MUST|SHOULD|SHALL|REQUIRED|NEVER|ALWAYS` AND a numeric
   token (`\d+(\.\d+)?%?`), outside code fences and blockquotes.
2. If any are found AND no `cites:` field was set, emit exactly:

   ```text
   ⚠ Agent body states N numeric threshold(s) on RFC-2119 lines but no
     cites: was declared. Eval drift defense will be blind on this agent.

     (a) add cites:  (b) proceed without
   ```

3. On `(a)`: prompt for a comma-separated list, validate each entry resolves
   to a real `skills/<name>/SKILL.md` or `knowledge/<name>.md`, insert
   `cites: [<list>]` into the frontmatter, and continue to Step 11.
4. On `(b)`: continue to Step 11 with no `cites:` — the lint will flag the
   agent as `advisory` going forward, which is the correct deferred state.

Omit the check entirely when the body states no thresholds; nothing for the
lint to verify means the field is genuinely optional.

---

## Step 10 — Generate Body

### Review Agent Body Structure (required order)

If `--context` was provided, use it for the `Context needs:` field. Otherwise infer a sensible default from the description (simple detectors → `diff-only`; agents that need full file context → `full-file`; agents that need project structure → `project-structure`).

If `--lang` was provided, insert a language scope line immediately after the title: `Scope: <exts> files only. Skip if no <exts> files are present.`

```markdown
# <Title Case Name>

[Scope: <exts> files only. Skip if no <exts> files are present.]

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=<condition>, warn=<condition>, fail=<condition>
Severity: error=<condition>, warning=<condition>, suggestion=<condition>
Confidence: high=<condition>, medium=<condition>, none=<condition>

Model tier: <small|mid|frontier>
Context needs: <diff-only|full-file|project-structure>

## Skip

Return `{"status": "skip", ...}` when:

- <inapplicability condition>

## Detect

<Category>:

- <specific pattern to flag>

## Ignore

<what other agents handle> (handled by other agents)

```

### Team Agent Body Structure (required order)

```markdown
# <Title Case Name>

You are a <role description: worldview, characteristic approach, communication style>. <2–3 additional sentences covering how this agent thinks, what it prioritizes, and how it delivers output.>

## Output discipline

- Write <artifact type specific to this role> to files, not chat.
- No preamble. <Role-specific communication default.>
- End-of-turn: one sentence on <what this role reports at turn end>.
- For structured deliverables (<role-specific examples>), emit only the structure.
- Status updates: one paragraph max.

## Technical Responsibilities

- <action-oriented responsibility>

[## Skills]              (optional — list skill name + one-line invocation context)

[## Behavioral Guidelines]  (optional — decision-making autonomy, escalation, conflict)
```

### Token-Efficiency Rules (both types)

Apply these rules when generating the body:

1. **No opener (review agents only)**: for review agents, no line may match `^You are an?` (case-insensitive). Team agents MUST start with a `You are…` persona paragraph — this rule does not apply to them.
2. **No description restatement**: title must not contain the `description` field value verbatim (whitespace-normalized)
3. **No placeholder text**: body must not contain `your-agent-name`, `One-sentence description`, or `# Agent Name`
4. **Bullet length**: no single bullet point may span more than two lines
5. **Knowledge file reference**: one line only — `Read knowledge/X.md before starting` — no prose explanation
6. **Review Skip section**: 1–3 bullet conditions, no prose explanation
7. **Review Ignore section**: one sentence listing what other agents handle
8. **Skills section (team)**: skill name + one-line invocation context only

### Line Budget Gate

After generating the body, count all lines (including blank lines).

**Review agents**: if line count > 40:

1. Emit: `Body is N lines — X lines over the 40-line budget for review agents`
2. List each removed/collapsed item, each prefixed with `-` (dash space)
3. Emit: `Approve this trim? (yes/no)`
4. On `yes`: apply trim and continue
5. On `no`: emit `Options: (a) reduce spec scope and regenerate, (b) accept N lines and proceed without trimming` and wait

**Team agents**: same gate with budget of 75 and label `team agents`.

**Trimmable content** (in priority order):

- Blank separator lines between sections (but not between bullets)
- Multi-line bullets collapsed to one line
- Wordy bullet text shortened to the essential action

**Protected content** (never trim):

- Output JSON block
- Section headings (`## Skip`, `## Detect`, `## Ignore`, `## Responsibilities`)
- The closing `---` of any required section

---

## Step 11 — Run /agent-audit Validation Gate

`/agent-audit` (structural compliance of the generated agent file) is the
validation gate of record — it is the tool that audits agent files. The gate is
**blocking**: an unresolved audit failure aborts creation (the cancel path
below), it never silently continues. (`claude-setup-review` audits project-level
CLAUDE.md setup, not a single new agent file, so it is not the gate here.)

**If `--dry` was passed**: display the complete generated file content to the user and stop. Do not write any file, do not run validation, do not update the registry or CLAUDE.md.

Otherwise: write the generated content to disk, then invoke the agent-audit skill:
`Skill(agent-audit plugins/dev-team/agents/<name>.md)`

**If the audit returns errors:**

1. Emit the raw `/agent-audit` output verbatim
2. Emit: `All your inputs are preserved.`
3. Emit: `(a) auto-correct and re-validate  (b) cancel`
4. On `(b)`: delete the file, make no changes, stop
5. On `(a)`: apply the minimal corrections, re-run `/agent-audit` once more
   - If the second run passes: continue to Step 12
   - If the second run also fails: emit new `/agent-audit` output verbatim; emit `All your inputs are preserved.`; emit `(a) auto-correct and re-validate  (b) cancel` again (no silent stop)

**If the audit passes:** continue to Step 12.

---

## Step 12 — Present Draft and Confirm Write

Ask: `Write this file to plugins/dev-team/agents/<name>.md? (yes/no)`

On `no`: delete the file written in Step 11, make no other changes, stop.
On `yes`: the file is already on disk from Step 11; no re-write needed unless the user modified the draft.

---

## Step 13 — Update Agent Registry

Locate the table in `knowledge/agent-registry.md` whose heading contains
`Review Agents` (for review type) or `Team Agents` (for team type).

If the heading is not found: emit
`Cannot update knowledge/agent-registry.md: heading containing '<type> Agents' not found. Update manually.`
and stop without modifying the file.

Map model to tier label: `haiku` → `small`, `sonnet` → `mid`, `opus` → `frontier`, `inherit` → `mid`.

Append a row to the correct table:

```
| <name> | agents/<name>.md | <tier-label> | <description> |
```

---

## Step 14 — Update CLAUDE.md

CLAUDE.md carries a **prose Quick Reference list**, not a table — the
authoritative agent tables live in `knowledge/agent-registry.md` (updated in
Step 13). Update the matching Quick Reference line under `### Quick Reference`:

- Review type → the line beginning `**Review agents** (<N>):`
- Team type → the line beginning `**Team agents** (<N>):`

Edit that line in place: **increment the parenthesised count** `(<N>)` → `(<N+1>)`
and **append `, <name>`** to the comma-separated list (before any trailing
token-count note, e.g. `(~4,510 tokens total)`).

If the line is not found: emit
`Cannot update CLAUDE.md: '<type> agents' Quick Reference line not found. Update manually.`
and stop without modifying the file. (This is a real-failure branch, not the
normal path — the line exists in the shipped CLAUDE.md.)

Confirm both updates in the completion report.

---

## Completion Report

```
Agent created: plugins/dev-team/agents/<name>.md
Type: <review|team>
Model: <model> (<tier-label>)
Body: <N> lines
Validation: PASS (/agent-audit)
Registry updated: knowledge/agent-registry.md (<type> Agents table)
CLAUDE.md updated: <type> agents Quick Reference list (count <N>→<N+1>)
```
