---
name: plugin-audit
description: >-
  Generalized structural compliance check for any Claude Code plugin. Audits
  architectural decisions only — agent type appropriateness (markdown vs script),
  frontmatter compliance, eval coverage, and body line-count budgets. Use when
  adding or modifying any agent or skill in a plugin, after scaffolding a new
  plugin, before a migration PR lands, or for a periodic health check. Accepts
  any plugin directory path; not hardcoded to one plugin's internal structure.
argument-hint: "[plugin-dir] [--fix]"
role: orchestrator
allowed-tools: Read, Edit, Grep, Glob
---

# Plugin Audit

Role: orchestrator. Mechanical, deterministic structural compliance — pattern
matching against the plugin contract. This is the generalized successor to
dev-team's internal `agent-audit`, scoped to **architectural decisions only**.

## Scope boundary

| In scope (this skill) | Out of scope |
|---|---|
| Agent type appropriateness (markdown vs script) | Detection-logic *quality* (→ the plugin's own `agent-eval`) |
| Frontmatter compliance | Shipping hygiene / `${CLAUDE_PLUGIN_ROOT}` ref resolution |
| Eval coverage presence | Shell portability (bash 3.2 / BSD / Git Bash) |
| Body line-count budgets | Catalog/version sync (→ release-please config) |

Architecture only. Do not evaluate whether a detector is *good* — only whether
the unit is the *right type*, well-formed, covered, and within budget.

## Orchestrator constraints

1. **Check structure, not semantics.** Verify fields/sections/patterns exist and
   the type matches the job. Never grade detection rules.
2. **Deterministic checks only.** Every check is reproducible — does the field
   exist? Is the format correct? Is the body within budget?
3. **Generalized.** Resolve every path from the target plugin dir. Never assume
   `plugins/dev-team`, an `agent-registry.md`, or a `.claude/docs/eval-system.md`.
4. **`--fix` applies minimal structural fixes** (insert missing sections/fields
   from templates). Never rewrite existing content.
5. **Be concise.** Output the report table and action items only.

## Step 1 — Resolve target plugin

Parse `$ARGUMENTS`:

- A directory path → audit that plugin.
- No path → if exactly one `plugins/*/` exists, use it; if several, list them and
  ask which to audit; if the cwd is itself a plugin dir (`.claude-plugin/plugin.json`
  present), use it.
- `--fix` → after the report, apply fixes for FAIL/WARN items.

Let `PLUGIN` = the resolved dir, `NAME` = its `.claude-plugin/plugin.json` `name`.
Eval fixtures are expected at the repo-root sibling `evals/<NAME>/` (never shipped
inside `PLUGIN`); accept `evals/<NAME>/fixtures/` or flat `evals/<NAME>/` layouts.

## Step 2 — Audit agents (`$PLUGIN/agents/*.md`)

For every agent file:

1. **Frontmatter compliance** — `name`, `description`, and `effort` (one of
   `low|medium|high`) are present; `tools` present. FAIL if `name`/`description`
   missing or `effort` absent/invalid. For the full official-contract check
   (required fields, name pattern, enum membership on any field present —
   `model`, `permissionMode`, `memory`, `isolation`, `color`, `background`,
   `maxTurns` — unknown-key and plugin-ignored-field warnings), run
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_agent_contract.py <file>`
   and fold any `error`/`warning` finding into this table as FAIL/WARN. This
   is advisory alongside the checks above until a future slice retires the
   effort-band requirement in favor of the contract's own defaults.
2. **No colon in `description`** — the value must not contain `:` (breaks
   argument-hints). FAIL on a colon.
3. **Skills–Skill invariant** — if the body has a `## Skills` heading, `tools:`
   must include `Skill`. FAIL otherwise.
4. **Agent type appropriateness** — read
   `${CLAUDE_PLUGIN_ROOT}/knowledge/agent-type-decision-rules.md` and classify
   the file by its observable behavior (the same R1–R10 walk as
   `/agent-type-advisor`'s retrospective mode). A `CHANGE` verdict is a WARN with
   the cited rule IDs; a `KEEP` is PASS. (For a deeper, dispatched review, the
   user can run the `plugin-best-practices-review` agent separately.)
5. **Review-agent shape** — a body containing the JSON status schema
   (`"status": "pass|warn|fail|skip"`) must declare the output schema
   (`status`, `issues`, `summary`), severity definitions, a `## Skip` section,
   and `Context needs:`. WARN on any missing.
6. **Body line-count** — count body lines (after frontmatter). Review agents
   (JSON-output) over 40 → WARN; team agents (persona `You are…` body) over
   75 → WARN.

## Step 3 — Audit skills (`$PLUGIN/skills/*/SKILL.md`)

1. **Frontmatter** — `name`, `description` (no colon), and `role` present. FAIL
   on missing `name`/`description`; WARN on missing `role`.
2. **Structured steps** — the body has an ordered procedure (numbered `##`/`###`
   steps or a `## Steps` section). FAIL if absent.
3. **Arguments documented** — a user-invocable skill (`user-invocable: true`)
   declares its arguments (`argument-hint` or an arguments section). WARN if
   missing.
4. **Conciseness directive** — the skill instructs concise output somewhere
   ("Be concise" / "no preamble" / output-only). WARN if absent.

## Step 4 — Eval coverage

For every **review agent** found in Step 2, check that at least one fixture
references it under `evals/<NAME>/`. WARN (not FAIL) when a review agent has no
fixture — eval authoring is a follow-up, but the gap must be visible.

## Step 5 — Report

```text
# Plugin Audit — <NAME> (<PLUGIN>)

## Agents
| Agent | Frontmatter | No-Colon Desc | Skills-Tool | Type | Review Shape | Body Budget | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Skills
| Skill | Frontmatter | Steps | Arguments | Concise | Status |
| --- | --- | --- | --- | --- | --- |

## Eval coverage
| Review agent | Fixture under evals/<NAME>/ | Status |
| --- | --- | --- |

## Summary
- Agents: N OK, N WARN, N FAIL
- Skills: N OK, N WARN, N FAIL
- Eval coverage: N covered, N gaps
- Action items: <list>
```

A clean plugin reports **zero findings** (every cell PASS / N/A). That is the bar
`/scaffold-plugin` output and a migrated skill must clear.

## Step 6 — Apply fixes (only when `--fix` is passed)

Without `--fix`, list action items and stop. With `--fix`, apply minimal
structural fixes and re-verify each:

- Missing review-agent output schema → insert the JSON block after the H1.
- Missing `## Skip` → insert the skip stub before `## Detect`.
- Missing `effort` → insert `effort: low` (review) / `effort: medium` (team).
- Colon in `description` → rewrite the value to remove colons (use `–`/`and`).
- `## Skills` without `Skill` in tools → append `, Skill` to the `tools:` line.

After each fix: re-read the file, re-run the specific check, report
`FIXED: <unit> — <what>`. Type mismatches (Step 2.4) are **never** auto-fixed —
converting markdown↔script is a human decision; report them as action items.
