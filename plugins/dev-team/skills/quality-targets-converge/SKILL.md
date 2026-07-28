---
name: quality-targets-converge
description: >-
  Multi-workflow convergence worker. Closes the gap between the current test
  suite and the four quality targets (line+branch coverage ≥ 90%, zero
  surviving mutants, 100% deterministic, fastest pre-merge wall-clock
  achievable on-machine). Each iteration reads the latest measurements,
  picks the largest gap, and dispatches the smallest action that moves it.
  Stops only when all four targets are green or each gap is explicitly
  waived by the operator with a recorded reason. Called by `/test-improve`
  (Phase 8) via `--workflow test-improve`.
argument-hint: "<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--max-iterations <n>] [--refactor-mode <no-refactor|refactor-allowed>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Write, Skill(coverage-delta *), Skill(mutation-testing *)
---

# Quality Targets Converge

Role: worker. The convergence close-out loop. Reads coverage, mutation, determinism, and wall-clock measurements; picks the largest gap; dispatches the smallest action that moves it; re-measures; repeats. The operator gates the loop and can waive any individual target.

You have been invoked with the `/quality-targets-converge` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>`.
- `--parent <issue-url>` — parent issue URL (or empty).
- `--repo-slug <slug>` — `.claude/memory/<workflow>/` namespace.
- `--workflow <name>` — the workflow namespace under `.claude/memory/` and `.claude/plans/`. Defaults to `test-improve`. Callers pass their own namespace so parallel runs stay quarantined.
- `--max-iterations <n>` — safety cap. Default 10. The operator can extend mid-run.
- `--refactor-mode <no-refactor|refactor-allowed>` — gates whether Step 4's
  "coverage gap, no existing seam" action may propose a paired
  `[Refactor-for-testability]` Story (see Step 4). **Default
  `refactor-allowed`** when the flag is absent or carries an unrecognized
  value — this preserves today's unconditional-propose behavior for callers
  other than `/test-improve` that don't pass the flag. Whenever the default
  fires because the flag was absent or unrecognized, print
  `"refactor-mode not specified by caller — defaulting to refactor-allowed"`
  (naming the unrecognized value received, if any) so a caller that forgot
  to wire the flag is visible in the run output rather than silently
  indistinguishable from one that explicitly wants `refactor-allowed`.

**Path templates.** Every filesystem path in the Steps below carries `<workflow>` as a placeholder; the skill interpolates the resolved `--workflow` value at run time. There is no literal workflow-name string inside a path.

## Steps

### 1. Load targets

Read `.dev-team/quality-targets.json` if it exists; otherwise use defaults:

```json
{
  "line_pct_min": 90,
  "branch_pct_min": 90,
  "surviving_mutants_max": 0,
  "determinism_runs": 5,
  "determinism_required_pass_rate": 1.0,
  "wall_clock_target_seconds": null
}
```

`wall_clock_target_seconds = null` means "fastest achievable" — the loop tracks it but does not gate on a number.

### 2. Measure all four dimensions

In one pass before the loop body:

- **Coverage** — invoke `/coverage-delta <repo> --workflow <workflow>` (no `--story`). Result lives in `.dev-team-reports/<workflow>/<slug>/data/coverage-history.json`.
- **Mutation scope — branch-vs-base changed set (cumulative, NOT whole-repo).** Phase-8 validation measures mutation only over the code this branch changed, accumulated across every session on the branch — never the whole repo (issue #1208). Resolve the scope in three moves:

  1. **Resolve the branch base** (same idiom as `/build`'s Farley-Score step — `skills/build/SKILL.md` Step 7 sub-step 1): `git merge-base HEAD origin/HEAD`, falling back to `origin/main`, then `main`, `master`, `develop`. **Degenerate-base guard (issue #916):** treat **base == HEAD, or every candidate ref unresolvable** (single-branch / no-remote repo where `merge-base` fails outright, or every commit landed directly on the fallback branch so `merge-base` resolves to HEAD) as a resolution **failure**, not a valid base. On resolution failure, fall back to the plan's recorded plan-start anchor — the same anchor `/build` resolves against (issue #865): `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_rollback_point.py get-by-symbolic --path .claude/memory/build-rollback.json --symbolic plan-start --repo <repo> --ancestor-of HEAD` (the `--repo`/`--ancestor-of` args reject a stale `plan-start` from an unrelated earlier build). If a qualifying entry is found, use its `sha` as `<base>`. If none is found, print `Branch-base resolution degraded — cannot bound the changed set; scoping to the full in-scope component list this run.` and scope to the full in-scope component list **only as a surfaced last resort** — so a widened run is visible in the output, never a silent whole-repo default.
  2. **Cumulative changed set:** `git diff --name-only <base>...HEAD` (three-dot — everything the branch added since it forked, across all sessions, not just the last commit).
  3. **Scope is the source covered by the changed TESTS, not just changed source files.** A test-improvement branch commonly changes no production source at all, so mapping only changed `*.ts`/`*.py`/etc. would scope to nothing. From the changed set, take every changed **test** file and resolve the production source it exercises: a co-located `X.spec.ts` / `X.test.ts` maps to its sibling `X.ts` (same basename, same directory); an a11y / contract / integration spec that names no co-located sibling maps to the first-party production modules it **imports** (parse the spec's import statements, drop third-party paths). Union that resolved-source set with any changed production source files. That union is the mutation `--scope`.

- **Mutation — reuse rule (applied BEFORE the fresh `/mutation-testing` invocation below).** The upstream phase already measured mutation per `[Component tests]` Story; that evidence is in `.dev-team-reports/<workflow>/<slug>/data/mutation-history.json`. Use it instead of re-running mutation against files (from the branch-scoped set above) the upstream phase already exercised:

  1. For each in-scope file, look up the most recent entry in `mutation-history.json`.
  2. Compare the entry's `captured_at` to the file's last committer date: `git log -1 --format=%cI -- <file>` (committer date — not file mtime. Uncommitted edits intentionally won't trigger re-measure; convergence runs over committed code).
  3. If the entry post-dates the file's last commit AND `status != "tool_unavailable"`, **reuse** the entry's `survivors_after` as the current count. Drop the file from the `--scope` glob passed to the fresh `/mutation-testing` run below.
  4. Otherwise (no entry, stale entry, or prior `status: "tool_unavailable"`) — measure the file fresh in the next bullet. The fresh result is written back to `.dev-team-reports/<workflow>/<slug>/data/mutation-history.json` as a **synthetic entry** with `story: "converge-<iteration>"` so within-iteration reuse works and so the next iteration sees the same evidence the upstream phase would have.

  **Backward compatibility — `mutation-history.json` absent.** Workflows that pre-date this contract have no upstream mutation evidence. When the file is absent, fall through to measuring fresh: the next bullet runs `/mutation-testing` over every file **in the branch-vs-base changed set** defined above — the reuse rule is opportunistic, not required, but absence of history never widens the run back to whole-repo.

- **Mutation (fresh measurement on files the reuse rule didn't cover).** Invoke `/mutation-testing <repo> --scope <remaining-files> --workflow-managed-approval --emit-json <tmp>` (where `<remaining-files>` is the branch-scoped set minus the files the reuse rule covered). Parse the surviving-mutant list from its JSON output (filter `status: "equivalent"` AND `status: "accepted"` — both carry a `reason` and neither counts against convergence). Capture file + line + mutant operator for each survivor. Write back each freshly-measured file as a synthetic entry to `.dev-team-reports/<workflow>/<slug>/data/mutation-history.json` (see reuse rule above) via **temp-file-then-rename** (write to `<path>.tmp` then `mv -f <path>.tmp <path>`) — the same idiom [`coverage-delta/SKILL.md`](../coverage-delta/SKILL.md) Step 2b uses for the same now-shared, git-tracked file, so both writers stay safe against interleaved writes.

- **Unmeasurable modules — held at baseline, never dropped (issue #1208, criterion 4).** A module `/mutation-testing` cannot finish — reported OOM, or a tool crash, or a run so slow that `mutation-testing`'s per-mutant wall-clock timeout (which counts a timed-out *mutant* as killed) still leaves the whole *module's* score unestablished — must NOT be silently omitted and must NOT be reported with an invented number. Instead:

  1. First retry the module's **non-static** subset with `ignoreStatic` (static initializers are the common OOM trigger); if that subset now measures, use it and mark only the static remainder held-at-baseline.
  2. For whatever still cannot be measured, **hold it at its persisted baseline count** — the `survivors_after` recorded for that file in `baseline-mutation.json` / `mutation-history.json` — and record it in the snapshot's `held_at_baseline` list.
  3. Report it in Step 6 verbatim as **"held at baseline (could not measure — needs ≥N GB agent)"** — never as a fresh zero, never dropped from the module list.

- **Whole-repo score via splice over the persisted baseline (issue #1208, criterion 2).** Report BOTH the branch-scoped result AND a whole-repo number, but do **not** re-run the whole repo to obtain it. The whole-repo score is a **splice**: the freshly-measured changed files (above) layered over the **persisted per-file baseline** for every untouched file. The baseline of record is `baseline-mutation.json` plus the per-file `survivors_after` in `mutation-history.json` (see `/coverage-delta`'s [`references/mutation-gate.md`](../coverage-delta/references/mutation-gate.md)). Both files are written directly to `.dev-team-reports/<workflow>/<slug>/data/` at capture/append time — `baseline-mutation.json` by `/coverage-baseline` and `/test-improve` Phase 2, `mutation-history.json` by `/coverage-delta` (other agents are landing those write paths concurrently) — so the splice source is always available for every convergence session.

- **Determinism** — re-run the test suite `determinism_runs` times. Capture: pass rate, the names of any test that failed in some runs but passed in others, the total wall-clock per run (lowest = current baseline).

- **Wall-clock** — already captured as part of determinism. Take the median.

Write the snapshot to `.claude/memory/<workflow>/<slug>/converge-<iteration>.json`:

```json
{
  "iteration": <n>,
  "captured_at": "<ISO-8601>",
  "line_pct": …, "branch_pct": …,
  "surviving_mutants": [ { "file":…, "line":…, "op":… }, … ],
  "surviving_mutants_whole_repo_spliced": <count>,
  "held_at_baseline": [ { "module":…, "baseline_survivors":…, "reason": "oom|timeout|tool_crash" }, … ],
  "mutation_scope": {
    "base_ref":              "<sha>",
    "changed_test_files":    <count>,
    "resolved_source_files": <count>
  },
  "mutation_reuse": {
    "reused_from_history": <count>,
    "measured_fresh":      <count>,
    "total_files":         <count>
  },
  "determinism_pass_rate": …, "flaky_tests": [ … ],
  "wall_clock_median_sec": …, "wall_clock_runs": [ …, … ]
}
```

The operator-visible iteration report (Step 6) names the cost saving directly: `mutation: reused N, measured M` — without that line, the reuse rule is invisible and the operator can't tell whether upstream mutation evidence actually paid off.

### 3. Compute the gap to each target

For each of the four, compute "distance to target":

- Line: `target - current` (clamped at 0).
- Branch: `target - current`.
- Mutants: the **whole-repo spliced score** (`surviving_mutants_whole_repo_spliced`) — survivors in the branch-scoped changed set plus the persisted-baseline survivor counts held for every untouched module and every held-at-baseline / unmeasurable module. Gate `surviving_mutants_max` on this spliced number, never on a partial branch-only count, so a convergence run is judged against the whole repo's honest score.
- Determinism: `determinism_runs - passes`.
- Wall-clock: tracked, not gated unless the operator set a number.

### 4. Pick the largest gap + dispatch the smallest action

Use this priority order (matches the spec's order of operations) when two gaps tie:

1. Determinism (a flaky suite invalidates every other metric).
2. Surviving mutants (coverage you can't trust isn't coverage).
3. Line + branch coverage.
4. Wall-clock (only if the operator set a target).

For the picked gap, dispatch the smallest action — by emitting a recommendation, not by editing code (the actual edit happens via `/build` against a downstream Story):

| Gap | Smallest action |
| --- | --- |
| Flaky test | Identify the source of non-determinism (real clock, RNG, sleep, shared state, order dependence). Propose a downstream Story to remove it. |
| Surviving mutant on a covered line | The test asserts coverage but not behavior; propose a downstream Story to add the specific assertion that kills this mutant. |
| Surviving mutant on an uncovered line | Propose a downstream Story to add a test that hits the line *and* asserts the behavior. |
| Coverage gap on a single file, existing seam | Propose a downstream Story to add a component test for the uncovered branch at the existing seam. |
| Coverage gap on a single file, no existing seam, `--refactor-mode refactor-allowed` | Propose a paired `[Refactor-for-testability]` Story (today's behavior, unchanged). |
| Coverage gap on a single file, no existing seam, `--refactor-mode no-refactor` | Do **not** propose a `[Refactor-for-testability]` Story — the operator already closed that decision at Phase 6. Instead, write an entry (seam-needed / behavior-gained / estimated-risk) to `.dev-team-reports/<workflow>/<slug>/refactor-backlog.md`, appending to the file Phase 6 writes if it already exists rather than creating a second backlog file. |
| Behavior-preserving (invariant) test refactor — a `done()`→`async`/`await` rewrite, a real-timer→`fakeAsync` migration, a callback→promise conversion that changes no assertion and kills no mutant | **Skip it — do not dispatch a Story.** These migrations preserve test semantics, so they close no coverage / mutation / determinism gap; dispatching work for them is pure churn. Log the skip with its rationale to `.dev-team-reports/<workflow>/<slug>/refactor-backlog.md` (the same backlog the no-refactor row appends to) as `invariant-refactor-skipped: <file> — <migration> — no gap closed`, so the decision is auditable rather than silent. |
| Wall-clock regression | Identify the slowest tests (top 10). Propose a Story to swap a local container for an in-memory double where both prove the behavior. |

**Invariant refactors are skipped, not dispatched (issue #1208).** The "behavior-preserving (invariant) test refactor" row exists because a convergence loop scanning changed tests will encounter semantics-preserving migrations. They change no assertion and kill no mutant, so they close no target gap — proposing a Story for them only adds churn. Skip them and log the rationale to the backlog so the skip is auditable rather than silent.

**Gherkin binding for proposed component tests.** When the smallest action is "add a component test" (the surviving-mutant rows, or the coverage-gap-with-existing-seam row above), first check `.claude/memory/<workflow>/<slug>/gherkin-bindings.json` for an approved Scenario covering that behavior at the relevant public surface:

- **Scenario exists** — the proposed Story extends the matching `[Component tests]` Story rather than creating a new one. The recommendation cites `<feature-file>::<scenario-name>` and the test added in `/build` binds to that scenario in the binding mode recorded in `phase-0.md`.
- **Scenario is missing** — do NOT invent a Scenario inside a downstream Story. Pause the convergence loop and hand back to the orchestrator: the operator remains the single author of intent, and the Gherkin surface must be updated via the workflow's standard Phase-2 sign-off before this loop resumes. Do not open ad-hoc amendment Stories from inside this worker; that route would bypass the human gate and is intentionally not available here.

This keeps the approved Gherkin as the single source of intended behavior even when convergence discovers a gap. The operator stays the only author of intent.

Each recommendation lands as a new child issue on the parent (via the same CLI dispatch convention as `/issues-from-assessment`) or as a new file under `.claude/plans/<workflow>/phase-7/`. The orchestrator then drives `/build` against each.

### 5. Re-measure + decide whether to loop

After `/build` closes the dispatched Story:

- Re-measure (Step 2).
- If all four targets met → exit loop, mark the close-out Story Done.
- If `--max-iterations` reached → halt, print current state, ask the operator to waive remaining gaps or extend.
- Otherwise → next iteration.

### 6. Post the converge history

Append a markdown block to the parent (or `FEATURE.md`):

```markdown
### Convergence iteration <n> (<ISO-8601>)
- Coverage: line <pct>% (target 90%) · branch <pct>% (target 90%)
- Surviving mutants (branch-scoped changed set): <n> (target 0)  ·  mutation: reused <N>, measured <M>
- Surviving mutants (whole-repo, spliced over persisted baseline): <n>  ·  Δ vs baseline: <±n>
- Held at baseline (could not measure — needs ≥N GB agent): <module list, or "none">
- Determinism: <passes>/<runs> (target <runs>/<runs>)
- Wall-clock median: <sec>s (target: fastest achievable / <n>s if set)
- Largest gap: <dimension>
- Dispatched: <story title / id>
```

Same CLI pattern as `/coverage-baseline` and `/coverage-delta`.

### 6b. Gherkin effectiveness roll-up (conditional)

When `.claude/memory/<workflow>/<slug>/gherkin.md` exists (Phase 3 ran — see
`/gherkin-derive`), run the roll-up after every iteration's re-measure so
there is a standing signal on whether the derived scenarios track real
coverage/mutation movement (issue #1296):

```bash
python3 plugins/dev-team/scripts/gherkin_effectiveness_rollup.py \
  --gherkin-md .claude/memory/<workflow>/<slug>/gherkin.md \
  --bindings-json .claude/memory/<workflow>/<slug>/gherkin-bindings.json \
  --baseline-coverage .claude/memory/<workflow>/<slug>/baseline-coverage.json \
  --current-coverage <this iteration's coverage measurement> \
  --baseline-mutation .claude/memory/<workflow>/<slug>/baseline-mutation.json \
  --current-mutation <this iteration's mutation measurement> \
  --out .claude/metrics/gherkin-derive-effectiveness.jsonl
```

Omit any flag whose file doesn't exist for this run (e.g. no
`gherkin-bindings.json` when the workflow only derived scenarios via
`/gherkin-derive` and never ran `/gherkin-public`) — the script degrades
gracefully and still records provenance/binding-mode per scenario with the
correlated field left `null`. When `gherkin.md` is absent (binding mode
`none`, or Phase 3 never ran), skip this step entirely — there is nothing
to roll up. This is a metrics side-effect only; it never changes convergence
gaps or which action Step 4 dispatches.

### 7. Waiver handling

If the operator chooses to waive a target:

- Capture the reason verbatim.
- Record it in `.claude/memory/<workflow>/<slug>/waivers.json`.
- Append a `**Waived**: <target> — <reason> (<ISO-8601>)` line to the parent issue / `FEATURE.md`.

A waiver counts as "met" for the loop's exit condition but is surfaced in the orchestrator's final Report.

### 8. Report

Print:

- Current state of all four dimensions.
- Whether the loop converged, halted, or is mid-iteration.
- Any waivers recorded.
- The path to `converge-<iteration>.json` and to `waivers.json` (if any).
- The path to `.claude/metrics/gherkin-derive-effectiveness.jsonl` when Step 6b ran.

## Examples / Integration

- `/test-improve` invokes this worker from Phase 8 with `--workflow test-improve`; paths resolve as `.claude/memory/test-improve/<slug>/` and `.claude/plans/test-improve/phase-8/`, with tracked evidence (coverage/mutation history, baselines) under `.dev-team-reports/test-improve/<slug>/data/`.
- `/test-improve` invokes this worker from Phase 8 with `--workflow test-improve`; the same template resolves with `<workflow>` = `test-improve`.

## Notes

- This worker does not write tests or edit production code. Its output is recommendations + dispatched Stories that `/build` then implements. That keeps the workflow's "every change goes through a Story with Acceptance Criteria" invariant intact.
- The 10-iteration default is a backstop, not a target. Most repos should converge in 3–5; persistent failure to converge means the dispatched actions aren't the smallest — surface the loop to the operator for a strategy decision.
- Wall-clock is measured but only gated when the operator sets a number; the spec's "fastest achievable" phrasing is reported as the trend across iterations.
- Adding a new workflow caller means passing a new `--workflow <name>` value; no path edits inside this skill are required because paths are templated.
- **Locating seams and existing tests (Step 4).** When determining whether a coverage gap has an existing seam or which test exercises a given line/mutant, prefer `codegraph_explore` (CodeGraph) or Repowise `get_context`/`search_codebase` over raw `Grep` — they return the actual call graph rather than a text match, which is what distinguishes a real seam from a coincidental identifier match. Fall back to `Grep`/`Read` when neither MCP server is available for the target repo.
