---
name: semantic-duplication-scan
description: >-
  Detect business logic reimplemented in multiple architectural layers. Builds a
  persistent computation-register.json by annotating non-trivial computation
  functions with structured semantic descriptions, then clusters entries to
  surface duplicate domain concepts. Runs in full-scan mode on first use,
  incremental (git-diff-based) mode on subsequent runs. Use when the user wants
  to find logical duplication that linters and diff-scoped review agents miss —
  the same domain calculation independently reimplemented across layers.
role: worker
user-invocable: true
---

# Semantic Duplication Scan

## Overview

Detect business logic that has been reimplemented multiple times across different architectural layers. Unlike linters (which detect syntactic similarity) or `domain-review` (which catches single-instance layer violations), this skill detects semantic equivalence — the same domain calculation independently appearing in domain services, client adapters, and presentation components with different variable names and structure.

## Annotation Prompt Version

**promptVersion**: `1.0`

When this version changes, any register entry with a different `promptVersion` is treated as stale and re-annotated on the next scan pass that touches that file.

---

## Pre-Filter Rules

**Apply before any LLM call. No model invocation at this stage.**

### Trivial Function Definition

A function is **trivial** — and must be excluded from the register — if it meets ALL of the following:

- Contains **no arithmetic operators**: `+`, `-`, `*`, `/`, `%`, `**`
- Contains **no boolean logic operators**: `&&`, `||`, `!`, `not`, `and`, `or`
- Contains **no branching constructs**: `if`, `else`, `switch`, `case`, `ternary` (`?:`), `match`
- Contains **no assignments to variables outside its own scope** (no external state mutation)
- Contains **no calls to higher-order collection operations**: `map`, `filter`, `reduce`, `flatMap`, `forEach`, `find`, `some`, `every`, or language equivalents

Trivial patterns (always excluded):
- Getters: read and return a field with no transformation
- Pass-through delegators: call one function with the same arguments, return the result unchanged
- Identity functions: return the input unchanged
- Constructors / initializers that only assign parameters to instance fields

If a file contains **only trivial functions**, output:

```
No computation units found to analyze
```

and do not create or modify the register.

### File Exclusion Patterns

Exclude the following from annotation regardless of content:

```
*.test.*
*.spec.*
__tests__/
*.test-d.*
*.generated.*
*.pb.*
*.d.ts
dist/
build/
.next/
coverage/
```

Also exclude any path matching a pattern listed in `.semanticscanignore` (one glob per line) if that file exists in the project root.

---

## Process Flow

### Step 1 — Mode Detection

Check for `computation-register.json` in the project root:
- **Absent** → full-scan mode
- **Present** → incremental mode

### Step 2 — Pre-Flight (Incremental Mode Only)

Run: `git rev-parse --is-shallow-repository`

If output is `true`:
- Output the exact string: `Shallow clone detected — semantic-scan requires full history for incremental mode. Run with --full to override.`
- Exit non-zero

If `--full` flag was passed: skip this check and force full-scan mode.

If `lastScanCommit` in the register is not found in git history:
- Output: `lastScanCommit not found in history — running full scan`
- Switch to full-scan mode

### Step 3 — Scope Resolution

1. If a path argument was provided (e.g., `/semantic-scan src/pricing`), use it as a prefix filter: only consider files whose paths start with the argument
2. Apply `.semanticscanignore` patterns: exclude any file matching a listed glob
3. Apply file exclusion patterns from the Pre-Filter Rules above

### Step 4 — File Selection

**Full-scan mode**: Glob all source files in the resolved scope.

**Incremental mode**: Run `git diff <lastScanCommit> HEAD --name-only`, then filter to files in the resolved scope.

If the git diff result is empty (no files changed since `lastScanCommit`):
1. Update `lastScanCommit` to HEAD in the register and write the updated register
2. Output: `No changes since last scan — register up to date`
3. Exit 0 — do not proceed to annotation or clustering

**Graph-assisted file/function discovery.** If the target repo has `.codegraph/`
(CodeGraph MCP server, `mcp__codegraph__codegraph_explore` — enumerate symbols
and their call sites fast) and/or a Repowise MCP server (`search_codebase` —
semantic search across the whole codebase, `get_context` — verified context
per file/symbol), prefer them over raw `Glob`/`Read` for locating candidate
computation functions across layers. Repowise's semantic search is
particularly well suited here — it is built for exactly the kind of
similarity search this skill needs to find the same domain concept
reimplemented in different layers. Never assume either is present — fall
back to `Glob`/`Read` when absent; the tools are simply unavailable (no
error) on repos without an index.

### Step 5 — Pre-Filter

For each selected file, identify non-trivial computation functions using the Trivial Function Definition above. Apply without an LLM call — use structural heuristics (presence of operators, branches, higher-order calls).

If no non-trivial functions remain after filtering:

- **First run**: `No computation units found to analyze` → exit 0, no register created
- **Incremental run**: `No new computation units found in changed files — register unchanged` → exit 0, register not modified

### Step 6 — Annotation (Haiku, file-level batching)

For each file with non-trivial functions:

1. Emit progress to stderr: `Annotating [N/total] <filename>`
2. Send all non-trivial functions from the file in a single Haiku call using the pinned prompt below
3. If the call fails, record `{file, error}` in `scanErrors` and continue — do not abort

**Annotation prompt (pinned — do not paraphrase):**

```
You are a semantic annotation assistant. For each function below, produce a JSON object describing what it computes in pure domain business terms.

Use this schema:
{
  "function": "<function name>",
  "layer": "<inferred layer — see rules below>",
  "semanticDescription": {
    "verb": "<lowercase infinitive verb>",
    "domainConcept": "<lowercase, no articles, normalized>",
    "inputs": ["<domain term>", ...],
    "outputConcept": "<domain term>"
  }
}

Layer inference rules — infer from what the function imports and uses:
- "infrastructure": imports DB clients, ORMs, HTTP clients, message brokers (pg, redis, axios, fetch, prisma, mongoose, etc.)
- "presentation": imports rendering primitives, formats for display, accesses DOM or templates (React, Vue, Svelte, JSX, HTML templates, etc.)
- "domain": depends only on domain types and pure functions, no external imports
- "application": orchestrates domain and infrastructure without owning business rules
- "unknown": cannot be determined from available context

domainConcept rules:
- Use lowercase
- Remove articles: a, an, the
- Normalize the verb to infinitive form
- Example: "calculates the discounted price" → domainConcept: "discounted price", verb: "calculate"

Describe only what the function computes in domain terms. Do not reference the implementation language, variable names, or data structure types.

Functions:
<paste function source here>
```

**Canonicalize `domainConcept` after receiving the response:**
1. Lowercase
2. Strip leading/trailing articles: `a `, `an `, `the `
3. Normalize verb in the `verb` field to infinitive (e.g., "calculates" → "calculate", "computing" → "compute")

### Step 7 — Register Update

Build a register entry for each annotated function:

```json
{
  "file": "<relative path from project root>",
  "function": "<function name>",
  "layer": "<inferred layer>",
  "semanticDescription": {
    "verb": "<canonicalized>",
    "domainConcept": "<canonicalized>",
    "inputs": ["<domain term>", ...],
    "outputConcept": "<domain term>"
  },
  "promptVersion": "1.0",
  "commitHash": "<HEAD commit hash>",
  "line": <first line of function definition>
}
```

**Merge strategy:**
- Replace all entries whose `file` matches a re-annotated file
- Remove entries whose `file` no longer exists on disk
- Remove entries for files matching `.semanticscanignore` patterns
- Preserve all other entries unchanged

**Idempotency:** Sort the full entry list by `file` ascending, then `function` ascending before writing.

**Write the register.** If the write fails (permissions, disk full):
- Output the exact path that could not be written and the OS error
- Exit non-zero

**Update `lastScanCommit`** to the current HEAD commit hash after successful write.

**Report partial failures.** After writing (only if `scanErrors` is non-empty):
- N=1: `Warning: 1 file could not be annotated. Re-run /semantic-scan to retry.`
- N>1: `Warning: N files could not be annotated. Re-run /semantic-scan to retry.`

Exit code 0 — partial success is not a failure.

---

## Clustering

### Token Budget and Partitioning

The full register may be too large to cluster in a single call. Use layer-pair sharding:

Shard the register by layer pair before sending to Sonnet:
- `domain × presentation`
- `domain × infrastructure`
- `application × presentation`
- `application × infrastructure`
- `domain × application`

For each shard: if the shard exceeds **50,000 tokens**, further shard by the first normalized token of `domainConcept` (split alphabetically into sub-groups).

After per-shard clustering, run a **cross-shard reconciliation pass**: send only the cluster representatives (one entry per cluster, the top-ranked candidate) back to Sonnet to catch equivalents that landed in different shards. Keep this merge input under 50,000 tokens.

### Clustering Call (Sonnet)

For each shard, emit progress: `Clustering [layer-pair]: <layer-a> × <layer-b>...`

**Clustering prompt (pinned — do not paraphrase):**

```
Group these register entries by semantic equivalence — entries that compute the same domain concept regardless of implementation differences. Return clusters as JSON arrays of entry IDs (use "file:function" as the ID).

Two entries belong in the same cluster ONLY IF both would need to change if the underlying business rule changed.

Input entries:
<paste shard entries as JSON array>

Return only:
{ "clusters": [["file1:funcA", "file2:funcB"], ...] }

Entries that are semantically unique should not appear in any cluster.
```

---

## Canonical Scoring

For each cluster with 2 or more entries:

**Layer rank** (higher = more canonical):
1. `domain`
2. `application`
3. `presentation`
4. `infrastructure`
5. `unknown`

**Within the same layer rank:** count infrastructure imports in the function's file; fewer imports = higher rank.

**Ambiguity predicate:** If the top two candidates tie on layer rank AND differ by ≤1 infrastructure import → escalate to Opus.

Before the Opus call, emit: `Resolving ambiguous canonical for cluster: <domainConcept>...`

**Opus prompt:**

```
Given these N entries that all compute the same domain concept, which one is the most appropriate canonical location for the business rule? Consider: domain purity, reusability, and least coupling to delivery mechanism. Return the file:function ID of the preferred canonical and a one-sentence rationale.

Entries:
<paste cluster entries>
```

If `--no-opus` flag was passed: skip Opus escalation. Report ambiguous clusters as:
```
canonical: ambiguous — human review required
```

### Canonical Verdict Output

- Clear winner (domain or application layer, no tie): `canonical: suggested <file:line> — requires human confirmation`
- No winner (all infrastructure/unknown, or tie unresolved): `canonical: none — a new domain-layer implementation may be required`

**Cross-scope notice** (scoped runs only): If a cluster contains entries outside the scoped path:
```
Note: this cluster includes <N> entry/entries outside the scoped path — run without scope argument to see full context
```
(Use "entry" when N=1, "entries" when N>1.)

---

## Report

After clustering is complete:

**Duplicates found:**

```
## Semantic Duplication Report

### Cluster: <domainConcept>

  - <file>:<line> [<layer>]  ← inferred canonical (or all entries if no canonical)
  - <file>:<line> [<layer>]

  canonical: suggested <file:line> — requires human confirmation
  [Note: this cluster includes N entry/entries outside the scoped path ...]

---
```

**No duplicates:**

```
No semantic duplication detected
```

**`file:line` accuracy:** Line numbers point to the first line of the function definition. If the file has been modified since annotation, append: `(line may have shifted — re-run scan to refresh)`

