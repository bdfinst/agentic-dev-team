---

name: angular-reactivity-review
description: Angular Zone.js change-detection pitfalls, OnPush + immutability violations, RxJS subscription leaks, async-pipe alternatives
tools: Read, Grep, Glob
effort: low
cites: [adversarial-review-protocol]
scope:
  - **/*.component.ts
  - **/*.component.html
  - **/*.service.ts
  - **/*.ts
---

# Angular Reactivity Review

Scope: Angular component, directive, and service files (`.component.ts`,
`.component.html`, `.service.ts`, and general `.ts` files in Angular projects).
Skip this agent entirely if the project has no `@angular/core` dependency in
`package.json` (or equivalent manifest).
Covers Zone.js-based Angular (Angular 2–17) and Angular Signals (Angular 16+
`signal()`, `computed()`, `effect()`).

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=no reactivity issues, warn=potential concerns, fail=likely silent reactivity breakage
Severity: error=silent change-detection failure or subscription leak; warning=potential reactivity concern; suggestion=defensive improvement
Confidence: high=mechanical Angular fix (use async pipe, markForCheck, unsubscribe); medium=pattern identified but component design may affect the fix; none=requires human judgment

Context needs: full-file

## Skip

Return `{"status": "skip", "issues": [], "summary": "No Angular files in target"}` when:

- No `@angular/core` dependency found in the project manifest (`package.json`, `package-lock.json`, `yarn.lock`, etc.)
- No Angular component/service/directive files in the target set

## Detect

Whole-file load: `${CLAUDE_PLUGIN_ROOT}/knowledge/reactive-effect-patterns.md` for cross-framework effect/watcher patterns shared with React and Vue agents before running the Angular-specific checks below.

Zone.js change-detection pitfalls:

- State mutations inside `setTimeout` / `setInterval` callbacks when `NgZone.runOutsideAngular()` is used — Zone.js won't detect them; must call `NgZone.run()` to trigger CD or use Angular Signals
- Using native browser APIs (IndexedDB callbacks, third-party library callbacks) that run outside Zone.js without a corresponding `NgZone.run()` to re-enter the zone
- Mutating component state inside a `Promise.then()` that was created before Zone.js could patch it (rare, but occurs with some polyfills)

OnPush + immutability violations:

- `ChangeDetectionStrategy.OnPush` component whose `@Input()` receives a mutable object that is mutated in-place by the parent — OnPush only checks input reference identity, so the view never updates
- Directly mutating a component's own state (`this.items.push(x)`, `this.config.flag = true`) inside an OnPush component — change detection won't fire; must replace the reference or call `ChangeDetectorRef.markForCheck()`
- `ChangeDetectorRef.detectChanges()` called in a loop or on every keystroke as a workaround for missing immutability discipline — a symptom of the underlying mutation problem

RxJS subscription leaks (without async pipe):

- `Observable.subscribe()` in `ngOnInit` (or constructor) without a corresponding `unsubscribe()` in `ngOnDestroy`
- No `takeUntil(this.destroy$)` / `takeUntilDestroyed()` pattern and no explicit unsubscribe
- Subscriptions stored in a plain variable instead of a `Subscription` object that is unsubscribed in `ngOnDestroy`
- Nested subscriptions (subscribing inside a subscribe callback) — almost always replaceable with `switchMap`/`mergeMap`/`concatMap`

Async pipe alternatives not used:

- Manual subscription management where the `async` pipe would cleanly handle subscribe + unsubscribe in the template
- Suggestion (not error): expose an Observable directly to the template and use `async` pipe instead of `.subscribe()` + storing value in a field

Angular Signals pitfalls (Angular 16+):

- `effect()` that writes to a signal it also reads — causes an infinite update loop (same pattern as Svelte `$effect` self-write; see `${CLAUDE_PLUGIN_ROOT}/knowledge/reactive-effect-patterns.md#effect-self-writes-infinite-loop`)
- `computed()` with side effects (network calls, `console.log`, DOM writes) — computed signals must be pure
- Reading a signal value (`.()`) outside a reactive context (not inside `computed`, `effect`, or template) and storing it in a plain variable — loses live tracking
- `signal()` wrapping a mutable object mutated in-place — Angular only tracks the signal reference, not deep object mutations; use `update()` with a new object or `mutate()` (Angular 16 only)

ExpressionChangedAfterItHasBeenCheckedError patterns:

- Setting component state in `ngAfterViewInit` or `ngAfterContentInit` that is also bound in the same template — triggers the dev-mode expression-changed error and indicates a check-order bug; wrap in `Promise.resolve().then(...)` or use `setTimeout` as a short-term fix, but prefer redesigning state flow

## Self-Challenge

After producing findings, run the shared challenger loop in `${CLAUDE_PLUGIN_ROOT}/knowledge/adversarial-review-protocol.md` (Whole-file load: the slim shared methodology — The Loop + Output format — read in full), then work these angular-reactivity-review-specific challenges:

- Did you confirm `@angular/core` is actually in the project's dependency tree before flagging any finding?
- For each OnPush finding, did you verify the component actually uses `ChangeDetectionStrategy.OnPush` (not the default `Default` strategy)?
- For each subscription-leak finding, did you check for `takeUntil`, `takeUntilDestroyed`, or `AsyncPipe` usage that already handles cleanup?
- For each Zone.js finding, did you confirm the callback actually runs outside Zone.js (via `runOutsideAngular` or a non-patched async API), not just inside a plain `setTimeout`?
- For Signal findings, did you verify the project uses Angular 16+ before flagging Signal-specific patterns?

Append confidence level (High/Medium/Low) to the `summary` field.

## Ignore

Component composition and prop drilling (component-architecture-review), generic array mutation style (js-fp-review), accessibility (a11y-review), race conditions in non-reactive paths (concurrency-review), RxJS operator correctness beyond subscription management (concurrency-review), security, naming, complexity (handled by other agents)
