---
name: agent-audit
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

# Agent Audit

Role: orchestrator. This skill performs mechanical compliance
checks — pattern matching against known-good structure.

You have been invoked with the `/agent-audit` skill. Audit agents and
skills for compliance with the eval system patterns documented in
`.claude/docs/eval-system.md`.

## Orchestrator constraints

1. **Check structure, not semantics.** Verify required sections,
   fields, and patterns exist. Do not evaluate whether detection
   rules are good — that's agent-eval's job.
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

**Scope**: this audit covers agents from all plugins in the repository, not just
`plugins/dev-team/agents/`. Currently audited directories:

- `plugins/dev-team/agents/` — the primary dev-team plugin agents
- `plugins/security-assessment/agents/` — the security-assessment plugin agents

The automated effort-band gate (`tests/agents/test_agent_effort_frontmatter.py`)
discovers and checks agents from both directories; add new plugin agent directories
to `AGENTS_DIRS` in that test file when a new plugin is introduced.

Read each file in `.claude/agents/*.md` whose body contains a structured JSON
output schema (a line with `"status": "pass|warn|fail|skip"`) — these are
review agents. Check:

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

8. **Effort band**: Does the agent declare `effort: low|medium|high` in
   its YAML frontmatter?
   - All agents MUST declare the reasoning-effort band their task needs
   - Valid values: `low`, `medium`, `high`
   - WARN if missing or outside the valid set
   - **Single source**: the band MUST be declared only in frontmatter — it is
     the only value the resolver reads. WARN if a body `Effort:` line (or other
     prose) restates the band; that duplicate is a drift source and must be
     removed.
   - **Deprecation (warn, never error this release)**: if the agent still
     declares a legacy `model: haiku|sonnet|opus` tier in frontmatter, WARN
     that the tier name is deprecated and name the band to use
     (`haiku` → `low`, `sonnet` → `medium`, `opus` → `high`)

9. **Context needs**: Does the agent declare
   `Context needs: diff-only|full-file|project-structure`?
   - All agents MUST declare what input context they need
   - Valid values: `diff-only`, `full-file`, `project-structure`
   - WARN if missing

10. **No colons in description**: Does the `description:` frontmatter field contain a colon?
    - The `description` field MUST NOT contain colons — they break argument-hints and other tooling
    - FAIL if the description value contains a colon character (`:`)

### 2b. Audit agent tool declarations (all agents)

Read every file in `.claude/agents/*.md` (team agents and review agents). Check:

1. **Skills-Skill invariant**: If the agent body contains a `## Skills` heading, the `tools:` frontmatter MUST include `Skill`.
   - The `## Skills` section documents which skills an agent invokes. Without `Skill` in `tools:`, the agent cannot load skill content at runtime (when `tools:` is specified as an allowlist, only listed tools are available).
   - FAIL if a `## Skills` section is present but `Skill` is absent from `tools:`.
   - PASS if no `## Skills` section is present (the invariant does not apply).
   - PASS if `## Skills` is present and `Skill` is in `tools:`.

Include the result in the agent report table under a `Skills-Tool` column.

**Fix (when `--fix` is passed)**: Append `, Skill` to the `tools:` frontmatter line. Report `FIXED: <agent> — Added Skill to tools:`.

### 2c. Audit team agent personas

A file is a **team agent** when its body contains a `## Behavioral Guidelines` section. **Exemption**: an agent that declares `enforcement: script` in its frontmatter is a script-enforced **prose spec**, not a persona-driven team agent — skip the persona checks below for it and instead verify it carries a `> **Implemented by:** <script>` pointer immediately after the H1. For each remaining team agent, check:

1. **Persona paragraph**: Is there a `You are…` sentence immediately after the H1 heading and before the first `##` section?
   - The line must begin with `You are` (case-sensitive).
   - FAIL if the first non-blank line after the H1 is a `##` heading instead of a persona paragraph.
   - PASS if a `You are …` paragraph is present between the H1 and the first `##`.

2. **Non-generic Output discipline**: Does the `## Output discipline` section exist and contain role-specific content?
   - FAIL if the `## Output discipline` section is absent entirely.
   - WARN if the first bullet still contains the old generic phrase `"plans, designs, ADRs, reports"` — this indicates the shared boilerplate was never personalised.
   - PASS if the section is present and does not match the generic boilerplate.

Include both results in the agent report table under `Persona` and `Output-Disc` columns.

**Fix (when `--fix` is passed)**:

- Missing persona paragraph: insert a placeholder `You are a <role>. <Add identity, worldview, communication style.>` after the H1. Report `FIXED: <agent> — Added persona placeholder (requires manual completion)`.
- Missing `## Output discipline`: insert the section with a placeholder bullet. Report `FIXED: <agent> — Added Output discipline placeholder (requires manual completion)`.
- Generic boilerplate detected: emit `WARN: <agent> — Output discipline still contains generic boilerplate; manual update required` (no auto-fix — content must be role-specific).

### 2d. Citation drift lint (preventive)

Reviewer agents sometimes inline normative rules — numeric thresholds like
"under 50 lines" or "80% coverage" — independently of the canonical skill or
knowledge file. When that source changes, the agent silently keeps enforcing
the stale value. The citation lint makes the dependency explicit: an agent
declares its sources in a `cites:` frontmatter list, and every numeric threshold
the agent states on an RFC-2119 line (MUST/SHOULD/SHALL/REQUIRED/NEVER/ALWAYS)
must also appear in a cited source.

Perform the check by reading (the same mechanical, deterministic style as the
other audits — no judgment):

1. Read each agent's frontmatter and look for a `cites:` list. Each entry names
   a skill (`skills/<name>/SKILL.md`) or knowledge file (`knowledge/<name>.md`).
2. In the agent body, find every line carrying an RFC-2119 keyword
   (MUST/MUST NOT/SHOULD/SHALL/REQUIRED/NEVER/ALWAYS). Ignore lines inside code
   fences (```` ``` ````/`~~~`) and blockquotes (`>`). On each such line, collect
   the **numeric thresholds** (`50`, `80%`, `40.5`); ignore issue refs like `#99`.
3. Read each cited source and check the threshold appears in it.

Classify:

- `cites:` present and every threshold backed → PASS in the Citation column.
- `cites:` present but a threshold absent from every cited source → WARN
  (possible drift): report the token + line number.
- no `cites:` but the agent states thresholds → WARN (advisory): recommend
  adding a `cites:` list.
- no `cites:` and no thresholds → PASS (nothing to verify).
- `cites:` an unknown source (no matching skill/knowledge file) → WARN.

**Phase 1 is non-blocking** — these are warnings, never failures. Do not
red-line the audit on a citation warning; surface it as an action item so drift
is visible while `cites:` adoption grows. CI runs the deterministic counterpart,
`scripts/citation_lint.py` (also advisory, exit 0), on every PR.

### 2e. Registry completeness (preventive)

The catalog tables (`knowledge/agent-registry.md` for agents and agent-loaded
skills; the plugin `CLAUDE.md` slash-command table for user-invocable skills) are
hand-maintained. When an agent or skill is added or removed without updating the
matching table, the catalog drifts and the orchestrator routes against a roster
that no longer matches the filesystem.

Run the deterministic sensor:

```
python3 scripts/check_registry_sync.py
```

It asserts a bijection between `plugins/dev-team/agents/*.md` +
`plugins/dev-team/skills/*/SKILL.md` and the registry rows, reporting `MISSING`
(file with no row) and `ORPHAN` (row with no file). Unlike the citation lint this
is a **hard gate** — exit 1 on any discrepancy. Fix it by adding or removing the
catalog row by hand (the `marketplace-dev` plugin's `/agent-create` /
`/agent-remove` maintain these tables automatically).
Effort bands are deliberately not checked — they live only in frontmatter. The
pytest suite `tests/repo/test_registry_sync.py` runs this on every PR.

### 2f. CLAUDE.md and token-efficiency structural checks

Two deterministic Python scripts validate concerns that the LLM-based review
agents (`claude-setup-review` and `token-efficiency-review`) handle as deeper
semantic checks. Run these scripts for a fast, CI-safe structural pass:

**CLAUDE.md / setup review** (frontmatter schema, field completeness, effort
bands, duplicate rules):

```
python3 scripts/claude_setup_review.py --plugin-root <plugin-root-path>
```

**Token-efficiency review** (file line counts, CLAUDE.md size, LLM
anti-patterns):

```
python3 scripts/token_efficiency_review.py --files <path>...
```

Both scripts exit 0 and emit JSON findings to stdout. Surface any `error`
or `warning` severity findings as FAIL/WARN rows in the audit report table.
The scripts are the authoritative structural gate — do **not** dispatch the
`claude-setup-review` or `token-efficiency-review` agents from this skill;
those agents run under `/code-review` for semantic depth.

### 3. Audit skills

Read each file in `.claude/skills/*.md` and `.claude/skills/*/SKILL.md` and check:

1. **Role declaration**: Does the skill declare its role?
   - **User-invocable skills** (`user-invocable: true` — slash commands and
     workflow initiators) MUST have an explicit `Role:` line in the SKILL.md
     **body**, immediately after the H1 (matching `/plan`, `/build`,
     `/code-review`, `/pr`, `/ship`): `Role: orchestrator`, `Role: worker`, or
     `Role: implementation`. A frontmatter-only `role:` field (lowercase key)
     does NOT satisfy this — it's easy to add without stating the
     orchestration-discipline contract the body line carries. WARN if a
     user-invocable skill has no body `Role:` line.
   - **Agent-loaded, non-user-invocable knowledge skills** (no
     `user-invocable: true`) are exempt from the body-line requirement — a
     frontmatter `role:` field, or no role at all for pure reference
     material, is acceptable. WARN only if such a skill has no role
     declared anywhere (frontmatter or body).
   - Orchestrators route work and aggregate results — they must not
     review or modify code
   - Workers perform semantic analysis using agent definitions
   - Implementation skills modify code following correction prompts

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

8. **No colons in description**: Does the `description:` frontmatter field contain a colon?
   - The `description` field MUST NOT contain colons — they break argument-hints and other tooling
   - FAIL if the description value contains a colon character (`:`)

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
# Agent Audit Report

## Agents
| Agent | Output Format | Severity | Detection | Scope | Self-Describing | File Scope | Skip | Model Tier | Context Needs | Skills-Tool | No-Colon Desc | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test-review | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | PASS | PASS | PASS | OK |
| js-fp-review | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | N/A | PASS | OK |
| ... | | | | | | | | | | |

## Skills
| Skill | Role | Constraints | Steps | Arguments | Output | Validation | No-Colon Desc | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| code-review | PASS | PASS | PASS | PASS | PASS | N/A | PASS | OK |
| apply-fixes | PASS | PASS | PASS | PASS | PASS | PASS | PASS | OK |
| ... | | | | | | | |

## Hooks
| Hook | Advisory | Input | Scope Filter | Status |
| --- | --- | --- | --- | --- |
| js-fp-review.sh | PASS | PASS | PASS | OK |
| token-efficiency-review.sh | PASS | PASS | PASS | OK |
| ... | | | | |

## Citation drift (Phase 1 — advisory)
| Agent | cites | Drift / Advisory | Status |
| --- | --- | --- | --- |
| complexity-review | yes | — | PASS |
| naming-review | no | states 1 threshold, no cites: | WARN |
| ... | | | |

## Summary
- Agents: N OK, N WARN, N FAIL
- Skills: N OK, N WARN, N FAIL
- Hooks: N OK, N WARN, N FAIL
- Citation drift: N PASS, N WARN (advisory, non-blocking)
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
- Colon in `description` → rewrite the description value to remove colons (use "–" or "and" instead)

**Skill fixes:**

- Missing numbered steps → restructure existing content under
  `## Steps` with `### 1.`, `### 2.`, etc.
- Missing argument section → insert `## Parse Arguments` section
  after the skill heading
- Colon in `description` → rewrite the description value to remove colons (use "–" or "and" instead)

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

Re-run /agent-audit to verify all fixes.
```
