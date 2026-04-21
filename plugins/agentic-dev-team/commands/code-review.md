---
name: code-review
description: >-
  Run all enabled review agents against target files. Use this whenever the
  user asks for a code review, wants feedback on their code, says "review my
  code", "check this before I PR", "what's wrong with this", "run the
  agents", or has just finished implementing a feature. Use proactively
  before commits and pull requests.
argument-hint: >-
  [--agent <name>] [--since <ref>] [--path <dir>] [--all]
  [--json] [--force]
user-invocable: true
allowed-tools: >-
  Read, Edit, Grep, Glob, AskUserQuestion,
  Bash(git diff *), Bash(npx *), Bash(npm run *),
  Bash(pnpm *), Bash(yarn *), Bash(tsc *), Bash(eslint *),
  Bash(git log *), Bash(gh run *), Bash(semgrep *),
  Bash(pylint *), Skill(review-agent *)
---

# Code Review

Role: orchestrator. This skill routes work — it does not review code
itself.

You have been invoked with the `/code-review` skill. Run all enabled
review agents and produce a summary.

This command is executed under orchestrator direction. Model selection
follows the Orchestrator Model Routing Table in `.claude/agents/orchestrator.md`.

For output format details, see [output-format.md](code-review/output-format.md).
For an example report, see
[examples/sample-report.md](code-review/examples/sample-report.md).

## Orchestrator constraints

Follow these constraints from the
[Minimum CD agent configuration](https://migration.minimumcd.org/docs/agentic-cd/agent-configuration/)
pattern:

1. **Do not review code yourself.** Delegate all semantic analysis to
   review agents.
2. **Minimize context passed to agents.** Each agent receives only
   what its `Context needs` field requires.
3. **Route to the right model tier.** Consult the Orchestrator Model
   Routing Table for model assignment. Each agent's `Model tier` field
   is a hint — the orchestrator's table is authoritative.
4. **Run deterministic gates first.** Standard tooling (lint,
   type-check, secret scan) is cheaper than AI review. Do not invoke
   agents if gates fail.
5. **Return structured results.** Aggregate agent JSON into a
   summary — do not add your own findings.
6. **Be concise.** Use tables, JSON, and short sentences. No
   preambles, no filler, no restating the task. Every output token
   costs money.

## Parse Arguments

Arguments: $ARGUMENTS

- `--agent <name>`: Run only the named agent (delegates to
  `/review-agent`)
- `--since <ref>`: Review files changed since a git ref
  (`git diff --name-only <ref>...HEAD`)
- `--path <dir>`: Review only files in this directory
- `--all`: Force full-repository review even when uncommitted
  changes exist
- `--json`: Output aggregated JSON instead of prose summary (for CI
  integration)
- `--init-risks`: Scaffold `ACCEPTED-RISKS.md` at the repo root from
  `templates/ACCEPTED-RISKS.md.tmpl` if the file is absent. Exits
  non-zero without overwriting if the file already exists. See
  `knowledge/accepted-risks-schema.md` for the rule schema and
  matching semantics.
- `--force`: Skip pre-flight gates and run agents even if
  deterministic checks fail. **Requires `--reason "<text>"`** — the
  justification is logged to `metrics/override-audit.jsonl`.
- `--reason "<text>"`: Override justification (required with
  `--force`, ignored otherwise)
- `--static-analysis`: Run a static analysis pre-pass (Semgrep,
  ESLint, TypeScript compiler, pylint) before dispatching AI review
  agents. Findings are passed to agents as pre-confirmed context so
  they focus on semantic concerns. Auto-enabled when tools are
  detected unless `--no-static-analysis` is passed.
- `--no-static-analysis`: Skip the static analysis pre-pass even
  when tools are available.
- `--background`: Drift review mode — review the default branch for
  accumulated documentation, naming, and structural drift without
  requiring changed files. Runs doc-review, arch-review,
  naming-review, and structure-review only. Does not run pre-flight
  gates. Intended for scheduled or periodic invocation.
- No arguments: **auto-scope** — review uncommitted changes if any
  exist, otherwise review the full repository (see step 1)

## Progress tracking

Copy this checklist and track progress:

```text
- [ ] Target files determined
- [ ] Pre-flight gates passed
- [ ] Static analysis pre-pass (if enabled)
- [ ] Agents loaded and filtered
- [ ] All agents executed
- [ ] Results aggregated
- [ ] User asked: fix or report only?
- [ ] Review-fix loop (if user chose fix, up to 5 iterations)
  - [ ] Fixes applied
  - [ ] Failed agents re-run
  - [ ] Re-aggregated
- [ ] Report generated
- [ ] Correction prompts saved for remaining issues
- [ ] Pre-commit gate file written (if auto-scoped to uncommitted changes)
```

## Steps

### 1. Determine target files

Build the file list using this priority order:

1. **Explicit path** (`--path <dir>`): Review only files in this
   directory (exclude node_modules, .git, dist, build, coverage)
2. **Explicit ref** (`--since <ref>`): Review files changed since
   that ref (`git diff --name-only <ref>...HEAD`)
3. **Force full repo** (`--all`): Review all source files regardless
   of git status
4. **Auto-scope** (no flags): Detect uncommitted changes and decide:

**Auto-scope logic** (the default when no targeting flag is given):

```
Run: git diff --name-only && git diff --cached --name-only
Combine and deduplicate the results.

If the list is non-empty:
  → Review only those files (uncommitted changes)
  → Report: "Reviewing N uncommitted files."

If the list is empty (working tree is clean):
  → Review all source files in the repository
  → Report: "Working tree is clean. Reviewing full repository."
```

This means `/code-review` with no arguments always does the right
thing: it reviews what you've changed, or everything if there's
nothing pending.

**Scope validation**: After building the file list, if reviewing
the full repository (auto-scope clean or `--all`):

| File count | Action |
|------------|--------|
| ≤200 | Proceed normally |
| 201-500 | Warn: "Reviewing {N} files — consider `--path` to narrow scope." Proceed. |
| >500 | Warn: "Reviewing {N} files is expensive. Use `--path` to narrow scope. Continue anyway?" Wait for confirmation. |

### 1b. Check for institutional context

Check if `REVIEW-CONTEXT.md` exists in the project root.

If it exists, read its full contents. This file contains
**institutional knowledge** — domain context, related services, known
issues, team notes, or architectural history that agents cannot
discover from code alone.

If it does not exist, proceed without it. This file is optional.

When passing context to agents in step 4, include the contents
prefixed with: "Institutional context provided for this review:"

### 1c. Probe for optional MCP tools

Check for availability of enhanced analysis tools. These are
additive — all agents work without them.

| Tool | Check | Benefits |
|------|-------|----------|
| RoslynMCP | Try `get_code_metrics` or `search_symbols` | C# code metrics, compiler diagnostics, symbol analysis |
| Code knowledge graph | Try `list_repos` | Cross-repo dependency mapping, blast radius |
| Documentation MCP | Try wiki/docs search | Architecture docs, design decisions |
| Semgrep | `which semgrep` | SAST findings for security-review context |

Record which tools are available. Pass availability info to each
agent so they can use enhanced tools or fall back to Glob/Grep/Read.
Include tool availability in the final report (see
`knowledge/review-template.md`).

### 2. Pre-flight gates (fail fast, fail cheap)

If `--background` is passed, skip pre-flight gates entirely and jump
to step 3.

If `--force` is passed without `--reason`, halt immediately:
```
ERROR: --force requires --reason "<justification>". Override without
justification cannot be logged.
```

If `--force` is passed with `--reason`, log the override before
skipping gates:
```bash
# Append to metrics/override-audit.jsonl (create if missing)
{
  "timestamp": "<ISO 8601>",
  "branch": "<current branch>",
  "triggeredBy": "--force",
  "reason": "<value of --reason>",
  "targetFiles": ["<file list>"],
  "gatesSkipped": ["lint", "type-check", "secret-scan", "semgrep", "pipeline-red"]
}
```

Then skip the remaining pre-flight steps and proceed to step 3.

Run deterministic checks before spending tokens on AI agents. Skip
this step if `--force` is passed.

Sequence (stop on first failure unless `--force`):

1. **Lint**: Run `npx eslint` (or project lint command from
   package.json) on target files. If lint fails, report errors and
   stop.
2. **Type check**: Run `npx tsc --noEmit` if a `tsconfig.json`
   exists. If type errors exist, report and stop.
3. **Secret scan**: Grep target files for common secret patterns
   (`(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['"][^'"]{8,}`).
   If found, report and stop.
4. **Semgrep SAST**: Run
   `semgrep scan --config auto --quiet --json` on target files if
   `semgrep` is installed. ERROR-severity findings → gate fails
   (stop unless `--force`). WARNING-severity findings → include in
   report but don't stop. Skip silently if `semgrep` is not
   installed. Save findings to pass as context to security-review
   agent in step 4.
5. **Pipeline-red check**: Run `git log --oneline -1` and check if
   there's a failing CI status on the current branch (run
   `gh run list --branch $(git branch --show-current) --limit 1`
   `--json conclusion -q '.[0].conclusion'` if `gh` is available).
   If the last CI run failed, warn: "Pipeline is red — existing
   tests are failing. Fix CI before adding new code. Use `--force`
   to override."

If any gate fails and `--force` is not set, output the failure
details and stop. Do not run agents.

If a tool is not available (e.g., no eslint, no tsconfig, no gh),
skip that gate silently.

### 2b. Static analysis pre-pass

Skip this step if `--no-static-analysis` is passed or if `--background`
is set.

This step runs deterministic static analysis tools to collect
confirmed findings before AI agents run. Refer to
[static-analysis-integration.md](../skills/static-analysis-integration/SKILL.md)
for the full tool detection, execution, and deduplication procedure.

**When to run**:

- `--static-analysis` flag: always run
- No flag and no `--no-static-analysis`: auto-detect available tools.
  If at least one tool is available, run the pre-pass. If none are
  available, skip silently.

**Execution**:

1. Detect available tools: Semgrep (`which semgrep`), ESLint
   (`npx eslint --version` or ESLint config exists), TypeScript
   (`tsconfig.json` exists), pylint (`which pylint`).
2. Run each available tool against the target files determined in
   step 1. Filter target files by tool file type support (e.g.,
   ESLint only gets `.js`, `.ts`, `.jsx`, `.tsx` files).
3. Collect structured findings from each tool.
4. Deduplicate findings across tools (same file + line + semantic
   match). Keep the more specific tool's finding.
5. Store the aggregated result for injection into agent context in
   step 4.

**Relationship to pre-flight gates**: Pre-flight gates (step 2) are
fail-fast checks — they stop the pipeline on errors. The static
analysis pre-pass does **not** stop the pipeline. Its purpose is to
collect findings as context for agents, not to gate execution.
Findings from the pre-pass that overlap with pre-flight gate checks
(e.g., ESLint errors caught in both) are naturally deduplicated — the
gate catches hard failures, the pre-pass provides detailed context.

**Note on Semgrep**: If Semgrep ran in the pre-flight gate (step 2,
gate 4) and findings were already collected, reuse those findings
here instead of running Semgrep again. Do not invoke Semgrep twice.

### 3. Determine enabled agents

If `--background` is passed, run only: doc-review, arch-review,
naming-review, structure-review. Skip all other agents for this mode.

Otherwise, list all agent files in `.claude/agents/*.md`. All review
agents are enabled by default. Review agents are identified by
declaring `Model tier:` in their body.

**Language-agnostic agents must always run.** The following agents are
not scoped to a specific programming language and must be included
regardless of the project's tech stack:

- `doc-review` — checks README, API docs, inline comments, and ADR
  alignment
- `arch-review` — checks layer boundaries, dependency direction, and
  pattern consistency
- `claude-setup-review` — checks CLAUDE.md completeness and accuracy
- `token-efficiency-review` — checks CLAUDE.md and rule verbosity

Do not skip these agents based on file extension filtering. They
operate on project structure and documentation, not source code syntax.

If a `review-config.json` exists in the project root, read it. It
can disable specific agents (`"enabled": false`). This file is
optional and project-local — it is not part of the toolkit.

### 4. Run each enabled agent

For each enabled agent, spawn it as a parallel subagent using the
Agent tool. Each agent runs in isolation against its matching files.

**File scope**: Each agent definition declares its own file scope
(e.g., js-fp-review says "JavaScript and TypeScript files only").
Respect these scope declarations — only pass matching files, and
skip the agent entirely if no target files match.

**Context needs**: Each agent declares a `Context needs` field.
When reviewing uncommitted changes (auto-scope or `--since`):

- `diff-only`: Pass only the diff output, not full files. More
  token-efficient.
- `full-file`: Pass full file contents for files in the target list.
- `project-structure`: Pass full files plus directory tree context.

When reviewing the full repository (clean working tree, `--all`,
or `--path`), always pass full files
regardless of context needs.

**Model assignment**: Consult the Orchestrator Model Routing Table in
`.claude/agents/orchestrator.md`. Pass the assigned model explicitly
when spawning each subagent via the Agent tool. The agent's own
`Model tier` field serves as a fallback if not running under
orchestrator direction.

**Static analysis context**: If the static analysis pre-pass (step 2b)
produced findings, inject them into **every** review agent's prompt
using the agent context injection format defined in
`skills/static-analysis-integration/SKILL.md`. This tells agents:
"These issues were detected by static analysis tools. Do not re-report
them. Focus on semantic and architectural concerns."

If only Semgrep findings were collected (from the pre-flight gate,
without a full pre-pass), pass those to the security-review agent as
before, plus any other agents whose domain overlaps (e.g.,
performance-review for resource issues, concurrency-review for
thread-safety findings).

**Parallelism**: Launch all agents concurrently using multiple Agent
tool calls in a single message. Wait for all to complete before
aggregating.

Produce a JSON result per agent:

```json
{"agentName": "<name>", "status": "pass|warn|fail", "issues": [], "summary": "..."}
```

### 5. Aggregate results

#### 5a. Apply ACCEPTED-RISKS.md (project-local suppression policy)

Before scoring, consult `ACCEPTED-RISKS.md` at the repo root if present.
Parse the `rules:` YAML frontmatter per
`knowledge/accepted-risks-schema.md`. For each finding across all
agent outputs, check rules in declaration order; the first matching
rule suppresses the finding and emits exactly one audit entry:

```
SUPPRESSED: <file>:<line> [<rule_id>] by ACCEPTED-RISKS rule <rule.id>
```

Suppression rules:
- Expired rules (past `expires` date) become inert — they stop
  suppressing, emit a WARN naming the rule and owner, and appear in
  the Expiry Report section.
- Rules with `broad: true` (wildcard `rule_id` or multi-file globs)
  emit an informational notice listing broad rules for auditor
  attention.
- Schema-invalid rules (missing required field, bad date, wildcard
  without `broad: true`, empty `rationale`) fail the review run with
  a specific parse error naming the rule id.

Suppressed findings are removed from the scoring input and listed in
a dedicated "Suppressed by ACCEPTED-RISKS" section of the report
(grouped by rule id). They bypass the fix loop (no auto-apply, no
re-run).

If `ACCEPTED-RISKS.md` is absent, skip this step silently.

#### 5b. Health scoring

Read `knowledge/review-rubric.md` for the health scoring formula.

Compute the overall health score from agent results using the rubric's
category weights and escalation rules. Security failures auto-escalate
to 🔴.

Classify each issue by actionability:

| Severity | Confidence | Actionable? | Auto-fix behavior |
|----------|------------|-------------|-------------------|
| error | high | Yes | Auto-apply |
| error | medium | Yes | Auto-apply |
| error | none | No | Report only — requires human judgment |
| warning | high | Yes | Auto-apply |
| warning | medium | Yes | Auto-apply |
| warning | none | No | Report only |
| suggestion | any | No | Report only — suggestions do not trigger the fix loop |

**Actionable issues** = issues with severity `error` or `warning`
AND confidence `high` or `medium`. These drive the fix loop.

### 6. Present findings and ask for direction

If there are **zero actionable issues**, skip to step 7 (generate
report). There is nothing to fix automatically.

If there **are** actionable issues, present a summary to the user
before taking any action:

```text
## Review Findings

Found N actionable issues (N errors, N warnings) that can be
auto-fixed, plus N issues requiring human review.

Actionable issues by agent:
- structure-review: 3 (2 error, 1 warning)
- naming-review: 2 (2 warning)
- js-fp-review: 1 (1 error)

Options:
1. **Fix** — Auto-fix actionable issues and re-run review
   (up to 5 iterations until clean)
2. **Report only** — Save all findings to a report without
   modifying any code
```

Ask the user: **"Fix these issues automatically, or save as
report only?"**

- If the user chooses **Fix** (or says "fix", "apply", "yes",
  "go ahead", etc.) → proceed to step 6a (review-fix loop)
- If the user chooses **Report only** (or says "report", "no",
  "don't fix", "just the report", etc.) → skip to step 7
  (generate report) with all issues intact — no code is modified

**Exception — non-interactive mode**: If running inside `/build`
(as part of the inline review checkpoint or final review gate),
skip this prompt and proceed directly to the fix loop. The build
pipeline is already an approved automated workflow — pausing for
confirmation at every review checkpoint would defeat the purpose.
The orchestrator's Phase 3 approval already serves as the human
gate.

### 6a. Review-fix loop

This loop fixes actionable issues and re-runs review until the
code is clean or the iteration limit is reached.

```
iteration = 1
MAX_ITERATIONS = 5

while actionable_issues > 0 AND iteration ≤ MAX_ITERATIONS:
    1. Apply fixes for all actionable issues
    2. Re-run only the agents that reported actionable issues
    3. Re-aggregate results
    4. iteration += 1

if iteration > MAX_ITERATIONS AND actionable_issues > 0:
    escalate to human with remaining issues
```

#### 6a-i. Apply fixes

For each actionable issue from step 5 (or the previous loop
iteration), apply the minimal fix:

1. Read the affected file(s)
2. Apply the fix described in the issue's `suggestedFix` field
3. Follow all repository rules and coding conventions
4. Change only what the fix requires — no surrounding improvements
5. After all fixes in this iteration are applied, run the project's
   test suite. If tests fail, revert the last fix that broke them
   and mark that issue as `[auto-fix failed — human review required]`

**Fix order**: Apply fixes file-by-file, top-to-bottom by line number
within each file. This prevents line-number drift from earlier fixes
invalidating later ones.

**Confidence handling**:
- `high` confidence: Apply without confirmation
- `medium` confidence: Apply without confirmation (the loop will
  re-validate by re-running the agent — if the fix was wrong, the
  agent will flag it again or flag a new issue)

#### 6a-ii. Re-run failed agents

After fixes are applied, re-run **only the agents that reported
actionable issues** in the previous iteration. Do not re-run agents
that passed or only had suggestions.

- Use the same model routing and file scope as the original run
- Pass only the files that were modified by the fixes (not the full
  original file list) — this is a targeted re-review
- Collect new results in the same JSON format

#### 6a-iii. Re-aggregate

Merge new agent results with the results from agents that already
passed (their status carries forward). Recompute the overall health
score. Reclassify remaining issues as actionable or not.

**Loop exit conditions** (checked after each iteration):

| Condition | Action |
|-----------|--------|
| Zero actionable issues remain | Exit loop → proceed to step 7 |
| Iteration limit reached (5) | Exit loop → escalate remaining issues |
| Same issues persist after fix attempt | Exit loop — the auto-fix is not converging |
| Tests fail after fix and revert | Mark issue as human-required, continue with remaining |

#### 6a-iv. Loop reporting

Track each iteration for the final report:

```text
## Review-Fix Loop

| Iteration | Actionable Issues | Fixed | Remaining | Agents Re-run |
|-----------|-------------------|-------|-----------|---------------|
| 1         | 7                 | 6     | 1         | 3             |
| 2         | 1                 | 1     | 0         | 1             |

Loop converged in 2 iterations.
```

If the loop did not converge:

```text
Loop stopped after 5 iterations. 2 issues remain:
- [security-review] SQL injection at src/db/query.ts:42 [auto-fix failed — human review required]
- [domain-review] Abstraction leak at src/api/handler.ts:15 [confidence: none — human review required]
```

### 7. Generate report

Read `knowledge/review-template.md` for the report structure.

**If `--json` flag is set**, output a single aggregated JSON object
and stop:

```json
{
  "overall": "pass|warn|fail",
  "timestamp": "<ISO 8601>",
  "targetFiles": 42,
  "preFlightPassed": true,
  "iterations": 2,
  "agents": [
    {"agentName": "test-review", "status": "pass", "issues": [], "summary": "..."},
    {"agentName": "security-review", "status": "pass", "issues": [], "summary": "..."}
  ],
  "totals": {"errors": 0, "warnings": 0, "suggestions": 3},
  "fixSummary": {"applied": 6, "failed": 0, "humanRequired": 1},
  "summary": "PASS after 2 fix iterations. 6 issues auto-fixed, 1 requires human review."
}
```

**Otherwise**, produce a summary table:

```text
# Code Review Summary

| Agent              | Status | Issues | Fixed | Model Tier |
|--------------------|--------|--------|-------|------------|
| test-review        | PASS   | 0      | —     | mid        |
| structure-review   | PASS   | 2      | 2     | mid        |
| security-review    | WARN   | 1      | 0     | frontier   |
| ...                | ...    | ...    | ...   | ...        |

Overall: WARN after 2 fix iterations (N agents passed, N warned, N failed)
Total issues found: N | Auto-fixed: N | Human review required: N
```

Then list remaining issues (those not auto-fixed) grouped by file,
sorted by severity (errors first). Mark each with its reason:
`[confidence: none]`, `[auto-fix failed]`, or `[suggestion]`.

Include the iteration table from step 6d.

### 8. Save correction prompts for remaining issues

For issues that were NOT auto-fixed (confidence: none, auto-fix
failed, or suggestions the user may want to address), generate
correction prompt files:

```json
{
  "priority": "high|medium|low",
  "confidence": "high|medium|none",
  "category": "<agent-name>",
  "instruction": "Fix: <message> (Suggested: <suggestedFix>)",
  "context": "Line <line> in <file>",
  "affectedFiles": ["<file>"],
  "autoFixResult": "not-attempted|failed|human-required"
}
```

Save to `corrections/` directory if any remain. These can be
addressed manually or via `/apply-fixes`.

### 9. Write pre-commit gate file

If the review was auto-scoped to uncommitted changes (step 1
auto-scope detected dirty working tree) and the overall review
status is `pass` or `warn` (after the fix loop), write a
`.review-passed` gate file so the pre-commit hook allows the next
commit:

```bash
git diff --cached --name-only | sort | shasum -a 256 | cut -d' ' -f1 > .review-passed
```

If no files are staged (e.g., auto-scope picked up unstaged
changes only), compute the hash from the files that were actually
reviewed:

```bash
echo "<reviewed-file-list>" | sort | shasum -a 256 | cut -d' ' -f1 > .review-passed
```

If the overall status is `fail`, do **not** write `.review-passed`.
The pre-commit hook will continue blocking commits until the
remaining issues are resolved and the review is re-run.
