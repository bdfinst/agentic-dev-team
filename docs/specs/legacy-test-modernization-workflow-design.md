# Design — `/test-modernize` orchestrator workflow

> **Implementation:** the `/test-modernize` skill at [`plugins/dev-team/skills/test-modernize/SKILL.md`](../../plugins/dev-team/skills/test-modernize/SKILL.md). For the operator-facing workflow overview with the rendered phase diagram, see [Architecture → Test modernization workflow](../../plugins/dev-team/docs/agent-architecture.md#test-modernization-workflow); for how it composes with the rest of the test-evaluation tools, see [Test Evaluation and Architecture](../../plugins/dev-team/docs/test-evaluation.md). This document is the design rationale — *why* the workflow has the shape it does.

A repeatable replacement for the legacy-test-modernization prompt, modeled on `/ship`. `/test-modernize` doesn't implement anything itself — it sequences existing skills/agents through the five-phase order of operations, holds the human gates, and writes its deliverables to whichever issue tracker the operator points at (ADO, GitHub, Jira, …) — or to local `plans/` and `specs/` files when no tracker is given.

## Why a skill, not a prompt

The prompt works once. A skill makes the procedure:

- **Versioned and reviewable** — the procedure ships with the plugin and goes through PR review.
- **Composable** — phases delegate to single-purpose skills (`/cd-test-architecture`, a new `/gherkin-public`, a new `/coverage-baseline`, etc.). Each skill is independently testable and re-usable.
- **Gated** — human gates are encoded in the skill instead of relying on the operator to remember to stop.
- **Observable** — metrics (coverage, mutants, determinism, wall-clock) land in `metrics/` and on the ADO Feature description automatically.
- **Resumable** — `/continue` already resumes phase progress files from `memory/`; phase-keyed progress means a multi-day modernization survives session boundaries.

## Pattern: orchestrator + per-phase worker skills + direct tracker-CLI dispatch

```
/test-modernize  (orchestrator skill, role: orchestrator)
│
├── Phase 0 — Resolve sink
│   └── Ask: "Parent issue URL? (ADO / GitHub / Jira / GitLab — or empty for local files)"
│       → Detect tracker from URL host; probe the matching CLI (gh / az / glab / acli).
│       → If empty (or the CLI is missing): sink = local-files (writes to ./plans/ and ./specs/).
│
├── Phase 1 — Analyze
│   └── /cd-test-architecture (existing worker)
│       → /issues-from-assessment <parent-url-or-empty>  (new worker — dispatches to the right sink)
│       ⇢ HUMAN GATE: backlog review
│
├── Phase 2 — Specify public interface
│   └── /gherkin-public  (new worker)
│       → writes .feature files at the public boundary per component pattern
│       ⇢ HUMAN GATE: Gherkin sign-off
│
├── Phase 3 — Audit + baseline coverage
│   └── /test-audit-disable  (new worker — disables cannot-fail tests)
│   └── /coverage-baseline   (new worker — runs coverage, posts to Feature)
│       ⇢ HUMAN GATE: baseline accepted
│
├── Phase 4 — Fix disabled tests + add no-refactor tests
│   └── /build  (existing — drives TDD slices for Phase-4 Stories)
│   └── /coverage-delta  (new worker — Δ vs baseline, posts to Feature)
│       ⇢ HUMAN GATE: delta accepted
│
├── Phase 5 — Refactor-for-testability + converge on quality targets
│   └── /build  (existing — Phase-5 Stories, one at a time, baseline-green-first)
│   └── /mutation-testing  (existing skill)
│   └── /quality-targets-converge  (new worker — closes gap to 90/0/det/speed)
│       ⇢ HUMAN GATE: targets met or explicitly waived
│
└── Report → final coverage %, surviving mutants, determinism, wall-clock; ADO Feature closed.
```

Each phase is one skill invocation from the orchestrator. The orchestrator never reads files, never edits code, never calls `az` directly — it sequences and gates.

## Skill set required

Existing, reusable:

- `/cd-test-architecture` — Phase 1 assessment (already shipping).
- `/build` — Phase 4 + 5 TDD execution against ADO Stories (already shipping; needs an ADO-input mode).
- `/code-review` — runs inline within `/build`.
- `mutation-testing` skill — Phase 5 mutant kill verification.
- `/continue` — resume the workflow from any phase boundary.

New, single-purpose workers (each ~80–150 lines):

| Skill | Role | Inputs | Outputs |
|---|---|---|---|
| `/issues-from-assessment` | worker | `/cd-test-architecture` report + parent-URL (or empty) | Issues written via the resolved tracker CLI — ADO Feature+Stories+Tasks via `az boards`, GitHub Issues via `gh`, Jira Epic+Stories+Subtasks via `acli`, GitLab Issues via `glab`, or local `./plans/*.md` + `./specs/*.md` files when no URL is given or the matching CLI is missing |
| `/gherkin-public` | worker | repo + component pattern map | `.feature` files at the public boundary per component (API endpoints, UI flows, batch entry points, library exports, event types) |
| `/test-audit-disable` | worker | repo's test suite | tests with no real assertions disabled (skip + tag), reasons recorded |
| `/coverage-baseline` | worker | repo's test suite | coverage report + number posted to Feature description |
| `/coverage-delta` | worker | baseline + current | Δ posted to Feature description |
| `/quality-targets-converge` | worker | coverage + mutation + flake + wall-clock data | loop that closes the gap to 90/0/det/speed; per iteration: smallest action that moves a metric |
| `/airplane-test` | worker | CI config + test runtime | enforces egress-blocked CI step; reports any off-machine call attempted by a test |

New review agent:

- `dev-team:test-modernization-review` — gate-keeper for each phase boundary. Reads the phase's deliverable and either approves the move to the next phase or returns blocker findings to the orchestrator. Mirrors how `progress-guardian` and `spec-compliance-review` already work.

## Orchestrator skill shape (sketch)

```yaml
# plugins/dev-team/skills/test-modernize/SKILL.md
---
name: test-modernize
description: >-
  Modernize a legacy repository's tests for CD: assessment → public-interface
  Gherkin → disable cannot-fail tests + baseline coverage → add no-refactor
  tests → minimum-refactor + converge on 90% coverage, zero surviving mutants,
  full determinism, fastest pre-merge wall-clock. Outputs phase issues to ADO,
  GitHub, Jira, or local plans/specs files — whichever the parent issue URL
  resolves to (no URL given falls back to local files).
argument-hint: "<repo-path> [--parent <issue-url>] [--ci <path>] [--external-tests <loc>] [--from-phase <n>]"
user-invocable: true
role: orchestrator
allowed-tools: Read, Glob, Grep, Bash, Skill, Agent
---
```

Step skeleton (each step is one delegated call + one gate):

1. **Approach contract** — confirm repo path, **parent issue URL (ADO / GitHub / Jira / GitLab — or empty for local files)**, external tests location, CI config, quality targets (defaults: 90% / 0 / 100% / fastest). One-batch question to operator if any is ambiguous. The sink adapter is resolved from the URL host (`dev.azure.com` → ADO, `github.com` → GitHub Issues, `*.atlassian.net` → Jira, `gitlab.com` / self-hosted GitLab → GitLab Issues, empty → local-files).
2. **Phase 1** — `Skill("cd-test-architecture", "<repo> --ci ... --external-tests ...")` → `Skill("issues-from-assessment", "<assessment> --parent <url-or-empty>")` → dispatch `dev-team:test-modernization-review` with `--phase 1`. Human gate.
3. **Phase 2** — Pass A: `Skill("gherkin-public", "<repo>")` writes `.feature` files only → dispatch the review agent with `--phase 2` (pass-A checks). Human gate. Pass B: `Skill("gherkin-public", "<repo> --create-stories --parent <url>")` creates one `[Component tests]` Story per approved (component, surface), each Story body binding its tests to the specific `<feature-file>::<scenario-name>` pairs it must satisfy. Backfill the Phase-1 predecessor placeholders for `[Component tests]` with the new IDs.
4. **Phase 3** — `Skill("test-audit-disable", "<repo>")` → `Skill("coverage-baseline", "<repo>")` → ADO Feature description updated. Human gate.
5. **Phase 4** — for each Phase-4 Story in dependency order: `Skill("build", "<story-id>")` (TDD + `/code-review`). For `[Component tests]` Stories, `/build` binds tests to the scenarios cited in the Story body using the binding mode recorded in `phase-0.md` (`bdd-runner` or `xunit-with-annotations`). `Skill("coverage-delta", "<repo>")` → review agent `--phase 4` (cross-checks scenario → Story-id map against the actually-submitted test code). Human gate.
6. **Phase 5** — for each Phase-5 ADO Story in dependency order: `Skill("build", "<story-id>")` → after every Story, `Skill("mutation-testing", ...)` and `Skill("quality-targets-converge", ...)` until targets are met. Final gate: human accepts metrics or waives a target with reason.
7. **Report** — final metrics, ADO Feature URL, PR list, what (if anything) was waived.

## State / resume

Each phase emits a single progress file under `memory/test-modernize/<repo>/phase-<n>.md` with: phase number, ADO Story IDs touched, deliverable paths, metric snapshot, gate status. `/continue` already reads `memory/` — `/test-modernize --from-phase <n>` keys off these files so a partial run resumes without re-doing the analysis.

## Gherkin binding — the approved scenarios drive the component tests

The Phase-2 Gherkin is not advisory. It is the **executable specification of intended behavior**, and every component test in the suite ends up bound to a specific approved Scenario.

The contract:

1. **Phase 1 does not create `[Component tests]` Stories.** `/issues-from-assessment` creates `[Gap]`, `[Baseline]`, `[Refactor-for-testability]`, `[De-duplicate]`, `[Re-scope]`, and non-component target-architecture Stories — never `[Component tests]`. Phase-1 Stories that would depend on a component-test Story (contract / integration / E2E / resilience) leave a placeholder predecessor (`Depends on: [Component tests] for <component>`) that Phase 2 backfills.
2. **Phase 2 Pass A — author scenarios only.** `/gherkin-public` writes `.feature` files per public surface. No Stories are created yet. The Phase-2 review-agent pass-A checks confirm `gherkin-bindings.json` does not yet exist (the operator-gate has not been bypassed).
3. **Human gate.** The operator reviews and may edit `.feature` files in place. This is the only point where the team decides what behavior the system intends.
4. **Phase 2 Pass B — bind Stories.** `/gherkin-public --create-stories` creates one `[Component tests] <component> · <surface>` Story per approved (component, surface). Each Story's Acceptance Criteria cites the specific `<feature-file>::<scenario-name>` pairs its tests must satisfy. The scenario → Story-id map is written to `memory/test-modernize/<slug>/gherkin-bindings.json`. Pass-B review-agent checks verify every Scenario has a Story citing it and every Story cites at least one Scenario.
5. **Phases 4 + 5 bind tests to scenarios.** When `/build` works a `[Component tests]` Story, it reads the Story body's scenario list + the binding mode the operator chose in Phase 0 (`bdd-runner` or `xunit-with-annotations`) and authors tests that mirror each Scenario by name (xUnit) or generate step definitions (BDD runner). Acceptance Criteria checkboxes (one per Scenario) all turn green before the Story closes.
6. **Phase-4 review verifies binding integrity.** The review agent cross-checks `gherkin-bindings.json` against the submitted test code and flags every unbound Scenario AND every test method that names a Scenario the approved Gherkin does not contain (drift in both directions).
7. **Phase 5 may not invent Scenarios.** If `/quality-targets-converge` discovers a coverage gap or surviving mutant that no approved Scenario covers, it opens a `[Phase-2 amendment]` Story and pauses convergence until the operator approves the new Scenario via the standard Phase-2 sign-off. The Phase-5 component-test Story then binds to the now-approved Scenario. The operator remains the only author of intent.

This is what keeps the workflow honest: the assessment proposes coverage gaps, the Gherkin specifies intended behavior, and the tests are written to the Gherkin — not to the assessment. The operator's Phase-2 review is the only place behavior is decided.

The binding mode (`bdd-runner` vs `xunit-with-annotations`) is a per-repo choice recorded once in `memory/test-modernize/<slug>/phase-0.md`. Both modes carry the same binding contract (each test cites the Scenario it exists to satisfy); they differ only in whether the runner executes the `.feature` file directly or whether the test name + leading comments serve as the citation. The default is `xunit-with-annotations` because it adds no new runtime dependency and works in every test framework the plugin already targets.

## Issue sink — direct CLI dispatch (no adapter library)

The orchestrator asks the operator for a **parent issue URL** at the approach-contract step. From that URL the workers resolve which tracker CLI to invoke — `gh`, `az boards`, `glab`, or `acli` (Jira). If the CLI isn't installed or authed, the workers inform the operator (with the exact install command) and fall back to local-files mode automatically.

**Supported sinks:**

| Parent URL pattern | CLI | Probe | Falls back to local files if probe fails |
|---|---|---|---|
| `https://dev.azure.com/<org>/<proj>/_workitems/edit/<id>` | `az` (with `az boards` extension) | `command -v az && az extension show -n azure-devops` | yes |
| `https://github.com/<owner>/<repo>/issues/<n>` | `gh` | `command -v gh && gh auth status` | yes |
| `https://<site>.atlassian.net/browse/<KEY>-<n>` | `acli` (Atlassian CLI; REST + `$JIRA_TOKEN` as fallback) | `command -v acli` | yes |
| `https://gitlab.com/<group>/<repo>/-/issues/<n>` (or self-hosted) | `glab` | `command -v glab && glab auth status` | yes |
| *empty / `--parent` omitted* | (none) | — | (already local-files mode) |

Two skills concentrate the CLI interaction:

- `/issues-from-assessment` — invokes the resolved CLI to create the parent's children from the Phase-1 assessment (or writes local plan files if the CLI is missing).
- `/coverage-baseline` / `/coverage-delta` / `/quality-targets-converge` — each appends metric snapshots to the parent issue (or `./plans/test-modernize/FEATURE.md`) using the same CLI invocation patterns documented in `/issues-from-assessment`. There is no shared shell-adapter library; CLI knowledge sits in the workers themselves so adding a tracker means editing one branch in each of those skills.

**Local-files mode.** When no `--parent` is given:

- `./plans/test-modernize/FEATURE.md` is the parent (assessment summary + running metric snapshots).
- `./plans/test-modernize/phase-<n>/<slug>.md` is one file per "Story" (one per CD-fitness gap, baseline, refactor-for-testability, etc.) with the same Acceptance Criteria the tracker-mode would emit.
- `./specs/test-modernize/<surface>.feature` is the Phase-2 Gherkin output.
- `sink_mark_done` flips a `Status:` line in the file and prepends a date.
- Predecessor links become a `Blocked by:` line citing the relative path of the blocker file.

This means the workflow is identical whether the operator has a tracker or not — only the final destination of the issues changes.

## Reuse pattern from `/ship`

Lift the structure verbatim:

- `role: orchestrator`.
- `allowed-tools` lists only `Skill(...)` (each delegated skill) plus `Agent` (for the gate-keeper review) and the read-only triplet — never `Edit`/`Write`.
- "Orchestrator constraints" block at the top: delegate every phase, honor human gates, confirm the approach first, be concise.
- One step per phase, each step ends with the gate keyword "**Human gate** — wait for approval before <next phase>."
- Notes block at the bottom: "if any phase stops at a gate, `/test-modernize` stops with it."

## What you get vs the prompt

| Concern | Prompt today | `/test-modernize` skill |
|---|---|---|
| Procedure source-of-truth | A markdown report the operator pastes | Versioned skill in the plugin |
| Gate enforcement | Operator self-discipline | Encoded in the orchestrator |
| Resumption mid-modernization | Re-paste, re-explain | `/continue` + phase progress files |
| Issue tracker writes | One blob the operator hand-runs against ADO only | Pluggable sink adapter (ADO / GitHub / Jira / GitLab / local files) selected from the parent issue URL |
| Metrics on the parent issue | "Post to the Feature description" — operator does it | `/coverage-baseline` / `/coverage-delta` / `/quality-targets-converge` post via the shared sink helper |
| No tracker available | Operator improvises | Local-files mode writes `./plans/test-modernize/` + `./specs/test-modernize/` automatically |
| Per-repo customization | Edit the pasted prompt | CLI flags + one-batch approach contract |
| Audit trail | Whatever the operator pasted that day | Progress files in `memory/` + ADO history |
| Repeatability across repos | Operator copy-pastes; drift over time | Identical procedure every repo |

## Incremental build order (lowest risk first)

The skill set above is big; ship it in slices:

1. `/issues-from-assessment` (worker) with the `local-files` and `github` adapters first + a thin `/test-modernize` that calls only `/cd-test-architecture` + this. Replaces Phase 1 of the prompt. Add `ado.sh`, `jira.sh`, `gitlab.sh` adapters incrementally as demand appears.
2. Add `/gherkin-public` and Phase 2. The skill now covers analysis + public-interface spec.
3. Add `/test-audit-disable` + `/coverage-baseline` and Phase 3.
4. Wire `/build` to consume ADO Story IDs for Phase 4. Add `/coverage-delta`.
5. Add `/quality-targets-converge` + the `dev-team:test-modernization-review` agent + Phase 5.

Each slice is independently shippable, and after step 1 the operator is already off the prompt for the most error-prone phase (ADO issue creation).

## Open questions for the build

- **Adapter implementations vs auth.** The orchestrator resolves the sink from the URL host, but each adapter still needs its own auth: ADO wants `az login` or `AZURE_DEVOPS_EXT_PAT`, GitHub wants `gh auth status`, Jira wants `JIRA_TOKEN` + base URL, GitLab wants `glab auth status`. `/test-modernize` should probe auth at Phase 0 and fail fast with a clear "run `gh auth login` first" message rather than discovering it mid-Phase-1. `/issues-from-plan` (the existing GitHub-only skill) is the reference for the GitHub adapter — lift its `gh issue create` patterns into `github.sh` rather than re-deriving them.
- **Where the airplane-test enforcement lives.** Either a hook (PreToolUse gate on tests that open non-loopback sockets) or a CI step injected by `/airplane-test`. The hook is stronger but is plugin-local; the CI step is portable. Probably both, with the hook on by default for plugin users.
- **Default quality targets.** 90 / 0 / 100% / "fastest" are good defaults. Make them overridable per-repo via `.dev-team/quality-targets.json` so the orchestrator can read them at the approach-contract step without prompting every time.
