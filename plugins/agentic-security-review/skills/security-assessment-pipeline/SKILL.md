---
name: security-assessment-pipeline
description: Declarative step graph for the /security-assessment orchestration. Phases run in fixed order with dependency enforcement; per-phase artifacts land in memory/ and feed the next phase. Supports --start (resume), --agents (partial run), --fp-reduce (skip FP-reduction for speed).
role: worker
user-invocable: false
version: 1.0.0
maintainers:
  - bdfinst
  - unassigned
required-primitives-contract: ^1.0.0
---

# Security Assessment Pipeline

## Purpose

The `/security-assessment` command executes a multi-phase pipeline over one or more target repos. This skill defines the phase order, dependencies, artifacts, and failure semantics so the command can remain thin and the behaviour is auditable.

Matches the four-phase structure of the `opus_repo_scan_test` reference (recon → per-repo scan → cross-repo synthesis → FP-reduction → report), with explicit incorporation of tool-first detection + LLM judgment.

## Phase graph

Key properties:

- **Multi-target**: each target's Phase 0 → Phase 2b pipeline runs **independently in parallel**. Only Phase 4 (cross-repo) and Phase 5 (exec report) join across targets.
- **Phase 4 runs concurrently with Phase 1b – Phase 3** once Phase 0 finishes — it only depends on Phase 0 output.
- **Phase timing**: every phase is bracketed with `scripts/phase-timer.sh start/end` so `memory/phase-timings-<slug>.jsonl` records actual wall times. The exec report surfaces this data and flags drift from intended parallelism.

```
                               ┌─────────────────────┐
                               │ Phase 0: Recon      │
                               │ (parallel per       │
                               │  target)            │
                               └──────────┬──────────┘
                                          │
                 ┌────────────────────────┼────────────────────────┐
                 │                        │                        │
                 ▼                        ▼                        ▼
     ┌─────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
     │ Phase 1+1b          │   │ Phase 4 (cross-  │   │ (anything else       │
     │ (parallel across    │   │  repo: service-  │   │  Phase-0-dependent)  │
     │  tools AND agents)  │   │  comm parser;    │   └──────────────────────┘
     └──────────┬──────────┘   │  multi-target    │
                │              │  only)           │
                ▼              └──────────────────┘
     ┌─────────────────────┐
     │ Phase 1c: SEQUENTIAL│
     │ ACCEPTED-RISKS      │
     └──────────┬──────────┘
                ▼
     ┌─────────────────────┐
     │ Phase 2: SEQUENTIAL │
     │ fp-reduction        │
     └──────────┬──────────┘
                ▼
     ┌─────────────────────┐
     │ Phase 2b: severity  │
     │ floors              │
     └──────────┬──────────┘
                ▼
     ┌─────────────────────┐
     │ Phase 3: narratives │
     │ + compliance        │
     │ (parallel)          │
     └──────────┬──────────┘
                ▼
     ┌─────────────────────┐
     │ Phase 5: exec report│
     │ (single agent)      │
     └─────────────────────┘
```

```
Phase 0: Reconnaissance
  agent:     codebase-recon (opus)
  produces:  memory/recon-<slug>.{json,md}
  parallelism: parallel across targets (each target runs its own recon)

Phase 1: Tool-first detection  (parallel across tools)
  skill:     static-analysis-integration
  produces:  memory/findings-<slug>.jsonl (unified finding stream)
  requires:  Phase 0
  parallelism: all tool × target × ruleset combinations run concurrently

Phase 1b: Judgment-layer detection  (parallel across agents)
  agents:    security-review, business-logic-domain-review (opus both)
  produces:  adds unified findings to memory/findings-<slug>.jsonl
  requires:  Phase 0, Phase 1
  parallelism: two agents dispatched in a single Agent tool message,
               repeated per target

Phase 1c: ACCEPTED-RISKS suppression (sequential gate, mandatory)
  procedure: scripts/apply-accepted-risks.sh parses ACCEPTED-RISKS.md
             at target root, filters matching findings
  produces:  memory/suppressed-<slug>.jsonl + memory/suppression-log-<slug>.jsonl
  requires:  Phase 1 + Phase 1b
  enforced:  exec-report-generator's Appendix C expects
             memory/suppressed-<slug>.jsonl to exist when
             ACCEPTED-RISKS.md was present

Phase 2: FP-reduction (sequential)
  agent:     fp-reduction (opus)
  produces:  memory/disposition-<slug>.json
  requires:  Phase 1 + Phase 1b + Phase 1c
  optional:  skipped when --fp-reduce=no passed

Phase 2b: Domain-class severity floors (sequential, deterministic)
  script:    scripts/apply-severity-floors.sh
  produces:  memory/severity-floors-log-<slug>.jsonl; rewrites
             memory/disposition-<slug>.json with floor-adjusted scores
  requires:  Phase 2
  optional:  no-op when Phase 2 was skipped

Phase 3: Narrative + compliance (parallel across agents)
  agent:     tool-finding-narrative-annotator (sonnet)
  skill:     compliance-mapping
  produces:  memory/narratives-<slug>.md, memory/compliance-<slug>.json
  requires:  Phase 2b (or Phase 1+1b if fp-reduction skipped)
  parallelism: narrative annotator + compliance mapping dispatched
               together in one Agent tool message

Phase 4: Service-communication (runs concurrently with Phase 1b-3)
  tool:      harness/tools/service-comm-parser.py
             harness/tools/shared-cred-hash-match.py (multi-target only)
  produces:  memory/service-comm-<slug>.mermaid,
             memory/shared-creds-<slug>.sarif
  requires:  Phase 0 only
  parallelism: does NOT wait for Phase 1-3 to complete; dispatched as
               soon as Phase 0 finishes and runs alongside the rest

Phase 5: Report generation (sequential, single-threaded)
  agent:     exec-report-generator (opus)
  produces:  memory/report-<slug>.md  (plus memory/cross-repo-summary-<slug>.md for multi-repo)
  requires:  Phase 2b + Phase 3 + Phase 4 (all parallel branches joined)

Phase 5b: Severity-consistency check (multi-target only, deterministic)
  script:    scripts/check-severity-consistency.sh
  produces:  memory/severity-consistency-<combined-slug>.txt
  requires:  Phase 5 (all report-<slug>.md written) + Phase 2 disposition registers
  condition: skipped for single-target runs

Phase 5c: Report verification (per target, deterministic)
  script:    scripts/verify-report.sh
  produces:  memory/verify-report-<slug>.txt
  requires:  Phase 5 (report-<slug>.md written)
  on-fail:   logs to audit trail; does NOT block publication; failures appear in Section 6
```

**Phase timing instrumentation**: every phase is bracketed with
`scripts/phase-timer.sh start <phase-name> <slug>` at its start and
`scripts/phase-timer.sh end <phase-name> <slug>` at its end. The
resulting `memory/phase-timings-<slug>.jsonl` is consumed by the exec-
report-generator (Section 6 § Phase timings) to report actual wall
times and identify drift from intended parallelism. Canonical phase
names:

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

All memory/ artifacts are persisted between phases so `--start` can resume from any phase.

## Invocation

```
/security-assessment <path>                    # single-repo assessment (default)
/security-assessment <path1> <path2> [...]     # multi-repo assessment (emits per-repo + cross-repo reports)
/security-assessment <path> --start 3          # skip to Phase 3 (requires Phase 0-2 artifacts)
/security-assessment <path> --agents 0 1b      # run only listed phases
/security-assessment <path> --fp-reduce=no     # skip Phase 2 (reports tag findings as "FP-reduction skipped")
```

## Flag semantics

### `--start <phase>`

Resume from the given phase. Valid values: `0`, `1`, `1b`, `2`, `3`, `4`, `5`. The skill validates that all artifacts required by the chosen phase exist in memory/. If a required artifact is missing, the skill fails with a specific error naming which phase produced it.

Dependency check is SKIPPED in `--start` mode — the operator is explicitly asserting the preconditions are satisfied. The artifacts-present check still runs.

### `--agents <phase-list>`

Run only the listed phases. Example: `--agents 0 4` runs only recon and service-comm-parser. Dependency check is skipped (operator asserts pre-state). Useful for running sub-steps during iteration.

### `--fp-reduce=no`

Skip Phase 2. Phases 3 and 5 still run; they operate on the raw finding stream from Phase 1+1b. The exec report carries a banner: "FP-reduction skipped; findings may contain false positives. Review Appendix B before acting."

Default: `--fp-reduce=yes`.

## Failure handling

Per-phase best-effort continuation:

- **Phase 0 failure**: stops the pipeline. RECON is the precondition for everything else.
- **Phase 1 / 1b failure**: the specific tool / agent that failed is logged; the pipeline continues to Phase 2 with a partial finding stream. Phase 5 notes which detectors failed.
- **Phase 2 failure**: pipeline continues with the raw finding stream and tags the output with `fp-reduce: failed`. Phase 5's banner names the failure.
- **Phase 3 failure**: narratives + compliance are marked "unavailable" in the final report. Phase 5 continues.
- **Phase 4 failure**: service-comm diagram replaced with a one-line note. Phase 5 continues.
- **Phase 5 failure**: the pipeline reports failure but leaves all produced artifacts in memory/ for manual assembly.

## Artifacts

Every phase writes to `memory/<kind>-<slug>.<ext>` where `<slug>` is derived from the target repo name (or `-`-joined names for multi-repo). This convention matches the `/cross-repo-analysis` command's slug scheme.

| Kind | Producer | Consumer |
|---|---|---|
| `recon-<slug>.json` | Phase 0 | Phase 1, 1b, 2, 3, 5 |
| `findings-<slug>.jsonl` | Phase 1, Phase 1b | Phase 2, 3 |
| `disposition-<slug>.json` | Phase 2 | Phase 3, 5 |
| `narratives-<slug>.md` | Phase 3 | Phase 5 |
| `compliance-<slug>.json` | Phase 3 | Phase 5 |
| `service-comm-<slug>.mermaid` | Phase 4 | Phase 5, `/cross-repo-analysis` |
| `report-<slug>.md` | Phase 5 | Final output |
| `cross-repo-summary-<slug>.md` | Phase 5 (multi-repo only) | Final output |
| `severity-consistency-<combined-slug>.txt` | Phase 5b (multi-target only) | exec-report-generator (Section 6) |
| `verify-report-<slug>.txt` | Phase 5c | Audit trail; surfaced in report Section 6 on FAIL |

## Dependency contract

Each phase's skill / agent declares its required inputs. If an input artifact is missing when a phase begins, the phase fails fast rather than running with partial data. This is strict by default; `--start` and `--agents` override by asserting operator responsibility.

## Invariants

- Every phase is idempotent within a run — re-invoking Phase N with same inputs produces the same outputs.
- Artifact writes are atomic — partial writes on failure produce an `.incomplete` suffix so the pipeline can detect and reject stale half-written artifacts.
- The pipeline never deletes prior artifacts. `--start` resumes from existing; a new run without `--start` overwrites (with a backup under `memory/archive/<timestamp>/`).
- Audit log at `memory/audit-<slug>.jsonl` records phase start/end, artifact produced, and any failures. Append-only.

## Not covered by this skill

- Red-team pipeline (Phase C of the companion plugin). That has its own orchestration in `harness/redteam/orchestrator.py`.
- Cross-repo analysis. `/cross-repo-analysis` is a separate command; the security-assessment pipeline handles single-repo execution, and multi-repo is a loop over this pipeline + a final cross-repo step.
- Exec report rendering to PDF. That is `/export-pdf`.
