<!-- spec-version: 1 -->
# Spec: Mutation-Kill Slice-Loop Refinements (issue #667)

**Format:** dev-team `/specs` v1

## Intent Description

Four refinements to the `mutation-kill` agent's per-slice kill loop, derived from a
real Stryker.NET drive on `slice-05-root` (8 root-level `.cs` files, 420 mutants, 3
kill iterations at 20–24 min each). Each iteration re-tested files that had already
converged in a prior iteration, spent full-`Standard`-level mutant budget on a first
pass whose only job was finding where survivors are, missed a DI-wiring file
(`ComponentModule.cs`) that the existing infra-exclusion heuristic's filename
allowlist doesn't cover, and ran Stryker's own mutant-testing processes at a flat
concurrency of 5 regardless of the machine's core count.

The change lands four refinements, all scoped to the `mutation-kill` agent and its
Stryker.NET reference/wrapper:

1. **Convergence history across `--all` invocations** — persist which files have
   fully converged (0 survivors) or been excluded, so a fresh `--all` invocation
   shrinks the `--mutate` glob instead of re-testing them. Mirrors the existing
   `mutation-history.json` reuse rule in `quality-targets-converge/SKILL.md`.
2. **Tiered `mutation-level` (Stryker.NET only)** — first pass at `Basic`; escalate
   to `Standard` only for files with survivors remaining after Basic converges.
3. **Broadened infrastructure-exclusion heuristic** — extend the filename allowlist
   with DI/wiring conventions (`*Module.cs`, `*Container.cs`, `*Registration.cs`,
   `*Bootstrap*.cs`, `*DependencyInjection*.cs`) and let the two numeric signals
   (`score < 15%` and `NoCoverage > 50%`) alone trigger the existing batched
   confirmation question when no filename pattern matches, rather than requiring
   both a numeric and a filename match.
4. **Concurrency default fix** — the Stryker.NET wrapper defaults Stryker's own
   `-c`/`--concurrency` mutant-testing-process flag to `max(1, cpu_count - 2)`
   unless the caller passes an explicit value, instead of relying on Stryker's own
   flat default of 5.

Excluded: the `coverage-analysis: perTest` + xunit.v2 shim experiment referenced in
the issue as a separate, not-yet-actionable follow-up
(`prompts/mutation-coverage-analysis-experiment.md` in the downstream repo).

The PR body must include `Closes #667`. This diff touches an agent spec, a
reference doc, and a shipped Python script — auto-merge is **not** armed; merge
requires explicit human approval per the repo working rules.

## Architecture Specification

**Files touched:**

1. `plugins/dev-team/agents/mutation-kill.md`
2. `plugins/dev-team/skills/mutation-testing/scripts/csharp_stryker_net_wrapper.py`
3. `plugins/dev-team/skills/mutation-testing/references/languages/csharp-stryker-net.md`
4. `tests/agents/mutation_kill_agent_tests.bats` — new assertions for items 1–3
5. `tests/scripts/test_csharp_stryker_net_wrapper.py` — new assertions for item 4

**Changes per file:**

### `agents/mutation-kill.md`

- **New section: Convergence history across `--all` invocations.** On `--all`,
  after each file's loop concludes (`survivors == 0`, or the file is
  infra-excluded / structurally-unkillable-excluded), write/update one entry in
  `StrykerOutput/mutation-kill-convergence.json` in the target repo:
  `{ "file": <path>, "status": "converged"|"excluded", "reason": <string|null>,
  "commit": <sha of HEAD at time of convergence> }`. On a fresh `--all`
  invocation, read this file **before** the baseline scan. For each entry whose
  recorded `commit` still matches the file's current last-commit SHA
  (`git log -1 --format=%H -- <file>`) — **regardless of whether its status is
  `"converged"` or `"excluded"`** — append `"!<file>"` to the baseline
  `--mutate` glob and skip the file in the per-file loop entirely, logging
  `SKIPPED <file> — already converged at <sha>` or `SKIPPED <file> — excluded:
  <reason>` respectively (matching the existing `EXCLUDED <file> — <reason>`
  file-first log convention). When the file has changed since the recorded
  commit, drop the stale entry and include the file in scope as normal. Print a
  run-level summary once the baseline scan completes: `convergence: skipped N
  (already converged/excluded), testing M`. This is the same shape as the
  existing mutation-history reuse rule in `quality-targets-converge/SKILL.md`
  (which requires the analogous summary line for the same reason: "without
  that line, the reuse rule is invisible"), applied within `mutation-kill`'s
  own `--all` lifecycle rather than across workflow phases. It is
  complementary to, not a replacement for, the existing `--since`
  incremental-run pattern: `--since` answers "did this source file change vs.
  a git ref," which cannot express "this file's mutant set already converged
  under `mutation-kill`" — a file can be unchanged since `main` yet never have
  been scoped by `mutation-kill` at all. Both mechanisms can narrow the same
  shard config's `mutate` glob simultaneously.
- **New section: Tiered mutation-level (Stryker.NET only).** The baseline `--all`
  scan runs at `--mutation-level Basic`. A file whose Basic-level rounds reach
  `survivors == 0` is done — no Standard pass. A file whose Basic-level rounds
  stop via the no-improvement or `--max-rounds` exit with `survivors > 0` logs
  `ESCALATING <file> — Standard pass: N survivors remaining after Basic` and gets
  **one** additional pass at `--mutation-level Standard`, scoped via `--mutate` to
  just that file, to surface the pickier operators (`LinqMutation`,
  `StringMutation`, etc.) the Basic level doesn't generate. Cross-reference the
  existing CompileError trap in `csharp-stryker-net.md` (caching/key-building
  classes under `Standard` producing 1000+ CompileErrors) — a file that hits that
  trap during its Standard escalation drops back to Basic-only and gets an
  `EXCLUDED` log line, not a retry loop.
- **Extend Infrastructure exclusion detection.** Add filename patterns `*Module.cs`,
  `*Container.cs`, `*Registration.cs`, `*Bootstrap*.cs`, `*DependencyInjection*.cs`
  to the existing allowlist (`Startup.cs`, `Program.cs`, `*Filter.cs`,
  `*Middleware.cs`, `*Logger*.cs`, `*HealthCheck*.cs`, `*.Designer.cs`). Change the
  trigger condition from "both numeric signals AND a filename match" to "both
  numeric signals alone are sufficient" — a filename match becomes a hint added to
  the confirmation question's wording, not a gate; failing either numeric signal
  alone never triggers the question. The confirmation question remains batched
  and gated exactly as today, but now itemizes each flagged file individually
  with its specific trigger reason (named convention, or "no filename
  convention matched — score/coverage signal only") rather than asking one
  undifferentiated question across a mixed batch.
- **New passage (near the per-language translation table or the `--concurrency`
  flag docs):** cross-reference that the Stryker.NET wrapper defaults its `-c`
  flag to `cores − 2` (see wrapper change below) — mutation-kill's own
  `--concurrency` flag (worktree fan-out, default 2) is unrelated and unchanged.

### `scripts/csharp_stryker_net_wrapper.py`

- Add `--stryker-concurrency` CLI flag with `STRYKER_MUTANT_CONCURRENCY`
  env-var equivalent, following the existing flag pattern (CLI wins over env,
  env wins over computed default). **Not** named `--concurrency`/`-c`: those
  spellings are reserved for (a) Stryker's own pass-through flag, which
  `argparse.parse_known_args` must never consume — registering `-c` as a
  wrapper-owned short option would make it structurally impossible for a
  caller's pass-through `-c` to reach the "already present" detection below —
  and (b) mutation-kill's own pre-existing `--concurrency` (worktree fan-out),
  a different dial at a different layer that already owns that name.
- Compute `default_concurrency = max(1, (os.cpu_count() or 2) - 2)` when no
  explicit value is given. Document that `os.cpu_count()` reads host/system
  core count, not a container's cgroup quota — operators on resource-capped CI
  runners should pass an explicit value.
- Before invoking Stryker, inject `-c <value>` into the forwarded `stryker_args`
  **unless** the caller's pass-through args already contain `-c` or
  `--concurrency` (explicit caller intent always wins; never override it). When
  a pass-through value is present alongside an explicit `--stryker-concurrency`
  or env value, log a one-line note naming the override so it is never silent.

### `references/languages/csharp-stryker-net.md`

- Document the tiered `mutation-level` pattern with example commands (Basic
  baseline, Standard escalation scoped to one file).
- Document the wrapper's concurrency default and override mechanism.
- Extend the existing "Infrastructure exclusion `mutate` glob template" section to
  show convergence-based `!<file>` negations alongside the permanent
  infra-exclusion negations — same `mutate` array, two sources of entries
  (infra-exclusion is permanent; convergence entries are re-checked and can drop
  out if the file changes).

## Acceptance Criteria

1. `mutation-kill.md` documents a persisted convergence-history mechanism: file
   path, entry shape (`file`, `status`, `reason`, `commit`), the staleness check
   (commit-SHA comparison), and the resulting glob-shrinking + skip-log behavior
   on a fresh `--all` invocation.
2. `mutation-kill.md` documents the Basic → Standard tiering: Basic runs first,
   only-survivors escalate to Standard, and the CompileError trap's interaction
   with the escalation (drop to Basic-only + `EXCLUDED` log, not a retry).
3. `mutation-kill.md`'s infra-exclusion section includes the five new filename
   patterns and states that the two numeric signals alone (no filename match
   required) trigger the existing batched confirmation.
4. `csharp_stryker_net_wrapper.py` injects a computed `-c` value into forwarded
   Stryker args when the caller didn't pass one, and never overrides an explicit
   caller-supplied `-c`/`--concurrency`. Covered by new pytest cases mirroring the
   existing `TestMainContract` style (assert on captured `stryker_args`).
5. `csharp-stryker-net.md` documents all three C#-specific mechanics (tiering,
   concurrency default, convergence-glob template extension) with runnable
   example commands/config.
6. `mutation_kill_agent_tests.bats` gains grep-contract assertions for items 1–3,
   consistent with the file's existing test style; `mutation-kill.md` stays under
   the existing 500-line file-size gate.
7. No regression: existing `mutation_kill_agent_tests.bats` and
   `test_csharp_stryker_net_wrapper.py` assertions continue to pass unchanged
   (the new filename patterns and concurrency injection are additive).

## Ambiguity Log

| Decision | Classification | Resolved By | Rationale / Answer |
| ---------- | --------------- | ------------- | ------------------- |
| Convergence-state file path/format (`StrykerOutput/mutation-kill-convergence.json`, per-entry shape) | `inferable` | inference | Low-reversal-cost path choice colocated with existing `StrykerOutput/` artifacts; mirrors the existing `mutation-history.json` shape used by `quality-targets-converge/SKILL.md` for an analogous reuse rule. |
| "Converged" threshold for tiering escalation (when does a file skip the Standard pass) | `inferable` | inference | Reuses `mutation-kill`'s existing `survivors == 0` convergence definition (no percentage-score target exists anywhere in this agent today) rather than inventing a new threshold concept. |
| Loosening the infra-exclusion AND-gate to numeric-signals-alone | `inferable` | inference | Extends the existing confirm-gated heuristic (never silent) rather than introducing a new classification mechanism; the issue itself frames this as "let the skill classify... or let the operator tag," and the repo's established pattern is heuristic-flags + human-confirms. |
| Concurrency default value (`cores − 2`) | `inferable` | inference | Directly matches the reasoning already documented for `mutation-kill`'s own `--concurrency` flag ("physical cores − 2") in the same file. |

## Consistency Gate

- [x] Intent is unambiguous
- [x] Every behavior/goal maps to an acceptance criterion
- [x] Architecture constrains without over-engineering
- [x] Terminology consistent across artifacts
- [x] No contradictions between artifacts
- [x] Every gap/ambiguity finding is logged — inferable with rationale or resolved by human
