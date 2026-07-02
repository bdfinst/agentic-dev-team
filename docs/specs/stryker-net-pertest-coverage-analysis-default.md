# Spec: Stryker.NET — default `coverage-analysis: perTest` for xunit.v2-shim projects

<!-- spec-version: 8.4.0 -->

## Intent Description

Update the `csharp-stryker-net` Stryker.NET mutation-testing skill reference
(`plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md`)
to recommend `"coverage-analysis": "perTest"` as the default `stryker-config.json`
setting for xunit.v2 and xunit.v2-shim C# projects. Issue #669 ran the experiment
this repo previously deferred (per #667): it validated that `perTest` produces
mutation-kill counts identical to a full-suite `"off"` baseline on `slice-05-root`,
including through the two known false-negative risks for static-analysis-based
coverage tools — reflection via `MethodInfo.Invoke` and Autofac
`container.Resolve<T>()` DI resolution — while cutting mutation-testing wall-clock
time roughly 5-6x (~19-24 min → ~6 min). This spec turns that validated result into
skill guidance so teams running Stryker.NET on xunit.v2/shim projects get the
faster default without re-deriving or re-running the experiment.

This is a documentation-only change: no code, hook, adapter, or agent behavior
changes.

## Architecture Specification

- **Component touched:** `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md` only.
- **Unchanged constraint:** the existing xunit.v3/MTP-runner mandate
  (`"coverage-analysis": "off"`, `additional-timeout`, `xunit.runner.json` steps,
  documented under "xunit.v3 detection") stays exactly as-is. Issue #669 did not
  re-test that failure mode; issues #554/#557 are still the reason it exists.
- **Scope of new guidance:** explicitly limited to non-xunit.v3 (xunit.v2 /
  xunit.v2-shim) projects. Must read as a complement to the xunit.v3 carve-out, not
  a blanket "always use perTest" statement that could be misread as superseding it.
- **Placement:** new subsection immediately after "xunit.v3 detection" — the
  section it is the counterpoint to — so a reader scanning coverage-analysis
  guidance sees both branches (xunit.v3 → off; else → perTest) together.
- **Internal consistency fix (in scope):** the doc's two existing CLI examples
  (`dotnet stryker --coverage-analysis perTest ...` in the "Run (scoped)" section)
  show `--coverage-analysis` as a working CLI flag. Issue #669 confirms Stryker.NET
  4.15.0 has no CLI flag for this setting — it is `stryker-config.json`-only
  (confirmed via `--help`). Leaving those examples uncorrected would have the doc
  contradict the new section. Correct or annotate both examples so a reader does
  not conclude the CLI flag has any effect.
- **Out of scope:**
  - `plugins/dev-team/hooks/mutation_adapters/stryker_net.py` — the sole
    Stryker.NET adapter (the legacy `hooks/mutation-adapters/stryker-net.sh` bash
    script no longer exists; the bash→Python migration in ADR 0015 removed it) —
    already passes `--coverage-analysis perTest` unconditionally as a CLI arg. Per
    #669 that flag is a no-op in 4.15.0, so its presence is harmless; the actual
    switch lives in `stryker-config.json`, which this adapter does not generate.
    No code change.
  - `stryker-setup.py` (the config generator referenced throughout the skill) lives
    in the external `nextgen-test-upgrade-process` toolkit, not this repo — not
    editable here.
  - `plugins/dev-team/hooks/lib/build_knowledge_index.py` rebuild — verified
    unnecessary; the indexer only reads `knowledge/*.md` and each skill's
    top-level `SKILL.md`, not nested `references/` files (confirmed by reading
    `build_knowledge_index.py`).

## Acceptance Criteria

1. `csharp-stryker-net.md` contains a new section recommending
   `"coverage-analysis": "perTest"` as the default for xunit.v2 / xunit.v2-shim
   Stryker.NET projects, citing issue #669's experiment result (identical Killed
   counts across both rounds — DataFormatter/SystemConstants/RequestContext/
   PublicApiAttribute/ComponentModule — and ~5-6x speedup) as evidence.
2. The new section explicitly states the recommendation does not apply to
   xunit.v3/MTP-runner projects, and cross-references the existing "xunit.v3
   detection" section's `"off"` mandate rather than restating it.
3. The doc no longer implies `--coverage-analysis` is a working CLI flag; both
   existing CLI examples showing `--coverage-analysis perTest` are corrected or
   annotated to state Stryker.NET 4.15.0 accepts this only via the
   `stryker-config.json` `coverage-analysis` key.
4. No code, agent, skill, or hook file is modified — only `csharp-stryker-net.md` plus this change's own companion spec/plan/verification-script artifacts (`docs/specs/`, `plans/`), per this repo's established convention for spec-driven doc PRs (precedent: issue #522 / commit `d9c0f1c`, which shipped its spec + plan alongside the corrected reference file).
5. The resulting diff qualifies as documentation-only under the repo's top-level
   `CLAUDE.md` auto-merge policy (touches only `*.md`, changes no code/agent/skill
   frontmatter/hook/eval-fixture/marketplace-manifest).

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
| ---------- | --------------- | ------------- | ------------------- |
| Should the xunit.v3 "off" mandate be weakened or merged with the new perTest guidance? | `inferable` | inference | #669 only tested xunit.v2-shim; the xunit.v3/MTP incompatibility (#554/#557) is untouched and unrelated. Keep both branches distinct. |
| Should the doc's existing CLI examples showing `--coverage-analysis perTest` be corrected? | `inferable` | inference | Leaving them would contradict the new section's "config-file only" statement within the same doc — direct internal-consistency violation the spec gate would catch. Fixing them is a documentation-correctness matter, not a product decision. |
| Should the CLI adapter (`stryker_net.py`) be updated to drop the no-op `--coverage-analysis perTest` flag? | `inferable` | inference | Out of scope: the flag is harmless (Stryker ignores it per #669), removing it changes shipped code for a doc-only issue, and the issue's own recommendation targets `stryker-config.json` generation, not the adapter CLI invocation. |
| Does this edit require a `build_knowledge_index.py` rebuild? | `inferable` | inference | Verified by reading the indexer: it reads `knowledge/*.md` and each skill's top-level `SKILL.md` only, not nested `references/` files. No rebuild needed. |
| Where should the new guidance live in the doc? | `inferable` | inference | Immediately after "xunit.v3 detection," since it is that section's direct counterpoint (else-branch) and readers scanning coverage-analysis guidance should see both branches together. |

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — inferable with rationale or resolved by human
