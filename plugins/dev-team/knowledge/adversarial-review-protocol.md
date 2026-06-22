# Adversarial Review Protocol

Reference file for all review agents. Run the challenger pass after producing initial findings to prevent incomplete analysis, unjustified severities, and premature exits.

## The Loop

After the initial review pass, re-examine findings with the following questions. Address each challenge before delivering the report.

1. **Completeness** — Did the reviewer examine every file in scope? List files NOT examined and state why.
2. **Evidence** — Does every finding quote actual code? Flag any finding without a direct code citation.
3. **Severity justification** — Is each error/high-severity rating backed by concrete impact (data loss, security breach, test suite failing silently, production breakage)? Downgrade if not.
4. **Blind spots** — What categories of issues are ABSENT from the findings? Absence in async code with no concurrency findings, or complex business logic with no domain findings, is suspicious. State the absent category and why it isn't an issue (or add a finding).
5. **False-negative pass** — Re-read the 3 largest files independently. Are there issues the initial pass walked past?
6. **Lazy exits** — Any finding with "could not assess because..." — is that actually true, or is it a shortcut?

Repeat until the challenger finds no new issues, or a maximum of 3 rounds is reached.

## Challenge Questions by Agent

### security-review

- Did you check EVERY source file, not just files with suspicious names?
- Did you trace user-controlled input all the way to its sink (query, shell, template, redirect)?
- Did you distinguish between `throw` (error handling) and silent swallow?
- Are hardcoded secrets in `.env` files actually committed (check `git ls-files`)? If not, do NOT flag them.
- Did you check CI/CD workflow files and Dockerfiles, which are in scope even for small changesets?
- Is every "missing auth check" finding verified against the actual middleware chain, not just the handler?

### test-review

- For every class below 90% effective coverage, did you identify the SPECIFIC uncovered behavior?
- For each "can't test because of static coupling" — did you verify there's no injectable constructor or interface available?
- Are there tests with no assertion (just "didn't crash")? These provide zero regression protection.
- Are there tests that verify test infrastructure instead of business logic (CanBeMocked, ImplementsInterface, ConstructorSetsField)?
- Did you check for shared mutable state between tests (static fields, module-level singletons)?
- Are there non-determinism sources (unstubbed clock, real network, file I/O) that weren't flagged as flakiness risks?

### test-smell-review

- For every smell flagged, did you name the specific xUnit smell (not just "this test is bad")?
- For each "Slow Tests" or "Erratic Test" finding, did you confirm the test's *intended* level — integration/E2E tests touch real resources by design?
- For each mock-related finding, did you verify a Stub + state assertion couldn't replace it, rather than assuming all mocking is a smell?
- Did you distinguish Test Code Duplication (extractable) from two tests covering genuinely different boundary conditions?
- For smells rooted in untestable production code, did you recommend the production-code change (per testability-patterns.md), not a test workaround?
- Did you defer tactical mechanics (missing assertion, missing await) to test-review instead of double-reporting them?

### structure-review

- Did you check every module/class for SRP violations, including small ones?
- Did you trace dependency direction? Does business logic depend on infrastructure (not just vice versa)?
- Are there hidden static singletons or global state that aren't injected?
- For every "duplicate code" finding, did you verify it's semantic duplication and not just structural similarity?
- Did you check constructor parameter counts? >5 parameters usually signals SRP violation.
- Are there God objects/Megaclasses you walked past because they're "just how the code is"?

### complexity-review

- Did you check ALL methods and functions, not just the visibly large ones?
- For each nesting-depth finding, did you count the actual levels rather than estimating by appearance?
- Are there methods just under the threshold (19 lines, 3 levels) that warrant a warning?
- Did you distinguish between genuine cognitive complexity (multiple concepts) and mechanical repetition (defensive null checks)?
- For async findings, did you verify the pattern is actually problematic in context (library vs. application code)?

### arch-review

- Did you read the ADRs before reviewing? Every finding should reference whether it contradicts an ADR.
- Did you check cross-boundary imports in BOTH directions (not just infrastructure → domain)?
- For each "inconsistent pattern" finding, did you verify the established pattern exists in at least 2 other locations?
- Did you check for circular dependencies introduced by the changeset?
- Are there new abstractions that duplicate existing ones?

### domain-review

- Did you check every entity/aggregate for anemic domain model patterns (data bags with all behavior in services)?
- For each "business logic in wrong layer" finding, did you quote the specific rule and its location?
- Did you check for ubiquitous language drift: same concept with 3+ different names across modules?
- Are domain objects leaking persistence annotations, HTTP concerns, or infrastructure types?
- Did you check aggregate boundary enforcement — are child entities accessed directly by external callers?

### spec-compliance-review

- Did you load EVERY spec artifact (spec, plan, design doc, all `.feature` files), or stop at the first one found?
- For each acceptance criterion, did you locate BOTH the implementation and its test — not assume a test exists because the criterion "looks covered"?
- For every scope-violation finding, did you confirm the change maps to no criterion, including criteria in linked or related slices?
- Did you check for planned changes that were NOT made (missing files), not just unplanned files that were added?
- Is every `error` (unmet criterion, uncovered scenario) backed by the specific criterion/scenario text, not a paraphrase?

### a11y-review

- Did you examine every component/template file in scope, not just the most obviously interactive one?
- For each contrast finding, did you cite the actual color values and the computed WCAG ratio rather than estimate "looks low"?
- Did you check keyboard operability for EVERY custom interactive element (handler + focusability + visible focus), not just buttons?
- Are there dynamic regions (live updates, route changes, modal open/close) with no announcement/focus-management finding — a suspicious absence?
- For each "missing label" finding, did you verify there's no `aria-labelledby` or visible-text association before flagging?

### claude-setup-review

- Did you check EVERY `.md` file under `agents/` for frontmatter schema compliance, not just a sample?
- For each "referenced path doesn't exist" finding, did you resolve the path against the actual tree rather than assume?
- Did you distinguish a required-field violation (error) from a plugin-unsupported field (warning) per the schema rules?
- Are there unknown frontmatter keys you walked past that should be flagged as suggestions?
- For each "command doesn't work" finding, did you confirm it against the actual manifest (package.json/Makefile), not infer from the name?

### concurrency-review

- Did you trace EVERY shared-mutable-state access across all async paths, or stop at the first guard you saw?
- For each race-condition finding, did you confirm the two accesses can actually interleave (same instance, concurrent entry), not just look risky?
- Is there async code (Promise/Task/Thread) with zero concurrency findings — a suspicious absence to justify or fill?
- Did you check error-path cleanup (finally/dispose) AND unhandled rejection on every awaited call?
- For each "should be parallel" suggestion, did you verify the awaits are genuinely independent (no data dependency)?

### doc-review

- Did you compare EVERY changed public signature against its doc comment, not just the ones with obvious drift?
- For each "README describes removed feature" finding, did you confirm the feature is actually gone from source (grep), not assume?
- Did you check whether agent/skill changes require a CLAUDE.md registry-table update — a common silent omission?
- Are there new architectural patterns or dependencies with no ADR-trigger finding — a suspicious absence?
- For each finding, did you distinguish a doc that is WRONG (flag) from one that merely differs in style (do not flag)?

### js-fp-review

- Did you enumerate every declaration and call site in the diff, or stop after the first few mutations?
- For each array-mutation finding, did you verify it mutates a shared/external reference, not a locally-constructed spread copy (`[...arr].sort()` is allowed)?
- Did you respect the documented exceptions (`mut`/`mutable`/`_` prefixes, `this.property` in class methods) before flagging?
- For each `let`→`const` finding, did you confirm the binding is never reassigned anywhere in scope?
- Is there parameter or global mutation you walked past because it "looked intentional" without an exception marker?

### naming-review

- Did you complete Phase 1 enumeration for EVERY identifier in the diff before classifying, or skip to the obvious offenders?
- For each misleading-name (error) finding, did you confirm the name signals the opposite of its value/behavior, with the code quoted?
- For each magic-value finding, did you verify there is no existing named constant for it already?
- Did you mark domain terminology you can't verify as confidence `none` rather than imposing a generic rename?
- Are there inconsistent names for the same concept across files that you missed by reviewing files in isolation?

### performance-review

- Did you check every loop and I/O site for N+1 / unbounded growth, not just the largest function?
- For each resource-leak finding, did you confirm there is no cleanup (finally/using/defer/dispose) anywhere on the path?
- For each algorithmic finding, did you verify it's on a hot path with realistic input size, not one-off init?
- Is there a long-lived cache or collection with no eviction-bound finding — a suspicious absence?
- For each "missing timeout" finding, did you check for a timeout configured at the client/global level before flagging the call site?

### svelte-review

- Did you examine every `.svelte`/`.svelte.ts`/`.svelte.js` file in scope, not just the most stateful component?
- For each reactivity finding, did you confirm the Svelte version (4 vs 5) and that the pattern actually breaks tracking in that version?
- Did you check every manual `.subscribe()` for a matching `unsubscribe`/`onDestroy` cleanup?
- For each `$state` finding, did you verify the mutation/destructure/spread actually escapes the proxy (`$store` auto-subscription is safe)?
- Is there an `$effect`/`$:` block with hidden dependencies or self-writes you walked past?

### token-efficiency-review

- Did you measure the actual char/line counts against the thresholds, or estimate "looks long"?
- For each LLM-anti-pattern finding (role preamble, filler, hedging), did you quote the offending text?
- Did you check whether a multi-step procedure in CLAUDE.md or rules should be a skill, not just flag its length?
- Are there duplicate or repetitive sections across files you missed by reviewing each file alone?
- For each "should be terser" suggestion, did you confirm trimming wouldn't drop a load-bearing instruction?

### refactor-opportunity-review

- For every duplication finding, did you apply the semantic-vs-structural test ("if the business rule changes, must both copies change?") before flagging?
- Did you check method length and nesting on every changed function, not just the first long one?
- For each extract-method finding, did you confirm a comment or block boundary marks a genuine separate responsibility?
- Did you defer naming-only and architecture-only issues to their owning agents instead of double-reporting?
- Are there feature-envy or primitive-obsession opportunities you walked past as "just how the code is"?

### progress-guardian

- Did you check EVERY plan step's status against actual git state, not just the most recent one?
- For each "step complete" claim, did you confirm fresh test evidence exists rather than trust the `[x]` mark? ("Marked complete" is not "demonstrated complete.")
- Did you trace every modified file to a plan step, flagging scope creep for any that map to none?
- For commit-discipline findings, did you count actual commits between completed steps rather than estimate?
- Is there a `fail` you should raise (unverified criteria) that you softened to `warning` without justification?

### data-flow-tracer

- Did you trace the ACTUAL code path for every step, or assume a conventional path you didn't open?
- Is every layer in the trace table backed by a concrete `file:line`, with no row left as "probably handled here"?
- Did you check every external call for timeout/retry/fallback and every write for a transaction boundary, or leave gaps unexamined?
- Are there branches of the use case (error paths, alternate flows) you walked past by tracing only the happy path?
- Did you report gaps without sliding into prescribing fixes (out of scope for this agent)?

### test-modernization-review

- Did you run EVERY check in the phase-specific list, or stop at the first failure?
- For each verification, did you open the cited artifact (feature file, coverage JSON, resolution JSON) rather than trust the progress file's summary?
- For a `pass`, did you confirm the next phase actually has the inputs it needs, not just that this phase's deliverable exists?
- Is every `error` tied to a specific invariant violation with file/row evidence, not a general impression?
- Did you check the integrity cross-references (disabled-tests ↔ resolution, scenarios ↔ bindings) exhaustively, with orphan count = 0?

### session-analysis

- Is every suggestion backed by a specific digest field and value, or did any rest on an assumed pattern?
- Did you weigh all three problem classes (token / rework / accuracy), not over-index on the loudest one?
- For each suggestion, does the `target` name a concrete artifact and the `handoff` a valid route?
- Did you avoid inventing numbers or quoting prompt/code content the digest does not contain?
- Are there strong digest signals (never-observed agents, low cache-hit ratio) you left without a suggestion?

## Output

After the challenger pass, append to the `summary` field in your JSON output:

```
Challenge: N round(s). Revisions: <count>. Blind spots examined: <list>. Confidence: High|Medium|Low.
```

Agents that emit a non-JSON report instead of a `summary` field — `data-flow-tracer` (trace report) and `session-analysis` (ranked suggestion list) — append the same `Challenge:` line to the report's closing summary sentence.

- **High**: all files examined, every finding has a code citation, no suspicious absences
- **Medium**: 1-2 files not examined or 1 finding revised downward
- **Low**: >2 files not examined, multiple revisions, or a finding was retracted
