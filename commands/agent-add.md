---
name: agent-add
description: >-
  Scaffold a new review agent from a description or URL. Use this whenever
  the user wants to add a new review agent, detect a new category of code
  issue, or says things like "add an agent for X", "create a reviewer for Y",
  "I want to check for Z in code reviews". Also use when given a URL to a
  coding standard or best-practices guide that should become a review agent.
argument-hint: >-
  <description-or-url> [--name <name>]
  [--tier small|mid|frontier]
  [--context diff-only|full-file|project-structure]
  [--lang <exts>] [--dry]
user-invocable: true
allowed-tools: Read, Write, Edit, Grep, Glob, WebFetch, Skill(eval-audit *)
---

# Agent Add

Role: implementation. This skill scaffolds new review agent files — it
generates compliant agent definitions from a description or reference URL.

You have been invoked with the `/agent-add` skill. Generate a new review
agent `.md` file that passes eval compliance checks, then update all
required documentation.

## Implementation constraints

1. **Follow the agent template exactly.** Every generated agent must
   have: frontmatter, Output JSON block, Status/Severity lines, Model
   tier, Context needs, `## Skip`, `## Detect`, `## Ignore` — in that
   order.
2. **Do not invent detection rules.** Derive rules from the user's
   description or URL content. If the description is vague, ask before
   guessing.
3. **Respect scope boundaries.** Check existing agents for overlap
   before generating. Warn the user if the new agent's scope conflicts
   with an existing one.
4. **Always update documentation.** Steps 7–9 are mandatory, not
   optional. A new agent that is not registered and documented does not
   exist as far as the rest of the system is concerned.
5. **Be concise.** Detection rules should be short phrases, not
   paragraphs. Skip/Ignore sections should be one-liners where possible.

## Parse Arguments

Arguments: $ARGUMENTS

Required: description or URL (`$0`) — either a text description of what
the agent should review, or a URL to fetch guidance from.

Optional:

- `--name <name>`: Agent name in kebab-case ending in `-review`
  (derived from description if omitted)
- `--tier small|mid|frontier`: Model tier (default: `small`)
- `--context diff-only|full-file|project-structure`: Context needs
  (default: `diff-only`)
- `--lang <exts>`: Comma-separated file extensions for
  language-specific scope (e.g., `js,ts,jsx,tsx`)
- `--dry`: Preview the generated content without writing to disk

## Steps

### 1. Parse input

- If `$0` starts with `http://` or `https://`, fetch it with WebFetch
  and extract the review focus from the page content.
- Otherwise, treat `$0` as a text description of the agent's purpose.

### 2. Derive agent name

If `--name` was not provided:

- Extract key concept from the description (e.g., "React hook
  violations" → `react-hook`)
- Append `-review` if not already present
- Convert to kebab-case

### 3. Check for scope overlap

Read all files in `.claude/agents/*.md` that declare `Model tier:`.
For each existing agent:

- Compare the `## Detect` section topics against the new agent's
  intended scope
- If overlap is found, warn the user:
  `⚠ Possible overlap with <existing-agent>: <overlapping topic>`
- Continue unless the user cancels

### 4. Generate agent file

Build the agent `.md` using this exact template:

```markdown
---
name: <name>
description: <one-line summary>
tools: Read, Grep, Glob
model: <haiku|sonnet|opus>
---

# <Title Case Name>

<If --lang provided>
Scope: <Language> files only (<extensions>).
Skip this agent entirely if the project has no <language> files.
</If>

Output JSON:
\```json
{"status": "pass|warn|fail|skip", "issues": [...], "summary": ""}
\```

Status: pass=<no issues>, warn=<minor concerns>, fail=<critical issues>
Severity: error=<must fix>, warning=<should fix>, suggestion=<consider>

Model tier: <tier>
Context needs: <context>

## Skip

Return `{"status": "skip", "issues": [], "summary": "<reason>"}` when:
- <inapplicability condition 1>
- <inapplicability condition 2>

## Detect

<Category 1>:
- <specific pattern to flag>
- <specific pattern to flag>

## Ignore

<What other agents handle> (handled by other agents)
```

Map `--tier` to frontmatter `model:`: small→haiku, mid→sonnet,
frontier→opus.

### 5. Write or preview

- If `--dry` was passed, display the generated content and stop.
- Otherwise, write to `.claude/agents/<name>.md`.

### 6. Run eval audit

Run `/eval-audit .claude/agents/<name>.md --fix` to validate compliance.
If any checks fail after auto-fix, report the remaining issues.

### 7. Update CLAUDE.md

Add a row to the Review Agents table in `.claude/CLAUDE.md`, inserted
alphabetically by agent name:

```text
| <name> | `agents/<name>.md` | <tier> | <short focus description> |
```

Also add an entry to the Orchestrator Model Routing Table if the new
agent's tier or name warrants a distinct row.

### 8. Update docs/agent_info.md

Add a row to the Review Agents table in `docs/agent_info.md`, inserted
alphabetically by agent name:

```text
| `<name>` | [`<name>.md`](../.claude/agents/<name>.md) | <model> | <short focus description> |
```

### 9. Update docs/team-structure.md

Add the new review agent to the Review Agent Dispatch Mermaid diagram
under the appropriate trigger condition. If no existing trigger matches,
add a new edge from `CO[Orchestrator]` to the new agent node.

### 10. Report

```text
Agent created: .claude/agents/<name>.md
Model tier: <tier>
Context needs: <context>
Eval audit: PASS|WARN (details)
Documentation updated:
  - .claude/CLAUDE.md (Review Agents table)
  - docs/agent_info.md (Review Agents table)
  - docs/team-structure.md (dispatch diagram)
```
