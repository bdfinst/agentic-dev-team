# Plan: /explore Command and Exploratory Testing Skill

**Created**: 2026-05-07
**Branch**: main
**Status**: draft

## Goal

Add `/explore` as a first-class command in the dev-team plugin. The command dispatches
the QA Engineer in "Chaos Specialist" mode — a charter-driven, discovery-first session that probes
a running feature or endpoint using five heuristics: Goldilocks (boundary + Some/None/All set
dimension), Happy-Path Divergence, Telemetry Deepening, Invariant Probing, and CRUD Sweep.

Before probing, the command evaluates charter quality and runs an adversarial charter expansion
step that generates up to 6 additional probe angles (2 per lens: authorization bypass, data
integrity, timing/ordering). When the agent finds a critical defect it auto-invokes `/triage`.
At session end the report includes Next Exploration Suggestions (2–3 runnable follow-up charters).

Scope is Slice 1 only: standalone `/explore` invocation. Post-build sentinel + Data Flow Tracing
+ State Transition Probing (Slice 2) and adversarial review integration (Slice 3) are deferred
until this slice ships.

**Dependency**: assumes `/triage` is updated separately to write to `.triage/<slug>.md` instead
of creating GitHub issues. `/explore` delegates to `/triage`; it does not own the triage storage
format.

Spec: `docs/specs/exploratory-testing-explore-command.md`

## Acceptance Criteria

- [ ] The command begins executing probes immediately upon invocation; probe results appear in chat output before the agent waits for user input
- [ ] The session report contains at least one Goldilocks probe entry and at least one Happy-Path Divergence probe entry unless the charter explicitly restricts scope; Telemetry Deepening entries appear only when a telemetry anomaly is detected
- [ ] Each probe entry includes: probe type, input, HTTP status code, response time (ms), response size (bytes), and captured stderr (if any); report is written incrementally after each probe
- [ ] When a critical defect is detected (after one retry, except invariant violations), `/triage` is invoked automatically; on success the `.triage/<slug>.md` path appears in the session report; on `/triage` failure the failure reason is recorded and the raw trace is preserved at `tmp/explore-trace-<timestamp>.md`
- [ ] When no critical defect is found, the report explicitly states this and no `/triage` invocation occurs
- [ ] Warning-severity defects appear in the session report with severity "warning"; no `/triage` invocation is triggered for warnings
- [ ] The session terminates at or before the probe budget (default 15); the report states the termination reason
- [ ] Missing `--charter` produces the exact prompt "What should I investigate? Provide a charter: --charter '<goal>'" before any probes execute; no session report is written
- [ ] Unreachable dev server: the agent reports the attempted URL and connection error before any probes execute; no session report is written
- [ ] Session report written to `reports/explore-<YYYYMMDDTHHMMSS>.md`; partial report written on `/stop` or unexpected termination
- [ ] `explore.md` and `exploratory-testing/SKILL.md` pass `/agent-audit`; all registry rows match adjacent column schema
- [ ] Charter quality evaluation runs before any probes; anti-pattern charter triggers one-line warning and prompt to refine or `--force`; no probes execute until user responds
- [ ] Adversarial expansion runs by default after quality evaluation; up to 6 probe angles displayed before first probe; `--no-adversarial` skips; adversarial probes labeled `adversarial-<lens>` in report
- [ ] `--invariants` flag: each probe validates declared invariants; violation is Critical with no retry and triggers auto-triage; session report records violated invariant and actual response
- [ ] Charter entity nouns trigger CRUD Sweep: one probe per Create/Read/Update/Delete with Goldilocks boundary inputs; probe entries labeled `CRUD:<operation>`
- [ ] Goldilocks includes set-dimension variants for permission/role/multi-select fields: `Goldilocks:set-none`, `Goldilocks:set-some`, `Goldilocks:set-all`
- [ ] Session report includes "Next Exploration" section with 2–3 runnable follow-up charter strings

## User-Facing Behavior

See spec: `docs/specs/exploratory-testing-explore-command.md` § User-Facing Behavior

## Steps

### Step 1: Create eval fixtures (RED)

**Complexity**: standard

**RED**: Write test artifacts before any implementation files exist. Running `/agent-eval` against
these fixtures will surface broken-path findings until the command file exists.

**GREEN**: Create the following four files:

`evals/fixtures/ex-explore-command-present/CLAUDE.md` — a minimal CLAUDE.md referencing
`/explore` at `commands/explore.md`.

`evals/expected/ex-explore-command-present.json`:

```json
{
  "fixture": "ex-explore-command-present",
  "description": "CLAUDE.md references /explore command which exists at commands/explore.md",
  "applicableAgents": ["claude-setup-review"],
  "agents": {
    "claude-setup-review": {
      "expectedStatus": "pass",
      "issueCount": { "min": 0, "max": 0 }
    }
  }
}
```

`evals/fixtures/ex-explore-command-missing/CLAUDE.md` — same CLAUDE.md referencing
`commands/explore.md`, but the fixture directory contains no explore.md.

`evals/expected/ex-explore-command-missing.json`:

```json
{
  "fixture": "ex-explore-command-missing",
  "description": "CLAUDE.md references /explore but commands/explore.md is absent",
  "applicableAgents": ["claude-setup-review"],
  "agents": {
    "claude-setup-review": {
      "expectedStatus": "fail",
      "issueCount": { "min": 1, "max": 3 }
    }
  }
}
```

Note: these fixtures validate structural compliance only. Behavioral correctness (probe quality,
heuristic selection) is a known gap in the eval harness for action-oriented commands and requires
manual invocation to verify.

**REFACTOR**: None — fixtures are data files

**Files**:

- `evals/fixtures/ex-explore-command-present/CLAUDE.md`
- `evals/expected/ex-explore-command-present.json`
- `evals/fixtures/ex-explore-command-missing/CLAUDE.md`
- `evals/expected/ex-explore-command-missing.json`

**Commit**: `test: add eval fixtures for /explore command structural compliance`

---

### Step 2: Create `skills/exploratory-testing/SKILL.md`

**Complexity**: standard

**RED**: Verify `skills/exploratory-testing/SKILL.md` does not exist (`test -f` returns non-zero).

**GREEN**: Create `plugins/dev-team/skills/exploratory-testing/SKILL.md`. Behavioral
detail lives in the spec `§Architecture Specification`; this step owns only the section list
and the tables that require exact syntax.

Sections to write (in order):
- Frontmatter: `name: exploratory-testing`, `description`, `role: worker`, `user-invocable: false`
- Overview: when to use vs. /build and /triage; reference `knowledge/exploratory-testing-field-guide.md`
- Constraints: budget 15 default; retry-before-classify (invariant violations are Critical-immediate); Playwright fallback; no external observability
- Pre-probe variable identification: parameters, values, types, sizes, character sets; budget allocated by charter risk
- Heuristic definitions table: Goldilocks (boundary + type + set dims), Happy-Path Divergence, Telemetry Deepening, Invariant Probing, CRUD Sweep
- Charter Quality Evaluation: 3-part format; anti-pattern table; `--force` bypass
- Adversarial Charter Expansion: three lenses; up to 2 probes each; `--no-adversarial` bypass
- Telemetry signals (exact `curl -w` syntax required):

| Signal | Capture method | Deepening trigger |
|--------|---------------|-------------------|
| Response time | `curl -w "%{time_total}"` | > 2× session median |
| Time to first byte | `curl -w "%{time_starttransfer}"` | spike while total is flat |
| Response size | `curl -w "%{size_download}"` | > 2× or < 0.5× median |
| HTTP status code | `curl -w "%{http_code}"` | class change on similar inputs |
| Stderr/stdout | `2>&1` capture | output where prior identical probe had none |

- Session aggregates: running median response time + size; status code distribution; error rate
- Optional log-file delta: `wc -l` before/after; tail the delta
- Session management: termination conditions; per-probe chat line; incremental write; partial on any termination
- Defect classification:

| Severity | Trigger | Action |
|----------|---------|--------|
| Critical | HTTP 5xx (after retry), unhandled exception, crash, data corruption, invariant violation (no retry) | Trace → `/triage` → stop |
| Warning | Unexpected 4xx on valid input, telemetry anomaly, inconsistent response | Log → continue |
| Informational | UX deviation, no error signal | Log |

- Auto-triage handoff: (1) write trace to `tmp/explore-trace-<YYYYMMDDTHHMMSS>.md`; (2) invoke `/triage` with trace *content* (not file path — verify in Step 7); (3) on success record `.triage/<slug>.md`; (4) on failure record reason, preserve trace
- Session Debrief: "Next Exploration" section; 2–3 runnable charter strings; based on anomalies, unexplored heuristics, anomaly patterns
- Report schema: `reports/explore-<YYYYMMDDTHHMMSS>.md`; incremental; partial on any termination; timestamp `YYYYMMDDTHHMMSS` (no colons)

**REFACTOR**: Tighten prose; confirm section names match agent-skill-authoring format

**Files**: `plugins/dev-team/skills/exploratory-testing/SKILL.md`

**Commit**: `feat: add exploratory-testing skill with five heuristics, charter quality, adversarial expansion, and session debrief`

---

### Step 3: Create `commands/explore.md`

**Complexity**: standard

**RED**: After Step 5 (CLAUDE.md update), `/agent-audit` will report `/explore` listed in the
registry but the command file absent. The `ex-explore-command-missing` eval fixture already
captures this state.

**GREEN**: Create `plugins/dev-team/commands/explore.md`. Keep the command thin —
procedural logic lives in the skill.

Required sections:

Frontmatter: `name: explore`, description (include intent and two concrete example charters — see
below), `argument-hint: "<target> --charter \"<investigation goal>\" [--probes <n>] [--invariants \"<statement>\"] [--no-adversarial] [--force]"`,
`user-invocable: true`,
`allowed-tools: Read, Glob, Grep, Bash, Bash(npx playwright *), Agent`

The `description` field must include two example invocations so users understand what a charter
is without prior testing-domain knowledge (Nielsen H2, H6, H10 — "charter" is opaque jargon):

```yaml
description: >-
  Charter-driven exploratory testing: probe a live feature or endpoint for
  behavioral fragility using five heuristics (Goldilocks, Happy-Path Divergence,
  Telemetry Deepening, Invariant Probing, CRUD Sweep). Evaluates charter quality,
  runs adversarial expansion, and auto-triages critical defects via /triage.
  Examples:
    /explore auth/login --charter "Find inputs that bypass validation"
    /explore payments --charter "Investigate 500s under concurrent requests"
```

Parse Arguments: extract `<target>` (positional), `--charter "<goal>"` (required),
`--probes <n>` (optional, default 15), `--invariants "<statement>"` (optional),
`--no-adversarial` (flag), `--force` (flag) from `$ARGUMENTS`.

Pre-probe sequence (all run before first probe; no report written on failure):

1. Input validation: missing charter → exact prompt: "What should I investigate? Provide a
   charter: --charter '<goal>'"; missing target → "Provide a target (feature or endpoint) and
   a charter"; connectivity check (curl HEAD to target) → on failure report attempted URL and error
2. Charter quality evaluation (delegate to skill): detect anti-patterns; warn and prompt to
   refine or `--force`; skip evaluation entirely if `--force` is present
3. Adversarial expansion (delegate to skill): display "Added N adversarial angles:" before first
   probe; skip if `--no-adversarial`

Directory setup: `mkdir -p reports/ tmp/` before first probe.

Playwright check: `npx playwright --version`; if unavailable, set browser-probe mode to
"disabled" and note in report; API-only probing continues.

Session loop (delegate to skill for details): apply heuristics; emit one-line chat status after
each probe; write probe result to session report after each probe; check defect classification;
retry once on apparent critical defect before classifying (no retry for invariant violations);
stop and invoke `/triage` on confirmed critical; continue on warning/informational; stop at probe
budget or /stop.

Report finalisation: write termination reason; write "Next Exploration" section (delegate to
skill); emit one-line chat summary including finding counts and report path.

Reference: `skills/exploratory-testing/SKILL.md` for heuristic definitions, telemetry signals,
defect thresholds, auto-triage handoff protocol, and report schema.

**REFACTOR**: Align tone and section style with existing commands (triage.md, browse.md)

**Files**: `plugins/dev-team/commands/explore.md`

**Commit**: `feat: add /explore command for charter-driven exploratory testing`

---

### Step 4: Update `agents/qa-engineer.md`

**Complexity**: trivial

**RED**: `grep "exploratory" plugins/dev-team/agents/qa-engineer.md` returns nothing.

**GREEN**: Add to the Skills section:

```markdown
- [Exploratory Testing](../skills/exploratory-testing/SKILL.md) — invoke when a charter-driven
  exploration session is needed; provides heuristic probe strategies, telemetry signals, session
  management, and auto-triage handoff
```

**REFACTOR**: None needed

**Files**: `plugins/dev-team/agents/qa-engineer.md`

**Commit**: `feat: register exploratory-testing skill in qa-engineer agent`

---

### Step 5: Update `plugins/dev-team/CLAUDE.md`

**Complexity**: trivial

**RED**: `grep "explore" plugins/dev-team/CLAUDE.md` returns no `/explore` row.

**GREEN**: Add to the Slash Commands Registry table (alphabetically, between `domain-analysis`
and `feedback-learning`):

```
| `/explore` | `commands/explore.md` | worker | Charter-driven exploratory testing: Goldilocks, Happy-Path Divergence, Telemetry Deepening probes against a live target; auto-triages critical defects via /triage |
```

**REFACTOR**: None needed

**Files**: `plugins/dev-team/CLAUDE.md`

**Commit**: `docs: register /explore in CLAUDE.md commands registry`

---

### Step 6: Update `knowledge/agent-registry.md`

**Complexity**: trivial

**RED**: `grep "exploratory" plugins/dev-team/knowledge/agent-registry.md` returns nothing.

**GREEN**: Count lines in the completed SKILL.md to calibrate the token estimate, then add to
the Skills Registry table (after "Domain-Driven Design"):

```
| Exploratory Testing | `skills/exploratory-testing/SKILL.md` | ~700 | QA Engineer |
```

Update the estimate if the actual count differs significantly from ~700.

**REFACTOR**: None needed

**Files**: `plugins/dev-team/knowledge/agent-registry.md`

**Commit**: `docs: register exploratory-testing skill in agent-registry`

---

### Step 7: Run `/agent-audit` and resolve compliance gaps

**Complexity**: standard

**RED**: After Steps 2–6, run `/agent-audit`. Expect the new files to surface in the audit output.
Structural issues (missing frontmatter fields, non-standard section headers, broken links) will
appear here.

**GREEN**: Fix all blockers and warnings:

- `explore.md` frontmatter: verify all required fields match the command schema
- `exploratory-testing/SKILL.md` frontmatter: verify all required fields match the skill schema
- `qa-engineer.md` skill link: confirm link syntax matches existing entries
- CLAUDE.md row: confirm column count and pipe alignment matches existing rows
- `agent-registry.md` row: confirm column count matches Skills Registry schema
- Verify `/triage` invocation contract: trace content vs. file path — update SKILL.md accordingly
- Confirm `reports/` and `tmp/` directory creation in `explore.md` is correct

**REFACTOR**: Improve prose flagged during the audit

**Files**: All files from Steps 2–6

**Commit**: `fix: address agent-audit compliance findings for /explore`

## Complexity Classification

| Step | Rating | Rationale |
|------|--------|-----------|
| 1: Create eval fixtures | standard | New test artifacts with schema requirements |
| 2: Create SKILL.md | complex | Five heuristics, charter quality rubric, adversarial expansion protocol, session debrief |
| 3: Create explore.md | standard | New command, pre-probe sequence (quality + adversarial), five flags, session flow with skill delegation |
| 4: Update qa-engineer.md | trivial | Single skill reference line |
| 5: Update CLAUDE.md | trivial | Single table row |
| 6: Update agent-registry.md | trivial | Single table row |
| 7: Run /agent-audit | standard | Compliance verification with potential fixes |

## Pre-PR Quality Gate

- [ ] All new files have valid frontmatter (name, description, role, user-invocable)
- [ ] `/agent-audit` passes with no blockers
- [ ] Session report format in SKILL.md matches what `explore.md` produces
- [ ] `/triage` invocation contract verified (trace content vs. file path)
- [ ] Retry-before-classify for HTTP 5xx present in defect classification table
- [ ] Invariant Probing listed as Critical-immediate (no retry) in defect classification table
- [ ] Telemetry signals table present in SKILL.md with all five signals
- [ ] All five heuristics present in SKILL.md: Goldilocks, Happy-Path Divergence, Telemetry Deepening, Invariant Probing, CRUD Sweep
- [ ] Goldilocks includes set-dimension section (set-none / set-some / set-all)
- [ ] Charter Quality section present with anti-pattern table
- [ ] Adversarial Charter Expansion section present with three lenses
- [ ] Session Debrief / Next Exploration Suggestions section present
- [ ] `explore.md` argument-hint includes `--invariants`, `--no-adversarial`, `--force`
- [ ] `explore.md` pre-probe sequence documents all three steps (validation → quality → adversarial)
- [ ] `reports/` and `tmp/` directory creation handled in `explore.md`
- [ ] Timestamp format is `YYYYMMDDTHHMMSS` (no colons) throughout
- [ ] CLAUDE.md registry row matches existing rows exactly
- [ ] `explore.md` description field contains two concrete example charters (Nielsen H2/H6/H10)
- [ ] `/code-review` passes (doc-review, claude-setup-review, token-efficiency-review)

## Risks & Open Questions

- **Behavioral eval gap**: Eval fixtures validate structural compliance only. Probe quality requires
  manual invocation against a running target. Documented explicitly in the fixture JSON.
- **/triage invocation contract**: `/triage`'s argument-hint is `<bug description or error message>`
  — a natural-language string. Verify whether it can read from a file path or requires trace content
  inline. Resolved in Step 7.
- **Slice 2 integration seam**: When Slice 2 (post-build sentinel) is specced, it attaches to
  `/build` after the full test suite passes. Leave a TODO comment at that point in `commands/build.md`.
- **`.triage/` dependency**: Until `/triage` is updated to write to `.triage/`, the auto-triage step
  will attempt GitHub issue creation. Track this as a prerequisite before enabling auto-triage in
  production use.

## Plan Review Summary

Four automated reviewers evaluated this plan. Two required revision (Acceptance Test Critic,
UX Critic); two approved (Design & Architecture Critic, Strategic Critic). All blockers were
addressed in this revision. See spec file for full artifact detail.

**Key changes from reviewer feedback**:

- AC-1 rewritten: observable "probe results appear in chat" replaces unverifiable "single agent turn"
- AC-2 rewritten: "session report contains at least one probe of each type" replaces "attempted"
- AC-4 expanded: error-path for `/triage` failure (trace preserved, failure reason recorded)
- Missing scenarios added: warning-only defects, `/triage` failure, `/stop` mid-session
- Per-probe chat progress output added (UX blocker)
- Incremental report write added — partial sessions are recoverable (UX blocker)
- Retry-before-classify added to prevent transient 5xx from triggering false triage
- Telemetry signals defined as five concrete `curl -w` and `Bash` captures
- GitHub issue language replaced with `.triage/<slug>.md` triage record throughout
- Two concrete example charters added to `explore.md` description (Nielsen H2/H6/H10): "charter"
  is testing-domain jargon — examples provide recognition over recall, system-world match, and
  inline documentation for users who have never heard of session-based test management
