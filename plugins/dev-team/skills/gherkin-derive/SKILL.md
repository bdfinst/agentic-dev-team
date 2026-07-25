---
name: gherkin-derive
description: >-
  Derive Gherkin scenarios directly from a codebase — standalone, with no
  prior legacy-modernization analysis. Discovers the public surface (OpenAPI,
  routes, existing tests, exported signatures, plus message-queue, cron, and
  websocket/GraphQL surfaces), recommends a BDD binding
  mode via the bdd-value-guide rubric, and writes `.feature` files plus
  (in bdd-runner mode) pending step-definition stubs. Use it on its own to
  capture intended behavior before changing tests, or as Phase 3 of
  `/test-improve`. Creates no tracker Stories.
argument-hint: "<repo-path> [--mode none|xunit-with-annotations|bdd-runner] [--repo-slug <slug>]"
role: worker
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write
---

# Gherkin Derive

Role: worker. A **standalone** Gherkin derivation skill. It derives scenarios for
a repo's public surface directly from code — it does **not** require any prior
`/cd-test-architecture` analysis, and it does **not** create tracker Stories
(the calling orchestrator owns triage). `/gherkin-public` remains a
public-boundary Gherkin authoring worker used standalone.

Usable two ways: on its own to capture intended behavior before any test change,
or as the Phase-3 sub-step of `/test-improve`.

## Parse Arguments

- Positional: `<repo-path>` (default: cwd).
- `--mode <none|xunit-with-annotations|bdd-runner>` — the binding mode. When
  omitted, present the BDD value rubric (Step 1) and let the operator choose.
- `--repo-slug <slug>` — namespace for the surface inventory under
  `.claude/memory/<workflow>/<slug>/` (`/test-improve` passes `--workflow test-improve`).

## Step 1 — Choose the binding mode (BDD value rubric)

If `--mode` was **not** supplied, present the 5-question rubric from
`knowledge/references/bdd-value-guide.md` and recommend a mode from the score:

- `≥ 3 yes` → **`bdd-runner`**
- `1–2 yes` → **`xunit-with-annotations`**
- `0 yes` → **`none`**

Show the recommendation and let the operator override. The three modes:

- **`none`** — emit no Gherkin. Exit immediately with a one-line recommendation
  to use plain xUnit (e.g. *"0/5 BDD signals — use plain xUnit; no `.feature`
  files written."*). **Write no files.**
- **`xunit-with-annotations`** — derive scenarios and write `.feature` files, but
  do **NOT** wire a BDD runner or install any framework. The files are
  documentation that `/build` cites in test method names and leading comments.
- **`bdd-runner`** — derive scenarios, write `.feature` files, wire the
  language-appropriate BDD framework (Step 4), and generate pending step
  definition stubs.

## Step 2 — Discover the public surface

No pre-computed component map is required. Discover surfaces in this **priority
order**, most authoritative first:

1. **OpenAPI / Swagger spec** (`openapi.yaml`, `openapi.json`, `swagger.json`) —
   the most authoritative description of the public surface. Each path+method is
   a surface.
2. **Route definitions** — Express/Fastify handlers, Spring `@Controller` /
   `@RestController`, ASP.NET `[ApiController]`, Go `http.HandleFunc` / Chi / Gin
   routes. Each registered route is a surface.
3. **Existing test names** — `describe` / `it` / `[Fact]` / `@Test` blocks. These
   yield **characterization** scenarios (current behavior, not intended
   behavior). Use them as the primary source only when OpenAPI and routes do
   not already cover the surface. **Never treat a test's assertion as ground
   truth on its own** — before accepting a test-derived scenario, cross-check
   it against any other available signal (docstrings, comments, adjacent
   OpenAPI/route info, obvious status-code conventions). Record what was
   cross-checked (or that nothing was found) per Step 3.
4. **Public function signatures + docstrings** — exported functions/classes with
   doc comments. The lowest-priority fallback for libraries with no HTTP surface.

Stop climbing the list for the **same surface description** once a
higher-priority source covers it — do not duplicate a route's success/failure
scenarios from its tests. But do not let this rule discard information: even
when a surface is already covered by OpenAPI or a route, still scan its
existing tests for error/edge branches that are **not** present in the
documented spec, and add those as *supplemental* characterization scenarios
rather than dropping them.

**Graph-assisted discovery.** If the target repo has `.codegraph/` (CodeGraph
MCP server, `mcp__codegraph__codegraph_explore` — fast callers/callees/impact
lookups) and/or a Repowise MCP server (`get_context`/`search_codebase` —
verified context and semantic search), prefer them over raw `Grep` for
locating routes, handlers, and exported signatures. Never assume either is
present — fall back to `Read`/`Grep`/`Glob` when absent; the tools are simply
unavailable (no error) on repos without an index.

**Async / event / scheduled surfaces — a separate discovery pass, run
regardless of the cascade above.** These have no OpenAPI equivalent and the
1–4 cascade will never find them, yet Step 3 already has templates
(**Batch / Scheduled Job**, **API / Event Consumer**) waiting to describe
them. Scan for:

- **Message-queue consumers/producers** — Kafka `@KafkaListener` /
  `KafkaConsumer`, SQS handlers, RabbitMQ `@RabbitListener`, generic
  `consume(...)` / `on_message(...)` callback registrations.
- **Scheduled/cron entry points** — Spring `@Scheduled`, `node-cron` /
  `cron.schedule(...)`, Quartz jobs, Kubernetes `CronJob` manifests.
- **WebSocket / GraphQL handlers** — `@SubscribeMessage`, `io.on(...)` /
  `socket.on(...)`, GraphQL resolver definitions (`Query`/`Mutation`/
  `Subscription` fields).

Each hit is its own surface: route message-queue and event hits to the
**API / Event Consumer** template, and cron/scheduled hits to the
**Batch / Scheduled Job** template.

**Resolve the existing file before authoring (issue #1420).** Run
`detect_bdd_convention.py` once per repo to get the project's `.feature`
destination directory, then compose each surface's path yourself as
`<dir>/<surface>.feature` — `detect_bdd_convention.py`'s own contract stays a
single project-wide directory probe; this skill composes the per-surface
path, it never asks the script to resolve one itself:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect_bdd_convention.py
```

If a file already exists at that composed path, **read it** before authoring
anything for that surface — Step 5 merges into it rather than overwriting.

## Step 3 — Author scenarios

Use the same templates as `/gherkin-public`: **API Provider**, **UI**,
**Batch / Scheduled Job**, **CLI / Library**, **API / Event Consumer**. Every
scenario covers at least one success and one failure path, and every step is
observable at the boundary — no internal calls.

**Ground every failure path in an observed condition.** Before filling a
failure-scenario placeholder, locate a specific failure condition actually
present in the code — a conditional, a thrown/raised exception, a documented
or observed HTTP status code, a validation rule — and cite it in the scenario
body. When CodeGraph/Repowise are available, use `codegraph_explore` (or
Repowise `get_context`/`search_codebase`) to inspect a surface's actual
branches and error-handling depth for this; fall back to reading the source
directly when the tools are unavailable. Do not invent a generic
`<invalid request>` / `<failure-mode-summary>` placeholder as a paraphrase of
the surface's name or signature. When no such condition is discoverable for a
surface, mark that scenario `# TODO: no observed failure path — hand-author`
instead of fabricating one — an honest gap beats an invented scenario.

**Label the provenance** in each `.feature` file header:

- Scenarios derived from OpenAPI or docstrings are **specification** scenarios
  (intended behavior).
- Scenarios derived from existing tests or code are **characterization**
  scenarios — the header MUST state `# Characterization: current behavior, not
  intended behavior` so a reader never mistakes a captured bug for a spec.
  They are hypotheses about intended behavior, not confirmed specs.

```gherkin
# Source: <openapi path | route | test file | signature>
# Provenance: specification | characterization
# Characterization: current behavior, not intended behavior   (characterization only)
# Cross-check: <docstring/OpenAPI/route signal that corroborates this, or "none found — unverified against intended behavior">   (characterization only)
Feature: <surface>
  Scenario: <success path>
    ...
  Scenario: <failure path — a real observed condition, or the hand-author TODO>
    ...
```

**Detect drift in retained scenarios (issue #1420).** For each existing
scenario retained (not replaced) during Step 5's merge, extract the observed
condition for that same path exactly the way this step already does when
authoring a fresh scenario — a status code, exception, or validation rule.
Then call `gherkin_feature_merge.py check-stale` to decide match/mismatch
deterministically, never by eyeballing the comparison yourself:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_feature_merge.py check-stale \
  --existing <dir>/<surface>.feature --feature-title "<surface>" \
  --observed "<scenario title>=<observed value>" --json
```

On a reported mismatch, leave the retained scenario's text unmodified — do
not rewrite it — and record it for the Step 6 report.

## Step 4 — Wire the BDD framework (bdd-runner mode only)

Skip this step entirely in `none` and `xunit-with-annotations` modes.

Read `knowledge/test-stack-profiles/bdd-frameworks.md` for the per-language install steps
and directory layout, then generate **pending** step-definition stubs so the
suite **compiles and fails intentionally** (red before green) — never empty stubs
that pass silently.

| Language | Framework | Pending stub |
|---|---|---|
| JS/TS | Cucumber.js | `return this.pending();` |
| Java (Maven) | Cucumber-JVM + `cucumber-junit-platform-engine` | `throw new io.cucumber.java.PendingException();` |
| Java (Gradle) | Same via Gradle config | `throw new io.cucumber.java.PendingException();` |
| C# | Reqnroll (xUnit / NUnit / MSTest) | `throw new PendingStepException();` (Reqnroll's own auto-suggested stub; `ScenarioContext.StepIsPending()` is deprecated as of Reqnroll 3.3.4 — see `bdd-frameworks.md`) |
| Go | Godog | `return godog.ErrPending` |

## Step 5 — Output

- `features/<surface>.feature` files (all non-`none` modes) — **merged, not
  replaced (issue #1420).** For each surface, write the newly-authored
  scenario text to a scratch candidates file, then invoke
  `gherkin_feature_merge.py merge` — never a raw `Write` — to produce the
  file on disk:

  ```
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_feature_merge.py merge \
    --existing <dir>/<surface>.feature --candidates <scratch-file> \
    --feature-title "<surface>" --json
  ```

  This is exactly one write path whether or not a file already existed at
  that path — a surface with no prior file goes through the same `merge`
  subcommand, which synthesizes a fresh block, so there is never a second,
  divergent write path to keep in sync. Any prior enrichment already in
  the file (hand-authored or from `/feature-coverage-analyzer`) — including
  `Background:` sections, `@tag`s, and `Scenario Outline:`/`Examples:` tables
  — is preserved byte-for-byte; only genuinely new scenario titles are
  appended, after the block's last existing unit. If the command exits 2
  (the named `Feature:` title can't be located, or the existing block's
  structure is malformed), no write occurred — report this per Step 6 rather
  than retrying with a raw `Write`.
- `step_definitions/<surface>_steps.<ext>` pending stubs (`bdd-runner` only).
- A surface inventory at `.claude/memory/<workflow>/<slug>/gherkin.md` listing each
  discovered surface, its discovery source, provenance, mode, and the files
  written. `/test-improve` reads this at Phase 4 (plan fixes) and Phase 5
  (build) to bind tests to the derived scenarios.

## Step 6 — Report

Print the mode, the count of surfaces by discovery source (OpenAPI / route /
test / signature / message-queue / scheduled-cron / websocket-graphql), the
specification-vs-characterization split, and the paths written. In `none`
mode, print only the one-line recommendation.

**Call out characterization scenarios separately — never fold them into the
same summary line as specification scenarios.** Print a distinct line: "N
scenarios captured from existing tests — confirm these are intended behavior,
not bugs, before treating them as spec," listing which had no cross-check
signal. This is what the operator uses to affirmatively accept each
characterization scenario at the human gate (`/test-improve` Phase 3's
review, before Phase 4 proceeds) before it is treated as accepted
living documentation rather than an unverified hypothesis.

**Call out possibly-stale retained scenarios separately (issue #1420) — never
fold them into the general summary,** mirroring the characterization
call-out above. Print a distinct "possibly stale existing scenario" section
listing every `check-stale` finding as `<file>:<line> — asserts <X>, code now
does <Y> — verify whether the code regressed or the requirement changed
before editing either the scenario or the code`. This is the same
action-oriented framing the characterization call-out already uses, not a
bare data dump — it tells the operator what decision to make, not just that
one exists.

**`bdd-runner` mode — report the pending-stub gate honestly (issue #1391).**
Choosing `bdd-runner` mode is a decision to end up with fully executing,
Gherkin-bound tests, not just scaffolded placeholders — but this skill's own
Step 4 only ever *generates* pending stubs; it never fills them in (that
happens later, in `/test-improve` Phase 5 or whatever follow-up work the
operator does after a standalone run). Run the gate and report its real
status rather than an unconditional "done":

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_stub_gate.py --dir <step-definitions-dir>
```

- Print the gate's result as its own report line: `N step definition(s)
  pending — bdd-runner binding is not complete until these are filled in`,
  listing each `file:line` the gate names, or `bdd-runner binding complete —
  0 pending step definitions` when it exits 0.
- **Never claim the surface's tests are "done" or "complete" while the gate
  reports pending stubs.** Immediately after a fresh Step 4 run every
  newly-generated stub is expected to be pending — that is not a failure of
  this skill, but the report must say so plainly rather than silently
  omitting the gate's output. Re-running gherkin-derive after some step
  definitions were filled in elsewhere reports the accurate mixed state.
- Skip entirely in `none` and `xunit-with-annotations` modes (no step
  definitions are generated in either).

## Key differences from `/gherkin-public`

- Does **not** require any prior assessment file — derives the surface itself
  from code.
- Does **not** create tracker Stories — the calling orchestrator (e.g.
  `/test-improve` Phase 4) owns triage.
- Usable standalone or as `/test-improve` Phase 3.
- `/gherkin-public` remains a separate public-boundary Gherkin authoring
  worker.

## Notes

- Characterization scenarios capture *what the code does now* — never treat an
  existing test as ground truth on its own. They are hypotheses about intended
  behavior, not confirmed specs: cross-check them against any other signal
  (docstrings, comments, adjacent OpenAPI/route info, status-code conventions),
  record "none found" when no cross-check exists, and call them out separately
  in the Step 6 report so the operator must affirmatively accept each one
  before it becomes living documentation.
- Where a UI flow cannot be inferred from code alone, emit a stub `.feature` with
  the header and a `# TODO: hand-author scenarios here` block — surface the gap
  rather than invent steps.
