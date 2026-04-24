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

#### Parallelization requirements

Wall time matters for real-world assessments. Three parallelism rules **MUST** be observed by the orchestrator:

1. **Multi-target fan-out.** When invoked with multiple targets, each target's Phase 0 through Phase 2b runs as an **independent pipeline**. Dispatch them as **parallel Agent tool calls in the SAME message** — not sequential. Each target's pipeline is self-contained until Phase 4 (service-comm across targets) and Phase 5 (cross-repo summary). For N targets on a machine with K cores, expect N-way wall-time parallelism up to K.

2. **Intra-phase fan-out.** Within a phase with multiple agents or tools:
   - Phase 1b dispatches `security-review` AND `business-logic-domain-review` as parallel Agent tool calls in one message
   - Phase 3 dispatches `tool-finding-narrative-annotator` AND `compliance-mapping` as parallel Agent tool calls in one message
   - Phase 1's static-analysis-integration skill dispatches every available tool (semgrep variants + gitleaks + trivy + hadolint + actionlint + custom scripts) as concurrent shell processes, not sequentially

3. **Phase 4 runs concurrently with Phase 1b–3 once Phase 0 finishes.** Phase 4 (service-communication) depends only on Phase 0. Do NOT block Phase 4 behind Phase 3 — it can start as soon as Phase 0 completes and run alongside everything between Phase 1 and Phase 5.

**Why this matters**: LLM agent phases dominate wall time. Sequential dispatch of two opus agents for Phase 1b costs ~2× the parallel dispatch cost, burning 2-5 minutes per target unnecessarily. Multi-target pipelines run sequentially by default (the LLM reads "for each target" as a loop) unless the spec explicitly calls for parallel fan-out — which this section does.

#### Phase timing (mandatory)

Every phase is bracketed with `scripts/phase-timer.sh start <phase> <slug>` at its beginning and `scripts/phase-timer.sh end <phase> <slug>` at its end. Writes accumulate in `memory/phase-timings-<slug>.jsonl` (one JSONL record per start and per end).

The exec-report-generator reads this file to compute actual parallelism vs. sequential execution and surfaces the result in Section 6 § Phase timings. Drift from the intended parallelism shows up visibly in the published report.

Phases to instrument:

```
phase-0-recon
phase-1-tool-first
phase-1b-judgment
phase-1c-accepted-risks
phase-2-fp-reduction
phase-2b-severity-floors
phase-3-narrative-compliance
phase-4-cross-repo
phase-5-report
```

**Phase 0 — Reconnaissance.** Dispatch `codebase-recon` (opus) via Agent tool. Write `memory/recon-<slug>.json` + `.md`. Verify schema conformance against `plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json`.

**Phase 1 — Tool-first detection.** Invoke the `static-analysis-integration` skill's SARIF pipeline over the target. For each available tool (semgrep, gitleaks, trivy, hadolint, actionlint, plus Step 3b optional/bespoke when available), run its invocation and normalize output to unified findings. Stream into `memory/findings-<slug>.jsonl`.

**CI/CD scope widening (deterministic).** Before running tools, enumerate CI files with the deterministic script:

```bash
scripts/find-ci-files.sh <target-dir>
```

This covers GitHub Actions, GitLab CI, CircleCI, Azure Pipelines, Bitbucket Pipelines, and Jenkins — walking up to parent directories when the target is a service subdirectory whose CI lives at the repo root. Pass every CI path on stdout to actionlint (if available) and to semgrep with `p/github-actions`. If the script prints zero paths AND the run is expected to find CI config (target has `.github/` dir, `CI=true` in env vars, or is a standalone repo), emit a warning in the final report: `"No CI configuration files found in scope — scan-06 (CI/CD security) not applicable for this target."`

If `find-ci-files.sh` prints paths but no CI tool is available (actionlint absent, semgrep absent), record them in `memory/meta-<slug>.json` under `ci_dirs_scanned` with a tool-availability note so the exec-report-generator can cite the coverage gap per `agents/exec-report-generator.md` § "Coverage-gap callouts".

Also invoke the two custom scripts:
- `plugins/agentic-dev-team/tools/entropy-check.py` on target
- `plugins/agentic-dev-team/tools/model-hash-verify.py` on target

Their SARIF outputs flow through the shared parser.

**Phase 1b — Judgment detection.** Dispatch in parallel (Agent tool with multiple calls in one message):
- `security-review` (opus; reads RECON + target files)
- `business-logic-domain-review` (opus; reads RECON + target files + `knowledge/domain-logic-patterns.md`)

Append their findings to `memory/findings-<slug>.jsonl`.

**Phase 1c — ACCEPTED-RISKS suppression (deterministic, mandatory gate).** Execute the deterministic script; do not delegate this to LLM reasoning:

```bash
scripts/apply-accepted-risks.sh <target-dir> <slug> [<memory-dir>]
```

Defaults: `memory-dir = ./memory`. The script:
- Checks for `ACCEPTED-RISKS.md` at `<target-dir>/`. Absent → exits 0 without changes; this target proceeds with all findings.
- Parses YAML frontmatter per `plugins/agentic-dev-team/knowledge/accepted-risks-schema.md`. Schema-invalid → exits 2 (fails the run with a named parse error).
- Applies first-match-wins: rule matches when its `rule_id` pattern matches finding's `rule_id` AND any of its `files[]` globs matches the finding's file (path-normalized relative to target root).
- Expired rules emit WARN but do not suppress.
- Rewrites `memory/findings-<slug>.jsonl` in place (suppressed entries removed).
- Writes `memory/suppressed-<slug>.jsonl` (removed entries + `_suppressed_by` metadata).
- Writes `memory/suppression-log-<slug>.jsonl` (audit log).

This step is **mandatory when `ACCEPTED-RISKS.md` is present**. If the exec report's Appendix C is empty but `ACCEPTED-RISKS.md` existed at the target root, the run surfaces a warning about the missed gate per `agents/exec-report-generator.md` § Section 7.

Multi-target runs invoke the script once per target.

**Phase 2 — FP-reduction.** Skip if `--fp-reduce=no`. Otherwise dispatch `fp-reduction` (opus). Produces `memory/disposition-<slug>.json`. Log `reachability_tool` (joern-cpg or llm-fallback) to audit.

**Phase 2b — Domain-class severity floors (deterministic).** Execute the deterministic script after fp-reduction has written the disposition register:

```bash
scripts/apply-severity-floors.sh <slug> [<memory-dir>]
```

The script reads `memory/disposition-<slug>.json`, applies domain-class severity floors by rule_id pattern (PII, TLS-disabled, weak-crypto, hardcoded-creds, fail-open-fraud, emulation-bypass, feature-poisoning, tokenization-skip, unauth admin endpoints path-gated to `/admin|/internal|/predict|/score|...`, unauth info-leak endpoints floor-5), and rewrites the register with:
- `exploitability.score = max(mechanical_score, floor)`
- `exploitability.rationale` annotated with the floor class + original rationale

Emits `memory/severity-floors-log-<slug>.jsonl` for audit (one line per floor applied).

**Why deterministic**: floor rules are pure functions over `(rule_id, file_path)` — delegating this to an LLM produces run-to-run variance. The pattern-matching logic belongs in code.

This step is a **no-op when fp-reduction was skipped** (`--fp-reduce=no`); exits 0 with no changes.

**Phase 3 — Narrative + compliance.** Dispatch in parallel:
- `tool-finding-narrative-annotator` (sonnet) → `memory/narratives-<slug>.md`
- `compliance-mapping` skill → `memory/compliance-<slug>.json` (invokes `compliance-edge-annotator` only for `llm_review_trigger: true` matches per the skill)

**Phase 4 — Service-communication.** Run `plugins/agentic-security-review/harness/tools/service-comm-parser.py` against the target. For multi-repo runs, pass all targets at once so cross-service edges are captured.

**Phase 5 — Report generation.** Dispatch `exec-report-generator` (opus). Single-repo: produces `memory/report-<slug>.md`. Multi-repo: produces per-repo reports + `memory/cross-repo-summary-<slug>.md`.

**Phase 5b — Severity consistency (multi-target only).** Run `scripts/check-severity-consistency.sh` with all target slugs. Skip for single-target runs.

**Phase 5c — Report verification.** Run `scripts/verify-report.sh memory/report-<slug>.md <slug>` for each target. Failures are logged to the audit trail and surfaced in Section 6 of the report; they do NOT prevent report publication.

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
