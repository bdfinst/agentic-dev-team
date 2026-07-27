---
name: test-design
description: >-
  Deep test-design review and forward-design advisor. Dispatches test-review
  (tactical quality) and test-smell-review (xUnit smells, double selection,
  pyramid placement) in parallel, and runs the test-design-advisor worker
  to recommend how to test hard-to-test code. Use when the user says "review
  my tests", "how should I test this", "is this testable", "design tests for
  this", "what's the right test for X", "test design review", or before
  writing a suite for an untested module. For a single unit, pass
  --advise --path <file>. Advisory — it recommends, it does not edit.
argument-hint: "[--path <dir>] [--since <ref>] [--advise]"
role: orchestrator
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *), Skill, Agent
---

# Test Design

Role: orchestrator. This command dispatches the two test review agents as
sub-agents and the test-design-advisor skill, then aggregates one report. It
does not review files itself — it coordinates.

This command is executed under orchestrator direction. Dispatch each agent with
its `model:`/`effort:` frontmatter as declared — the harness resolves both
fields natively before dispatch, per Model/Effort Resolution in
`agents/orchestrator.md` (ADR 0026).

## Orchestrator constraints

1. **Advisory only.** Aggregate findings and recommendations. Do not edit
   production code or write test files. Hand actionable fixes to `/apply-fixes`
   or `/build`.
2. **Dispatch in parallel.** `test-review` and `test-smell-review` are
   independent — spawn them in one batch for context isolation; each returns
   structured JSON, not file dumps.
3. **No double-reporting.** Apply `knowledge/test-review-division-of-labor.md`:
   when the same line appears in both `test-review` and `test-smell-review`,
   keep the design-level framing and drop the duplicate — record every such
   drop in the report's `### Suppressed duplicates` section (see step 6).
   For `test-smell-review` and `test-design-advisor`, no de-duplication is
   required: per the "test-smell-review ↔ test-design-advisor — remedy
   division" section of the knowledge doc, the smell agent cites the remedy
   family (via `remedyFamily`) and the advisor names the specific remedy
   pattern and refactor sequence — smell rows and advisor rows join
   structurally on `remedyFamily`, not by prose match.
4. **Be concise.** One aggregated report. Issue messages one sentence;
   recommendations map to a concrete next edit.
5. **MinimumCD vocabulary.** Layer labels in the aggregated report use the
   MinimumCD six test types (static analysis / unit / component / contract /
   integration / E2E) from `knowledge/cd-test-architecture.md`. Prefer
   "contract test" over "narrow integration test"; if you must use the
   alias, gloss it once: `contract test (also called narrow integration
   test)`. Define each test type on first use (one-line gloss inline or
   a "Test type definitions used in this report" block at the top).
6. **No target-shape tables.** Per
   `knowledge/cd-test-architecture.md#the-pyramid-is-a-cost-heuristic-not-a-target-shape`,
   do not emit "current shape vs recommended shape" tables or per-layer target
   counts; the aggregated report carries the advisor's per-behavior placement
   table, not a silhouette target.
7. **E2E justification gate.** Forward the advisor's four-condition E2E verdict
   verbatim (the gate is canonical in
   `knowledge/cd-test-architecture.md#the-e2e-justification-gate`). Never
   recommend E2E in the rollup without it.

## Parse Arguments

Arguments: $ARGUMENTS

Optional:

- `--path <dir>`: target directory (default: current working directory)
- `--since <ref>`: target files changed since a git ref (`git diff --name-only <ref>...HEAD`)
- `--advise`: also run the test-design-advisor skill for forward-looking design (default on when the target has untested production code or few/no test files, **or when the target resolves to a single production file** — via `--path <file>` or a `--since` diff that touches exactly one production file; this is the path for forward-design on a single unit — the `test-design-advisor` skill has no user-facing slash command)

## Steps

### 1. Determine target files

Same auto-scope logic as `/code-review`: uncommitted changes if present, else
all source files; honor `--since` and `--path`. Identify test files and the
production code they cover.

**Single-file → auto-`--advise`.** If the resolved target is exactly one
production file (`--path <file>` pointing at a production source file, or a
`--since` diff whose production set has one file), set `--advise` on for this
run and record it in the report header. This is the entry path for
forward-design on a single unit (the `test-design-advisor` worker skill has
no user-facing slash command).

### 2. Dispatch review agents (parallel)

Spawn both as sub-agents in one batch:

- `test-review` — tactical quality gate (assertions, hygiene, non-determinism mechanics, testability blockers)
- `test-smell-review` — xUnit smells, test-double selection, pyramid-layer placement

Each returns its standard JSON (`status`/`issues`/`summary`). If no test files
exist, both skip — proceed to Step 4 with `--advise`.

### 3. Score the in-scope tests (Farley Score)

Using the file set already resolved in Step 1 (Step 1 is the single
scope-resolution authority in this skill), invoke `Skill(farley-score ...)`
to produce the Farley Score, rating, and distribution. Label the score with
the scope it was computed over:

- No `--path` / no `--since` → every test file in the repository (test-file
  indicators in `knowledge/test-file-indicators.md`); label `all tests`.
- `--path <dir>` → tests under `<dir>` or covering production code under
  `<dir>`; label `under <dir>`.
- `--since <ref>` → tests touched in the diff plus tests covering production
  files touched in the diff; label `changed since <ref>`.
- `--path <dir>` and `--since <ref>` together → tests under `<dir>` that are
  also touched (directly or via covered production code) since `<ref>` — the
  intersection of both sets; label `under <dir>, changed since <ref>`.
- Empty in-scope test set → skip the score and print `no in-scope test files`
  in the report instead of a number.

### 4. Run the advisor (when applicable)

If `--advise` is set (or auto-triggered), use the Skill tool (`Skill(test-design-advisor ...)`) on the production code to produce testability assessment, pyramid
placement, double strategy, and a behavior-preserving refactor sequence for
any untestable units.

### 5. Aggregate and de-duplicate

Merge findings. Resolve overlaps per constraint 3. Group by file. Rank:
behavior/project smells and testability blockers first (they undermine the
whole suite), then fragile/obscure smells, then suggestions.

### 6. Report

Produce one report (chat for a small target; `.dev-team-reports/test-design-<date>.md`
for a module):

```markdown
## Test Design Review — <target>

**Health**: <pass|attention|critical>   **Test files**: N   **Findings**: N
**Farley Score (<scope>)**: <score> (<rating>) — Exemplary N · Good N · Adequate N · Poor N

`<scope>` is the label produced by Step 3; render it verbatim. Concrete
forms: `Farley Score (all tests)`, `Farley Score (under <dir>)`,
`Farley Score (changed since <ref>)`, `Farley Score (under <dir>, changed since <ref>)`.
When the in-scope set was empty, replace the whole line with
`**Farley Score**: no in-scope test files`.

### Test type definitions used in this report
<one-line glosses for MinimumCD terms appearing below; verbatim from
`knowledge/cd-test-architecture.md` § The Six Test Types — at minimum
the terms actually used in the report>

### Findings (by severity)
| File:line | Smell / Issue | Severity | Source | Suggested fix |

### Design recommendations (advisor)
<testability table · pyramid placement (per-behavior, two-direction
justification, NO target counts) · double strategy · refactor sequence ·
E2E justification (only when E2E is recommended)>

### Suppressed duplicates
<Every drop constraint 3 performed at aggregation time. Each entry cites the
finding's `file:line`, what was dropped (which agent's finding, keyed by
smell/message), and the reason (e.g. "mechanics duplicate of Assertion
Roulette owned by test-smell-review"). test-smell-review ↔ test-design-advisor
overlaps are never listed here — they are joined structurally on
`remedyFamily`, not dropped. Emit `_None._` when nothing was dropped.>

### Next steps
- Mechanical fixes → /apply-fixes
- Refactor sequence → /plan or /build
```

Surface only what's actionable. If everything is clean, say so in one line.
Do NOT include a "current shape vs recommended shape" table — see Orchestrator
constraint #6.
