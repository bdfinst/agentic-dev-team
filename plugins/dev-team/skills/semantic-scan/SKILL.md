---
name: semantic-scan
description: >-
  Build a computation register and detect semantic duplicates across architectural
  layers. Finds business logic reimplemented multiple times in different layers —
  the same domain calculation independently appearing in domain services, client
  adapters, and presentation components. Runs incrementally (git-diff-based) after
  the first scan. Produces a structured duplicate report with file:line references
  and canonical location suggestions.
argument-hint: "[path] [--full] [--no-opus]"
user-invocable: true
---

# Semantic Scan

Role: worker.

## Worker constraints

1. Detect and report duplicates; do not refactor.
2. Run incrementally (git-diff based) after the first scan.
3. **Be concise.** Report the duplicate table with file:line refs, no narration.

## Steps

### 1. Parse arguments

Capture the optional path and flags from `$ARGUMENTS`.

### 2. Delegate

Invoke the semantic-duplication-scan skill.

**Graph-assisted discovery.** Prefer CodeGraph/Repowise over raw `Grep`/`Read`
when locating and comparing candidate implementations — Repowise's semantic
search is especially well suited to finding duplicate implementations across
layers. See
[`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md)
for tool selection and the fallback contract.

### 3. Report

Output the duplicate report.

Apply the guidelines defined in skills/semantic-duplication-scan/SKILL.md to the current task. Read the skill file and follow its process flow, pre-filter rules, annotation procedure, clustering strategy, and report format.

## Flags

- `[path]` — Optional subdirectory to scope the scan. Only files under this path are re-annotated; out-of-scope register entries are preserved.
- `--full` — Force full-scan mode regardless of whether a register exists. Bypasses the shallow-clone pre-flight check. Use when `lastScanCommit` is stale or after a major restructuring.
- `--no-opus` — Skip Opus canonical resolution for ambiguous clusters. Ambiguous clusters are reported as `canonical: ambiguous — human review required` instead of triggering an Opus call. Use in cost-sensitive environments (CI, personal accounts).

Apply this skill to: $ARGUMENTS
