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
output schema — either inline (a line with `"status": "pass|warn|fail|skip"`)
or a citation of `knowledge/review-agent-output-contract.md` — these are
review agents. Check:

1. **Structured output format**: Does the agent specify a JSON output
   schema, inline or by citing the shared contract?
   - Review agents MUST include `status`, `issues`, and `summary`
     fields (inline or via the cited contract)
   - FAIL if a review agent has no output format and no contract citation

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

8. **Model/effort contract**: Does the agent's frontmatter conform to the
   native Claude Code sub-agent contract (ADR 0026)?
   - Run `python3 scripts/validate_agent_contract.py <file>` and fold every
     `error` into FAIL and every `warning` into WARN in the report. This is
     the sole frontmatter-contract check — required-field presence (`name`,
     `description`), `name` pattern, enum membership on any field present
     (`model`, `effort`, `permissionMode`, `memory`, `isolation`, `color`,
     `background`, `maxTurns`), unknown/misspelled-key warnings, and the
     plugin-ignored-field warning for `hooks`/`mcpServers`/`permissionMode`.
   - **This repo's own convention**: every `plugins/dev-team/` and
     `plugins/security-assessment/` agent declares `model:` (an alias, full
     model ID, or `inherit`) and `effort: high` — WARN if either is missing,
     since that is this repo's local practice, not a contract requirement.
   - **Single source**: `model:`/`effort:` MUST be declared only in
     frontmatter. WARN if a body line restates either as prose (e.g. an
     `Effort:` line, or a body-level model-tier label) — that duplicate is a
     drift source and must be removed.
   - **Carve-out — `Verify-model:` / `Verify-effort:` (#1628)**: these two
     body declarations are NOT a restatement of `model:`/`effort:` and must
     never be flagged by the single-source rule above. They name a *different*
     tier — the one used for fix-verification re-dispatches only — and they
     live in the body for the same reason `Scope:` and `Cites:` do (#1333:
     frontmatter is reserved for the official contract; these are not part
     of it). Validate them with:

     ```bash
     python3 scripts/verify_tier.py --all
     ```

     Fold a non-empty `errors` array into WARN, naming the agent and the
     invalid value. An agent with no declaration is correct, not incomplete —
     the default is deliberately "same tier as discovery". Contract:
     `knowledge/verification-mode.md`.

9. **Context needs**: Does the agent declare a `Context needs:` field?
   - All agents MUST declare what input context they need
   - Valid standalone values:
     - `diff-only` — agent reads only the unified diff
     - `full-file` — agent needs the complete file content
     - `project-structure` — agent needs directory/project layout
     - `artifact-stream` — agent consumes upstream JSON artifact streams
       (prior-phase findings, RECON output) and does **not** read source
       files directly; qualifies when the agent's only input is an artifact
       produced by an earlier pipeline phase
   - **Combinability**: a comma-separated list of two or more values is
     valid when every token is one of the four values above (e.g.
     `artifact-stream, full-file` is valid for an agent that reads both
     upstream artifacts **and** full source files). An unknown token in a
     combined declaration still WARNs on that token specifically.
   - WARN if the field is missing entirely
   - WARN if the declaration contains an unrecognised token

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

2. **Code-intelligence MCP invariant (review agents)**: Every read-only `*-review` agent MUST grant the five code-intelligence MCP tools in `tools:` — `mcp__codegraph__codegraph_explore` and `mcp__plugin_repowise_repowise__{get_context,get_symbol,search_codebase,get_risk}` — so a review on a repo with a CodeGraph/Repowise index uses verified skeletons and resolved call graphs instead of raw whole-file reads (the grant is inert when the server is absent; agents fall back to Read/Grep/Glob). This mirrors the Skills-Skill invariant: it self-extends to future `*-review` agents.
   - FAIL if any `*-review` agent's `tools:` line is missing one or more of the five names.
   - PASS if every `*-review` agent grants all five.
   - Also checks that [`code-review/SKILL.md`](../code-review/SKILL.md) still contains the code-intelligence phrases (the five tool names and `.codegraph/`) as a proxy for the detection/preference guidance — it asserts the phrases are present, not the instruction wording itself.

3. **Code-intelligence mapping invariant (non-review team agents)**: Every non-review team agent in the #1108 mapping MUST grant its **tier's** tools in `tools:` — the **narrow** tier (`software-engineer`, `mutation-kill`, `qa-engineer`, `data-flow-tracer`) grants codegraph + the four Repowise tools, with `data-flow-tracer` also carrying a scoped `Bash(graphify *)`; the **rationale** tier (`adr-author`, `architect`, `security-engineer`, `platform-engineer`, `codebase-recon`) additionally grants `mcp__plugin_repowise_repowise__get_why`. Coverage is the union of the mapping's config keys and a structural sweep (team agents by `## Behavioral Guidelines` **or** `Enforcement: script`, minus `*-review`, minus a documented exclusion list), so a new team agent that is neither mapped nor excluded fails rather than silently escaping the mapping. This is the non-review counterpart to invariant 2: review agents keep their five-tool set there; this check never evaluates `*-review` agents.
   - FAIL if a mapped agent's `tools:` line is missing any of its tier's names, or a swept team agent is in neither the mapping nor the exclusion list (unclassified).
   - PASS if every mapped agent grants its tier's tools and every swept agent is mapped or excluded.

4. **Code-intelligence grant invariant (security-assessment plugin, issue #1388)**: Invariants 2 and 3 above cover `plugins/dev-team/agents/` only. Every agent in `CODE_READING_AGENTS` (`authorization-logic-review`, `business-logic-domain-review`, `compliance-edge-annotator`, `cross-repo-synthesizer`, `deep-code-reasoning`, `fp-reduction`, `recon-driven-scan`, `tool-finding-narrative-annotator`) MUST grant the same five-tool `BASE_MCP_TOOLS` set in `tools:`. The remaining 5 synthesis-only `plugins/security-assessment/agents/*.md` files (`redteam-report-generator`, `exec-report-generator`, `redteam-recon-analyzer`, `redteam-evasion-analyzer`, `redteam-extraction-analyzer`) interpret a fixed set of upstream probe/report artifacts and produce narrative output rather than reasoning about arbitrary target-repo code, and are excluded — the grant would be inert for them (this is a fixed classification, not a `Glob`-presence heuristic: `exec-report-generator` carries `Glob` for its own artifact-directory walk yet is still excluded).
   - FAIL if a code-reading agent's `tools:` line is missing one or more of the five names, or an agent on disk is in neither roster (unclassified).
   - PASS if every code-reading agent grants all five and every agent on disk is classified.

**Mechanics for invariants 2–4**: all three delegate to `scripts/lib/mcp_tool_grants.py`'s shared `run_grants_check` (single read+parse pass per agent, both for detection and `--fix`) and, under `--json`, report the same envelope (`check`/`evaluated`/`offenders`/`unclassified`/`fixed`/`unfixable`/`ok`/`notes`) so results are comparable across the three checks.

| Invariant | Report column | Delegated script | Config source of truth | Unclassified handling |
|---|---|---|---|---|
| 2. Code-intelligence (review agents) | `Code-Intel` | `scripts/check_review_agent_mcp_tools.py` | `MCP_TOOL_NAMES` | n/a — glob-discovered, no roster |
| 3. Code-intelligence mapping (non-review) | `Mapping` | `scripts/check_agent_tool_mapping.py` | `TIER_CONFIG` / `EXCLUSIONS` | reported, not auto-fixed |
| 4. Code-intelligence (security-assessment) | `SA-MCP` | `plugins/dev-team/scripts/check_security_assessment_mcp_tools.py` | `CODE_READING_AGENTS` / `NON_CODE_READING_AGENTS` | reported, not auto-fixed |

Include each invariant's result in the agent report table under its column above. Invariant 4 is additionally wired into `scripts/ci-local.sh` as `chk_sa_mcp_tools`, so drift fails CI, not just this manual audit pass.

**Fix (when `--fix` is passed)**: run the delegated script above with `--fix` — it appends its missing tool names to `tools:` (merge, never replacing existing grants such as `Read, Grep, Glob`/`Skill`). Unclassified agents, where applicable, are reported, not auto-fixed — classify each into the config or exclusion list named above. Report `FIXED: <agent> — added <tool names>`.

### 2c. Audit team agent personas

A file is a **team agent** when its body contains a `## Behavioral Guidelines` section. **Exemption**: an agent that declares `Enforcement: script` in its body is a script-enforced **prose spec**, not a persona-driven team agent — skip the persona checks below for it and instead verify it carries a `> **Implemented by:** <script>` pointer immediately after the H1. For each remaining team agent, check:

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
declares its sources in a body-level `Cites:` list (not frontmatter — `cites`
is not part of the official sub-agent contract), and every numeric threshold
the agent states on an RFC-2119 line (MUST/SHOULD/SHALL/REQUIRED/NEVER/ALWAYS)
must also appear in a cited source.

Perform the check by reading (the same mechanical, deterministic style as the
other audits — no judgment):

1. Read each agent's body and look for a `Cites:` list. Each entry names
   a skill (`skills/<name>/SKILL.md`) or knowledge file (`knowledge/<name>.md`).
2. In the agent body, find every line carrying an RFC-2119 keyword
   (MUST/MUST NOT/SHOULD/SHALL/REQUIRED/NEVER/ALWAYS). Ignore lines inside code
   fences (```` ``` ````/`~~~`) and blockquotes (`>`). On each such line, collect
   the **numeric thresholds** (`50`, `80%`, `40.5`); ignore issue refs like `#99`.
3. Read each cited source and check the threshold appears in it.

Classify:

- `Cites:` present and every threshold backed → PASS in the Citation column.
- `Cites:` present but a threshold absent from every cited source → WARN
  (possible drift): report the token + line number.
- no `Cites:` but the agent states thresholds → WARN (advisory): recommend
  adding a `Cites:` list.
- no `Cites:` and no thresholds → PASS (nothing to verify).
- `Cites:` an unknown source (no matching skill/knowledge file) → WARN.

**Phase 1 is non-blocking** — these are warnings, never failures. Do not
red-line the audit on a citation warning; surface it as an action item so drift
is visible while `Cites:` adoption grows. CI runs the deterministic counterpart,
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

### 2e-bis. Knowledge-reference integrity (preventive)

Agents read shared guidance from `knowledge/*.md`. Two ways this silently
breaks (issue #1103): the file is renamed/removed but a reference lingers, or
the reference uses a bare `knowledge/X.md` path that resolves against the
*target repo's* cwd at runtime — not the plugin dir — so the agent reads
nothing and degrades to hardcoded fallbacks.

Run the deterministic sensor:

```
python3 -m pytest tests/agents/test_agent_knowledge_anchor.py
```

It hard-gates three invariants on every `knowledge/X.md` reference in an
agent body: it cites a valid `index.json` anchor or carries `Whole-file
load:`; the file is packaged on disk; and it is prefixed with
`${CLAUDE_PLUGIN_ROOT}/` (the only runtime-resolvable form — a prose "lives
in `plugins/dev-team/knowledge/...`" pointer is tolerated). Runs on every PR.

### 2f. CLAUDE.md and token-efficiency structural checks

Two deterministic Python scripts validate concerns that the LLM-based review
agents (`claude-setup-review` and `token-efficiency-review`) handle as deeper
semantic checks. Run these scripts for a fast, CI-safe structural pass:

**CLAUDE.md / setup review** (frontmatter schema, field completeness, effort
bands, duplicate rules):

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/claude_setup_review.py --plugin-root <plugin-root-path>
```

**Token-efficiency review** (file line counts, CLAUDE.md size, LLM
anti-patterns):

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/token_efficiency_review.py --files <path>...
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
| naming-review | no | states 1 threshold, no Cites: | WARN |
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
  Output JSON: per `${CLAUDE_PLUGIN_ROOT}/knowledge/review-agent-output-contract.md` (Whole-file load: short, canonical schema).
  ```

  Prefer this citation form over inlining the schema — see
  `knowledge/review-agent-output-contract.md` for the canonical shape and
  its documented per-agent extensions/status exceptions.

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
