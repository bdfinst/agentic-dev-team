---
name: speculative-build
description: >-
  Implement one complex /build step N times in independent worktrees, screen
  and rank the candidates, and merge the winner. Reached only through
  /build --candidates N. Not user-invocable: do not run it directly.
role: orchestrator
allowed-tools: >-
  Bash(python3 *, git *)
---

# Speculative Build (#2273)

Role: orchestrator. This procedure implements one `complex` step N times, ranks the candidates with scripts, and merges the winner. `/build --candidates N` is the only entry point. The flag is experimental.

## Preconditions

`/build` runs these checks before it follows this skill:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" validate-flags --candidates=<raw> --max-cost-usd=<raw> --jobs=<raw>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_worktree_baseref.py" detect
```

This skill assumes three results:

- `validate-flags` exited 0 and printed `"speculative": true`.
- `/build` located the session transcript, the way `skills/cost-report/SKILL.md` does.
- `build_worktree_baseref.py detect` printed `head` for `worktree.baseRef`.

If any result is missing, halt with `speculative dispatch requires a session transcript, worktree.baseRef = head and validated flags; run /build, not this skill`. This skill halts when you invoke it outside `/build`.

At step start, print `speculative dispatch: step <N.M>, <N> candidates, cost cap $<X>, attempt <k>`.

## Base and batches

Set `base` to the build worktree's current commit:

```bash
git rev-parse HEAD
```

Then derive the run:

- Set attempt `k` to 1 plus the number of attempts the plan's table already records for the step.
- Number the candidates 1 to N.
- Read the Branch column of the table's earlier-attempt rows for this step, before any spend. If any of those branches still exists, print `candidate branches from attempt(s) <ks> still exist: <branches>; discard them with the cleanup command or merge one by hand`. Then continue. Stale branches use disk only; harness-named branches never collide.
- Make batch 1 candidate 1 alone, so the cost cap is checked before any second candidate.
- Size each later batch with `build_jobs.py --wave-width`. Do not pass `--jobs`. The batches are sequential unless `DEV_TEAM_MAX_PARALLEL_BUILDS` is set.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_jobs.py" --wave-width <N-1>
```

## Dispatch

Dispatch each candidate as the `software-engineer` agent, by `subagent_type`, with `isolation: "worktree"`. Use its declared frontmatter. Pass no `model:` or `effort:` override.

Use exactly the prompt that `/build` Step 4 assembles for a single dispatch ("For each step within a slice, dispatch ..."). That prompt holds the step, the slice Gherkin, the design constraint, and the authoring digest. Add these two lines:

```text
Candidate <i> of <N>; commit every green on your worktree branch
Do not write the plan file
```

Each candidate owns this state:

- Each candidate commits on its own worktree branch.
- Each candidate writes its own `.claude/memory/build-phase.json` inside its worktree, under `/build`'s standalone-dispatch fallback. The parent's record stays `implement` for the step until the winner is merged.
- When the plan opts into freeze, engage it per candidate before dispatch, against the candidate worktree's hooks dir. The freeze state leaves with the worktree.
- Only the parent writes the plan file.
- The step's rollback point is the one `/build` took before the first batch.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_slice_scope.py" engage <plan> --slice <id> --hooks-dir <candidate-worktree>/.claude/hooks
```

After each dispatch returns, read the branch name from the `branch:` line of the dispatch result. Do not infer it from a name pattern. Confirm the branch and its worktree path:

```bash
git worktree list --porcelain
```

Treat a dispatch as a no-commits candidate when it returns no `branch:` line or its branch has no commit beyond `base`. A no-commits candidate has `suite_green` false and the reason `no commits`. It is not a halt. Build its dict yourself, without `collect`. Set `T` to the scenario count of the slice's Gherkin block and `C` to its cost:

```json
{"id": <i>, "branch": "<name or empty>", "suite_green": false, "scenarios_total": T, "scenarios_unmet": T, "errors": 0, "warnings": 0, "diff_lines": 0, "cost_usd": C, "screening": "ok"}
```

## Suite and diff

Run the plan's suite command in each candidate worktree yourself. Keep its exit code. The agent's own report is advisory.

```bash
( cd <candidate-worktree> && <suite command> ); echo "suite-exit=$?"
```

Do not measure the diff by hand. `collect` counts the diff lines (see Screening).

## Screening

Screen each candidate once, after its suite run. Run two review lenses and save each output to a file:

- `/review-agent spec-compliance-review --internal --json --path <worktree> --since <base>`
- `/review-agent correctness-review --internal --json --path <worktree> --since <base>`

Then run `collect`. It builds the candidate dict from the suite exit code, the diff, and the two lens files:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" collect --id <i> --branch <branch> --worktree <worktree> --base <base> --suite-exit <exit> --spec-json <spec-json> --correctness-json <correctness-json> --plan <plan> --step <N.M> --cost-usd <cost>
```

`collect` counts a spec-compliance finding with category `uncovered-scenario` or `unmet-criterion` as an unmet scenario. It counts correctness findings by severity as errors and warnings. It marks a lens file that is missing or unparseable as `unparseable: <lens>`, and that candidate is disqualified.

The inline checkpoint on the merged winner runs the lenses `/build` would have run anyway. The winner is therefore screened again by design. The benchmark measures that cost.

## Cost cap

Read the cost meter for the session transcript:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py" report --transcript <transcript> --json
```

Use `totals.cost_usd` from its output. Take these readings:

- Read `before` just before batch 1. Also read `prev` just before every later batch dispatches.
- Read `now` immediately after the batch's dispatches return. Read it before Suite and diff and before Screening.
- Compute `delta = now - prev`. Add it to `spent`. Both values then count candidate dispatch spend only. Screening and suite runs are outside the cap.
- Give each candidate in the batch `cost_usd = delta / width`, where `width` is the batch width.

The meter is read right after the batch's dispatches return. `project` runs before every batch after the first, while candidates remain. It never runs inside a batch. One batch can therefore overrun the cap.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" project --cap <X> --spent <S> --completed <C> --remaining <R> --last-batch-delta <D>
```

Act on the `decision` it prints:

- `continue`: dispatch the next batch.
- `stop`: record every undispatched candidate as `not dispatched` with the reason `cost cap`.
- `halt`: treat it as a failure mode. The meter recorded no spend for the last batch, so the cap cannot be enforced.

Print one status line after every batch. While candidates remain:

`speculative <N.M>: batch <b> done — spent $<S> of $<X>, projected $<P>, <decision>`

After the last batch, when no candidates remain:

`speculative <N.M>: batch <b> done — spent $<S> of $<X>, no candidates remain`

A `halt` prints the Failure modes template instead.

## Rank

Write `{"candidates": [...]}` to a file. Include the dict of every dispatched candidate, with `cost_usd` filled in. Then run `rank`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" rank --candidates-json <candidates-json>
```

`rank` prints `winner`, `order`, `rank`, `disqualified`, and `reasons`. A `null` winner is a failure mode.

## Record

Write the table rows to a file as `{"rows": [...]}`, one row per candidate id. Run `record` with provisional outcomes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_summary_record.py" record --plan <plan> --step <N.M> --attempt <k> --result <rows-json>
```

Set the provisional outcomes this way:

- The winner is `kept`, with the reason `provisional (reconcile pending)`.
- Every other ranked candidate is `removed`.
- A disqualified candidate is `disqualified`. Its reason is `red suite`, `screening: <lens> unparseable`, or `no commits`. `rank` reports a no-commits candidate as `red suite`, so write `no commits` yourself.
- An undispatched candidate is `not dispatched`, with the reason `cost cap`.

`record` runs before Keep. Run it again with the same attempt after Keep, to write the final outcomes. Do not run two `record` calls at the same time on one plan file.

## Keep

Merge the winner with `reconcile`. It restores the build branch on failure:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" reconcile --repo <build-worktree> --into <build-branch> --base <base> --test-cmd "<suite>" <winner-branch>
```

Handle its exit code:

- Exit 0: the winner is merged.
- Exit 1: the winner becomes `disqualified`, with the reason `reconcile failed`. Try the next non-disqualified id in `order`, from the restored branch. If none remains, halt (see Failure modes).
- Exit 2: halt (see Failure modes) and name the pre-merge SHA in the reason.

Then run `record` again, with the final outcomes. Print:

`speculative <N.M>: kept candidate <i> (<branch>); removed <ids>; disqualified <ids>; not dispatched <ids>; spent $<S>`

## Cleanup

Do not run this section before the checkpoint. `/build` runs it after the step's inline checkpoint passes on the merged winner:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" cleanup --repo <build-worktree> --remove <every candidate branch>
```

The command is idempotent. List every candidate branch, including the kept one. The kept candidate's commits are already on the build branch. If `cleanup` fails after the checkpoint, report the remaining branches. The failure does not undo the step.

## Resume

The step continues at `/build` sub-step 4's inline checkpoint on the merged winner. That is the `complex` checkpoint. `/build` ticks Build Progress as usual.

## Failure modes

Every halt first writes the record, removes nothing, and prints the halt template.
