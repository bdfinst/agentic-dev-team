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
  (Phase 6) via `--workflow test-improve`.
argument-hint: "<repo-path> [--parent <issue-url>] [--repo-slug <slug>] [--workflow <name>] [--max-iterations <n>]"
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
- `--repo-slug <slug>` — `memory/<workflow>/` namespace.
- `--workflow <name>` — the workflow namespace under `memory/` and `./plans/`. Defaults to `test-improve`. Callers pass their own namespace so parallel runs stay quarantined.
- `--max-iterations <n>` — safety cap. Default 10. The operator can extend mid-run.

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

- **Coverage** — invoke `/coverage-delta <repo> --workflow <workflow>` (no `--story`). Result lives in `memory/<workflow>/<slug>/coverage-history.json`.
- **Mutation — reuse rule (applied BEFORE the fresh `/mutation-testing` invocation below).** The upstream phase already measured mutation per `[Component tests]` Story; that evidence is in `memory/<workflow>/<slug>/mutation-history.json`. Use it instead of re-running mutation against files the upstream phase already exercised:

  1. For each in-scope file, look up the most recent entry in `mutation-history.json`.
  2. Compare the entry's `captured_at` to the file's last committer date: `git log -1 --format=%cI -- <file>` (committer date — not file mtime. Uncommitted edits intentionally won't trigger re-measure; convergence runs over committed code).
  3. If the entry post-dates the file's last commit AND `status != "tool_unavailable"`, **reuse** the entry's `survivors_after` as the current count. Drop the file from the `--scope` glob passed to the fresh `/mutation-testing` run below.
  4. Otherwise (no entry, stale entry, or prior `status: "tool_unavailable"`) — measure the file fresh in the next bullet. The fresh result is written back to `mutation-history.json` as a **synthetic entry** with `story: "converge-<iteration>"` so within-iteration reuse works and so the next iteration sees the same evidence the upstream phase would have.

  **Backward compatibility — `mutation-history.json` absent.** Workflows that pre-date this contract have no upstream mutation evidence. When the file is absent, fall through to the prior behavior: the next bullet runs `/mutation-testing` scoped to the full in-scope component list, exactly as before. The reuse rule is opportunistic, not required.

- **Mutation (fresh measurement on files the reuse rule didn't cover).** Invoke `/mutation-testing <repo> --scope <remaining-files> --workflow-managed-approval --emit-json <tmp>`. Parse the surviving-mutant list from its JSON output (filter `status: "equivalent"`). Capture file + line + mutant operator for each survivor. Write back each freshly-measured file as a synthetic entry in `mutation-history.json` (see reuse rule above).

- **Determinism** — re-run the test suite `determinism_runs` times. Capture: pass rate, the names of any test that failed in some runs but passed in others, the total wall-clock per run (lowest = current baseline).

- **Wall-clock** — already captured as part of determinism. Take the median.

Write the snapshot to `memory/<workflow>/<slug>/converge-<iteration>.json`:

```json
{
  "iteration": <n>,
  "captured_at": "<ISO-8601>",
  "line_pct": …, "branch_pct": …,
  "surviving_mutants": [ { "file":…, "line":…, "op":… }, … ],
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
- Mutants: count of survivors.
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
|---|---|
| Flaky test | Identify the source of non-determinism (real clock, RNG, sleep, shared state, order dependence). Propose a downstream Story to remove it. |
| Surviving mutant on a covered line | The test asserts coverage but not behavior; propose a downstream Story to add the specific assertion that kills this mutant. |
| Surviving mutant on an uncovered line | Propose a downstream Story to add a test that hits the line *and* asserts the behavior. |
| Coverage gap on a single file | Propose a downstream Story to add a component test for the uncovered branch at the existing seam. If none exists, propose a paired `[Refactor-for-testability]`. |
| Wall-clock regression | Identify the slowest tests (top 10). Propose a Story to swap a local container for an in-memory double where both prove the behavior. |

**Gherkin binding for proposed component tests.** When the smallest action is "add a component test" (rows 2, 3, 4 above), first check `memory/<workflow>/<slug>/gherkin-bindings.json` for an approved Scenario covering that behavior at the relevant public surface:

- **Scenario exists** — the proposed Story extends the matching `[Component tests]` Story rather than creating a new one. The recommendation cites `<feature-file>::<scenario-name>` and the test added in `/build` binds to that scenario in the binding mode recorded in `phase-0.md`.
- **Scenario is missing** — do NOT invent a Scenario inside a downstream Story. Pause the convergence loop and hand back to the orchestrator: the operator remains the single author of intent, and the Gherkin surface must be updated via the workflow's standard Phase-2 sign-off before this loop resumes. Do not open ad-hoc amendment Stories from inside this worker; that route would bypass the human gate and is intentionally not available here.

This keeps the approved Gherkin as the single source of intended behavior even when convergence discovers a gap. The operator stays the only author of intent.

Each recommendation lands as a new child issue on the parent (via the same CLI dispatch convention as `/issues-from-assessment`) or as a new file under `./plans/<workflow>/phase-5/`. The orchestrator then drives `/build` against each.

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
- Surviving mutants: <n> (target 0)  ·  mutation: reused <N>, measured <M>
- Determinism: <passes>/<runs> (target <runs>/<runs>)
- Wall-clock median: <sec>s (target: fastest achievable / <n>s if set)
- Largest gap: <dimension>
- Dispatched: <story title / id>
```

Same CLI pattern as `/coverage-baseline` and `/coverage-delta`.

### 7. Waiver handling

If the operator chooses to waive a target:

- Capture the reason verbatim.
- Record it in `memory/<workflow>/<slug>/waivers.json`.
- Append a `**Waived**: <target> — <reason> (<ISO-8601>)` line to the parent issue / `FEATURE.md`.

A waiver counts as "met" for the loop's exit condition but is surfaced in the orchestrator's final Report.

### 8. Report

Print:

- Current state of all four dimensions.
- Whether the loop converged, halted, or is mid-iteration.
- Any waivers recorded.
- The path to `converge-<iteration>.json` and to `waivers.json` (if any).

## Examples / Integration

- `/test-improve` invokes this worker from Phase 6 with `--workflow test-improve`; paths resolve as `memory/test-improve/<slug>/` and `./plans/test-improve/phase-6/`.
- `/test-improve` invokes this worker from Phase 6 with `--workflow test-improve`; the same template resolves with `<workflow>` = `test-improve`.

## Notes

- This worker does not write tests or edit production code. Its output is recommendations + dispatched Stories that `/build` then implements. That keeps the workflow's "every change goes through a Story with Acceptance Criteria" invariant intact.
- The 10-iteration default is a backstop, not a target. Most repos should converge in 3–5; persistent failure to converge means the dispatched actions aren't the smallest — surface the loop to the operator for a strategy decision.
- Wall-clock is measured but only gated when the operator sets a number; the spec's "fastest achievable" phrasing is reported as the trend across iterations.
- Adding a new workflow caller means passing a new `--workflow <name>` value; no path edits inside this skill are required because paths are templated.
