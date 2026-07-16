---

name: react-reactivity-review
description: React hook rules violations, stale closures in useEffect, missing dependency arrays, setState-during-render, subscription leaks
tools: Read, Grep, Glob
effort: low
cites: [adversarial-review-protocol]
scope:
  - **/*.jsx
  - **/*.tsx
  - **/*.js
  - **/*.ts
---

# React Reactivity Review

Scope: React component and hook files (`.jsx`, `.tsx`, and `.js`/`.ts` files
that import from `react`). Skip this agent entirely if the project has no
`react` or `react-dom` dependency in `package.json` (or equivalent manifest).
Covers React 16.8+ hooks and class-component lifecycle patterns.

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=no reactivity issues, warn=potential concerns, fail=likely silent reactivity breakage
Severity: error=silent stale-closure or infinite-loop bug; warning=potential reactivity concern; suggestion=defensive improvement
Confidence: high=mechanical fix (add dep, remove inline object); medium=pattern identified but component design may affect the fix; none=requires human judgment

Context needs: full-file

## Skip

Return `{"status": "skip", "issues": [], "summary": "No React files in target"}` when:

- No `react` / `react-dom` dependency found in the project manifest (`package.json`, `package-lock.json`, `yarn.lock`, etc.)
- No `.jsx` / `.tsx` / `.js` / `.ts` files import from `react` in the target set

## Detect

Whole-file load: `${CLAUDE_PLUGIN_ROOT}/knowledge/reactive-effect-patterns.md` for cross-framework effect/watcher patterns shared with Vue and Angular agents before running the React-specific checks below.

Stale closures in useEffect / useCallback / useMemo:

- Callback captures a state or prop variable at mount time and never re-captures it because the dependency array is wrong (missing dep, empty array `[]` when deps exist, or no array)
- Event handlers defined inside `useEffect` that reference props/state without deps — classic button-click stale counter
- `setTimeout` / `setInterval` callbacks capturing stale values — should use `useRef` or functional updater (`setState(prev => ...)`)

Missing or incomplete dependency arrays:

- `useEffect` / `useCallback` / `useMemo` with no second argument — runs on every render (performance) or conceals missing deps
- `useEffect` omitting a function prop from the dep array (`onSubmit`, `fetchData`, etc.) — infinite-loop risk if the parent recreates it each render
- Deps array contains the entire object when only a field is read — triggers unnecessarily on every parent render

setState during render:

- Calling `setState`/`dispatch` directly in the component body (not inside a handler or effect) — triggers a synchronous re-render loop
- Calling `setState` inside `useMemo` or `useCallback` body (not a handler)

Effect self-writes (infinite loop):

- `useEffect` that writes to a state variable that is also in its dep array — causes unconditional re-render cascade
- See `${CLAUDE_PLUGIN_ROOT}/knowledge/reactive-effect-patterns.md#effect-self-writes-infinite-loop` for the shared pattern

Missing cleanup in useEffect:

- `setInterval` / `setTimeout` without returning a cleanup function
- Event-listener `addEventListener` without a matching `removeEventListener` cleanup
- WebSocket / EventSource opened without closing in cleanup
- Third-party subscriptions (RxJS observable `.subscribe()`, Redux `store.subscribe()`) without unsubscribe in cleanup

Unstable references as dependencies:

- Inline object/array literals in JSX props passed down to a child's `useEffect` dep array — new reference on every render
- Functions created inline in render passed to a memoized child without `useCallback` — defeats `React.memo`

useRef misuse:

- Reading `ref.current` inside `useMemo`/`useCallback` dep computation — refs are mutable and not tracked
- Writing to `ref.current` during render (side effect during render phase)

Context value instability:

- `<Context.Provider value={{ ... }}>` with a new object literal on every render — all consumers re-render unconditionally
- Provider value derived from state without `useMemo`

## Self-Challenge

After producing findings, run the shared challenger loop in `${CLAUDE_PLUGIN_ROOT}/knowledge/adversarial-review-protocol.md` (Whole-file load: the slim shared methodology — The Loop + Output format — read in full), then work these react-reactivity-review-specific challenges:

- Did you confirm `react` is actually in the project's dependency tree before flagging any finding?
- For each stale-closure finding, did you trace the actual captured variable and confirm it changes after mount?
- For each missing-dep finding, did you verify the dep is actually read inside the effect body (not just referenced outside)?
- Did you check every `useEffect` for a cleanup return when it opens subscriptions, timers, or listeners?
- For each infinite-loop candidate, did you confirm the write actually targets a dep of the same effect?

Append confidence level (High/Medium/Low) to the `summary` field.

## Ignore

Component composition, prop drilling, reusable extraction (component-architecture-review), generic array mutation style (js-fp-review), accessibility (a11y-review), race conditions in non-reactive paths (concurrency-review), security, naming, complexity (handled by other agents)
