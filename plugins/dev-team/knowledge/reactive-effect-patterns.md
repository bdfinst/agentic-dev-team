# Reactive Effect Patterns — Cross-Framework Reference

Shared reactivity patterns that appear in multiple UI frameworks. Cited by
`react-reactivity-review`, `vue-reactivity-review`, `angular-reactivity-review`,
and `svelte-review`. Agents read this file for the shared taxonomy, then apply
their own framework-specific detection sections.

## Effect self-writes (infinite loop)

**Pattern**: A reactive effect / watcher reads a reactive value *and* writes
back to that same reactive value unconditionally, causing an infinite update
cycle.

| Framework | API | Infinite-loop example |
|-----------|-----|----------------------|
| React | `useEffect` | `useEffect(() => { setCount(count + 1); }, [count])` |
| Vue 3 | `watchEffect` | `watchEffect(() => { state.x = state.x + 1; })` |
| Angular (Signals) | `effect()` | `effect(() => { counter.set(counter() + 1); })` |
| Svelte 5 | `$effect` | `$effect(() => { count = count + 1; })` |

**Correct pattern**: use a one-time handler or a guard condition so the write
only fires when the new value differs meaningfully from the current value, or
restructure so the write is not in the same effect that reads the dep.

## Effect cleanup (subscription / timer leaks)

**Pattern**: A reactive effect opens a resource (timer, subscription, socket,
event listener) and does not clean it up when the effect is torn down or
re-run, causing memory leaks and duplicate handlers.

| Framework | API | Cleanup mechanism |
|-----------|-----|-------------------|
| React | `useEffect` | `return () => cleanup()` inside the effect |
| Vue 3 | `watchEffect` | `onCleanup(fn)` parameter or `onUnmounted` hook |
| Angular | `ngOnDestroy` / `DestroyRef` | `unsubscribe()`, `takeUntilDestroyed()`, `ngOnDestroy` |
| Svelte 5 | `$effect` | `return () => cleanup()` inside the effect |
| Svelte 4 | `onDestroy` | `onDestroy(cleanup)` |

**Detection signal**: any `setInterval`, `setTimeout`, `addEventListener`,
`.subscribe()`, `new WebSocket()`, or `new EventSource()` inside a reactive
effect body that is not paired with a corresponding teardown in the cleanup
path.

## Stale captured values

**Pattern**: A reactive effect captures a variable by closure at the time the
effect is created. If the variable changes and the effect is not re-subscribed,
the effect operates on a stale snapshot of the value.

Primarily a React `useEffect` / `useCallback` pattern (missing dep array entry),
but also appears in Vue `watch` with a plain-value source and in Angular
Zone.js callbacks that capture component state by closure at the time a
`runOutsideAngular` block is set up.

**Detection signal**: a variable read inside an effect that is also declared or
assigned outside the effect, where the effect's dependency registration
(dep array, `watch` source, or Zone.js context) does not include that variable.

## Computed / derived values with side effects

**Pattern**: A derived/computed value is given a getter function that performs
side effects (network request, DOM write, state mutation). Derived values must
be pure; side effects belong in effects/watchers.

| Framework | Pure API | Side-effect API |
|-----------|----------|-----------------|
| React | `useMemo` | `useEffect` |
| Vue 3 | `computed()` | `watch` / `watchEffect` |
| Angular Signals | `computed()` | `effect()` |
| Svelte 5 | `$derived` | `$effect` |

**Detection signal**: network calls (`fetch`, `axios`, `http.get`), DOM writes,
`console.log`-as-real-logic, or state mutations inside a `computed` / `useMemo`
/ `$derived` getter.
