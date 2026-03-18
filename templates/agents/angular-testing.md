---
name: angular-testing
description: Angular component testing — TestBed setup, component harnesses, OnPush testing, RxJS marble testing, no direct DOM queries
tools: Read, Grep, Glob
model: sonnet
---

# Angular Testing

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=good Angular testing, warn=anti-patterns, fail=unreliable tests
Severity: error=test won't catch regressions, warning=anti-pattern, suggestion=improvement
Confidence: high=mechanical (use harness, fix TestBed); medium=test design; none=domain context

Model tier: mid
Context needs: full-file
File scope: `*.spec.ts`

## Activates when

`@angular/core` in `package.json` dependencies.

## Skip

Return skip when no `.spec.ts` files for Angular components/services in the changeset.

## Detect

TestBed setup:

- Over-configured TestBed (importing entire modules instead of declaring only what's needed)
- Missing `TestBed.compileComponents()` for components with external templates
- Not resetting TestBed between tests when configuration changes

Component harnesses:

- Direct DOM queries (`querySelector`, `nativeElement`) instead of `HarnessPredicate`
- Missing Material component harnesses when `@angular/material` is used
- Not using `TestbedHarnessEnvironment.loader(fixture)` for harness access

OnPush change detection:

- Tests that pass with Default but fail with OnPush (missing `fixture.detectChanges()`)
- Missing `ChangeDetectorRef.markForCheck()` after programmatic state changes
- Not wrapping async operations that update state

RxJS testing:

- Testing observables with `subscribe` + `done` callback instead of marble testing
- Missing `fakeAsync`/`tick` for time-dependent observables
- Not unsubscribing in `afterEach` (subscription leaks)
- Using real timers instead of `TestScheduler`

HTTP testing:

- Mocking `HttpClient` directly instead of using `HttpClientTestingModule`
- Not verifying outstanding requests with `httpTestingController.verify()`
- Missing error response testing

## Ignore

Non-Angular tests, E2E tests (Protractor/Cypress), service worker tests.
