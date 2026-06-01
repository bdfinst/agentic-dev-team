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

## Output

After the challenger pass, append to the `summary` field in your JSON output:

```
Challenge: N round(s). Revisions: <count>. Blind spots examined: <list>. Confidence: High|Medium|Low.
```

- **High**: all files examined, every finding has a code citation, no suspicious absences
- **Medium**: 1-2 files not examined or 1 finding revised downward
- **Low**: >2 files not examined, multiple revisions, or a finding was retracted
