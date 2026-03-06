---
name: eval-audit
description: >-
  Audit code-review agents, skills, and hooks for structural compliance.
  Use this when adding or modifying any agent, skill, or hook file, or for
  a periodic health check of the toolkit. Trigger phrases: "audit the
  agents", "check compliance", "validate the skills", "are the agents
  correct", or any time agent/skill files change.
argument-hint: "[file-path | --all] [--fix]"
user-invocable: true
allowed-tools: Read, Edit, Grep, Glob
---

# Eval Audit

Role: orchestrator. This skill performs mechanical compliance
checks — pattern matching against known-good structure.

You have been invoked with the `/eval-audit` skill. Audit agents and
skills for compliance with the eval system patterns documented in
`.claude/docs/eval-system.md`.

## Orchestrator constraints

1. **Check structure, not semantics.** Verify required sections,
   fields, and patterns exist. Do not evaluate whether detection
   rules are good — that's eval-runner's job.
2. **Deterministic checks only.** Every check should be reproducible:
   does the field exist? Is the format correct? Does the section
   match the expected pattern?
3. **When `--fix` is used, apply minimal structural fixes.** Insert
   missing sections/fields using templates. Do not rewrite existing
   content.
4. **Be concise.** Output the report table and action items. No
   preambles, no per-file narration, no restating what was checked.

## Steps

### 1. Parse arguments

Arguments: $ARGUMENTS

- No argument or `--all`: audit everything
- A specific file path (e.g., `.claude/agents/js-fp-review.md`): audit that
  file only
- `--fix`: after generating the report, automatically apply fixes
  for FAIL/WARN items

### 2. Audit agents

Read each file in `.claude/agents/*.md` that declares `Model tier:` (these are
review agents). Check:

1. **Structured output format**: Does the agent specify a JSON output
   schema?
   - Review agents MUST include `status`, `issues`, and `summary`
     fields
   - FAIL if a review agent has no output format

2. **Severity definitions**: Does the agent define severity levels?
   - MUST define `error`, `warning`, and `suggestion` with clear
     criteria
   - FAIL if severity levels are missing

3. **Detection rules**: Does the agent list what it detects?
   - MUST have a section listing specific patterns/issues to flag
   - WARN if detection rules are vague or missing

4. **Scope boundaries**: Does the agent declare what it ignores?
   - Review agents SHOULD state what other agents handle
   - WARN if missing (helps avoid duplicate findings)

5. **Self-describing**: Does the agent depend on external config?
   - Agents MUST NOT reference `config/`, `review-config.json`, or
     external config files
   - Thresholds, file scope, and defaults MUST be declared inline
     in the agent definition
   - FAIL if an agent references external config

6. **File scope**: Does the agent declare which file types it
   applies to?
   - Language-specific agents (e.g., js-fp-review) MUST declare
     their file scope
   - Language-agnostic agents (e.g., structure-review) may omit this
   - WARN if a language-specific agent has no file scope declaration

7. **Skip support**: Does the agent define when to return
   `status: "skip"`?
   - All review agents MUST have a `## Skip` section
   - MUST describe conditions when the agent is inapplicable
   - MUST show the skip JSON response format
   - WARN if skip section is missing

8. **Model tier**: Does the agent declare
   `Model tier: small|mid|frontier`?
   - All agents MUST declare which model tier they require
   - Valid values: `small`, `mid`, `frontier`
   - WARN if missing

9. **Context needs**: Does the agent declare
   `Context needs: diff-only|full-file|project-structure`?
   - All agents MUST declare what input context they need
   - Valid values: `diff-only`, `full-file`, `project-structure`
   - WARN if missing

### 3. Audit skills

Read each file in `.claude/commands/*.md` and check:

1. **Role declaration**: Does the skill declare its role?
   - All skills MUST have a `Role:` line (orchestrator, worker, or
     implementation)
   - Orchestrators route work and aggregate results — they must not
     review or modify code
   - Workers perform semantic analysis using agent definitions
   - Implementation skills modify code following correction prompts
   - WARN if role is missing

2. **Constraints section**: Does the skill declare its boundaries?
   - All skills SHOULD have a constraints section matching their role
   - Orchestrators: must not review code, must delegate, must
     minimize context
   - Workers: must follow agent definition, must return structured
     JSON
   - Implementation: must apply minimal fixes, must validate after
     changes
   - WARN if constraints are missing

3. **Structured steps**: Does the skill have numbered steps?
   - All skills MUST have a clear sequence of steps
   - FAIL if steps are missing or unstructured

4. **Argument parsing**: Does the skill document its arguments?
   - Skills MUST document required and optional arguments
   - WARN if argument section is missing

5. **Output format**: Does the skill describe its output?
   - Skills that produce reports MUST define their output format
   - WARN if output format is missing

6. **Conciseness directive**: Does the skill instruct concise output?
   - All skills MUST include a "Be concise" constraint to minimize
     output tokens
   - WARN if missing

7. **Validation gates**: Does the skill run validation where
   appropriate?
   - Skills that modify code (apply-fixes) SHOULD run
     lint/build/tests
   - WARN if a code-modifying skill has no validation step

### 4. Audit hooks

Read each file in `.claude/hooks/*.sh` and check:

1. **Advisory behavior**: Does the hook exit 0?
   - Hooks MUST be advisory only (exit 0), never blocking
   - FAIL if a hook exits non-zero on warnings

2. **Input handling**: Does the hook read stdin and extract file
   path?
   - Hooks MUST handle the PostToolUse input format
   - WARN if input parsing looks incorrect

3. **Scope filtering**: Does the hook filter by file type?
   - Hooks SHOULD only run on relevant file types
   - WARN if no file type filter is present

### 5. Generate report

```text
# Eval Audit Report

## Agents
| Agent | Output Format | Severity | Detection | Scope | Self-Describing | File Scope | Skip | Model Tier | Context Needs | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test-review | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | OK |
| js-fp-review | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | OK |
| ... | | | | | | | | | | |

## Skills
| Skill | Role | Constraints | Steps | Arguments | Output | Validation | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| code-review | PASS | PASS | PASS | PASS | PASS | N/A | OK |
| apply-fixes | PASS | PASS | PASS | PASS | PASS | PASS | OK |
| ... | | | | | | | |

## Hooks
| Hook | Advisory | Input | Scope Filter | Status |
| --- | --- | --- | --- | --- |
| js-fp-review.sh | PASS | PASS | PASS | OK |
| token-efficiency-review.sh | PASS | PASS | PASS | OK |
| ... | | | | |

## Summary
- Agents: N OK, N WARN, N FAIL
- Skills: N OK, N WARN, N FAIL
- Hooks: N OK, N WARN, N FAIL
- Action items: [list of things to fix]
```

### 6. Apply fixes (when `--fix` is passed)

If `--fix` was NOT passed, list action items and stop.

If `--fix` WAS passed, automatically apply fixes for each FAIL/WARN
item:

**Agent fixes:**

- Missing output format → insert after the `# <Agent Name>` heading:

  ```text
  Output JSON:
  \```json
  {"status": "pass|warn|fail|skip", "issues": [...], "summary": ""}
  \```
  ```

- Missing severity definitions → insert after the output format:

  ```text
  Severity: error=<agent-specific>, warning=<agent-specific>, suggestion=<agent-specific>
  ```

- Missing skip support → insert a `## Skip` section before
  `## Detect`:

  ```text
  ## Skip

  Return `{"status": "skip", "issues": [], "summary": "<reason>"}` when:
  - <agent-specific inapplicability conditions>
  ```

- Missing scope boundaries → append `## Ignore` section at the end

**Skill fixes:**

- Missing numbered steps → restructure existing content under
  `## Steps` with `### 1.`, `### 2.`, etc.
- Missing argument section → insert `## Parse Arguments` section
  after the skill heading

**After each fix:**

1. Read the file to confirm the fix was applied
2. Re-run the specific check to verify it now passes
3. Report: `FIXED: <agent/skill> — <what was fixed>`

### 7. Fix summary

If `--fix` was used, append a fix summary after the audit report:

```text
## Fixes Applied
- FIXED: <name> — Added output format
- FIXED: <name> — Added skip section
- SKIPPED: <name> — <reason fix could not be auto-applied>

Re-run /eval-audit to verify all fixes.
```
