---
name: security-assessment-pipeline
description: Declarative phase graph for /security-assessment. Phases run in fixed order with dependency enforcement; per-phase artifacts land in memory/ and feed the next phase.
role: worker
user-invocable: false
version: 1.0.0
maintainers:
  - bdfinst
  - unassigned
required-primitives-contract: ^1.0.0
---

# Security Assessment Pipeline

The `/security-assessment` command executes this multi-phase pipeline over
one or more target repos. This skill is authoritative for phase order,
dependencies, artifacts, and failure semantics.

## Phase graph

Key properties:

- **Multi-target**: each target's Phase 0 → Phase 2b runs **independently
  in parallel**. Only Phase 4 (cross-repo) and Phase 5 (exec report) join
  across targets.
- **Phase 4 runs concurrently with Phase 1b – Phase 3** once Phase 0
  finishes — it only depends on Phase 0 output.
- **Phase timing**: every phase is bracketed with
  `scripts/phase-timer.sh start/end` so `memory/phase-timings-<slug>.jsonl`
  records actual wall times. exec-report-generator surfaces this data and
  flags drift from intended parallelism.

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

## Per-phase spec

```
Phase 0: Reconnaissance
  agent:     codebase-recon (opus)
  produces:  memory/recon-<slug>.{json,md}
  parallelism: parallel across targets

Phase 1: Tool-first detection (parallel across tools)
  skill:     static-analysis-integration
  produces:  memory/findings-<slug>.jsonl (unified finding stream)
  requires:  Phase 0
  parallelism: all tool × target × ruleset combinations run concurrently

Phase 1b: Judgment-layer detection (parallel across agents)
  agents:    security-review, business-logic-domain-review, deep-code-reasoning,
             authorization-logic-review, recon-driven-scan (opus all five)
  produces:  adds unified findings to memory/findings-<slug>.jsonl
  requires:  Phase 0, Phase 1
  parallelism: all five agents dispatched in a single Agent tool message,
               repeated per target
  adapters:  see knowledge/phase-1b-adapters.md

Phase 1c: ACCEPTED-RISKS suppression (sequential gate, mandatory)
  procedure: scripts/apply-accepted-risks.sh parses the first fenced
             ```json block in ACCEPTED-RISKS.md, matches findings by
             (rule_id exact, source_ref_glob), and suppresses matches
  produces:  memory/accepted-risks-<slug>.jsonl (suppressed + expired
             entries) + rewrites memory/findings-<slug>.jsonl in place
  requires:  Phase 1 + Phase 1b
  enforced:  exec-report-generator's Appendix C expects
             memory/accepted-risks-<slug>.jsonl when ACCEPTED-RISKS.md
             was present at target root

Phase 2: FP-reduction (sequential)
  agent:     fp-reduction (opus)
  produces:  memory/disposition-<slug>.json
  requires:  Phase 1 + Phase 1b + Phase 1c
  optional:  skipped when --fp-reduce=no

Phase 2b: Domain-class severity floors (sequential, deterministic)
  script:    ${CLAUDE_PLUGIN_ROOT}/scripts/apply-severity-floors.sh
  produces:  memory/severity-floors-log-<slug>.jsonl; rewrites
             memory/disposition-<slug>.json with floor-adjusted scores
  requires:  Phase 2
  optional:  no-op when Phase 2 was skipped

Phase 3: Narrative + compliance (parallel across agents)
  agent:     tool-finding-narrative-annotator (sonnet)
  skill:     compliance-mapping
  produces:  memory/narratives-<slug>.md, memory/compliance-<slug>.json
  requires:  Phase 2b (or Phase 1+1b if fp-reduction skipped)
  parallelism: dispatched together in one Agent tool message

Phase 4: Service-communication (runs concurrently with Phase 1b-3)
  tools:     ${CLAUDE_PLUGIN_ROOT}/harness/tools/service-comm-parser.py
             ${CLAUDE_PLUGIN_ROOT}/harness/tools/shared-cred-hash-match.py (multi-target only)
  produces:  memory/service-comm-<slug>.mermaid,
             memory/shared-creds-<slug>.sarif
  requires:  Phase 0 only

Phase 5: Report generation (sequential)
  agent:     exec-report-generator (opus)
  produces:  memory/report-<slug>.md (+ memory/cross-repo-summary-<slug>.md for multi-repo)
  requires:  Phase 2b + Phase 3 + Phase 4 (joined)

Phase 5b: Severity-consistency check (multi-target only, deterministic)
  script:    ${CLAUDE_PLUGIN_ROOT}/scripts/check-severity-consistency.sh
  produces:  memory/severity-consistency-<combined-slug>.txt
  requires:  Phase 5 + Phase 2 disposition registers
  condition: skipped for single-target runs

Phase 5c: Report verification (per target, deterministic)
  script:    ${CLAUDE_PLUGIN_ROOT}/scripts/verify-report.sh
  produces:  memory/verify-report-<slug>.txt
  requires:  Phase 5
  on-fail:   logs to audit trail; does NOT block publication
```

Canonical phase names for `phase-timer.sh`: `phase-0-recon`,
`phase-1-tool-first`, `phase-1b-judgment`, `phase-1c-accepted-risks`,
`phase-2-fp-reduction`, `phase-2b-severity-floors`,
`phase-3-narrative-compliance`, `phase-4-cross-repo`, `phase-5-report`.

## Graph-assisted discovery

If a target repo has `.codegraph/` (CodeGraph MCP server — `codegraph_explore`/`get_symbol` for fast callers/callees/impact lookups) and/or a Repowise MCP server (`get_context`/`search_codebase` for semantic search), prefer them over raw `Grep`/`Read` when locating candidate files and tracing call paths. This benefits the **recon-driven scanning** step (Phase 1b's `recon-driven-scan` agent, bridging RECON narrative claims to concrete file:line evidence) most directly — graph-backed callers/impact lookups and semantic search surface exactly the file:line evidence that step needs. Never assume either tool is present — fall back to `Read`/`Grep`/`Glob` when neither is present; the tools are simply unavailable (no error) on repos without an index.

## Helper-script invocation contract

Deterministic phase helpers carry strict ordering requirements. The
orchestrator must not reorder these invocations:

**Invocation paths (discoverable in an installed plugin).** Every helper
below ships inside this plugin and MUST be invoked by its plugin-root path so
it resolves regardless of the caller's working directory — the bare names in
the table are shorthand for these:

- helper scripts → `${CLAUDE_PLUGIN_ROOT}/scripts/<name>` (e.g.
  `${CLAUDE_PLUGIN_ROOT}/scripts/phase-timer.sh`)
- harness tools → `${CLAUDE_PLUGIN_ROOT}/harness/tools/<name>`

| Script | Must run after | Must run before | Artifacts |
|---|---|---|---|
| `${CLAUDE_PLUGIN_ROOT}/scripts/phase-timer.sh start/end` | any phase boundary | — | `phase-timings-<slug>.jsonl` |
| `${CLAUDE_PLUGIN_ROOT}/scripts/find-ci-files.sh` | phase-0-recon | phase-1-tool-first | stdout (Phase 1 tool fan-out) |
| `${CLAUDE_PLUGIN_ROOT}/scripts/apply-accepted-risks.sh` | phase-1b-judgment | phase-2-fp-reduction | rewrites `findings-<slug>.jsonl`; writes `accepted-risks-<slug>.jsonl` |
| `${CLAUDE_PLUGIN_ROOT}/scripts/apply-severity-floors.sh` | phase-2-fp-reduction | phase-3-narrative-compliance | rewrites `disposition-<slug>.json` in place; writes `severity-floors-log-<slug>.jsonl` |

**Concurrency**: each script assumes a single writer on its input file.
`.tmp`+`mv` handles the single-writer-but-crash case. Concurrent writers
are a contract violation. Callers MUST serialize invocations against the
same slug.

**Idempotency**: `apply-severity-floors.sh` and `apply-accepted-risks.sh`
are both idempotent (marker-based and atomic-rewrite-based respectively)
— safe to re-run from `--start`.

## Invocation

```
/security-assessment <path>                    # single-repo (default)
/security-assessment <path1> <path2> [...]     # multi-repo
/security-assessment <path> --start 3          # resume from Phase 3
/security-assessment <path> --agents 0 1b      # run only listed phases
/security-assessment <path> --fp-reduce=no     # skip Phase 2
```

## Flag semantics

- **`--start <phase>`**: resume from `0|1|1b|2|3|4|5`. Skill validates
  required artifacts exist; dependency check is SKIPPED (operator
  asserts preconditions).
- **`--agents <phase-list>`**: run only listed phases. Dependency check
  skipped.
- **`--fp-reduce=no`**: skip Phase 2. Phases 3 and 5 run on the raw
  finding stream; exec report carries banner "FP-reduction skipped;
  findings may contain false positives. Review Appendix B before
  acting." Default: `yes`.

## Failure handling

Per-phase best-effort continuation:

- **Phase 0**: stops the pipeline. RECON is the precondition.
- **Phase 1 / 1b**: failed tool/agent logged; pipeline continues to
  Phase 2 with partial stream. Phase 5 names the failed detectors.
- **Phase 2**: continue with raw stream; tag `fp-reduce: failed`. Phase 5
  banner names the failure.
- **Phase 3**: narratives + compliance marked "unavailable"; Phase 5
  continues.
- **Phase 4**: service-comm diagram replaced with a one-line note;
  Phase 5 continues.
- **Phase 5**: failure reported; all produced artifacts remain in
  `memory/` for manual assembly.

## Artifacts

Every phase writes to `memory/<kind>-<slug>.<ext>`. Slug is derived from
target repo name (or `-`-joined for multi-repo).

| Kind | Producer | Consumer |
|---|---|---|
| `recon-<slug>.json` | Phase 0 | Phase 1, 1b, 2, 3, 5 |
| `findings-<slug>.jsonl` | Phase 1, 1b | Phase 2, 3 |
| `deep-reasoning-<slug>.json` | Phase 1b | Phase 1b append step |
| `authz-review-<slug>.json` | Phase 1b | Phase 1b append step |
| `recon-driven-<slug>.json` | Phase 1b | Phase 1b append step |
| `disposition-<slug>.json` | Phase 2 | Phase 3, 5 |
| `narratives-<slug>.md` | Phase 3 | Phase 5 |
| `compliance-<slug>.json` | Phase 3 | Phase 5 |
| `service-comm-<slug>.mermaid` | Phase 4 | Phase 5, `/cross-repo-analysis` |
| `report-<slug>.md` | Phase 5 | Final output |
| `cross-repo-summary-<slug>.md` | Phase 5 (multi-repo) | Final output |
| `severity-consistency-<combined>.txt` | Phase 5b | exec-report Section 6 |
| `verify-report-<slug>.txt` | Phase 5c | Audit trail; surfaced on FAIL |

## Invariants

- Every phase is idempotent within a run — same inputs → same outputs.
- Artifact writes are atomic — partial writes produce an `.incomplete`
  suffix so the pipeline can detect and reject stale half-written
  artifacts.
- The pipeline never deletes prior artifacts. `--start` resumes from
  existing; a new run without `--start` archives to
  `memory/archive/<timestamp>/`.
- Audit log at `memory/audit-<slug>.jsonl` is append-only; records phase
  start/end, artifact produced, and failures.

## Not covered

- Red-team pipeline — `harness/redteam/orchestrator.py`.
- Cross-repo analysis as a standalone command — `/cross-repo-analysis`.
- PDF rendering — `/export-pdf`.
