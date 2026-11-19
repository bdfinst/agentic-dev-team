# E2E triage

Classify each existing E2E, find the minimum set across repos, and discover gaps. Taxonomy, candidate criteria, and placement are in `knowledge/cd-test-architecture.md`; the gate is not restated here.

## Detection

Find E2E tests in each repo (automation frameworks, tests that hit deployed services) and the pipeline files that run them. A journey wired as a pre-merge or PR gate is still listed, with stage `post-deploy` and advice to remove it from the pre-merge gate. Dedupe repeated repo paths.

## Classification

| Class | Rule |
|---|---|
| `KEEP` | Passes the gate and carries exactly one taxonomy category. |
| `PUSH DOWN -> <layer>` | A smaller layer can own it. Name the covering test, or `none found, create one first`. |
| `DELETE` | Only when a named smaller test already asserts the same behavior. |

"Covering" means a test at a smaller layer that asserts the same expected outcome for the same service pair or component. Edge-case, validation, and error-path E2Es are never `KEEP`. A mixed E2E is `KEEP` for the journey and `PUSH DOWN` for its error assertions. Never `DELETE` without a named covering test.

Each `KEEP` journey states: real component names spanned; taxonomy category; one sentence on why contract, component, and resilience tests cannot cover it; stage (post-deploy, scheduled, acceptance in an ephemeral environment, or synthetic monitoring; never pre-merge); source repos.

## Multi-repo merge

- **Merge key:** the lowercased, alias-mapped, sorted component set plus the taxonomy category. The same key from two repos is one journey, listed once with both repos as provenance.
- **Alias map:** inferred from service names in config, compose files, and client class names, and listed in Scope for correction. `--aliases <path>` (JSON `{"alias": "canonical"}`) overrides it.
- **Partial component overlap:** separate journeys, each marked `possibly same`.

## Gap discovery

Use repowise first: `get_overview` per repo for structure and entry points; `search_codebase` for interaction signals (producer/consumer, client, topic, queue, endpoint names; `complete: true` means every match); `get_context include=["references"]` to follow a symbol across repos; `get_answer` for one how/where question per call.

Inventory edges that cross a repo or deployable boundary: pub/sub producers and consumers, gRPC/HTTP clients calling another deployable, shared-database writers and readers, token or tenant propagation, startup/config/migration wiring, third-party integrations. For each, ask whether a `KEEP` journey covers it. If not, apply gate conditions 1-3. If a contract, component, or resilience test can cover it, report `Cover with <contract|component|resilience> test instead` and propose no E2E. Propose an E2E only when all four gate conditions hold: a contract, a component, and a resilience test each cannot cover it, and it is a critical journey across real components.

Each gap candidate states: components (real names, with file or symbol evidence); taxonomy category; why smaller tests cannot cover it; proposed stage; priority note (`critical business path` or `lower risk`) with the reason.

- **Cap:** at most 10 gap candidates; say when capped. Gap candidates are never part of the minimum set.
- If none: `No E2E gaps found in scanned repos`. If no `KEEP` journeys: `No E2E journeys justified in scanned repos` plus the scanned list.
