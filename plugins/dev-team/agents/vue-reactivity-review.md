---

name: vue-reactivity-review
description: Vue ref/reactive unwrapping pitfalls, watchEffect dependency tracking, reactive proxy escapes, composition API subscription leaks
tools: Read, Grep, Glob, mcp__codegraph__codegraph_explore, mcp__plugin_repowise_repowise__get_context, mcp__plugin_repowise_repowise__get_symbol, mcp__plugin_repowise_repowise__search_codebase, mcp__plugin_repowise_repowise__get_risk
effort: low
cites: [adversarial-review-protocol]
scope:
  - **/*.vue
  - **/*.js
  - **/*.ts
---

# Vue Reactivity Review

Scope: Vue component and composable files (`.vue`, and `.js`/`.ts` files that
import from `vue`). Skip this agent entirely if the project has no `vue`
dependency in `package.json` (or equivalent manifest).
Covers Vue 3 Composition API (`ref`, `reactive`, `computed`, `watch`,
`watchEffect`) and Vue 2 Options API reactivity pitfalls.

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=no reactivity issues, warn=potential concerns, fail=likely silent reactivity breakage
Severity: error=silent reactivity breakage; warning=potential reactivity concern; suggestion=defensive improvement
Confidence: high=mechanical Vue fix (wrap in ref/reactive, add dep, use .value); medium=pattern identified but component design may affect the fix; none=requires human judgment

Context needs: full-file

## Skip

Return `{"status": "skip", "issues": [], "summary": "No Vue files in target"}` when:

- No `vue` dependency found in the project manifest (`package.json`, `package-lock.json`, `yarn.lock`, etc.)
- No `.vue` / `.js` / `.ts` files import from `vue` in the target set

## Detect

Whole-file load: `${CLAUDE_PLUGIN_ROOT}/knowledge/reactive-effect-patterns.md` for cross-framework effect/watcher patterns shared with React and Angular agents before running the Vue-specific checks below.

ref vs reactive unwrapping pitfalls (Vue 3):

- Destructuring a `reactive()` object breaks reactivity — the destructured variables become plain (non-reactive) copies
- Spreading `reactive()` into a new object (`{ ...state }`) loses tracking — returned object is no longer reactive
- Using `reactive()` on a primitive (number, string, boolean) — use `ref()` instead; `reactive()` only wraps objects
- Passing a `reactive()` property directly to a composable parameter — the composable receives the current value, not a reactive reference; use `toRef()` or pass the whole object
- Forgetting `.value` on a `ref` in `<script setup>` — compiler auto-unwraps refs in templates but not in JS code

ref.value mutation pitfalls:

- Replacing the entire `.value` of a `ref` holding an object with a plain object (`ref.value = { ...newData }`) — creates a new reactive proxy, watch/watchEffect callbacks still track it, but watchers relying on the old proxy reference stop firing
- Direct array index assignment on a reactive array (`arr[0] = x`) in Vue 2 — use `Vue.set` or `splice`; Vue 3 proxies track this correctly but note it anyway if Vue 2 usage is detected

watchEffect / watch dependency tracking (Vue 3):

- `watchEffect` callback that reads a value via a plain function call that doesn't access the ref inside the effect scope — the effect doesn't track it and won't re-run
- `watch(source, handler)` with a non-reactive, plain-JS source value — handler never fires because Vue can't track a non-reactive source
- Accessing deeply nested reactive data inside a `watch` without `deep: true` — misses nested mutations
- See `${CLAUDE_PLUGIN_ROOT}/knowledge/reactive-effect-patterns.md#effect-self-writes-infinite-loop` for the shared infinite-loop pattern (applies to `watchEffect` writing to its own tracked dep)

Computed property pitfalls:

- `computed()` with a getter that has side effects (should be pure) — makes reactive tracking unpredictable
- Computed property writing to reactive state (mutable computed without explicit setter)
- `computed` depending on `ref.value` where the ref is passed as a parameter (not in scope) — always returns the initial value only

Subscription / watcher leaks (Composition API):

- `watch` / `watchEffect` called inside a composable or utility function outside a component setup context without the returned `stop` handle being saved and called on cleanup
- Event-bus listeners added in `onMounted` without a corresponding `onUnmounted` removal
- Third-party subscriptions (RxJS `.subscribe()`, `EventSource`, `WebSocket`) opened in `setup()` without cleanup in `onUnmounted`

Options API pitfalls (Vue 2 / Vue 3 Options):

- Properties added to `data()` objects after component creation (not declared in `data()`) — Vue cannot make them reactive retroactively; use `Vue.set` in Vue 2 or declare all fields up front in Vue 3
- Mutation of a Vuex state property directly instead of via a mutation — bypasses change detection

## Self-Challenge

After producing findings, run the shared challenger loop in `${CLAUDE_PLUGIN_ROOT}/knowledge/adversarial-review-protocol.md` (Whole-file load: the slim shared methodology — The Loop + Output format — read in full), then work these vue-reactivity-review-specific challenges:

- Did you confirm `vue` is actually in the project's dependency tree before flagging any finding?
- For each destructuring/spread finding, did you verify the source is a `reactive()` object (not a `ref`)? Destructuring a `ref` is fine — you'd lose `.value` access but not reactivity.
- For each watcher finding, did you confirm the watched source is actually non-reactive, not just passed in an unusual way?
- Did you check every composable for unregistered `watch`/`watchEffect` stop handles used outside component lifecycle?
- For Vue 2 array mutation findings, did you confirm the target is a Vue 2 project (Vue 3 proxies handle index assignment correctly)?

Append confidence level (High/Medium/Low) to the `summary` field.

## Ignore

Component composition and prop drilling (component-architecture-review), generic array mutation style (js-fp-review), accessibility (a11y-review), race conditions in non-reactive paths (concurrency-review), security, naming, complexity (handled by other agents)
