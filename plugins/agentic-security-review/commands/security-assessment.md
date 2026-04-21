---
name: security-assessment
description: Full security assessment pipeline — reconnaissance, SARIF-first tool detection, business-logic + security review, FP-reduction, narrative + compliance mapping, service-comm diagram, executive report. Single-repo or multi-repo (emits per-repo + cross-repo reports).
argument-hint: "<path> [<path> ...] [--start <phase>] [--agents <phase> ...] [--fp-reduce=yes|no]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
---

# /security-assessment

You have been invoked with the `/security-assessment` command.

## Role

Orchestrator for the full static-analysis pipeline defined in `skills/security-assessment-pipeline/SKILL.md`. Dispatches per phase; passes artifacts via `memory/`; produces a publication-ready exec report per target repo (plus a cross-repo summary if multiple targets).

Matches the `opus_repo_scan_test` reference's four-phase structure with tool-first detection replacing the reference's prompt-heavy scanning.

## Constraints

1. **Follow the pipeline exactly.** See the skill's phase graph. The orchestration is deterministic; decisions are surfaced to the user via the final report's Top 3 Actions, not made autonomously mid-run.
2. **Never silently drop findings.** Every input finding flows through to either the published report or a suppression appendix with reason.
3. **Artifacts are the source of truth.** Every phase writes to `memory/`; `--start` and failure-recovery rely on that.
4. **Informational-not-audit-grade.** Every produced report carries the compliance-mapping disclaimer verbatim at the header.

## Parse arguments

Arguments: $ARGUMENTS

**Positional:** one or more directory paths (target repos).

**Flags:**
- `--start <phase>`: resume from phase (0 / 1 / 1b / 2 / 3 / 4 / 5). Requires prior phase artifacts in memory/.
- `--agents <phase> [<phase> ...]`: run only the listed phases. Dependency check skipped.
- `--fp-reduce=yes|no`: skip Phase 2 FP-reduction when `no` (speeds assessment at the cost of false-positive noise). Default `yes`.

Parse flags out; remaining positionals are target paths.

## Steps

### 1. Validate arguments

- At least one target path required.
- Each target path must be a directory (not a file).
- For each target: consult ACCEPTED-RISKS.md if present at that target's root; load matched-rules into a shared suppression context.

### 2. Initialize run

For each target repo, derive a slug from its directory name (kebab-cased, lowercased). Multi-repo runs use dash-joined slug for cross-repo artifacts.

Create `memory/audit-<slug>.jsonl` (append-only). Record run start with targets, flags, and contract version.

If a prior run's artifacts exist AND `--start` is NOT set, archive them to `memory/archive/<timestamp>/` before overwriting.

### 3. Execute phase graph

For each target repo, run phases 0 → 5 per the pipeline skill. Between targets, phases can interleave if independent (e.g. Phase 0 of repo A + Phase 0 of repo B run in parallel subagent dispatches).

**Phase 0 — Reconnaissance.** Dispatch `codebase-recon` (opus) via Agent tool. Write `memory/recon-<slug>.json` + `.md`. Verify schema conformance against `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json`.

**Phase 1 — Tool-first detection.** Invoke the `static-analysis-integration` skill's SARIF pipeline over the target. For each available tool (semgrep, gitleaks, trivy, hadolint, actionlint, plus Step 3b optional/bespoke when available), run its invocation and normalize output to unified findings. Stream into `memory/findings-<slug>.jsonl`.

**Scope includes CI/CD workflow files.** The target walk must include `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/config.yml`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `Jenkinsfile`, and their respective subdirectories — see `plugins/agentic-dev-team/skills/static-analysis-integration/SKILL.md` § "Target walk" for the full list. These files are in scope for scan-06 (CI/CD security): printenv in `run:` blocks, `continue-on-error: true` on security steps, excessive `permissions:` blocks, hardcoded PAT embedding, `npm audit` / `pip audit` behind `continue-on-error`. actionlint is the canonical tool but semgrep with `p/github-actions` catches the same patterns when actionlint is unavailable. If the target lacks ALL of these files, record `ci_dirs_scanned: []` in the summary — the exec report can then surface "no CI configuration in scope" as a Top 3 Actions item if a CI config would be expected.

Also invoke the two custom scripts:
- `plugins/agentic-dev-team/tools/entropy-check.py` on target
- `plugins/agentic-dev-team/tools/model-hash-verify.py` on target

Their SARIF outputs flow through the shared parser.

**Phase 1b — Judgment detection.** Dispatch in parallel (Agent tool with multiple calls in one message):
- `security-review` (opus; reads RECON + target files)
- `business-logic-domain-review` (opus; reads RECON + target files + `knowledge/domain-logic-patterns.md`)

Append their findings to `memory/findings-<slug>.jsonl`.

**Phase 1c — ACCEPTED-RISKS suppression (mandatory gate).** Runs exactly once after all Phase 1 + 1b findings have been collected, before Phase 2 begins. Procedure:

1. For each target, check for `ACCEPTED-RISKS.md` at the target root. Absent → skip this target; log `no ACCEPTED-RISKS.md; proceeded with all findings`.
2. Parse the YAML frontmatter (`rules:` list) per `plugins/agentic-dev-team/knowledge/accepted-risks-schema.md`. A schema-invalid file fails the run with a named parse error; do not silently skip.
3. Validate rules: every rule must have `id`, `rule_id`, `files[]`, `rationale` (≥ 50 chars), `expires` (ISO-8601), `owner`, `scope`. Wildcards in `rule_id` require `broad: true`.
4. For each finding in `memory/findings-<slug>.jsonl`, iterate rules in file-declaration order. First matching rule wins (per the schema's matching algorithm): match when rule's `rule_id` pattern matches the finding's `rule_id` AND one of the rule's `files[]` globs matches the finding's `file`.
5. Expired rules (past `expires` date) become inert — they stop suppressing and emit a WARN naming the rule + owner; listed in the audit log.
6. Matched findings are written to `memory/suppressed-<slug>.jsonl` (one per line, each with a `_suppressed_by` field naming the rule id). The matched findings are removed from `memory/findings-<slug>.jsonl` and do NOT advance to Phase 2. Emit exactly one audit log entry per suppression: `SUPPRESSED: <file>:<line> [<rule_id>] by ACCEPTED-RISKS rule <rule.id>`.
7. After filtering, write `memory/suppression-log-<slug>.jsonl` (the audit entries) and record in the final report's Appendix C per `agents/exec-report-generator.md` § Section 7.

**This step is mandatory when `ACCEPTED-RISKS.md` is present.** The exec report's Appendix C is populated from `memory/suppressed-<slug>.jsonl`; if that file is absent or empty AND `ACCEPTED-RISKS.md` existed, the run surfaces a warning about the missed gate.

**Phase 2 — FP-reduction.** Skip if `--fp-reduce=no`. Otherwise dispatch `fp-reduction` (opus). Produces `memory/disposition-<slug>.json`. Log `reachability_tool` (joern-cpg or llm-fallback) to audit.

**Phase 3 — Narrative + compliance.** Dispatch in parallel:
- `tool-finding-narrative-annotator` (sonnet) → `memory/narratives-<slug>.md`
- `compliance-mapping` skill → `memory/compliance-<slug>.json` (invokes `compliance-edge-annotator` only for `llm_review_trigger: true` matches per the skill)

**Phase 4 — Service-communication.** Run `plugins/agentic-security-review/harness/tools/service-comm-parser.py` against the target. For multi-repo runs, pass all targets at once so cross-service edges are captured.

**Phase 5 — Report generation.** Dispatch `exec-report-generator` (opus). Single-repo: produces `memory/report-<slug>.md`. Multi-repo: produces per-repo reports + `memory/cross-repo-summary-<slug>.md`.

### 4. Surface summary

Print:
```
Security assessment complete.

  Target(s): <list>
  Phases run: <list of phase numbers>
  Artifacts:
    memory/recon-<slug>.{json,md}
    memory/findings-<slug>.jsonl (<N> unified findings)
    memory/disposition-<slug>.json (<N> entries, <X>% true_positive or likely_true_positive)
    memory/narratives-<slug>.md
    memory/compliance-<slug>.json (<N> annotations, <M> triggered LLM)
    memory/service-comm-<slug>.mermaid
    memory/report-<slug>.md (CRITICAL: <N>, HIGH: <N>, MEDIUM: <N>, LOW: <N>)
    (+ memory/cross-repo-summary-<slug>.md for multi-repo)

  Run `/export-pdf <report>.md` to produce a PDF.
  Run `/cross-repo-analysis <path1> <path2>` for cross-repo attack-chain analysis if not already included.
```

## Escalation

Stop and ask the user when:
- No target paths are provided.
- Any target path is not a directory.
- `--start` is set but the required precondition artifacts are missing.
- Phase 0 (recon) fails on any target — there is no meaningful downstream without it.
- More than 3 phases fail in a single target run — the pipeline output is no longer trustworthy; escalate rather than emit a misleading report.

## Integration

- Built atop the `security-assessment-pipeline` skill — that skill defines the phase graph and invariants; this command is the user-facing entry point.
- Paired with `/cross-repo-analysis` for multi-repo attack-chain synthesis. Single-repo assessments do not need it.
- Paired with `/export-pdf` for report export.
- Consumes primitives from `plugins/agentic-dev-team/` via the contract at `knowledge/security-primitives-contract.md`.
