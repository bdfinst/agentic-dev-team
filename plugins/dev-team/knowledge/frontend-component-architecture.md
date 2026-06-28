# Frontend Component Architecture

Reference catalog for reviewing how reusable UI components are factored as a
frontend evolves. The goal is to keep duplication from accreting: when the same
rendering, layout, or interaction logic appears in several places, it should be
extracted into one reusable component with a deliberate prop/slot contract —
without over-abstracting incidental similarity into the wrong shared component.

Framework-agnostic. Map each pattern to the local framework's idiom (see
[Framework mapping](#framework-mapping)) rather than pattern-matching one
framework's syntax.

## When to extract (and when not to)

- **Rule of three.** Two occurrences are not yet duplication — they may diverge.
  At the **third** copy of the same UI structure + behavior, extract a reusable
  component. Flag the third occurrence, not the second.
- **Semantic vs incidental similarity.** Before flagging, apply the test: *if the
  visual or behavioral rule changes, must every copy change together?* If yes →
  semantic duplication (extract it). If the copies look alike today but answer to
  different product concepts that will diverge → incidental similarity (leave it).
  Two unrelated forms that happen to have a name + email field are not the same
  component.
- **Cost of the wrong abstraction.** A premature shared component that accumulates
  boolean flags (`isAdmin`, `compact`, `variant`, `mode`) to serve divergent
  callers is worse than the duplication it replaced. Prefer composition over a
  flag-laden mega-component.

## Detection categories

### Duplicate render logic

The same JSX/template subtree (markup structure + class/style + bindings) is
repeated across components or files with only data substituted. Three+ near-copies
of a card, list row, modal, empty-state, or table is an extraction candidate.
Severity `warning` (third copy) → `error` when a behavioral rule (validation,
formatting, accessibility wiring) is duplicated and would force multi-site edits.

### Reusable-primitive extraction candidates

Repeated *patterns* that the codebase keeps re-implementing inline instead of
calling a shared primitive: form-field + label + error wrapper, button variants,
input groups, loading/skeleton states, pagination, toast/alert. If the project
already has such a primitive, an inline reimplementation should call it instead
(name the existing component). If it does not, recommend extracting one.

### Component granularity

- **God component**: one component mixing data fetching, business logic, layout,
  and several unrelated UI regions (a 300-line `Dashboard` rendering header +
  sidebar + table + modal inline). Recommend splitting along the seams.
- **Over-fragmentation**: a separate component per trivial wrapper (`<NameField>`,
  `<EmailField>`, `<PhoneField>` that each only render one labeled input) where a
  single parameterized component would do. Recommend collapsing.

### Prop drilling

State or callbacks threaded through intermediate components that do not use them,
purely to reach a deep descendant (three+ levels of pass-through). Signals that
the state should be lifted to a context/provider, store, or that the subtree
should be composed via `children`/slots so the owner passes the node directly.
Severity `warning`; `suggestion` at two levels.

### Inconsistent component APIs

Sibling components that do the same job expose different contracts: event-handler
naming drift (`onClick` vs `onPress` vs `handleClick`), boolean vs enum for the
same concept (`isPrimary` in one, `variant="primary"` in another), inconsistent
prop shapes (`{user}` object here, `userName`/`userId` scalars there). Inconsistent
public APIs across reusable components block reuse and invite copy-paste. Recommend
one convention and align the outliers.

### Composition over configuration

- A component accumulating mode/variant flags that switch large rendering branches
  is usually better split or recomposed via slots/`children`/compound components.
- Prefer exposing a `children`/default slot for caller-supplied content over a
  `renderX`/`content` prop that re-implements composition the framework gives free.
- Compound-component / named-slot patterns (`<Menu><Menu.Item/></Menu>`) suit
  families of parts that share implicit state; recommend them over prop-configured
  monoliths when the family keeps growing.

### Cross-feature / design-system reuse

The same visual primitive reimplemented independently in two feature folders
(two hand-rolled `Modal`s, two date pickers). As a frontend grows these drift in
behavior and accessibility. Recommend promoting one into the shared component
layer (`components/`, `ui/`, design system) and deleting the duplicate.

### Library barrel / public exports

A shared component library needs **one public entry point** — an `index`
barrel (`index.ts`/`index.js`/`index.tsx`) that re-exports the components callers
are meant to use. Flag:

- A shared component directory (`components/`, `ui/`, `lib/components`, a
  design-system package) that has **no index barrel** re-exporting its
  components, so consumers must reach into file paths to import them.
- A barrel that exists but is **stale** — newly added reusable components are not
  re-exported from it, so they are effectively private and get copy-pasted instead
  of reused.
- Consumers **deep-importing internals** (`import { Button } from
  "ui/components/button/Button"`) when a barrel entry exists (`import { Button }
  from "ui"`); deep imports couple callers to internal layout and discourage reuse.

A single, stable public surface makes the library's components discoverable and
keeps internal file moves from breaking consumers. Recommend adding/updating the
`index` barrel and importing through it. This is `warning` for a missing/stale
barrel in an established shared layer, `suggestion` for deep-import drift.

## Framework mapping

Recognize the *concept*, then express the fix in the project's framework:

- **React/JSX** — extract a function component; lift state to Context or a store;
  use `children`/render-as-children; compound components via `Component.Sub`;
  custom hooks for duplicated stateful logic (not just markup).
- **Vue (SFC)** — extract a `.vue` component; `provide`/`inject` or a Pinia store
  for drilling; default + named `<slot>`s; composables for shared logic.
- **Svelte** — extract a `.svelte` component; context API (`setContext`/
  `getContext`) or a store for drilling; default + named slots / snippets.
- **Angular** — extract a component; a shared service (DI) instead of `@Input`
  chains; content projection via `<ng-content>`; structural directives for
  repeated template fragments.

## What NOT to flag

- Two occurrences (below the rule-of-three threshold) with no shared behavioral
  rule — wait for the third.
- Structurally similar markup serving genuinely different product concepts that
  are expected to diverge (incidental similarity).
- Framework-idiomatic prop passing one level deep (that is not drilling).
- One-off layout markup that is intentionally unique to a single screen.
- A single component or a feature-local folder that is not a reusable library —
  don't demand a barrel for components that aren't meant to be shared.
- Pure styling/className concerns with no structural duplication (defer to design
  tokens / CSS review, not component extraction).
- Business-logic duplication that is not UI-shaped — that belongs to
  structure-review / refactor-opportunity-review, not this review.
