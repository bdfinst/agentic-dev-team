# Exec Report — Section 6 (Methodology and Scope) — Detailed Spec

Loaded on demand by `agents/exec-report-generator.md` when assembling
Section 6.

## What Section 6 contains

- Tools run (and any that were absent; cite install hint from the
  static-analysis skill)
- Agents invoked
- Target scope
- Excluded files (test fixtures, vendored third-party, etc.)
- Phase timings (table)
- Coverage-gap callouts (sub-bullet)
- Cross-repo severity calibration warnings (sub-section; multi-target only)

## Phase timings — sources

Read TWO timing sources and merge them:

1. **`memory/phase-timings-<slug>.jsonl`** — produced by `scripts/phase-timer.sh`
   at every shell-driven phase boundary. Always reliable for deterministic-
   script phases (Phase 1c, Phase 2b); optional for LLM phases (depends on
   orchestrator compliance with command spec).
2. **`memory/agent-dispatches.jsonl`** — produced automatically by
   `hooks/agent-dispatch-log.sh` on every Agent tool dispatch (PreToolUse +
   PostToolUse). Reliable for every LLM phase, regardless of orchestrator
   compliance.

**Correlation**: agent-dispatches are attributed to the current assessment
run by time-window filter. A dispatch belongs to this run if its epoch
falls between `first-phase-timing-start-epoch - 60s` and
`last-phase-timing-end-epoch + 60s`. Dispatches outside that window belong
to other commands and are excluded.

## Agent → phase mapping

| Agent type (from `tool_input.subagent_type`) | Phase |
|---|---|
| `codebase-recon` | phase-0-recon |
| `security-review`, `business-logic-domain-review`, `deep-code-reasoning`, `authorization-logic-review`, `recon-driven-scan` | phase-1b-judgment |
| `fp-reduction` | phase-2-fp-reduction |
| `tool-finding-narrative-annotator`, `compliance-edge-annotator` | phase-3-narrative-compliance |
| `cross-repo-synthesizer` | phase-4-cross-repo (narrative sub-phase) |
| `exec-report-generator` | phase-5-report |
| `redteam-*-analyzer`, `redteam-report-generator` | phase-redteam-* (out of /security-assessment scope) |

When both sources have entries for the same phase, prefer the earlier
`start` epoch and later `end` epoch (widest interval — captures all
subagent dispatches within a phase).

## Phase-timing table format

| Phase | Start | End | Duration | Overlapped with |
|---|---|---|---|---|
| phase-0-recon | 00:00 | 00:12 | 12s | — |
| phase-1-tool-first | 00:12 | 00:48 | 36s | phase-1b-judgment, phase-4-cross-repo |
| phase-1b-judgment | 00:12 | 02:30 | 2m18s | phase-1-tool-first, phase-4-cross-repo |
| phase-4-cross-repo | 00:13 | 00:16 | 3s | phase-1, phase-1b |
| phase-1c-accepted-risks | 02:30 | 02:31 | 1s | — |
| phase-2-fp-reduction | 02:31 | 04:50 | 2m19s | — |
| ... | | | | |
| **Total wall time** | 00:00 | 07:15 | **7m15s** | |

## Computation

- For each `end` record, compute duration from its paired `start` record
  (same phase name).
- "Overlapped with" = OTHER phases whose intervals intersect this phase's
  interval. Phase X overlaps Y when
  `max(X.start, Y.start) < min(X.end, Y.end)`.
- Wall time = `last_end_epoch - first_start_epoch` across all records.

## Drift detection (verbatim messages)

Emit when the intended parallelism per
`skills/security-assessment-pipeline/SKILL.md § Phase graph` didn't happen:

- If `phase-1-tool-first` and `phase-1b-judgment` did NOT overlap:
  `"INFO: Phase 1 and Phase 1b ran sequentially (should have been parallel per skill § Phase graph). Wall-time cost: ~<phase-1-duration + phase-1b-duration - parallel-optimum>s."`
- If `phase-4-cross-repo` did NOT overlap with `phase-1*` / `phase-2*` /
  `phase-3*`:
  `"INFO: Phase 4 ran sequentially after Phase 3 (should have run concurrently with Phase 1b-3). Wall-time cost: ~<phase-4-duration>s."`
- If multi-target runs show per-target phases completing strictly
  sequentially (no per-target interval overlap):
  `"INFO: Multi-target phases ran sequentially (N targets took ~N×single-target time; parallel fan-out would have run at wall time ≈ max(per-target-time))."`

These messages are informational — the report still publishes — but they
make suboptimal orchestration visible so the dispatching pattern can be
tightened over time.

## Coverage-gap callouts

When tools were absent, surface the specific scan concerns that lose
coverage in a "Scan concerns with reduced coverage" sub-bullet, so the
reader understands what the report cannot claim.

| Absent tool | Reduced-coverage concerns |
|---|---|
| actionlint | scan-06 (CI/CD): printenv in workflows, continue-on-error misuse, excessive permissions |
| hadolint | scan-05 (container): Dockerfile linting — USER directive, unpinned images, apt-get pipelines |
| gitleaks | scan-01 (secrets): pattern-detected credentials (supplemented by entropy-check.py but narrower) |
| trivy | scan-05 + scan-08: IaC policy + CVE in deps + image-layer scanning |
| joern | Reachability analysis in fp-reduction — falls back to LLM (banner emitted; analysis less precise on dead-code paths) |

### CI-files-present logic

- If `ci_dirs_scanned: []` AND target has no `.github/workflows/`,
  `.gitlab-ci.yml`, or equivalent:
  `"No CI/CD configuration files in scope — scan-06 not applicable for this target."`
- If `ci_dirs_scanned: []` AND target DOES have CI files (tool-availability
  gap): list actionlint + semgrep p/github-actions as missing tools and
  include scan-06 in reduced-coverage concerns.

## Cross-repo severity calibration

When the pipeline ran against multiple targets, read
`memory/severity-consistency-<combined-slug>.txt`. If the file contains any
WARN lines, emit them verbatim in Section 6 under the heading "Severity
calibration warnings". If the file is absent or empty, omit the
subsection.
