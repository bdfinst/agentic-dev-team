---
name: test-design
description: >-
  Deep test-design review: dispatch test-review (tactical quality) and
  test-smell-review (xUnit smells, double selection, pyramid placement) in
  parallel, then run the test-design-advisor skill to recommend how to test
  hard-to-test code. Use when the user says "review my tests", "how should I
  test this", "is this testable", "test design review", or before writing a
  suite for an untested module. Advisory — it recommends, it does not edit.
argument-hint: "[--path <dir>] [--since <ref>] [--advise]"
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *), Skill, Agent
---

# Test Design

Role: orchestrator. This command dispatches the two test review agents as
sub-agents and the test-design-advisor skill, then aggregates one report. It
does not review files itself — it coordinates.

This command is executed under orchestrator direction. Dispatch each agent with
its tier alias (from its `model:` frontmatter); the PreToolUse hook
`hooks/agent-model-resolve.sh` resolves it to the active snapshot per the
Resolution Procedure in `agents/orchestrator.md`.

## Orchestrator constraints

1. **Advisory only.** Aggregate findings and recommendations. Do not edit
   production code or write test files. Hand actionable fixes to `/apply-fixes`
   or `/build`.
2. **Dispatch in parallel.** `test-review` and `test-smell-review` are
   independent — spawn them in one batch for context isolation; each returns
   structured JSON, not file dumps.
3. **No double-reporting.** `test-smell-review` defers tactical mechanics to
   `test-review`. When the same line appears in both, keep the design-level
   framing and drop the duplicate.
4. **Be concise.** One aggregated report. Issue messages one sentence;
   recommendations map to a concrete next edit.

## Parse Arguments

Arguments: $ARGUMENTS

Optional:

- `--path <dir>`: target directory (default: current working directory)
- `--since <ref>`: target files changed since a git ref (`git diff --name-only <ref>...HEAD`)
- `--advise`: also run the test-design-advisor skill for forward-looking design (default on when the target has untested production code or few/no test files)

## Steps

### 1. Determine target files

Same auto-scope logic as `/code-review`: uncommitted changes if present, else
all source files; honor `--since` and `--path`. Identify test files and the
production code they cover.

### 2. Dispatch review agents (parallel)

Spawn both as sub-agents in one batch:

- `test-review` — tactical quality gate (assertions, hygiene, non-determinism mechanics, testability blockers)
- `test-smell-review` — xUnit smells, test-double selection, pyramid-layer placement

Each returns its standard JSON (`status`/`issues`/`summary`). If no test files
exist, both skip — proceed to Step 4 with `--advise`.

### 3. Score all existing tests (Farley Score)

A user-requested test review reports a quality score for the whole suite, not
just the changed slice. Invoke the `test-design-reviewer` skill over **all
existing test files in the repository** (use the test-file indicators from
`agents/test-review.md` § Skip) to produce the suite-level Farley Score, rating,
and distribution. This headline score is independent of `--path` / `--since` —
those scope the findings below; the score always reflects the full suite. If the
repository has no test files, skip this step and note it in the report.

### 4. Run the advisor (when applicable)

If `--advise` is set (or auto-triggered), invoke the `test-design-advisor`
skill on the production code to produce testability assessment, pyramid
placement, double strategy, and a behavior-preserving refactor sequence for
any untestable units.

### 5. Aggregate and de-duplicate

Merge findings. Resolve overlaps per constraint 3. Group by file. Rank:
behavior/project smells and testability blockers first (they undermine the
whole suite), then fragile/obscure smells, then suggestions.

### 6. Report

Produce one report (chat for a small target; `reports/test-design-<date>.md`
for a module):

```markdown
## Test Design Review — <target>

**Health**: <pass|attention|critical>   **Test files**: N   **Findings**: N
**Farley Score (all existing tests)**: <score> (<rating>) — Exemplary N · Good N · Adequate N · Poor N

### Findings (by severity)
| File:line | Smell / Issue | Severity | Source | Suggested fix |

### Design recommendations (advisor)
<testability table · pyramid placement · double strategy · refactor sequence>

### Next steps
- Mechanical fixes → /apply-fixes
- Refactor sequence → /plan or /build
```

Surface only what's actionable. If everything is clean, say so in one line.
