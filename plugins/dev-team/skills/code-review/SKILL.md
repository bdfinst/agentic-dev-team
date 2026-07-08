---
name: code-review
description: >-
  Run all enabled review agents against target files. Use this whenever the
  user asks for a code review, wants feedback on their code, says "review my
  code", "check this before I PR", "what's wrong with this", "run the
  agents", or has just finished implementing a feature. Use proactively
  before commits and pull requests.
argument-hint: >-
  [--agent <name>] [--since <ref>] [--path <dir>] [--all] [--json]
  [--internal] [--force --reason "<text>"]
  [--static-analysis|--no-static-analysis] [--init-risks] [--background]
user-invocable: true
allowed-tools: >-
  Read, Write, Edit, Grep, Glob, AskUserQuestion, Agent,
  Bash(git diff *), Bash(npx *), Bash(npm run *),
  Bash(pnpm *), Bash(yarn *), Bash(tsc *), Bash(eslint *),
  Bash(git log *), Bash(gh run *), Bash(semgrep *),
  Bash(ruff *), Bash(mypy *), Skill(review-agent *)
---

# Code Review

**The review-agent panel is the primary quality gate** (Rec 5,
`docs/experiments/RECOMMENDATIONS.md`). The review-agent lens — SRP,
complexity, coupling, duplication — was the only quality axis that separated
workflow arms in the experiment line. Coverage and mutation scores saturate
near-identically across every workflow shape and must **never** be used to
rank workflow quality: the losing big-batch and split arms posted *higher*
mutation scores (0.93–0.98) than the two winners (0.80–0.86). A higher
coverage or mutation number is not evidence that code — or the workflow that
produced it — is better. (The deterministic static-analysis pre-pass below is
a different, complementary axis: mechanical findings cleared before the
semantic panel runs, not a metric competing with it.)

Role: orchestrator. Route work to review agents; do not review code yourself. Pass each agent's tier alias (from its `model:` frontmatter) when dispatching — the PreToolUse hook `hooks/agent_model_resolve.py` resolves it to the active snapshot per the Resolution Procedure in `agents/orchestrator.md`.

Output templates and JSON schemas: [`output-format.md`](output-format.md). Example report: [`examples/sample-report.md`](examples/sample-report.md).

## Orchestrator constraints

1. **Do not review code yourself.** Delegate all semantic analysis to review agents.
2. **Minimize context per agent.** Pass only what each agent's `Context needs` field requires.
3. **Route to the right model tier.** Each agent's `model:` frontmatter declares its tier alias (`haiku`/`sonnet`/`opus`); the PreToolUse hook `hooks/agent_model_resolve.py` resolves it to the active snapshot per `agents/orchestrator.md` → Resolution Procedure. Do not override the frontmatter value.
4. **Run deterministic gates first.** Lint, type-check, secret scan are cheaper than AI. Stop if they fail.
5. **Return structured results.** Aggregate agent JSON; do not add your own findings.
6. **Be concise.** Tables and JSON, no preambles, no filler.

## Parse Arguments

Arguments: $ARGUMENTS

| Flag | Behavior |
| --- | --- |
| `--agent <name>` | Run only the named agent (delegates to `/review-agent`) |
| `--since <ref>` | Review files changed since the ref (`git diff --name-only <ref>...HEAD`) |
| `--path <dir>` | Review only files in this directory |
| `--all` | Force full-repository review even when uncommitted changes exist |
| `--json` | Output aggregated JSON to **stdout** instead of prose. Contractually non-interactive (for CI): never prompts; defaults to report-only (no code modified). |
| `--internal` | This is an orchestrator-internal dispatch (`/build`'s Step 6 backstop review, `/test-improve`'s Phase 4/5 end-of-phase review loop) — skip the `DEV_TEAM_REPORTS/code-review.md` report write in step 7. Orthogonal to `--json`: `--internal` alone still runs the prose/fix-loop path; both sanctioned callers use `--internal` without `--json` specifically to keep the fix loop. `/build` and `/test-improve` are the only sanctioned callers of this flag today — see `knowledge/report-output-location.md` for `/ship`'s deliberate exception (writes the report by default, no `--internal`). |
| `--init-risks` | Scaffold `ACCEPTED-RISKS.md` from `templates/ACCEPTED-RISKS.md.tmpl` if absent. Exits non-zero without overwriting if present. Schema: `knowledge/accepted-risks-schema.md`. |
| `--force` | Skip pre-flight gates **and the documentation-only short-circuit** (forces a full review of doc-only changes). **Requires `--reason "<text>"`** — logged to `metrics/override-audit.jsonl`. |
| `--reason "<text>"` | Override justification (required with `--force`) |
| `--static-analysis` / `--no-static-analysis` | Force on/off the static analysis pre-pass (Semgrep, ESLint, TypeScript, Ruff, mypy). Auto-enabled when tools are detected. |
| `--background` | Drift review mode — review default branch for documentation, naming, and structural drift. Runs doc-review, arch-review, naming-review, structure-review only. Skips pre-flight gates. |
| (no flags) | **Auto-scope**: review uncommitted changes if any exist, otherwise full repository |

## Progress tracking

```text
- [ ] Target files determined
- [ ] Documentation-only check (short-circuit if all docs)
- [ ] Pre-flight gates passed
- [ ] Static analysis pre-pass (if enabled)
- [ ] Agents loaded and filtered
- [ ] All agents executed
- [ ] Results aggregated
- [ ] User asked: fix or report only?
- [ ] Review-fix loop (if user chose fix, up to 5 iterations)
- [ ] Report generated
- [ ] Correction prompts saved
- [ ] Pre-commit gate file written (if auto-scoped to uncommitted changes)
```

## Steps

### 1. Determine target files

Priority order:

1. `--path <dir>` — files in that directory (exclude node_modules, .git, dist, build, coverage)
2. `--since <ref>` — `git diff --name-only <ref>...HEAD`
3. `--all` — all source files
4. **Auto-scope** (no flags): run `git diff --name-only` + `git diff --cached --name-only`, combine and dedupe. If non-empty, review those files. If empty, review the full repository.

**Never `Read` a directory path directly to enumerate its contents** — `Read` on a directory throws `EISDIR` (the same hazard step 3 avoids for agent-roster enumeration). This applies to `--path <dir>`, `--all`, and the full-repository fallback alike: always list files with `Glob` (e.g. `Glob("<dir>/**/*")`), never a bare `Read` on the directory itself. See `${CLAUDE_PLUGIN_ROOT}/knowledge/directory-enumeration.md` for the shared rule.

**Scope validation** (full-repo paths only):

| File count | Action |
| --- | --- |
| ≤200 | Proceed |
| 201–500 | Warn: "Reviewing {N} files — consider `--path` to narrow scope." Proceed. |
| >500 | Warn + confirm: "Reviewing {N} files is expensive. Continue?" Wait. |

**Documentation-only short-circuit.** After the target set is known, classify each file. A file is **documentation** when it matches a doc type or path:

- extension `.md`, `.mdx`, `.markdown`, `.rst`, `.txt`, `.adoc`
- any path under a `docs/` directory
- a root doc: `README*`, `CHANGELOG*`, `CONTRIBUTING*`, `LICENSE*`, `NOTICE*`, `AUTHORS*`, `CODE_OF_CONDUCT*`

…**except functional Claude-config markdown, which is never documentation** (it drives agent/skill/command behavior and must be reviewed): any path containing a `.claude/` segment, or under `agents/`, `skills/`, `prompts/`, `knowledge/`, or `templates/agents/`. Treat `CLAUDE.md` and `AGENTS.md` as functional config too, not documentation.

If **every** target file is documentation, short-circuit:

1. Emit: `Documentation-only changeset ({N} files) — skipping code review. Re-run with --force --reason "<text>" to review anyway.`
2. If the review was auto-scoped to uncommitted changes, write the `.review-passed` gate file (per step 9) so the pre-commit hook allows the commit.
3. In `--json` mode, emit `{"status": "skipped", "reason": "documentation-only", "files": [<list>]}` instead.
4. **Stop.** Do not run pre-flight gates, static analysis, or any agent.

**Bypass:** the short-circuit does **not** apply with `--force` (with `--reason`), `--agent <name>`, or `--background` (drift review always inspects docs).

### 1b. Check for institutional context

If `REVIEW-CONTEXT.md` exists at the repo root, read it and pass its contents to every agent in step 4, prefixed with: "Institutional context provided for this review:". This file is optional.

### 1c. Probe for optional MCP tools

| Tool | Check | Use |
| --- | --- | --- |
| RoslynMCP | `get_code_metrics` / `search_symbols` available | C# metrics, compiler diagnostics |
| Code knowledge graph | `list_repos` available | Cross-repo dependency mapping |
| Documentation MCP | wiki/docs search available | Architecture docs |
| Semgrep | `which semgrep` | SAST context for security-review |

Pass availability info to each agent so they can use enhanced tools or fall back to Glob/Grep/Read. Include in the final report per `knowledge/review-template.md`.

### 2. Pre-flight gates

Skip entirely if `--background`. If `--force` without `--reason`, halt:

```
ERROR: --force requires --reason "<justification>".
```

If `--force` with `--reason`, append an entry to `metrics/override-audit.jsonl` per the schema in [`output-format.md`](output-format.md#override-audit-log-entry-step-2---force-path), then proceed to step 3.

Otherwise run these in sequence (stop on first failure):

1. **Lint**: `npx eslint` (or project lint command) on target files.
2. **Type check**: `npx tsc --noEmit` if `tsconfig.json` exists.
3. **Secret scan**: grep target files for `(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['"][^'"]{8,}`.
4. **Semgrep SAST**: `semgrep scan --config auto --quiet --json` on target files if installed. ERROR-severity → fail. WARNING-severity → continue, include in report. Save findings for security-review context.
5. **Pipeline-red check**: `gh run list --branch $(git branch --show-current) --limit 1 --json conclusion -q '.[0].conclusion'` if `gh` is available. If the last CI run failed, warn: "Pipeline is red. Fix CI before adding new code. Use `--force` to override."

Skip any gate silently if its tool is unavailable.

### 2b. Static analysis pre-pass

Skip if `--no-static-analysis` or `--background`.

Follow the detection, execution, and deduplication procedure in [`skills/static-analysis-integration/SKILL.md`](../static-analysis-integration/SKILL.md). Output is structured findings injected into agent context in step 4. **This step does not gate execution** — it collects context only.

If Semgrep already ran in the pre-flight gate, reuse those findings. Do not run Semgrep twice.

### 3. Determine enabled agents

If `--background`: run only `doc-review`, `arch-review`, `naming-review`, `structure-review`. Skip all others.

Otherwise read the roster from the **Review Agents** section of `knowledge/agent-registry.md` — each row names an agent and its `agents/<name>.md` file. **Never `Read` the bare `agents/` directory** (it throws `EISDIR`); if you must confirm files on disk, list them with `Glob("agents/*.md")`, never a directory `Read` (see `${CLAUDE_PLUGIN_ROOT}/knowledge/directory-enumeration.md`). All are enabled by default.

**Language-agnostic agents always run** regardless of tech stack: `doc-review`, `arch-review`, `claude-setup-review`, `token-efficiency-review`.

**Frontend component files in scope** (`.jsx`, `.tsx`, `.vue`, `.svelte`, Angular `*.component.ts` + their templates, or `.js`/`.ts` modules that render UI): always include `component-architecture-review` — the same lens `/frontend-architecture` runs standalone — scoped to those files in step 4.

If `review-config.json` exists at the repo root, honor its per-agent `"enabled": false` flags.

### 4. Run each enabled agent

Spawn agents as parallel subagents in a single message using the Agent tool.

- **File scope**: pass only files matching each agent's declared scope. Skip the agent if no files match.
- **Context payload** (controlled by the agent's `Context needs`):
  - `diff-only` → diff output only (for auto-scope or `--since` only)
  - `full-file` → complete files
  - `project-structure` → full files + directory tree
  - When reviewing full repository (clean auto-scope, `--all`, or `--path`), always pass full files.
- **Model**: pass each agent's declared tier alias (`haiku`/`sonnet`/`opus`) from its `model:` frontmatter. The PreToolUse hook `hooks/agent_model_resolve.py` resolves the tier to the active snapshot per `agents/orchestrator.md` → Resolution Procedure.
- **Static analysis context**: if step 2b produced findings, inject into every agent's prompt using the format in `skills/static-analysis-integration/SKILL.md`: "These issues were detected by static analysis. Do not re-report them. Focus on semantic concerns."
- **Per-agent output**: `{"agentName": "<name>", "status": "pass|warn|fail", "issues": [], "summary": "..."}` (full schema in `output-format.md`).

**Graph-assisted architectural review**: if the target repo has `.codegraph/` (CodeGraph MCP server, `mcp__codegraph__*` tools — fast callers/callees/impact lookups) and/or `graphify-out/graph.json` (Graphify CLI — `graphify query`/`path`/`explain` — architecture and cross-artifact questions), pass availability to agents doing structural/architectural review (`arch-review`, `component-architecture-review`, `structure-review`, `domain-review`) so they may consult the graph for impact/dependency context before flagging findings. See `knowledge/codegraph-vs-graphify.md` for when to use which. Never assume either tool exists — agents fall back to Read/Grep/Glob when absent.

Wait for all agents to complete before aggregating.

### 5. Aggregate results

#### 5a. Apply ACCEPTED-RISKS.md

If `ACCEPTED-RISKS.md` exists at the repo root, parse its `rules:` YAML frontmatter per `knowledge/accepted-risks-schema.md`. For each finding, check rules in declaration order; the first match suppresses and emits one audit entry:

```
SUPPRESSED: <file>:<line> [<rule_id>] by ACCEPTED-RISKS rule <rule.id>
```

- Expired rules become inert: stop suppressing, emit a WARN naming the rule and owner, list in an Expiry Report section.
- Rules with `broad: true` (wildcard `rule_id` or multi-file globs) emit an informational notice for auditor attention.
- Schema-invalid rules fail the run with a parse error naming the rule id.

Suppressed findings are removed from scoring, listed under "Suppressed by ACCEPTED-RISKS" in the report (grouped by rule id), and bypass the fix loop.

#### 5b. Health scoring

Read `knowledge/review-rubric.md` for the formula. Compute the overall health score; security failures auto-escalate to 🔴.

Classify each issue by actionability:

| Severity | Confidence | Actionable? |
| --- | --- | --- |
| error or warning | high or medium | **Yes** — auto-apply |
| error or warning | none | No — report only (human judgment) |
| suggestion | any | No — report only |

**Actionable issues** drive the fix loop.

#### 5c. Consolidate cross-agent findings

When multiple agents flag the same `file:line`, emit one `topFindings` entry: `severity` = the single **highest** enum for that finding, `agents` = an array of the reporting agents (e.g. `["structure-review", "complexity-review"]`). Never pack multiple values into `severity` or any agent scalar — no slash- or comma-joined strings. Every scalar field stays single-valued; multi-agent attribution lives only in the `agents: []` array. Schema: [`output-format.md`](output-format.md#aggregated-json-result---json-flag).

### 6. Present findings and ask for direction

If zero actionable issues, skip to step 7.

Otherwise present the Review Findings prompt (template: [`output-format.md`](output-format.md#review-findings-prompt-interactive--step-6)) and ask: **"Fix these issues automatically, or save as report only?"**

- "Fix" / "apply" / "yes" → step 6a
- "Report" / "no" / "don't fix" → step 7 (no code modified)

**Exception — non-interactive mode**: skip this prompt when the run is non-interactive.

- (a) If `--json` (or `--yes`), **default to report only** — proceed to step 7 and emit the aggregated JSON; **never modify code** without an explicit caller opt-in. `--json` is contractually non-interactive (CI-safe): it never blocks on this prompt.
- (b) If running inside `/build` or `/pr`, proceed to the fix loop. The caller owns the human gate (the orchestrator's Phase 3 approval for `/build`; the pre-PR confirmation for `/pr`).

### 6a. Review-fix loop

```
iteration = 1
MAX_ITERATIONS = 5

while actionable_issues > 0 AND iteration ≤ MAX_ITERATIONS:
    1. Apply fixes for all actionable issues (file-by-file, top-to-bottom by line)
    2. After each iteration's fixes, run the project's test suite.
       If tests fail, revert the last fix that broke them and mark the
       issue [auto-fix failed — human review required].
    3. Re-run only the agents that reported actionable issues, against only
       the modified files. Carry forward statuses of agents that passed.
    4. Re-aggregate. Reclassify remaining issues.
    5. iteration += 1

if iteration > MAX_ITERATIONS AND actionable_issues > 0:
    escalate to human with remaining issues
```

**Exit conditions**:

| Condition | Action |
| --- | --- |
| Zero actionable issues | Exit → step 7 |
| Iteration limit (5) | Exit → escalate |
| Same issues persist | Exit — not converging |
| Tests fail after fix and revert | Mark issue human-required; continue |

Track each iteration for the report — template in [`output-format.md`](output-format.md#review-fix-loop-iteration-log-step-6a-iv).

### 7. Generate report

**Output paths.** All file artifacts (`./corrections/*.json`, `./.review-passed`) are repo-relative to the target repository's working directory (the cwd `/code-review` was invoked in). Never prepend a scratchpad, sandbox, or session root onto an already-absolute path, and never join two absolute paths. `--json` prints to **stdout** and writes no file.

Read `knowledge/review-template.md` for the structure.

**If `--json`: the JSON object is the ONLY output for this run — non-negotiable, not model discretion.** Emit the aggregated JSON object per the schema in [`output-format.md`](output-format.md#aggregated-json-result---json-flag) to **stdout**, write no file, and **stop: do not proceed to step 8 or step 9 in this run, regardless of how many issues were found or whether any are actionable.** There is no fallback to prose, and no `corrections/`/`.review-passed` persistence, in `--json` mode — ever. (`/pr`'s `--json` call already only reads this JSON object's `overall`/`status` field, so this loses nothing a caller depends on.)

**A sentence describing the JSON is not the JSON.** A completed run whose final text reads like "Aggregated JSON emitted to stdout per `--json` contract; run stops here" — with no `{...}` object actually present anywhere in that text — is a contract violation, not compliance, even though it correctly stopped rather than proceeding further. The literal final output of the turn must be the JSON object itself, not a narration of having produced it. If the next action being considered is a summary sentence announcing that the JSON was (or is about to be) emitted, that is the signal to emit the actual object instead — there is no valid end state for a `--json` run that consists of prose alone.

Otherwise (no `--json`): emit the prose summary using the Code Review Summary template in [`output-format.md`](output-format.md#code-review-summary-report-step-7-prose-mode). Append the iteration table.

**Write the durable report (skip when `--internal`).** See
`knowledge/report-output-location.md` for the shared write-scope convention
this step follows. When `--internal`
was **not** passed, write the identical prose summary to
`DEV_TEAM_REPORTS/code-review.md` in the target repository's working
directory (creating the directory if absent), overwriting any existing
file at that path — write it even when the review found zero issues. Print
one confirmation line: `Report written: DEV_TEAM_REPORTS/code-review.md`,
or `Report written: DEV_TEAM_REPORTS/code-review.md (replaced previous
run)` when a file already existed at that path. If the write fails
(permission/read-only): report `Cannot write
DEV_TEAM_REPORTS/code-review.md: <error>` to chat and continue unaffected —
the write failure is non-fatal. When `--internal` **was** passed, skip this
write entirely (the fix loop and every other prose-mode behavior above are
unaffected — `--internal` only suppresses this one write). Then continue to
step 8.

### 8. Save correction prompts for remaining issues

**Skip this entire step if `--json` was set.** Step 7 already stopped the run for `--json` mode; corrections are never written to disk in `--json` mode.

For issues NOT auto-fixed (confidence: none, auto-fix failed, or suggestions), generate one correction prompt per issue using the Correction prompt schema in [`output-format.md`](output-format.md#correction-prompt-json). Save to `./corrections/` **in the target repository's working directory** (the cwd `/code-review` was invoked in). Write all output artifacts only to these repo-relative paths — never prepend a scratchpad, sandbox, or session root, and never join two absolute paths. These can be addressed manually or via `/apply-fixes`.

### 9. Write pre-commit gate file

**Skip this entire step if `--json` was set** (same reason as step 8).

If the review was auto-scoped to uncommitted changes and the overall status is `pass` or `warn`, write `.review-passed` so the pre-commit hook allows the next commit. Use the **shared gate-hash helper** so the writer and the pre-commit hook compute the hash identically — it hashes the staged **content** (the cached patch), not just the file paths (#193), so any edit after review invalidates the gate:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/review_gate_hash.py > .review-passed
```

Stage the exact changes you reviewed (`git add` them) before writing the gate, so the staged content the hook hashes matches what was reviewed. If `git diff --cached` is empty (you reviewed unstaged changes), stage them first — the gate binds to the staged patch by design.

If overall status is `fail`, do **not** write the gate file — the pre-commit hook will keep blocking until issues are resolved and the review re-run.
