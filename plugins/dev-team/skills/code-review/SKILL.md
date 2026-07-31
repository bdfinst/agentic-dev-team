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
  [--pdf]
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

Role: orchestrator. Route work to review agents; do not review code yourself. Pass each agent's `model:`/`effort:` frontmatter as declared when dispatching — the harness resolves both fields natively before dispatch, per Model/Effort Resolution in `agents/orchestrator.md` (ADR 0026).

Output templates and JSON schemas: [`output-format.md`](output-format.md). Example report: [`examples/sample-report.md`](examples/sample-report.md).

## Orchestrator constraints

**MUST — confirm agent-dispatch capability before anything else in this skill (issue #1461).** Before attempting to dispatch ANY review agent (Step 4), you MUST confirm the `Agent` (or `Task`) tool is actually present and available in your current toolset. If it is not present: **STOP.** Do not proceed with a self-applied, inline, or checklist-based review of any kind as a substitute for independent dispatch — an orchestrator applying the review agents' checklists itself is not a review, it is self-certification, and it defeats the entire purpose of this gate. Do not write `.review-passed` under any circumstance in this state. Instead, report to the user/operator plainly: code review cannot run in this environment because no agent-dispatch capability (`Agent`/`Task` tool) is available; name exactly what's missing; and state that the commit gate cannot be satisfied until `/code-review` is re-run from a session that has that capability. This is a hard requirement, not a preference — "should dispatch agents" is not sufficient; a missing `Agent`/`Task` tool always halts this skill before Step 2.

1. **Do not review code yourself.** Delegate all semantic analysis to review agents.
2. **Minimize context per agent.** Pass only what each agent's `Context needs` field requires.
3. **Route to the right model.** Each agent's `model:`/`effort:` frontmatter declares its model alias and reasoning effort; the harness resolves both fields natively before dispatch, per `agents/orchestrator.md` → Model/Effort Resolution (ADR 0026). Do not override the frontmatter value.
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
| `--slice <N>` | Engage sliced large-repo review explicitly, capping each slice at N files (module-aligned) at any repo size. `N` must be a positive integer. See [`sliced-mode.md`](sliced-mode.md). |
| `--resume` | Resume a sliced run — skip slices whose section artifact already exists on disk. See [`sliced-mode.md`](sliced-mode.md). |
| `--no-slice` | Escape hatch — force the legacy single-pass review even on a large full-repo scope that would otherwise auto-engage sliced mode. |
| `--json` | Output aggregated JSON to **stdout** instead of prose. Contractually non-interactive (for CI): never prompts; defaults to report-only (no code modified). |
| `--pdf` | After the durable report is written, also render it to a sibling PDF via `hooks/lib/report_pdf.py`. See `knowledge/report-pdf-integration.md`. No-op with a message when no report file is written (`--json` or `--internal`); under `--json`, that status goes to **stderr** so stdout stays pure JSON. Additive: never changes the review's own output or exit status. |
| `--internal` | This is an orchestrator-internal dispatch (`/build`'s Step 6 backstop review, `/test-improve`'s Phase 4/5 end-of-phase review loop) — skip the `.dev-team-reports/code-review.md` report write in step 7. Orthogonal to `--json`: `--internal` alone still runs the prose/fix-loop path; both sanctioned callers use `--internal` without `--json` specifically to keep the fix loop. `/build` and `/test-improve` are the only sanctioned callers of this flag today — see `knowledge/report-output-location.md` for `/ship`'s deliberate exception (writes the report by default, no `--internal`). |
| `--init-risks` | Scaffold `ACCEPTED-RISKS.md` from `templates/ACCEPTED-RISKS.md.tmpl` if absent. Exits non-zero without overwriting if present. Schema: `knowledge/accepted-risks-schema.md`. |
| `--force` | Skip pre-flight gates **and the documentation-only short-circuit** (forces a full review of doc-only changes). **Requires `--reason "<text>"`** — logged to `.claude/metrics/override-audit.jsonl`. |
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
4. **Auto-scope** (no flags): run `git -c diff.relative=false diff --name-only` + `git -c diff.relative=false diff --cached --name-only`, combine and dedupe. If non-empty, review those files. If empty, review the full repository. The explicit `-c diff.relative=false` matters here (#1461 fourth security re-review): a repo/global `diff.relative=true` config would otherwise silently scope this listing to the invocation's cwd, and `review_gate_hash()`/`_staged_names()` (which pin the same override) would then hash/gate a broader staged patch than what was actually reviewed.

**Stage auto-scoped changes now, before anything else (#1461).** When the auto-scope path found a non-empty file set, `git add` those files immediately — before pre-flight gates, static analysis, or any agent dispatch — so the staged content's hash is fixed from this point through step 9's gate write. This is not cosmetic: `agent_dispatch_ledger.py` stamps each review-agent dispatch's `subject_hash` with `review_gate_hash()` at **dispatch time** (step 4). If staging happened only at step 9 (after dispatch) as previously documented, the dispatch-time hash and the gate-write-time hash would differ whenever the auto-scope target was unstaged — the common case — and every genuine dispatch would silently fail to corroborate the gate, forcing a hard block on a fully legitimate review. Staging here, before dispatch, is what makes step 9's hash and the dispatch ledger's `subject_hash` the same value. An unstaged working-tree edit after this point does **not** by itself change the staged hash (`review_gate_hash()` hashes `git diff --cached`, not the working tree) — step 6a's fix loop explicitly re-stages (`git add`) each iteration's fixes for exactly this reason; see that step for how corroboration is re-established after a fix loop runs.

**Never `Read` a directory path directly to enumerate its contents** — `Read` on a directory throws `EISDIR` (the same hazard step 3 avoids for agent-roster enumeration). This applies to `--path <dir>`, `--all`, and the full-repository fallback alike: always list files with `Glob` (e.g. `Glob("<dir>/**/*")`), never a bare `Read` on the directory itself. See `${CLAUDE_PLUGIN_ROOT}/knowledge/directory-enumeration.md` for the shared rule.

**Scope validation** (full-repo paths only):

| File count | Action |
| --- | --- |
| ≤200 | Proceed |
| 201–500 | Warn: "Reviewing {N} files — consider `--path` to narrow scope." Proceed. |
| >500 | **Auto-engage sliced mode** (large-repo review) unless `--no-slice`. |

**Sliced large-repo review.** On a full-repo scope exceeding the >500 tier (or
whenever `--slice <N>` is passed), **auto-engage sliced mode**: run the sliced
path in [`sliced-mode.md`](sliced-mode.md) instead of steps 4–9 below. That file
owns the full activation precedence (via `scripts/activation.py`), partitioning,
per-slice panels, persist-and-drop, `--resume`, and cross-slice consolidation —
not restated here. `--no-slice` forces the legacy single-pass review (steps 2–9)
even past the threshold; Exactly at 500 files does not auto-engage.
**Non-full-repo scope** (`--path`, `--since`, auto-scoped uncommitted changes)
**never** auto-engages, regardless of file count — the review proceeds exactly
as before this feature. Sliced mode is **report-only** (no interactive fix loop).

**Documentation-only short-circuit.** After the target set is known, classify each file. A file is **documentation** when it matches a doc type or path:

- extension `.md`, `.mdx`, `.markdown`, `.rst`, `.txt`, `.adoc`
- any path under a `docs/` directory
- a root doc: `README*`, `CHANGELOG*`, `CONTRIBUTING*`, `LICENSE*`, `NOTICE*`, `AUTHORS*`, `CODE_OF_CONDUCT*`

…**except functional Claude-config markdown, which is never documentation** (it drives agent/skill/command behavior and must be reviewed): any path containing a `.claude/` segment, or under `agents/`, `skills/`, `prompts/`, `knowledge/`, or `templates/agents/`. Treat `CLAUDE.md` and `AGENTS.md` as functional config too, not documentation.

If **every** target file is documentation, short-circuit:

1. Emit: `Documentation-only changeset ({N} files) — skipping code review. Re-run with --force --reason "<text>" to review anyway.`
2. If the review was auto-scoped to uncommitted changes, write the `.review-passed` gate file (per step 9) so the pre-commit hook allows the commit. **Contemporaneously** (before or immediately after that write), record the doc-only exemption as an explicit, auditable boundary event — the `.review-passed` gate's dispatch-ledger corroboration (#1461) reads this event, bound to the gate's own hash, to let the doc-only path stay exempt from agent-dispatch evidence without being a silent, unaccountable code-path skip:
   ```bash
   HASH=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/review_gate_hash.py)
   mkdir -p .claude/memory && echo "$HASH" > .claude/memory/.review-passed
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/boundary_events.py --event doc-only --subject-hash "$HASH"
   ```
3. In `--json` mode, emit `{"status": "skipped", "reason": "documentation-only", "files": [<list>]}` instead.
4. **Stop.** Do not run pre-flight gates, static analysis, or any agent.

**Bypass:** the short-circuit does **not** apply with `--force` (with `--reason`), `--agent <name>`, or `--background` (drift review always inspects docs).

### 1b. Check for institutional context

If `REVIEW-CONTEXT.md` exists at the repo root, read it and pass its contents to every agent in step 4, prefixed with: "Institutional context provided for this review:". This file is optional.

### 1c. Probe for optional MCP tools

| Tool | Check | Use |
| --- | --- | --- |
| RoslynMCP | `get_code_metrics` / `search_symbols` available | C# metrics, compiler diagnostics |
| CodeGraph | `.codegraph/` present / `mcp__codegraph__codegraph_explore` available | Verified structural skeletons, resolved callers/callees/impact |
| Repowise | `get_context` / `get_symbol` / `search_codebase` / `get_risk` available | Verified file/symbol context + modification-risk lookups |
| Documentation MCP | wiki/docs search available | Architecture docs |
| Semgrep | `which semgrep` | SAST context for security-review |

Pass availability info to each agent so they can use enhanced tools or fall back to Glob/Grep/Read. All read-only review agents grant these MCP tools; see [`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md) for tool selection and the fallback contract. Include availability in the final report per `knowledge/review-template.md`.

### 2. Pre-flight gates

Skip entirely if `--background`. If `--force` without `--reason`, halt:

```
ERROR: --force requires --reason "<justification>".
```

If `--force` with `--reason`, append an entry to `.claude/metrics/override-audit.jsonl` per the schema in [`output-format.md`](output-format.md#override-audit-log-entry-step-2---force-path), then proceed to step 3.

Otherwise run these in sequence (stop on first failure):

1. **Lint**: `npx eslint` (or project lint command) on target files.
2. **Type check**: `npx tsc --noEmit` if `tsconfig.json` exists.
3. **Secret scan**: grep target files for the runnable pattern in [`knowledge/owasp-detection.md`](../../knowledge/owasp-detection.md) § Hardcoded-key pattern (the fenced code block, not the table row — table cells escape `|` as `\|`, a literal pipe rather than alternation).
4. **Semgrep SAST**: `semgrep scan --config auto --quiet --json` on target files if installed. ERROR-severity → fail. WARNING-severity → continue, include in report. Save findings for security-review context.
5. **Pipeline-red check**: `gh run list --branch $(git branch --show-current) --limit 1 --json conclusion -q '.[0].conclusion'` if `gh` is available. If the last CI run failed, warn: "Pipeline is red. Fix CI before adding new code. Use `--force` to override."

Skip any gate silently if its tool is unavailable.

### 2b. Static analysis pre-pass

Skip if `--no-static-analysis` or `--background`.

Follow the detection, execution, and deduplication procedure in [`skills/static-analysis-integration/SKILL.md`](../static-analysis-integration/SKILL.md). Output is structured findings injected into agent context in step 4. **This step does not gate execution** — it collects context only.

**Repo-specific invariant pre-pass (#1608).** Also run:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/repo_invariants.py"
```

It checks a small, growable list of this repo's own "every X should have
exactly one corresponding Y" invariants — mechanically checkable facts a full
agent panel would otherwise re-derive independently, once per agent, every
round. Its `findings` array merges into step 4's static-analysis context using
the same envelope and the same "detected by static analysis — do not
re-report, focus on semantic concerns" framing. Expand `CHECKS` in that script
as more rediscovered-N-times cases turn up; this step never needs to change to
pick up a new check.

If Semgrep already ran in the pre-flight gate, reuse those findings. Do not run Semgrep twice.

### 3. Determine enabled agents

If `--background`: run only `doc-review`, `arch-review`, `naming-review`, `structure-review`. Skip all others.

Otherwise read the roster from the **Review Agents** section of `knowledge/agent-registry.md` — each row names an agent and its `agents/<name>.md` file. **Never `Read` the bare `agents/` directory** (it throws `EISDIR`); if you must confirm files on disk, list them with `Glob("agents/*.md")`, never a directory `Read` (see `${CLAUDE_PLUGIN_ROOT}/knowledge/directory-enumeration.md`). All are enabled by default.

**Agent eligibility is resolved by `select_lenses.py` (#1523).** Run:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/select_lenses.py --files <target files>
```

Take its `lenses` array as the Scope-eligible roster, and **surface its `warnings`** in the review output (an agent missing its `Scope:` declaration is included include-biased and named — never silently dropped). The resolver reads each review agent's body-level `Scope:` declaration — `Scope: always` (eligible for any non-empty changeset) or a glob list (eligible only when at least one target file matches a declared glob). `Scope:` is a body declaration, not frontmatter (`agent-contract.json`). This is the single source of truth shared with `/build`'s inline checkpoints: adding or changing an agent's trigger scope needs only an edit to that agent's own body — zero edits to this skill. (The framework-reactivity agents react/vue/angular are **not** in the resolver's roster; they are governed by the manifest rule below. `ai-provenance-review` **is** resolver-governed via its own `Scope: always` declaration.)

**Framework-specific reactivity review** — dispatch based on the project's dependency manifest (`package.json` etc.):

- React (`react` / `react-dom` in deps): include `react-reactivity-review` scoped to `.jsx`/`.tsx` and React-importing `.js`/`.ts` files
- Vue (`vue` in deps): include `vue-reactivity-review` scoped to `.vue` and Vue-importing `.js`/`.ts` files
- Angular (`@angular/core` in deps): include `angular-reactivity-review` scoped to `*.component.ts`, `*.component.html`, `*.service.ts`, and general `.ts` files

**AI-provenance review**: `ai-provenance-review` is resolver-governed via its own `Scope: always` declaration — the resolver includes it on every non-empty changeset. It audits AI-authored assertions and non-obvious decisions for verification debt and regeneration risk.

If `review-config.json` exists at the repo root, honor its per-agent `"enabled": false` flags.

**Change-shape gate for low-yield lenses (#1254).** After the eligible roster is
known, drop the two low-yield code lenses (`performance-review`,
`correctness-review`) when the changeset has **no runtime surface** — every
target file is documentation or config, so those lenses would only no-op. Decide
deterministically with the shared helper (not by eyeballing the file list):

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/change_shape.py" --files <target files>
```

It prints `{"hasRuntimeSurface": <bool>, "skipLenses": [...]}`. When `skipLenses`
is non-empty, exclude those agents from this run and note the skip in the report
(they were gated by change shape, not by `Scope:`). The gate is **fail-safe**: any
file it cannot prove is doc/config (source, an unknown extension, or functional
Claude-config markdown under `agents/`, `skills/`, `knowledge/`, `.claude/`, …)
counts as runtime surface and keeps every lens. This never fires on a pure-docs
changeset — that is already handled earlier by the documentation-only
short-circuit; this gate covers the doc/config-**mixed** and config-only diffs
the short-circuit does not. Bypassed by `--force` and by `--agent <name>` (an
explicit single-agent request always runs that agent).

**Change-size gate for small changesets (#1339).** After `Scope:` eligibility
and the change-shape gate above have both been applied, apply this gate —
never before, and never in a way that re-adds an agent either already removed.
It narrows the `Scope: always` roster by diff *size* rather than file *type*:
the pre-commit hook (`hooks/pre_commit_review.py`) requires a `.review-passed`
hash match **and** (#1461) >= 2 distinct, recent, registered review-agent
dispatches recorded in the dispatch ledger — so this gate must never narrow
`keepAgents` below 2, and today's four-agent floor (`security-review`,
`correctness-review`, `spec-compliance-review`, `doc-review`) clears that with
room to spare. Which specific agents to keep at a given diff size remains
this step's decision, not the hook's — the hook only enforces the *count*
floor, never which agents satisfy it.

**Applies only to diff-scoped reviews** — auto-scoped uncommitted changes, or
`--since <ref>`. `--path`, `--all`, and the full-repository fallback review
complete files, not a diff, so this gate never engages for those scopes
(existing eligibility unchanged).

Compute the numstat lines and feed them to the shared helper — for auto-scope,
union unstaged and staged the same way step 1 unions `--name-only`:

```bash
# Auto-scope (uncommitted changes):
{ git diff --numstat; git diff --cached --numstat; } | python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/change_size.py" --numstat-from -

# --since <ref>:
git diff --numstat <ref>...HEAD | python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/change_size.py" --numstat-from -
```

It prints `{"filesChanged": <int>, "addedLines": <int>, "qualifiesForFastPath":
<bool>, "keepAgents": [...]}`. When `qualifiesForFastPath` is `true`, drop
every `Scope: always` agent **not** in `keepAgents` (today: `security-review`,
`correctness-review`, `spec-compliance-review`, `doc-review` — the four lenses
that stay meaningful at any diff size; the rest are code-quality-at-scale
concerns a diff this small essentially cannot exhibit meaningfully) and note
the drop in the report (gated by change size, not by `Scope:`).
`Scope:`-glob-matched agents are unaffected — they already run only against
matching file types, so a diff this small already narrows their incremental
cost to near-zero. The gate is **fail-safe**: any `git diff --numstat` error,
binary-file marker, or unparseable line disqualifies the run (full panel), as
does any file under `hooks/` or `skills/code-review/` (the enforcement
machinery and this gate's own orchestration) — a change there is exactly the
case where a cheap, self-certifying review is a problem, so it never qualifies
for the shortcut it defines, regardless of size. Bypassed by `--force` and by
`--agent <name>`, matching the change-shape gate's bypass list.

### 4. Run each enabled agent

**Dispatch-capability gate (re-confirm here, not just at the top of this file — issue #1461).** Before spawning anything below, re-verify the `Agent`/`Task` tool is present in this toolset. If it is not, STOP per the Orchestrator constraints above — do not fall back to reviewing the files yourself, inline, as a stand-in for the panel; report the missing capability and halt the run before any agent is spawned.

Spawn agents as parallel subagents in a single message using the Agent tool.

- **File scope**: pass only files matching each agent's declared scope. Skip the agent if no files match.
- **Context payload** (controlled by the agent's `Context needs`):
  - `diff-only` → diff output only (for auto-scope or `--since` only)
  - `full-file` → complete files
  - `project-structure` → full files + directory tree
  - When reviewing full repository (clean auto-scope, `--all`, or `--path`), always pass full files.
- **Model**: pass each agent's declared `model:`/`effort:` frontmatter. The harness resolves both fields natively before dispatch, per `agents/orchestrator.md` → Model/Effort Resolution (ADR 0026).
- **Static analysis context**: if step 2b produced findings, inject into every agent's prompt using the format in `skills/static-analysis-integration/SKILL.md`: "These issues were detected by static analysis. Do not re-report them. Focus on semantic concerns."
- **Per-agent output**: the shared contract in [`knowledge/review-agent-output-contract.md`](../../knowledge/review-agent-output-contract.md), wrapped with `agentName`/`modelTier` (full aggregation shape in `output-format.md`).

**Graph-assisted review**: pass tool availability to **all read-only review agents** — the structural lenses (`arch-review`, `component-architecture-review`, `structure-review`, `domain-review`) benefit most from resolved call graphs, but every lens gains cheaper verified reads — so they may consult the index for impact/dependency context before flagging findings. Tool selection and the fallback contract are the same as step 1c above; see [`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md).

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

#### 5b-i. Record round 1 (#1624)

The initial panel is **round 1**. Append its row to
`.claude/metrics/review-value.jsonl` now, before any fix is applied — this
stream is what makes #1623's "is this churn or value?" question answerable at
all, and a row written only on the happy path would bias every derived metric:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/review_round_log.py" \
  --round 1 --agents "<comma-separated agents dispatched>" \
  --findings <path-to-this-round's-findings.json> \
  --purpose discovery --outcome "<fixed|no-op|escalated>"
```

Round 1 never passes `--fix-diff`: it has no preceding fix, so its
`fix_provenance_new` is `0` by definition. The script writes counts, agent
names, and enum values only — never file paths, code, or finding text.
Full schema: `knowledge/telemetry-schema.md` § `review-value.jsonl`.

Every later round records itself the same way from step 6a — see that step's
"Record each round" item for the `--fix-diff` argument that turns
`fix_provenance_new` into the "the previous fix introduced this" signal.

#### 5c. Consolidate cross-agent findings

When multiple agents flag the same `file:line`, emit one `topFindings` entry: `severity` = the single **highest** enum for that finding, `agents` = an array of the reporting agents (e.g. `["structure-review", "complexity-review"]`). Never pack multiple values into `severity` or any agent scalar — no slash- or comma-joined strings. Every scalar field stays single-valued; multi-agent attribution lives only in the `agents: []` array. Schema: [`output-format.md`](output-format.md#aggregated-json-result---json-flag).

### 6. Present findings and ask for direction

If zero actionable issues, skip to step 7.

Otherwise present the Review Findings prompt (template: [`output-format.md`](output-format.md#review-findings-prompt-interactive--step-6)) and ask: **"Fix these issues automatically, or save as report only?"**

- "Fix" / "apply" / "yes" → step 6a
- "Report" / "no" / "don't fix" → step 7 (no code modified)

**Exception — non-interactive mode**: skip this prompt when the run is non-interactive.

- (a) If `--json` (or `--yes`), **default to report only** — proceed to step 7 and emit the aggregated JSON; **never modify code** without an explicit caller opt-in. `--json` is contractually non-interactive (CI-safe): it never blocks on this prompt.
- (b) If running inside `/build`, `/pr`, or `/test-improve`, proceed to the fix loop. The caller owns the human gate (the orchestrator's Phase 3 approval for `/build`; the pre-PR confirmation for `/pr`; for `/test-improve`, the Phase 3 Story-set approval gating entry to Phase 4 and the `[r]evise/[w]aive/[q]uit` prompt raised after 2 failed iterations of its own end-of-phase review loop — see `../test-improve/SKILL.md`'s Phase 4/5 "End-of-phase review loop" sections).

### 6a. Review-fix loop

```
iteration = 1
MAX_ITERATIONS = 5

while actionable_issues > 0 AND iteration ≤ MAX_ITERATIONS:
    1. Apply fixes for all actionable issues (file-by-file, top-to-bottom by line)
    2. After each iteration's fixes, run the project's test suite.
       If tests fail, revert the last fix that broke them and mark the
       issue [auto-fix failed — human review required].
    3. **When the review was auto-scoped to uncommitted changes** (the only
       scope that ever writes a gate file — see step 9), stage the fixes
       just applied (`git add` the modified files) — an Edit/Write only
       touches the working tree, it does not change `git diff --cached`, so
       without this the fixes would never reach the eventual commit (#1461
       security re-review: an earlier draft's step 1 claimed a working-tree
       edit "naturally" changes the staged hash — false for
       `sha256(git diff --cached)`, and it silently dropped every fix-loop
       iteration's output from the final commit). For `--path`/`--since`/
       `--all` scopes, leave the index untouched — no gate is ever written
       for those scopes, so staging here would only mutate the operator's
       index unasked, for no corroboration benefit.
    3b. **Deterministic-first triage (#1610) — language-agnostic, not
       Python-specific.** Before re-dispatching an agent to re-verify a fix,
       check whether the fix already qualifies for a cheaper, deterministic
       close: (a) it is a pure rename/mechanical edit (docstring correction,
       import fix, identifier rename), (b) **whichever language-appropriate
       lint/type-check tool(s) step 2b's static-analysis pre-pass already
       detected and ran for this repo** — Tier 1 in
       `skills/static-analysis-integration/references/tool-configs.md`
       (semgrep + ruff/mypy for Python, pmd for Java/Kotlin, ESLint/tsc for
       JS/TS, `dotnet format`/`dotnet build` for C#, gofmt/`go vet` for Go,
       etc. — whatever the target project's own stack is, never assume
       Python) — plus the full test suite already ran clean in step 2, and
       (c) the specific claim needing verification is itself checkable by a
       targeted `grep`/diff (e.g. "every occurrence was renamed, no
       partial/mangled identifiers", "the removed import has no remaining
       references"). When all three hold, run that deterministic check now
       and mark the issue resolved on a pass — do not spend a re-dispatch
       confirming what the language's own lint/test/grep tooling already
       proved. Escalate to the normal per-agent re-dispatch (step 4) whenever
       any condition fails to hold, or the check itself can't fully close the
       question (e.g. judging whether a restored docstring's *prose* is
       accurate needs semantic reading, not a grep). This is a triage habit,
       not a gate: it only ever *removes* work from step 4, never adds new
       issues or skips a fix that genuinely needs judgment. The same triage
       applies to ad-hoc fix-verification inside `/build`'s inline review
       checkpoints (`../build/SKILL.md` sub-steps 4/6) — one shared habit,
       not a duplicated checklist.
    4. Re-run only the agents whose remaining actionable issues were not
       already closed by step 3b's deterministic triage, against only the
       modified files. Carry forward statuses of agents that passed.
    5. Re-aggregate. Reclassify remaining issues.
    5b. **Record this round (#1624).** Append one row per re-dispatch round
       to `.claude/metrics/review-value.jsonl`, passing THIS iteration's fix
       diff so `fix_provenance_new` can be computed (see below).
    6. iteration += 1

if iteration > MAX_ITERATIONS AND actionable_issues > 0:
    escalate to human with remaining issues
```

**Record each round (#1624).** The initial panel was round 1 (step 5b-i);
each fix-loop iteration's re-dispatch set is one further round. Capture the
iteration's fix diff **before** re-staging (item 3) so the row can attribute
this round's new findings to the previous round's fix:

```bash
# Item 1 applied fixes; capture them as a diff, then (item 3) `git add` them.
git -c diff.relative=false diff --no-color > "$FIX_DIFF"
# …after item 5's re-aggregation:
python3 "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/review_round_log.py" \
  --round <N> --agents "<agents re-dispatched this round>" \
  --findings <this-round's-NEW-findings.json> \
  --carried <count of findings carried over from the prior round> \
  --purpose "<discovery|verification|closing>" \
  --outcome "<fixed|no-op|escalated>" \
  --fix-diff "$FIX_DIFF"
```

`fix_provenance_new` — how many of this round's new findings land inside the
line ranges the previous round's fix touched — is the judgment-free "the fix
introduced it" signal #1623 asks for. It is interval math over the diff, not
an LLM call: a round whose new error/warning findings **all** carry
provenance is churn by construction. `--purpose` distinguishes a discovery
panel from a fix-verification re-dispatch and from the gate-closing pass, so
per-agent cost can be split by purpose rather than lumped into one dispatch
count. Derived metrics (churn ratio, per-agent discovery-vs-verification
split, gate recidivism) are computed by `/harness-audit` — see its Step 4a.

**Re-establishing dispatch-ledger corroboration after the loop (#1461, auto-scope only — same condition as item 3 above).** Step 3's `git add` changes the staged content's hash, so `agent_dispatch_ledger.py` stamps each iteration's re-dispatched agents (step 4) with that NEW hash — not step 4 (the outer, pre-loop)'s original dispatch hash, and not an earlier iteration's hash either. Step 9's gate write needs **>= 2 distinct dispatches whose `subject_hash` equals the FINAL staged content's hash** (the one actually committed). Because step 4 of this loop only re-dispatches the agents that had actionable issues, a final iteration that fixes just one agent's finding re-dispatches only that one agent against the final content — insufficient on its own. **Unconditionally, after any loop iteration ran** (i.e. any fix was applied and re-staged) — not only when the count looks short, since that count isn't something to reason about from memory — re-dispatch the FULL original agent panel once more against the final staged content before proceeding to step 7. **This re-dispatch is a real review, not a rubber stamp**: if it reports any actionable issue, treat it exactly like any other iteration — re-enter this loop (subject to `MAX_ITERATIONS`) rather than proceeding to step 7. If the iteration limit is reached with issues still outstanding, follow the existing "escalate to human" exit condition below — step 9's gate-write condition explicitly excludes this case (treat it as if overall status were `fail` for that one purpose, even if every outstanding issue is only `warning`-severity), so an escalation is never silently overridden by a passing gate write. A corroboration pass whose findings carry no consequence would be exactly the "dispatch trivial calls purely to clear the gate" abuse `pre_commit_review.py`'s own module docstring names as the residual risk this mechanism does NOT protect against.

**Exit conditions**:

| Condition | Action |
| --- | --- |
| Zero actionable issues | Exit → step 7 |
| Iteration limit (5) | Exit → escalate (#1461: step 9 treats this as `fail` for its gate-write condition, even if remaining issues are only `warning`-severity) |
| Same issues persist | Exit → escalate — not converging (same #1461 step 9 treatment as the iteration-limit row: this is also an escalation with actionable issues outstanding, not a quiet exit) |
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
`.dev-team-reports/code-review.md` in the target repository's working
directory (creating the directory if absent), overwriting any existing
file at that path — write it even when the review found zero issues. Print
one confirmation line: `Report written: .dev-team-reports/code-review.md`,
or `Report written: .dev-team-reports/code-review.md (replaced previous
run)` when a file already existed at that path. If the write fails
(permission/read-only): report `Cannot write
.dev-team-reports/code-review.md: <error>` to chat and continue unaffected —
the write failure is non-fatal. When `--internal` **was** passed, skip this
write entirely (the fix loop and every other prose-mode behavior above are
unaffected — `--internal` only suppresses this one write). Then continue to
step 8.

**`--pdf` (additive, after the write).** When `--pdf` was passed and a report
file **was** written this run, render it to a sibling PDF per
`knowledge/report-pdf-integration.md`:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" .dev-team-reports/code-review.md
```

Surface the module's `Rendering PDF via <engine>…` and result lines. When no
report file was written this run (`--json` or `--internal`), `--pdf` is a
no-op: state `--pdf: no report file was written this run, nothing to render.`
and do nothing else. Under `--json`, emit that no-op line (and any render
status) to **stderr** so stdout stays valid JSON. `--pdf` never alters the
review's own output or exit status — a missing engine or render error is
non-fatal.

### 8. Save correction prompts for remaining issues

**Skip this entire step if `--json` was set.** Step 7 already stopped the run for `--json` mode; corrections are never written to disk in `--json` mode.

For issues NOT auto-fixed (confidence: none, auto-fix failed, or suggestions), generate one correction prompt per issue using the Correction prompt schema in [`output-format.md`](output-format.md#correction-prompt-json). Save to `./corrections/` **in the target repository's working directory** (the cwd `/code-review` was invoked in). Write all output artifacts only to these repo-relative paths — never prepend a scratchpad, sandbox, or session root, and never join two absolute paths. These can be addressed manually or via `/apply-fixes`.

### 9. Write pre-commit gate file

**Skip this entire step if `--json` was set** (same reason as step 8).

If the review was auto-scoped to uncommitted changes and the overall status is `pass` or `warn` **and step 6a did not exit with actionable issues outstanding** — whether via the iteration limit or the "not converging" exit, both of which are escalations, per that step's Exit conditions table (regardless of whether those outstanding issues are only `warning`-severity — either escalation overrides `warn` for this condition specifically, since escalating and then writing a passing gate anyway would silently defeat the escalation) — write `.review-passed` to `.claude/memory/` so the pre-commit hook allows the next commit. Use the **shared gate-hash helper** so the writer and the pre-commit hook compute the hash identically — it hashes the staged **content** (the cached patch), not just the file paths (#193), so any edit after review invalidates the gate:

```bash
HASH=$(python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/review_gate_hash.py)
mkdir -p .claude/memory && echo "$HASH" > .claude/memory/.review-passed
```

**If `--agent <name>` was used** (a sanctioned single-agent review — it deliberately dispatches exactly 1 agent, which can never clear the dispatch-ledger gate's `>= 2` distinct-dispatch floor on its own), record that as an explicit, auditable exemption event bound to this same hash **contemporaneously** with the write above — same pattern as the doc-only short-circuit's exemption event (step 1a):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/boundary_events.py --event single-agent --subject-hash "$HASH"
```

This step only runs when the review was auto-scoped to uncommitted changes (see the gate condition above), and that path already staged these changes in step 1, before any agent was dispatched — that ordering, not a re-stage here, is what makes this hash match the `subject_hash` `agent_dispatch_ledger.py` recorded at dispatch time (#1461), refreshed by step 6a's own re-staging when a fix loop ran. Do not `git add` a different file set at this point: staging something here that wasn't already staged (and therefore wasn't the reviewed, dispatch-hashed content) would write a gate hash with no corroborating dispatch evidence behind it.

If overall status is `fail`, do **not** write the gate file — the pre-commit hook will keep blocking until issues are resolved and the review re-run.
