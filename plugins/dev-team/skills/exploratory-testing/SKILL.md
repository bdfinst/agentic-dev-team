---
name: exploratory-testing
description: Charter-driven exploratory testing — probe a running feature/endpoint with structured heuristics, evaluate charter quality, run adversarial expansion, classify defects, and auto-triage critical findings into an incremental report. Use when the user runs /explore, says "explore this endpoint", "poke at this feature", "find bugs in the running app", or wants hands-off exploratory testing of a live target.
role: worker
user-invocable: true
---

# Exploratory Testing

## Overview

The QA Engineer in charter-driven **"Chaos Specialist"** mode. Given a charter and a running target (endpoint, CLI, feature), it probes with structured heuristics, captures telemetry on every probe, classifies defects, auto-triages critical findings, and writes an incremental report ending with runnable follow-up charters. It is bounded by a **probe budget** so a session always terminates.

Frameworks (charter quality, variable identification, state model, implicit-expectation lenses) live in `knowledge/exploratory-testing-field-guide.md`; this file is the protocol.

## Constraints

- **Probe a running target.** This skill exercises live behavior — it does not read code to reason about bugs (that is `/triage`'s job once a defect is found).
- **Bounded.** Stop at or before the probe budget (default 15) with a stated reason. Every probe counts.
- **Incremental.** Append each probe result to the report as it runs — a `/stop` or budget exhaustion must still leave a usable partial report.
- **Auto-triage critical defects only**, and never fix them — hand off to `/triage`.
- **Be concise.** Stream one line per probe to chat; the detail lives in the report.

## Parse Arguments

- `--charter '<goal>'` — **required.** Charter format: `Explore [target] with [approach] to discover [concern]`.
- `--probe-budget <n>` — max probes (default **15**).
- `--invariants '<expr,...>'` — per-probe invariants to validate; a violation is Critical-immediate.
- `--no-adversarial` — skip adversarial expansion (on by default).
- `--force` — proceed past a charter-quality warning without refining.
- target — the URL/endpoint/command under test (from the charter or an explicit arg).

If `--charter` is absent, do not probe: emit exactly `What should I investigate? Provide a charter: --charter '<goal>'` and stop with no report.

## Steps

### 1. Evaluate charter quality (before any probe)

Check the charter against the anti-patterns in the field guide (§1): too specific (a test case), too broad (infinite scope), missing `with` (no approach), missing `to discover` (no risk hypothesis). On a match, emit a **one-line warning** naming the anti-pattern and prompt: refine the charter, or re-run with `--force`. Do not probe until the charter is acceptable or `--force` is given.

### 2. Reachability pre-flight

Confirm the target responds (a baseline request). If unreachable, write no report and report the target URL plus the connection error. A reachable baseline (the happy path) is **probe 1** and anchors Happy-Path Divergence.

### 3. Plan the probe set (variable identification)

From the field guide (§2), identify what can vary for this target (parameters, values, types, sizes, character sets, combinations). If the charter names an **entity noun** (order, user, account…), include a **CRUD Sweep** (create/read/update/delete + read-after-delete). For permission/role/multi-select fields, include **Goldilocks set-dimension variants** (none / one / some / all / invalid member).

### 4. Probe loop (until budget or `/stop`)

Run heuristics, decrementing the budget per probe. Capture telemetry on **every** probe: probe type, exact input, HTTP status (or exit code), response time, response size, and any captured stderr.

The five heuristics:

| Heuristic | What it does |
|-----------|--------------|
| **Goldilocks** | too-small / just-right / too-big for each variable; plus set-dimension variants (none/one/some/all/invalid) for set-valued fields |
| **Happy-Path Divergence** | start from the confirmed happy path (probe 1), then change one thing at a time and watch for divergence |
| **Telemetry Deepening** | when a probe is slow / large / noisy, follow it with sharper probes around that variable (perf cliffs, O(n²), truncation) |
| **Invariant Probing** | if `--invariants` given, assert each after every probe (e.g. balance never negative, count conserved) |
| **CRUD Sweep** | for entity charters: create → read → update → delete → read-after-delete; watch for orphans, stale reads, double-delete |

**Follow surprises:** when a probe produces an unexpected result, spend the next probes varying that input (field guide §4). **Off-charter temptations** are recorded as follow-up charters (Step 7), not chased now.

### 5. Adversarial expansion (default on; `--no-adversarial` skips)

After the heuristic probes, expand along **3 implicit-expectation lenses** (field guide §5) — pick the 3 most relevant of: authorization bypass, data integrity, timing/ordering, performance-at-scale, crash-resistance — generating **up to 6 angles** total (budget permitting). Label every adversarial probe `adversarial-<lens>` in the report.

### 6. Classify defects + auto-triage

Classify each finding by severity. A **Critical** defect (data corruption, auth bypass, crash, invariant violation) triggers auto-triage:

- Retry the probe **once** to rule out a transient — **except invariant violations**, which are **Critical-immediate** (no retry).
- If it reproduces (or is invariant-immediate), invoke **`/triage`** with the reproduction. On success, record the returned `triage-record: DEV_TEAM_REPORTS/triage/<slug>.md` path in the report. On triage failure, preserve the reproduction at `tmp/explore-trace-<timestamp>.md` and record that path instead.
- **No defect → no triage.** Non-critical findings are recorded in the report only.

### 7. Session debrief

When the budget is exhausted or `/stop` is received, stop and state the termination reason (budget reached / charter exhausted / stopped). Finalize the report, ending with a **"Next Exploration"** section: 2–3 runnable follow-up charter strings (off-charter temptations and unfollowed surprises become these).

## Output

Write incrementally to `reports/explore-<YYYYMMDDThhmmss>.md`:

```markdown
## Exploration — <charter>

**Target**: <url>   **Budget**: <used>/<n>   **Status**: <complete|partial|stopped — reason>

### Probes
| # | Heuristic | Input | Status | Time | Size | stderr | Finding |

### Defects
| Severity | Probe # | Summary | Triage |
(Triage = `DEV_TEAM_REPORTS/triage/<slug>.md` path, or `tmp/explore-trace-<ts>.md` on triage failure)

### Next Exploration
- `--charter 'Explore … with … to discover …'`
- `--charter '…'`
```

The report must contain **≥1 Goldilocks and ≥1 Happy-Path Divergence** entry unless the charter explicitly restricts scope. Write it incrementally so a partial report survives `/stop`.

## Integration

- Invoked by the `/explore` command; runs as the QA Engineer's Chaos Specialist mode.
- Hands critical defects to `/triage` (which writes `DEV_TEAM_REPORTS/triage/<slug>.md`).
- Frameworks: `knowledge/exploratory-testing-field-guide.md`. For *test design* (which layer, which double) use `test-design-advisor`; this skill probes running behavior, it does not design a suite.
