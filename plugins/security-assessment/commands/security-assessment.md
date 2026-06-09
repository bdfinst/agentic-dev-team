---
name: security-assessment
description: Full security assessment pipeline — recon, SARIF-first tool detection, judgment review, FP-reduction, narrative + compliance, service-comm diagram, exec report. Single-repo or multi-repo.
argument-hint: "<path> [<path> ...] [--start <phase>] [--agents <phase> ...] [--fp-reduce=yes|no]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
---

# /security-assessment

Orchestrator for the static-analysis pipeline. Execute the phase graph
defined in `skills/security-assessment-pipeline/SKILL.md`. Phases dispatch
to agents/scripts; artifacts pass through `memory/`. Produces a
publication-ready exec report per target (plus a cross-repo summary for
multi-target runs).

## Constraints

1. **Follow the pipeline exactly.** The skill is authoritative. Do not
   reorder phases or skip deterministic gates.
2. **Never silently drop findings.** Every input flows through to either
   the published report or a suppression appendix with reason.
3. **Artifacts are the source of truth.** Every phase writes to
   `memory/`; `--start` and failure-recovery rely on that.
4. **Informational-not-audit-grade.** Every produced report carries the
   compliance disclaimer (verbatim per `knowledge/disclaimers.md`) at the
   header.

## Parse arguments

Arguments: $ARGUMENTS

**Positional:** one or more directory paths (target repos).

**Flags:**

- `--start <phase>`: resume from phase (0 / 1 / 1b / 2 / 3 / 4 / 5).
  Requires prior phase artifacts in `memory/`.
- `--agents <phase> [<phase> ...]`: run only listed phases. Dependency
  check skipped.
- `--fp-reduce=yes|no`: skip Phase 2 FP-reduction when `no`. Default
  `yes`.

## Steps

### 1. Validate arguments

- ≥ 1 target path required.
- Each target must be a directory (not a file).
- For each target: consult `ACCEPTED-RISKS.md` if present at the target
  root.

### 2. Initialize run

For each target repo, derive a slug from the directory name (kebab-cased,
lowercased). Multi-repo runs use dash-joined slug for cross-repo
artifacts.

Create `memory/audit-<slug>.jsonl` (append-only). Record run start with
targets, flags, and contract version. If prior artifacts exist AND
`--start` is NOT set, archive them to `memory/archive/<timestamp>/`
before overwriting.

### 3. Execute the phase graph

Follow `skills/security-assessment-pipeline/SKILL.md` § "Phase graph".
The skill defines per-phase inputs, outputs, agents/scripts, and
parallelism. Three parallelism rules MUST be observed:

1. **Multi-target fan-out** — each target's Phase 0 → Phase 2b runs as an
   independent pipeline; dispatch as parallel Agent tool calls in the
   SAME message.
2. **Intra-phase fan-out** — Phase 1b dispatches its five agents
   (`security-review`, `business-logic-domain-review`,
   `deep-code-reasoning`, `authorization-logic-review`,
   `recon-driven-scan`) in one message; Phase 3 dispatches narrative +
   compliance in one message; Phase 1's static-analysis-integration runs
   every tool concurrently.
3. **Phase 4 runs concurrently with Phase 1b–3** once Phase 0 finishes.
   Phase 4 depends only on Phase 0.

Per-phase agent / script dispatch + adapter wiring is documented in the
skill. Do not reorder. Helper-script invocation contract (which script
runs after which phase boundary) is in the skill § "Helper-script
invocation contract".

### 4. Phase timing

Every phase is bracketed with
`${CLAUDE_PLUGIN_ROOT}/scripts/phase-timer.sh start <phase> <slug>` /
`${CLAUDE_PLUGIN_ROOT}/scripts/phase-timer.sh end <phase> <slug>`. Writes accumulate in
`memory/phase-timings-<slug>.jsonl`. The exec-report-generator reads this
file to compute actual parallelism vs. sequential execution.

### 5. Surface summary

Print:

```
Security assessment complete.

  Target(s): <list>
  Phases run: <list of phase numbers>
  Artifacts:
    memory/recon-<slug>.{json,md}
    memory/findings-<slug>.jsonl (<N> unified findings)
    memory/disposition-<slug>.json (<N> entries, <X>% true/likely-true)
    memory/narratives-<slug>.md
    memory/compliance-<slug>.json (<N> annotations, <M> LLM-triggered)
    memory/service-comm-<slug>.mermaid
    memory/report-<slug>.md (CRITICAL: <N>, HIGH: <N>, MEDIUM: <N>, LOW: <N>)
    (+ memory/cross-repo-summary-<slug>.md for multi-repo)

  Run `/export-pdf <report>.md` for PDF.
  Run `/cross-repo-analysis <path1> <path2>` for cross-repo chain analysis
  if not already included.
```

## Escalation

Stop and ask the user when:

- No target paths are provided.
- Any target path is not a directory.
- `--start` is set but required precondition artifacts are missing.
- Phase 0 (recon) fails on any target — no meaningful downstream without it.
- More than 3 phases fail in a single target — pipeline output is no
  longer trustworthy; escalate rather than emit a misleading report.

## Integration

- Phase graph: `skills/security-assessment-pipeline/SKILL.md`
- Cross-repo: pair with `/cross-repo-analysis`
- PDF: pair with `/export-pdf`
- Primitives: `plugins/dev-team/knowledge/security-primitives-contract.md`
