---
name: gherkin-derive
description: >-
  Derive Gherkin scenarios directly from a codebase — standalone, with no
  prior legacy-modernization analysis. Discovers the public surface (OpenAPI,
  routes, existing tests, exported signatures, plus message-queue, cron, and
  websocket/GraphQL surfaces), recommends a BDD binding
  mode via the bdd-value-guide rubric, and merges scenarios into `.feature`
  files (preserving prior enrichment, never overwriting) plus
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

**Graph-assisted discovery.** Prefer CodeGraph/Repowise over raw `Grep` for
locating routes, handlers, and exported signatures — see
[`knowledge/codegraph-vs-graphify.md`](../../knowledge/codegraph-vs-graphify.md)
for tool selection and the fallback contract.

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

**In-depth, codebase-wide analysis is the mandatory default — always on,
never operator-supplied (issue #1450).** Every invocation of this step
performs an in-depth analysis of the codebase, not a shallow scan limited to
registered entry points. Beyond the cascade above and the async/event/
scheduled sweep, explicitly analyze **controllers, handlers, services,
domain logic, workflows, validation rules, error handling, and business
processes** to identify behavior-driven scenarios that an entry point's bare
signature does not reveal — e.g. a thin route handler backed by a service
that enforces three distinct business rules yields three scenarios, one per
rule, not one generic "invalid input" scenario. This depth requirement is
unconditional: it is never gated behind an operator-supplied instruction, a
flag, or a specific prompt phrasing — a run that skips this analysis is a
spec violation of this skill, not an acceptable shallow default. Record what
was analyzed for each of these eight categories in the Step 5 surface
inventory's `## Analysis Coverage` section (see Step 5), so a thin run is
detectable rather than merely asserted.

**Resolve the existing file before authoring (issue #1420).** Run
`detect_bdd_convention.py` once per repo to get the project's `.feature`
destination directory, then compose each surface's path yourself as
`<dir>/<surface>.feature` — `detect_bdd_convention.py`'s own contract stays a
single project-wide directory probe; this skill composes the per-surface
path, it never asks the script to resolve one itself:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_bdd_convention.py"
```

A `"dir": null` result (`"signal": "none"`) means the script found no usable
convention — including, since issue #1462, a repo whose only existing
`.feature` root sits under a non-conventionally-named directory. Never
compose a path from `null`; fall back to
`../plan/references/gherkin-persistence.md`'s no-signal handling (prompt the
operator, or its non-interactive default) instead of guessing a destination.

If a file already exists at that composed path, **read it** before authoring
anything for that surface — Step 5 merges into it rather than overwriting.

**Surface identifiers must be unique per method+path (or equivalent
distinguishing element for non-HTTP surfaces) — never collapse two different
surfaces onto the same `<surface>` stem (issue #1526).** For an API Provider
surface, derive `<surface>` from both the HTTP method and the normalized
path (e.g. `GET /users/{id}` → `get_users_id`, `DELETE /users/{id}` →
`delete_users_id`) so two endpoints that differ only by method or path never
compose the same file/feature-title pair. For a non-HTTP surface
(message-queue consumer, cron job, CLI command, exported function), use the
fully-qualified name (queue/topic name, job name, module.function) for the
same reason. A surface-identifier collision is a defect regardless of how it
happens — it silently merges two unrelated behaviors' scenarios into one
Feature block, where the exact-title dedup in Step 5 will treat a second
surface's same-titled scenario as an existing duplicate and drop it.

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

**Titles must be specific enough to identify the surface without relying on
the `Feature:` header for context (issue #1526).** A `Scenario:` title read
in isolation — in a CI report, a BDD runner's scenario list, or a coverage
dashboard — must be recognizable as belonging to its specific surface, not a
generic category label that could describe any endpoint (e.g. `returns error
for invalid input`, `handles success case`). Prefer wording that names the
concrete condition or resource involved (e.g. `rejects the request when the
id path parameter is non-numeric`, `returns the created order with a 201 and
Location header`) over a bare category name. This applies to success-path
titles as well as failure-path titles — the no-generic-placeholder rule
above already covers failure-path *content*; this rule covers *all* scenario
*titles*. A title that is merely a paraphrase of the surface name (the same
words as the `Feature:` line, reworded) fails this rule the same way a
placeholder failure condition does.

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
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_feature_merge.py" check-stale \
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

**Merge, never overwrite (issue #1421).** Step-definition stubs are merged
into the existing file the same way Step 5 merges `.feature` scenarios —
never a raw `Write`, which would silently discard any step a human (or
`/build`) has already implemented. For each surface's step-definition file,
write the newly-derived stub text (using the pending-stub form from the
table above) to a scratch candidates file, then invoke
`gherkin_stub_merge.py merge`:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_stub_merge.py" merge \
  --existing <dir>/<surface>_steps.<ext> --candidates <scratch-file> \
  --ext <.js|.ts|.mjs|.cjs|.java|.cs|.go> --json
```

This is exactly one write path whether or not a step-definition file already
existed at that path. Any step already bound in the file — pending or
already implemented — is left byte-for-byte untouched; only genuinely new
step patterns are appended, as pending stubs, after the file's last existing
binding. **Exit 2 means no write occurred** — read the `--json` payload's
`error` field to know why, and report the specific cause per Step 6 rather
than a generic "could not merge" (never retry with a raw `Write`, whichever
cause it is):
- `unbalanced-braces` — the existing file's braces/parens don't lexically
  balance, so no binding's body can be safely bounded. The file needs
  hand-repair before any merge can succeed.
- `dangling-annotation` — a step marker (a call, annotation, or attribute)
  was found with no attached, boundable body. Same remediation — hand-repair
  the file first.
- `unsafe-path` — the composed `--existing` path contained a `..` component
  and was rejected before any read or write. Fix how the surface name was
  derived into a path; do not retry with the same value.
- `malformed-candidates` — the scratch candidates file (this skill's own
  intermediate output, not the operator's step-definition file) itself
  couldn't be bounded. Re-author the candidates text for that surface and
  retry.
- `unreadable-candidates` — the scratch candidates file (this skill's own
  intermediate output) is missing or couldn't be read at all. Re-check how
  this skill wrote that scratch file for the surface before retrying — not
  the operator's step-definition file.
- `unsupported-extension` — the `--ext` value doesn't name a language this
  script recognizes (`.js`/`.ts`/`.mjs`/`.cjs`/`.java`/`.cs`/`.go`). Fix how
  this skill derived `--ext` from the surface's language before retrying.

**Batch shared context-file edits (issue #1775).** When multiple surfaces
discovered in this run add to the same shared acceptance-test-context file
(e.g. a shared step-definition registration/support file, hooks module, or
world/context setup shared across surfaces), collect every surface's
addition to that shared file first, then apply them in **one edit pass** for
that file — never reopen and re-edit the same shared context file once per
step definition or per surface. Reopening it N times for N step
registrations produces N redundant read/write round-trips for content that
could have been composed once. **"One edit pass" still means one merge, never
one raw `Write`, when the shared file is a step-definition/registration
file** — collecting every surface's addition first is a batching optimization
over how many times you invoke `gherkin_stub_merge.py merge`, not a license
to replace it with a single `Write`; combine all the batched additions into
one `--candidates` scratch file and make exactly one `gherkin_stub_merge.py
merge` call against the shared file, per the Merge, never overwrite rule
above (issue #1421).

## Step 5 — Output

- `features/<surface>.feature` files (all non-`none` modes) — **merged, not
  replaced (issue #1420).** For each surface, write the newly-authored
  scenario text to a scratch candidates file, then invoke
  `gherkin_feature_merge.py merge` — never a raw `Write` — to produce the
  file on disk:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_feature_merge.py" merge \
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
  appended, after the block's last existing unit. **Exit 2 means no write
  occurred** — read the `--json` payload's `error` field to know why, and
  report the specific cause per Step 6 rather than a generic "could not
  merge" (never retry with a raw `Write`, whichever cause it is):
  - `feature-not-found` — the named `Feature:` title isn't in the existing
    file; most likely a human renamed it. Reconcile `--feature-title` with
    the file's actual header.
  - `malformed-feature-block` — the title was found but the block's
    structure can't be bounded (a dangling `@tag` line, or a `Scenario
    Outline:` missing its `Examples:` table). The existing file needs
    hand-repair before any merge can succeed.
  - `unsafe-path` — the composed `--existing` path contained a `..`
    component and was rejected before any read or write. Fix how the
    surface name was derived into a path; do not retry with the same value.
  - A malformed `--candidates` scratch file (this skill's own intermediate
    output, not the operator's `.feature` file) — re-author the candidates
    text for that surface and retry.
- `step_definitions/<surface>_steps.<ext>` pending stubs (`bdd-runner` only) —
  written via Step 4's `gherkin_stub_merge.py merge` invocation, never a raw
  `Write`, so an already-implemented step is never clobbered.
- A surface inventory at `.claude/memory/<workflow>/<slug>/gherkin.md` listing each
  discovered surface, its discovery source, provenance, mode, and the files
  written. `/test-improve` reads this at Phase 4 (plan fixes) and Phase 5
  (build) to bind tests to the derived scenarios. **The inventory MUST also
  include an `## Analysis Coverage` section** (issue #1450) recording, for
  each of the eight mandatory analysis categories named in Step 2 —
  controllers, handlers, services, domain logic, workflows, validation
  rules, error handling, business processes — either what was found for
  that category or an explicit "none found in this codebase" statement.
  Never omit a category silently: an omitted or empty entry is exactly the
  thin-analysis gap this section exists to make detectable (see Step 6's
  `gherkin_analysis_coverage_gate.py` invocation).

## Step 5b — Adversarial Gherkin Quality Review

Whenever this run wrote or merged at least one `.feature` file in Step 5,
dispatch the adversarial review before Step 6's report — no operator opt-in
required. **Skip entirely** in `none` mode (no `.feature` files exist) or on a
run that wrote/merged zero `.feature` content.

Follow `knowledge/gherkin-quality-review-dispatch.md` for the shared dispatch,
aggregation, failure-handling, and zero-findings mechanics — this step states
only what's specific to `/gherkin-derive`: each of the two
`gherkin-quality-critic` instances receives, for every surface reviewed, that
surface's `.feature` file content plus its Step 3 `# Source:` header (the
route, OpenAPI path, test file, or signature it was derived from), so the
agent can check scenarios against the actual cited source. The resulting
`agreed`/`single-source` buckets feed Step 6's two new report sections below.

## Step 6 — Report

Print the mode, the count of surfaces by discovery source (OpenAPI / route /
test / signature / message-queue / scheduled-cron / websocket-graphql), the
specification-vs-characterization split, and the paths written. In `none`
mode, print only the one-line recommendation.

**Print Step 5b's two Gherkin quality sections — "Agreed Gherkin quality
findings" and "Single-source (unconfirmed) Gherkin quality findings":**
whenever Step 5b ran (skip this pair of sections entirely when it was skipped
— `none` mode or zero `.feature` writes), follow
`knowledge/gherkin-quality-review-dispatch.md`'s Report section format for the
exact per-finding line format, the zero-findings sentence, and the
failure-handling wording.

Neither section is folded into the characterization, possibly-stale,
title-mismatch, or skipped-duplicate callouts below — this is semantic
gap/balance judgment from an independent reviewer, not a structural-presence
check.

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

**Call out `check-stale` title mismatches too, distinctly from staleness
findings (issue #1420).** `check-stale --json`'s `unmatched_titles` array
lists every `--observed` title that isn't an exact key among the retained
scenarios — this is a different problem from a stale assertion: it means the
title-extraction step and the retained scenario's exact text have diverged,
not that the code's behavior changed. Report each as "title mismatch: `<X>`
not found among retained scenarios in `<feature-title>` — check for a typo or
drift between the observed title and the scenario it should describe",
separate from the "possibly stale" section above. The operator action
differs (fix title extraction vs. verify a behavior change), so folding the
two together would obscure which one applies.

**Call out `merge`'s skipped duplicate scenarios too (issue #1420).**
`merge --json`'s `skipped_duplicate_titles` lists every candidate scenario
that was *not* written — either it matched a title already in the file (the
scenario is present either way, low stakes), or it collided with another
candidate authored in the same run (the dropped one is not written anywhere
and never will be, unless re-authored). Report each as "skipped duplicate:
`<title>` — a scenario with this exact title already exists in
`<feature-title>`, or two authored candidates shared it; confirm the
retained one actually covers the intended behavior before treating the
surface as covered." Do not fold this into the surface-count summary — a
dropped candidate is exactly the kind of silent gap this report exists to
surface.

**Call out `gherkin_stub_merge.py`'s skipped duplicate steps too, mirroring
the scenario-merge callout above (issue #1421).** `merge --json`'s
`skipped_duplicate_patterns` lists every candidate step that was *not*
written — either it matched a pattern already bound in the file (the step
is present either way, low stakes), or it collided with another candidate
authored in the same run (the dropped one is not written anywhere and never
will be, unless re-authored). Report each as "skipped duplicate step:
`<pattern>` — a binding with this exact pattern already exists in `<path>`,
or two derived candidates shared it; confirm the retained binding actually
covers the intended step before treating the surface as covered." Do not
fold this into the surface-count summary — a dropped candidate is exactly
the kind of silent gap this report exists to surface, the same reasoning
that already applies to `skipped_duplicate_titles` above.

**Call out step-definition merge structural errors, distinctly from the
scenario-merge callouts above (issue #1421).** When Step 4's
`gherkin_stub_merge.py merge` invocation exits 2, report it using this exact
template, naming the concrete problem, file, and sentinel: `"Could not merge
step-definition stubs into <path>: <language> structure not recognized
(<sentinel>). No changes were made — fix the file's syntax and re-run, or
report the file:line if the structure looks valid."` for the two
step-definition-specific structural sentinels the `stub_extractors` package
returns (`unbalanced-braces` — the existing file's braces/parens don't
lexically balance; `dangling-annotation` — a step marker has no attached,
boundable body). The other four sentinels `gherkin_stub_merge.py` can return
are **not** step-definition syntax problems and need their own remediation,
reusing Step 4's own per-cause text rather than the template above:
`unsafe-path` — "fix how the surface name was derived into a path; do not
retry with the same value" (a bug in how this skill composed the path, not
in the operator's file); `malformed-candidates` — "re-author the candidates
text for that surface and retry" (this skill's own scratch file, not the
operator's step-definition file); `unreadable-candidates` — "re-check how
this skill wrote that scratch file for the surface before retrying" (this
skill's own scratch file was missing or couldn't be read, not the
operator's step-definition file); `unsupported-extension` — "fix how this
skill derived `--ext` from the surface's language before retrying" (a bug
in how this skill chose the extension, not in the operator's file). This is
a distinct failure mode from the scenario-merge callouts above: no scenario
was skipped or retained here, the step-definition file was never written at
all.

**`bdd-runner` mode — state completion plainly, as the report's headline
(issues #1391, #1420).** Choosing `bdd-runner` mode is a decision to end up
with fully executing, Gherkin-bound tests, not just scaffolded placeholders —
but this skill's own Step 4 only ever *generates* pending stubs; it never
fills them in (that happens later, in `/test-improve` Phase 5 or whatever
follow-up work the operator does after a standalone run). Run the gate:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_stub_gate.py" --dir <step-definitions-dir>
```

- **Pending stubs remain → print one consolidated statement as the FIRST
  line of this mode's report**, replacing (not sitting alongside) the
  previous secondary aside about binding status: `This run is not done — N
  step definition(s) pending, listing each file:line the gate names. Run
  /build against the derived scenarios to fill them in.` This applies identically
  regardless of caller (standalone or a `/test-improve` Phase 3 sub-step) —
  it is one shared code path, not a standalone-specific branch. **No other
  part of this report** (the surface-count summary, the characterization
  call-out, the possibly-stale-scenario section, the failure-path gate
  section) may use unqualified "complete"/"done"/"success" language for this
  run when this statement applies — the not-done headline governs the whole
  report's tone, not just its own line.
  - **Proactive hand-off (standalone invocations only).** After printing the
    statement, ask the operator whether to continue into `/build` now,
    rather than only printing the recommendation and moving on. When
    gherkin-derive runs as a `/test-improve` Phase 3 sub-step, **do not ask**
    — Phase 3's own human gate, Phase 4's triage, and Phase 5's fill-in loop
    already own that decision (see below).
  - **Non-interactive fallback.** When no interactive response is possible
    (headless/CI invocation), print the statement and the `/build`
    recommendation in full and never ask the question — it is best-effort
    and never blocks the run.
  - **Never fills in an already-pending stub itself.** Reporting this state
    never modifies a step-definition file or clears an existing pending
    marker — that is distinct from, and never blocks, Step 4's normal job of
    scaffolding *new* pending stubs for newly-discovered scenarios, which
    legitimately changes the pending-stub count on an ordinary re-run.
- **Zero pending stubs → print `bdd-runner binding complete — 0 pending step
  definitions`**, with no recommendation and no continue-into-`/build`
  question.
- **The gate exits 2 when it did not run** (no step-definition files were
  found under `--dir` — most often a mistyped or mis-probed directory, not
  an empty-but-legitimate `0 pending`). Never report this as `bdd-runner
  binding complete`; print "gate did not run — no step-definition files
  found under `<dir>`, re-check the step-definitions directory" instead.
- Skip entirely in `none` and `xunit-with-annotations` modes (no step
  definitions are generated in either).

**Consistency with `/test-improve` Phase 5's own gate.** Phase 3's headline
statement and Phase 5's later hard block (`../test-improve/SKILL.md`'s Phase 5
section) describe the *same* pending-stub state at two different
checkpoints, not two different requirements — both name `/build`
(Phase 5's own per-Story build loop) as the remediation, so an operator never
receives two conflicting instructions for the same fact.

**Every mode that writes `.feature` files — report the failure-path
coverage gate (issue #1420).** Unlike the pending-stub gate above, which is
`bdd-runner`-only, this one is **not `bdd-runner`-only** — `xunit-with-annotations`
mode is in scope here too, since the coverage gap this checks for exists
whenever `.feature` files exist, independent of whether `bdd-runner` mode
wired a runner:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_failure_path_gate.py" --dir <feature-files-dir>
```

Print the gate's result as its own report section, never folded into the
general summary: `N Feature block(s) missing a failure-path scenario`,
listing each `file:line — <feature title>` the gate names, or `OK: all
Feature block(s) have a failure-path scenario` when it exits 0. **A third
outcome exists — exit 2 means the gate did not run** (no `.feature` files
were found under the scanned directory, most often a mistyped or
mis-probed `--dir`); report this as "gate did not run — no `.feature`
files found under `<dir>`, re-check the feature-files directory," never as
an `OK`/all-clear (a scan of zero files finding zero problems is not the
same as zero problems). Skip entirely in `none` mode (no `.feature` files
are written).

**Every mode that writes `.feature` files — report the cross-feature
duplicate-title gate (issue #1526).** Same scope as the failure-path gate
immediately above — not `bdd-runner`-only, since the collision this checks
for exists whenever `.feature` files exist:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_cross_feature_duplicate_titles_gate.py" --dir <feature-files-dir>
```

Print the gate's result as its own report section, never folded into the
general summary: `OK: no scenario title is duplicated across distinct
Feature blocks` when it exits 0, or `N scenario title(s) duplicated across
distinct Feature blocks` when it exits 1, listing each finding as `"<title>"
appears in <feature-title-A> (<file>:<line>) and <feature-title-B>
(<file>:<line>) — confirm these are genuinely the same behavior, or rename
one to be surface-specific`. **A third outcome exists — exit 2 means the
gate did not run** (no `.feature` files were found under the scanned
directory, most often a mistyped or mis-probed `--dir`); report this as
"gate did not run — no `.feature` files found under `<dir>`, re-check the
feature-files directory," never as an `OK`/all-clear. Skip entirely in
`none` mode (no `.feature` files are written).

**Every mode — report the analysis-coverage gate (issue #1450).** Unlike
the two gates above, this one runs even in `none` mode: the surface
inventory (and its `## Analysis Coverage` section) is written regardless of
binding mode, since the mandatory in-depth analysis (Step 2) happens before
mode-specific output does:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_analysis_coverage_gate.py" --file <inventory-path>
```

Print the gate's result as its own report section: `OK: all 8 analysis
categories recorded` when it exits 0, or `N analysis categor(y/ies) missing
from the coverage record`, listing each missing category, when it exits 1.
**A third outcome exists — exit 2 means the gate did not run** (no
`## Analysis Coverage` section was found in the inventory, or the inventory
file itself is missing); report this as "gate did not run — no Analysis
Coverage section found in `<path>`, re-check the surface inventory," never
as an `OK`/all-clear.

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
