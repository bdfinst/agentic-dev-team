# Spec: Exploratory Testing — /explore Command (Slice 1)

## Scope Note

This spec covers Slice 1 of a three-slice feature. The proposal also described:

- Slice 2: Post-build sentinel (automatic `/explore` run as part of `/build`) + Data Flow Tracing + State Transition Probing (both require inter-probe state that fits naturally here)
- Slice 3: Adversarial review (Explorer as "Chaos" voice in parallel review)

Each of those requires its own spec after this slice ships.

This spec was updated after competitive analysis against the Xray "Useful Heuristics" catalog and
"Explore It!" by Elisabeth Hendrickson. New capabilities incorporated: Invariant Probing, CRUD Sweep,
Some/None/All set-dimension extension to Goldilocks, Charter Quality Evaluation, Adversarial Charter
Expansion, and session debrief with Next Exploration Suggestions.

**Dependency**: This spec assumes `/triage` is updated (separately) to write triage records to
`.triage/<slug>.md` instead of creating GitHub issues. `/explore` delegates defect handoff to
`/triage` without owning the triage storage format.

---

## Intent Description

The `/explore` command adds discovery-driven, charter-guided exploratory testing as a first-class
workflow in the agentic-dev-team pipeline. Where `/build` executes a predetermined TDD plan and
`/code-review` applies deterministic rules, `/explore` is unscripted: the QA Engineer is chartered
with a specific investigation goal and given latitude to probe a running feature or endpoint using
heuristic strategies.

The core motivation is that well-tested code can still be behaviorally fragile under unusual input
combinations, interrupted user flows, or boundary conditions that no reviewer thought to specify. A
structured exploration session — bounded by a probe budget and guided by a charter — surfaces these
"unknown unknowns" at machine speed, before a human ever opens a PR.

Before probing begins, the command evaluates charter quality and runs an adversarial expansion step
that adds probe angles the charter didn't explicitly request. This ensures the session covers not
only the stated concern but the adjacent attack surface implied by it.

When the agent discovers a defect during exploration, it captures the reproduction trace and
automatically invokes `/triage` to produce a triage record at `.triage/<slug>.md` with root cause
analysis and a TDD fix plan. This closes the loop: exploratory discovery feeds directly into the TDD
pipeline rather than becoming a manual note.

---

## User-Facing Behavior

```gherkin
Feature: /explore — Charter-Driven Exploratory Testing
  As a developer,
  I want to run a charter-driven exploration session against a feature or endpoint
  So that I can discover behavioral fragility that TDD and static review miss

  Background:
    Given the agentic-dev-team plugin is installed
    And the local development server is running

  # ─── Happy path ──────────────────────────────────────────────────────────────

  Scenario: Basic exploration with a charter completes without defects
    When I run "/explore auth/login --charter 'Investigate login edge cases'"
    Then the agent evaluates the charter quality and displays no warning
    And the agent displays the adversarial angles added before the first probe
    And the agent emits a one-line status message after each probe completes
    And the session report contains at least one Goldilocks probe entry
    And the session report contains at least one Happy-Path Divergence probe entry
    And the session report is written to "reports/explore-<timestamp>.md"
    And the session report contains a "Next Exploration" section with at least one suggestion
    And the chat summary states "Exploration complete — no defects found"
    And no /triage invocation occurs

  Scenario: Warning-severity defect found — report but no triage
    When I run "/explore auth/login --charter 'Investigate login edge cases'"
    And a probe receives an unexpected HTTP 4xx response on a valid input
    Then the session report records the finding with severity "warning"
    And no /triage invocation occurs
    And the session continues to the next probe

  Scenario: Exploration finds a critical defect and auto-triages successfully
    When I run "/explore payments --charter 'Test payment boundary values'"
    And a probe triggers an HTTP 5xx response or unhandled exception
    And the probe condition persists on a second attempt
    Then the agent captures the probe trace and reproduction steps
    And the agent automatically invokes /triage with the captured trace
    And a triage record is written to ".triage/<slug>.md"
    And the session report includes the path to the triage record
    And the session terminates after the triage handoff
    And the chat summary lists the defect and the triage record path

  Scenario: /triage invocation fails — trace preserved locally
    When I run "/explore payments --charter 'Test payment boundary values'"
    And a probe triggers a critical defect
    And /triage fails to write the triage record
    Then the session report records the triage failure reason
    And the probe trace is preserved at "tmp/explore-trace-<timestamp>.md"
    And the chat summary reports the triage failure and the trace file path

  Scenario: Charter restricts heuristic scope
    When I run "/explore search --charter 'Only test empty and whitespace-only queries'"
    Then the session report contains only Goldilocks probe entries
    And the session report notes the restricted scope
    And no Happy-Path Divergence or Telemetry Deepening entries appear in the report

  Scenario: Telemetry deepening triggers on latency anomaly
    Given a controlled endpoint that returns slow responses on specific parameters
    When I run "/explore search --charter 'Investigate search performance'"
    And a probe response time exceeds 2x the median response time of prior probes
    Then the agent executes additional probes varying the parameters of the slow endpoint
    And the session report contains Telemetry Deepening probe entries for those parameters
    And each entry includes response time, TTFB, response size, and captured stderr

  # ─── Charter quality ─────────────────────────────────────────────────────────

  Scenario: Charter is too broad — agent warns and requests refinement
    When I run "/explore auth --charter 'Test the auth system'"
    Then the agent displays "Charter is too broad: no investigation angle specified"
    And the agent asks the user to refine or add --force to proceed
    And no adversarial expansion runs
    And no probes are executed
    And no session report is written

  Scenario: User proceeds with a broad charter using --force
    When I run "/explore auth --charter 'Test the auth system' --force"
    Then the agent proceeds without charter quality warnings
    And adversarial expansion runs normally
    And probes execute normally

  # ─── Adversarial charter expansion ───────────────────────────────────────────

  Scenario: Adversarial expansion adds probe angles before session starts
    When I run "/explore payments --charter 'Test payment boundary values'"
    Then before any probe executes, the agent displays "Added N adversarial angles:"
    And the listed angles include at least one authorization bypass angle
    And at least one adversarial-<lens> probe entry appears in the session report

  Scenario: User skips adversarial expansion
    When I run "/explore payments --charter 'Test payment boundary values' --no-adversarial"
    Then the agent skips adversarial expansion
    And no "Added N adversarial angles" message appears
    And no adversarial-<lens> probe entries appear in the session report

  # ─── Invariant probing ───────────────────────────────────────────────────────

  Scenario: Invariant declared in charter is violated — immediate Critical classification
    When I run "/explore auth/login --charter 'Check auth rejects bad tokens' --invariants 'auth always returns 401 on invalid token'"
    And a probe with an invalid token receives HTTP 200
    Then the defect is classified Critical without a retry
    And the session report records the invariant that was violated and the actual response
    And /triage is invoked automatically

  Scenario: All probes satisfy declared invariant — session completes normally
    When I run "/explore auth/login --charter 'Check auth rejects bad tokens' --invariants 'auth always returns 401 on invalid token'"
    And all probes with invalid tokens receive HTTP 401
    Then no Critical defect is recorded for the invariant
    And the session report notes the invariant was validated across all applicable probes

  # ─── CRUD sweep ──────────────────────────────────────────────────────────────

  Scenario: CRUD sweep generates operations for entity referenced in charter
    When I run "/explore api/users --charter 'Investigate user creation edge cases'"
    Then the session report contains probe entries for Create, Read, Update, and Delete operations on the user entity
    And Goldilocks boundary inputs are applied to each CRUD operation
    And each probe entry is labeled with its operation type (e.g. "CRUD:Create", "CRUD:Delete")

  # ─── Some/None/All (Goldilocks set-dimension) ────────────────────────────────

  Scenario: Goldilocks probes include set-dimension variants for permission fields
    When I run "/explore api/permissions --charter 'Test permission assignment edge cases'"
    Then the session report contains a probe entry with no roles assigned
    And a probe entry with a single role assigned
    And a probe entry with all available roles assigned
    And each probe entry is labeled "Goldilocks:set-none", "Goldilocks:set-some", or "Goldilocks:set-all"

  # ─── Session lifecycle ────────────────────────────────────────────────────────

  Scenario: Session ends when probe budget is exhausted
    Given the probe budget is set to the default of 15
    When 15 probes have been executed with no critical defect found
    Then the agent stops probing and writes the session report
    And the termination reason in the report is "budget exhausted"
    And the chat summary states "Probe budget (15) exhausted"

  Scenario: Custom probe budget via flag
    When I run "/explore api/users --charter 'Test user creation' --probes 5"
    Then the session report contains at most 5 probe entries
    And the termination reason in the report is "budget exhausted" if no defect was found

  Scenario: User interrupts session with /stop
    Given an /explore session is running
    When the user invokes /stop
    Then the agent writes the session report with all probes executed up to that point
    And the termination reason in the report is "session interrupted by user"
    And the chat summary states the number of probes completed and the report path

  # ─── Session debrief ─────────────────────────────────────────────────────────

  Scenario: Session report includes next exploration suggestions
    When an /explore session completes for any reason
    Then the session report contains a "Next Exploration" section
    And the section contains 2–3 recommended follow-up charters
    And each suggestion is a single-line charter string the user can run directly

  # ─── Input validation ─────────────────────────────────────────────────────────

  Scenario: Missing charter argument
    When I run "/explore auth/login" without --charter
    Then the agent asks: "What should I investigate? Provide a charter: --charter '<goal>'"
    And no probes are executed
    And no session report is written

  Scenario: No target specified
    When I run "/explore" with no arguments
    Then the agent asks: "Provide a target (feature or endpoint) and a charter"
    And no probes are executed
    And no session report is written

  # ─── Error handling ───────────────────────────────────────────────────────────

  Scenario: Dev server not reachable
    Given the local dev server is not running
    When I run "/explore auth/login --charter 'Investigate login'"
    Then the session fails immediately with an error message containing the attempted URL
    And no probes are executed
    And no session report is written

  Scenario: Playwright not available — curl fallback
    Given Playwright is not installed
    When I run "/explore auth/login --charter 'Investigate UI flows'"
    Then the agent falls back to API-only probing via curl
    And Goldilocks probe entries appear in the session report using curl inputs
    And the session report notes "Browser probes skipped — Playwright not available"
    And the chat summary includes the Playwright fallback notice
```

---

## Architecture Specification

### New components

| File | Purpose |
|------|---------|
| `commands/explore.md` | `/explore` command — parses args, validates prerequisites, runs pre-probe steps (charter quality, adversarial expansion), dispatches QA Engineer with exploratory-testing skill |
| `skills/exploratory-testing/SKILL.md` | Heuristic probe strategies, telemetry signals, charter quality rubric, adversarial expansion protocol, session management, defect classification, auto-triage handoff, session debrief. References field guide for deep framework detail. |
| `knowledge/exploratory-testing-field-guide.md` | Synthesized frameworks from *Explore It!*: charter format and generation, variable identification, type variation probes, state modeling heuristics, implicit expectations taxonomy. Loaded by the skill at session start. |

### Modified components

| File | Change |
|------|--------|
| `plugins/agentic-dev-team/CLAUDE.md` | Add `/explore` row to the Slash Commands Registry table |
| `agents/qa-engineer.md` | Add `exploratory-testing` skill reference in the Skills section |
| `knowledge/agent-registry.md` | Add `exploratory-testing` skill row with token estimate |

### Separate dependency

`/triage` must be updated (its own spec/plan) to write triage records to `.triage/<slug>.md`
instead of creating GitHub issues. `/explore` delegates to `/triage` without owning the storage
format. Until `/triage` is updated, the auto-triage step will create GitHub issues.

### Tool model — no new tools required

The explorer reuses the QA Engineer's existing tool grants:

- `Bash(npx playwright *)` — browser-based UI probing (form fills, navigation, double-submit)
- `Bash(curl ...)` — API probing and telemetry measurement
- `Bash` — stdout/stderr capture, log inspection, process-level signals
- `Read`, `Glob`, `Grep` — codebase context before probing

### Pre-probe sequence

Before the first probe executes, three steps run in order. No probes execute and no session report
is written if any step fails.

```
1. Input validation   — target and charter present; connectivity check
2. Charter quality    — rubric evaluation; warn and prompt if anti-pattern detected
3. Adversarial expansion (default on) — generate up to 6 additional probe angles
```

### Charter Quality Evaluation

A good charter "offers direction without overspecifying test actions" (Hendrickson, *Explore It!*).
It is a prompt — it suggests sources of inspiration without dictating precise actions or outcomes.

**The 3-part charter format** (from *Explore It!* §2.3):

```
Explore [target] with [approach or resources] to discover [concern or risk]
```

Examples of well-formed charters:
- "Explore input fields with JavaScript and SQL injection payloads to discover security vulnerabilities"
- "Explore the payment flow with boundary values and concurrent requests to discover double-billing conditions"
- "Explore login with spoofed session tokens to discover if users can access content they didn't purchase"

**Anti-patterns** (trigger a one-line warning and a prompt to refine or `--force`):

| Anti-pattern | Why it fails | Example |
|-------------|-------------|---------|
| Too specific | Specifying exact inputs/values turns it into a test case, not a charter; no room for discovery | "Explore editing with the value O'Malley to check if apostrophes work" |
| Too broad | Infinite scope; you can never know when you're done | "Explore system security with all hacking programs to discover any holes" |
| Missing "with" component | No approach specified; agent has no direction for how to probe | "Explore /payments to find bugs" |
| Missing "to discover" component | No risk hypothesis; any result is equally valid | "Explore auth with boundary inputs" |

When an anti-pattern is detected:
- Display: `Charter quality warning: <anti-pattern description>`
- Prompt: `Refine the charter using the format: "Explore [target] with [approach] to discover [concern]"`
- No probes execute; no session report is written until the user responds

`--force` bypasses the quality check and proceeds directly to adversarial expansion.

### Adversarial Charter Expansion

After the charter passes quality evaluation, the agent surfaces **implicit expectations** — concerns
that stakeholders consider too obvious to state but that every feature must satisfy (Hendrickson,
*Explore It!* §2.4: "We have a security model in this system. New features have to honor that
security model."). These implicit expectations become additional probe angles the charter didn't
explicitly request.

The agent applies three adversarial lenses, each generating up to two additional probe targets:

| Lens | Implicit expectation probed | Example probe generated |
|------|-----------------------------|------------------------|
| Authorization bypass | The feature must honor the existing security model | Empty/null auth token, missing required header, role escalation via parameter |
| Data integrity | Operations must not corrupt state under valid but unusual inputs | Concurrent create+delete of the same entity, max-value update on a constrained field |
| Timing / ordering | The feature must be safe under interstitial states and race conditions | Submit before auth completes, rapid sequential state changes, double-submit |

Before the first probe:
- Display: `Added N adversarial angles: <brief description of each>`
- Inject generated probes into the probe queue with type `adversarial-<lens>`
- Each adversarial probe counts against the probe budget

`--no-adversarial` skips this step entirely.

### Telemetry signals

All signals are captured via `curl` and `Bash` without external observability dependencies.

**Per-probe signals**

| Signal | Capture method | Deepening trigger |
|--------|---------------|-------------------|
| Response time (total) | `curl -w "%{time_total}"` | > 2× session median |
| Time to first byte | `curl -w "%{time_starttransfer}"` | Spike while total is flat → server-side slowness |
| Response size | `curl -w "%{size_download}"` | > 2× or < 0.5× median → payload anomaly |
| HTTP status code | `curl -w "%{http_code}"` | Class change on similar inputs (2xx → 4xx) |
| Stderr/stdout | `2>&1` capture | Any output where prior identical probes produced none |

**Session-level aggregates (computed by agent)**

- Running median of response time and size across probes
- Status code distribution
- Error rate (% of probes returning 4xx/5xx)

**Log-file delta (optional, when log path is known)**

```bash
lines_before=$(wc -l < "$LOG_FILE")
# ... execute probe ...
lines_after=$(wc -l < "$LOG_FILE")
tail -n $((lines_after - lines_before)) "$LOG_FILE"
```

### Pre-probe variable identification

Before the first probe, the agent enumerates everything that can vary in the target, drawn from
the charter's "with" component and the target's interface (from *Explore It!* Ch. 10):

- **Parameters**: count, names, order
- **Values**: boundary values, null/empty/zero, wrong types, special values, large sizes
- **Data types**: string, number, boolean, null, object, array — and mixed combinations
- **Character sets**: ASCII, Unicode, accented, CJK, nonprinting, whitespace variants

This list is not exhaustive — it's a starting point. The agent allocates probe budget across
variables according to the charter's risk hypothesis ("to discover" clause). Variables most
relevant to the stated concern get the most probes.

### Heuristic definitions

| Heuristic | Description | Implementation |
|-----------|-------------|----------------|
| Goldilocks | Boundary-value probing: null/empty, max-length, valid-range boundaries. Type-variation probing: null, wrong type, special values (Infinity, NaN, -0, empty string, Unicode, nonprinting chars). Set-dimension variants: empty set, single element, full set (None/Some/All) for permissions/roles/multi-select fields. | `curl` payloads and Playwright form fills. Probe labels: `Goldilocks:boundary`, `Goldilocks:type`, `Goldilocks:set-none`, `Goldilocks:set-some`, `Goldilocks:set-all`. |
| Happy-Path Divergence | Interrupt standard user flows at critical state changes | Playwright `page.goBack()`, double-submit, session abandonment |
| Telemetry Deepening | Reactive: triggered by telemetry anomaly including response time spikes on very large inputs; varies parameters on anomalous endpoint | `curl -w` measurement; size escalation probes; parameter sweep on the flagged endpoint |
| Invariant Probing | Validates declared system invariants on every probe. Invariants are specified via `--invariants "<statement>"` in the command invocation or inferred from the charter's stated expectations. | Each probe response is checked against all declared invariants. Any invariant violation is immediately classified Critical — no retry, because the invariant is the oracle. Probe label: `Invariant`. |
| CRUD Sweep | Systematically exercises Create, Read, Update, Delete on any entity noun referenced in the charter. | Agent extracts entity nouns from the charter text. Generates one probe per CRUD operation. Integrates with Goldilocks by applying boundary inputs to each operation. Probe labels: `CRUD:Create`, `CRUD:Read`, `CRUD:Update`, `CRUD:Delete`. |

### Session termination model

Sessions end when the first of these conditions is met:

1. Probe budget exhausted (default: 15, overridable via `--probes <n>`)
2. Critical defect detected — retry once (except invariant violations, which are Critical immediately), then stop and triage
3. User invokes `/stop`
4. Agent judgment: no further productive probes reachable given the charter

### Defect classification

| Severity | Trigger | Action |
|----------|---------|--------|
| Critical | HTTP 5xx (after retry), unhandled exception, application crash, data corruption, invariant violation (no retry) | Write trace → invoke `/triage` → stop session |
| Warning | Unexpected 4xx on valid input, telemetry anomaly, inconsistent response structure | Log to report → continue probing |
| Informational | UX deviation with no error signal | Log to report |

### Auto-triage handoff

When a critical defect is detected:

1. Write trace to `tmp/explore-trace-<YYYYMMDDTHHMMSS>.md`
2. Invoke `/triage` with the trace content as its argument
3. On success: record the `.triage/<slug>.md` path in the session report
4. On failure: record the failure reason; preserve `tmp/explore-trace-<timestamp>.md`

### Session Debrief: Next Exploration Suggestions

During exploration, off-charter temptations are signals, not distractions. As Hendrickson writes
(*Explore It!* §2.4): "Such temptations are a cue that you need to jot down additional charters
to pursue in later sessions." The session debrief captures these signals as runnable charters.

At session end (any termination reason), the report includes a "Next Exploration" section with
2–3 recommended follow-up charters in the 3-part format. Suggestions are generated based on:

- Off-charter anomalies encountered: "Probe of /auth triggered an unexpected response at /session — explore /session with expiry edge cases to discover timeout handling bugs"
- Heuristics not fully exercised: "CRUD Sweep wasn't applicable to this read-only endpoint — explore /api/users with write operations to discover data mutation constraints"
- Probe types with the most anomalies: "Goldilocks boundary inputs found 2 warnings — explore the same target with extended boundary ranges to discover where validation breaks"

Each suggestion is formatted as a runnable charter string in the 3-part format:

```
Next Exploration:
- /explore api/orders --charter "Explore /api/orders with invalid state transitions to discover error handling gaps"
- /explore api/users --charter "Explore /api/users with CRUD operations to discover data mutation constraints"
```

### Output locations

| Artifact | Path |
|----------|------|
| Session report | `reports/explore-<YYYYMMDDTHHMMSS>.md` |
| Trace file (on critical defect) | `tmp/explore-trace-<YYYYMMDDTHHMMSS>.md` |
| Triage record (via /triage) | `.triage/<slug>.md` |

Timestamp format: `YYYYMMDDTHHMMSS` — no colons, filesystem-safe on all platforms.

### Out of scope for this slice

- `/build` post-build sentinel integration (Slice 2)
- Data Flow Tracing / "Follow the Data" heuristic (Slice 2 — requires inter-probe state)
- State Transition Probing (Slice 2 — see framework notes below)
- Adversarial review phase integration — Explorer as "Chaos" voice in parallel code review (Slice 3)
- Resource exhaustion / Starve heuristic (Low priority — requires OS-level resource control outside curl)
- External observability platform integration (Grafana, Datadog, etc.)
- Parallel multi-charter sessions

**Slice 2 forward guidance — State Transition Probing framework** (from *Explore It!* Ch. 8):

State identification uses two heuristics the Slice 2 spec should formalize:

1. **Jorgensen's 3 questions** — ask these about the target to detect states:
   - Are there things I could do now that I could not do before?
   - Are there things I cannot do now that I could do before?
   - Do my actions have different results now than before?

2. **The "while" language cue** — scan charter text, requirements, and code comments for sentences
   using "while": "while the account is suspended...", "while the system is importing data...".
   Each "while" clause identifies a state.

3. **Event taxonomy** (three event types to probe):
   - *User action events*: explicit inputs triggering transitions
   - *System-generated events*: background activities (auth, data loading) with interstitial states
   - *Time-based events*: timeouts, scheduled operations, expiry windows

4. **Abstraction dial** — narrow target → map transitory substates; broad target → lump substates
   into one named state. "If you cannot give it a simple name, it's probably more than one target."

State model for Slice 2: states = circles; transitions = labeled arrows; probe set = valid
forward transitions + reverse (invalid) transitions + skipped transitions + time-based events.

---

## Acceptance Criteria

1. The command begins executing probes immediately upon invocation; probe results appear in chat output before the agent waits for user input.
2. The session report contains at least one logged probe entry of type Goldilocks and at least one of type Happy-Path Divergence unless the charter text explicitly restricts scope or a probe type is inapplicable to the target. Telemetry Deepening entries appear only when a telemetry anomaly is detected.
3. Each probe entry in the session report includes: probe type, input, HTTP status code, response time (ms), response size (bytes), and captured stderr (if any). Report is written incrementally after each probe.
4. When a critical defect is detected (after one retry, except invariant violations), `/triage` is invoked automatically. On success, the `.triage/<slug>.md` path appears in the session report. On `/triage` failure, the failure reason is recorded and the raw trace is preserved at `tmp/explore-trace-<timestamp>.md`.
5. When no critical defect is found, the report explicitly states this and no `/triage` invocation occurs.
6. Warning-severity defects appear in the session report with severity "warning". No `/triage` invocation is triggered for warning-severity findings.
7. The session terminates at or before the probe budget (default 15); the report states the termination reason.
8. Missing `--charter` argument: the agent prompts with the exact wording "What should I investigate? Provide a charter: --charter '<goal>'" before any probes execute; no session report is written.
9. Unreachable dev server: the agent reports the attempted URL and the connection error before any probes execute; no session report is written.
10. Session report is written to `reports/explore-<YYYYMMDDTHHMMSS>.md`; a partial report is written on `/stop` or unexpected termination.
11. `explore.md` and `exploratory-testing/SKILL.md` pass `/agent-audit` structural compliance. All registry rows are present and match the column schema of adjacent rows.
12. Charter quality evaluation runs before any probes execute. If the charter matches an anti-pattern (too specific/test case, too broad/infinite scope, missing "with" component, missing "to discover" component), the agent displays a one-line warning and prompts: `Refine the charter using the format: "Explore [target] with [approach] to discover [concern]"`. No probes execute and no session report is written until the user responds.
13. Adversarial charter expansion runs by default after charter quality evaluation. Up to 6 additional probe angles are generated (2 per lens: authorization bypass, data integrity, timing/ordering) and displayed before any probe executes. `--no-adversarial` skips this step entirely. Adversarial probes are labeled `adversarial-<lens>` in the session report.
14. When `--invariants` is provided, each probe response is validated against the declared invariants. Any invariant violation is classified Critical immediately (no retry) and triggers the auto-triage handoff. The session report records the violated invariant and the actual response.
15. When the charter references an entity noun, a CRUD Sweep generates Create, Read, Update, and Delete probes for that entity. Each CRUD probe applies Goldilocks boundary inputs. Probe entries are labeled `CRUD:Create`, `CRUD:Read`, `CRUD:Update`, `CRUD:Delete`.
16. Goldilocks probing includes set-dimension variants when the target involves permissions, roles, or multi-select fields: one probe with no values (set-none), one with a single value (set-some), one with all available values (set-all). Probe entries are labeled `Goldilocks:set-none`, `Goldilocks:set-some`, `Goldilocks:set-all`.
17. The session report includes a "Next Exploration" section at the end with 2–3 recommended follow-up charters formatted as runnable command strings.

---

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret it the same way
- [x] Every behavior in the intent has a corresponding BDD scenario
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across all four artifacts ("probe", "charter", "session", "triage record", "adversarial angle", "invariant")
- [x] No contradictions between artifacts
- [x] Deferred capabilities (Data Flow, State Transition, Slice 3 adversarial review) are explicitly named in Out of Scope
