---
name: speculative-build
description: >-
  Implement one complex /build step N times in independent worktrees, screen
  and rank the candidates, and merge the winner. Reached only through
  /build --candidates N. Not user-invocable: do not run it directly.
role: orchestrator
allowed-tools: Bash
---

# Speculative build

Role: orchestrator. This procedure implements one `complex` step N times, ranks the candidates with scripts, and merges the winner. `/build --candidates N` is the only entry point. The flag is experimental.

## Preconditions

`/build` runs these checks before it follows this skill:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" validate-flags --candidates=<raw> --max-cost-usd=<raw> --jobs=<raw>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_worktree_baseref.py" detect
```

This skill assumes four results:

- `validate-flags` exited 0 and printed `"speculative": true`.
- `/build` located the session transcript, the way `skills/cost-report/SKILL.md` does.
- `build_worktree_baseref.py detect` printed `head` for `worktree.baseRef`.
- `/build` holds the `Agent` (or `Task`) tool.

If the `Agent` (or `Task`) tool is missing, halt before batch 1. Give the report that `/build`'s Orchestrator constraints prescribe.

If any other result is missing, halt with this message:

`speculative dispatch requires a session transcript, worktree.baseRef = head and validated flags; run /build, not this skill`

This skill halts when you invoke it outside `/build`.

## Base and batches

Run the step as a loop of batches. The sections below detail each part. For each batch:

1. Read `prev` from the cost meter.
2. Hash the plan file, dispatch the batch, then hash it again. Halt if the hashes differ.
3. Read `now`. Compute `delta = now - prev`. Add `delta` to `spent`.
4. Run the suite in each candidate worktree.
5. Screen each candidate, then run `collect`.
6. Run `project`, then dispatch the next batch. After the last batch, go to Rank.

These placeholders recur in templates and commands:

- `<X>` is the cap from `--max-cost-usd`.
- `<P>` is the projected total that `project` prints.
- `<b>` is the batch number.
- `<ks>` lists the earlier attempt numbers.

Set `base` to the build worktree's current commit:

```bash
git rev-parse HEAD
```

Then derive the run:

- Set attempt `k` to 1 plus the highest attempt number the plan's table records for the step. Use 0 when it records none.
- Number the candidates 1 to N.
- Print `speculative dispatch: step <step>, <N> candidates, cost cap $<X>, attempt <k>`. `<step>` is the plan step id. `<N>` is the candidate count.
- Read the Branch column of the table's earlier-attempt rows for this step, before any spend.
- If any of those branches still exists, print `candidate branches from attempt(s) <ks> still exist: <branches>; discard them with the cleanup command or merge one by hand`. Then continue.
- Stale branches take disk space only. Dispatch never creates a branch with one of these names.

Make batch 1 candidate 1 alone, so the cost cap is checked before any second candidate. `build_jobs.py`'s wave is this skill's batch. Size each later batch with `--wave-width`. Do not pass `--jobs`. The batches are sequential unless `DEV_TEAM_MAX_PARALLEL_BUILDS` is set.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_jobs.py" --wave-width <N-1>
```

## Dispatch

Dispatch each candidate as the `software-engineer` agent, by `subagent_type`, with `isolation: "worktree"`. Use its declared frontmatter. Pass no `model:` or `effort:` override.

Use exactly the prompt of a single dispatch in `/build` Step 4 ("For each step within a slice, dispatch ..."). That prompt holds the step, the slice Gherkin, the design constraint, and the authoring digest. Add these lines:

```text
Candidate <i> of <N>; commit every green on your worktree branch
Do not write the plan file
Before your first edit run: python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_slice_scope.py" engage '<plan>' --slice <slice-id> --hooks-dir '<your worktree>/.claude/hooks'
```

Add the third line only when `/build`'s Slice dispatch bookkeeping step 1 would engage freeze. That is when this check exits 0 and the slice declares `**Files:**`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_slice_scope.py" enabled '<plan>'
```

Each candidate owns this state:

- Each candidate commits on its own worktree branch.
- Each candidate writes its own `.claude/memory/build-phase.json` inside its worktree, under `/build`'s standalone-dispatch fallback. The parent's record stays `implement` for the step until the winner is merged.
- The freeze state, when engaged, leaves with the candidate's worktree.
- Only the parent writes the plan file.
- The step's rollback point is the one `/build` recorded before the slice's first step, if the slice declares one. This skill records none.

Hash the parent's plan file in the build worktree just before the batch dispatches. Hash it again when the batch returns:

```bash
git hash-object '<plan>'
```

If the two hashes differ, a candidate wrote the parent's plan file. Halt with the reason `plan file changed during batch <b>`.

Pair each returned result with the dispatch that produced it. Candidate `<i>` is that dispatch's id.

Read the `branch:` line of the dispatch result. Do not infer the name from a pattern. Check it against the worktree list:

```bash
git worktree list --porcelain
```

Accept the name only when it meets both rules:

- It exactly matches a `branch refs/heads/<name>` entry of `git worktree list --porcelain`.
- It matches `^[A-Za-z0-9._/][A-Za-z0-9._/-]*$`.

Take `<worktree>` from the `worktree <path>` line of that same porcelain entry. Never take it from the dispatch result.

Otherwise, treat the dispatch as a no-commits candidate. Use an empty branch when the name was rejected. Also treat it as a no-commits candidate when this count is 0:

```bash
git rev-list --count <base>..'<branch>'
```

A no-commits candidate has `suite_green` false and the reason `no commits`. It is not a halt. It skips Suite and diff and Screening. Build its dict yourself, without `collect`. Set `T` to the scenario count of the slice's Gherkin block and `<cost>` to its cost:

```json
{"id": <i>, "branch": "<name or empty>", "suite_green": false, "scenarios_total": T, "scenarios_unmet": T, "errors": 0, "warnings": 0, "diff_lines": 0, "cost_usd": <cost>, "screening": "ok"}
```

## Suite and diff

Run the plan's suite command in each candidate worktree yourself. Keep its exit code. The agent's own report is advisory. The suite command and `--plan` always come from the parent's build worktree.

```bash
( cd '<worktree>' && <suite> ); echo "suite-exit=$?"
```

Do not measure the diff by hand. `collect` counts the diff lines (see Screening).

## Screening

Screen each candidate once, after its suite run. Run two review lenses and save each output to a file:

- `/review-agent spec-compliance-review --internal --json --path '<worktree>' --since <base>`
- `/review-agent correctness-review --internal --json --path '<worktree>' --since <base>`

`--since <base>` resolves in the repository of the `--path` worktree. There, `base` is an ancestor of the candidate branch.

Then run `collect`. It builds the candidate dict from the suite exit code, the diff, and the two lens files:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" collect --id <i> --branch '<branch>' --worktree '<worktree>' --base <base> --suite-exit <exit> --spec-json <spec-json> --correctness-json <correctness-json> --plan '<plan>' --step <step> --cost-usd <cost>
```

`collect` counts a spec-compliance finding with category `uncovered-scenario` or `unmet-criterion` as an unmet scenario. It clamps the unmet count to `scenarios_total`. It counts correctness findings by severity as errors and warnings. It marks a lens file that is missing or unparseable as `unparseable: <lens>`, and that candidate is disqualified.

Check the plan file before Rank. A candidate may have edited it. This command lists the plan file if the candidate changed it:

```bash
git diff --name-only --end-of-options <base>..'<branch>' -- '<plan>'
```

Run this check in the parent's build worktree, with the repo-relative plan path. A non-zero exit is a script failure. Halt.

If the output is non-empty, keep the candidate's `collect` dict and its branch. Record it as `disqualified` with the reason `plan file edited`. Do not rank it.

The inline checkpoint on the merged winner runs the lenses `/build` would have run anyway. The winner is therefore screened again by design. The benchmark measures that cost.

## Cost cap

Read the cost meter for the session transcript:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/cost_meter.py" report --transcript <transcript> --json
```

Use `totals.cost_usd` from its output. Take these readings:

- Set `spent` to 0 before batch 1.
- Read `prev` just before every batch dispatches, including batch 1.
- Read `now` immediately after the batch's dispatches return, before Suite and diff and before Screening.
- Compute `delta = now - prev`.
- Add it to `spent`.
- `delta` and `spent` count candidate dispatch spend only. Suite runs and screening are outside the cap.
- Give each candidate in the batch `cost_usd = delta / width`. `width` is the number of candidates actually dispatched in that batch.

`project` runs before every batch after the first, while candidates remain. It never runs inside a batch. One batch can therefore overrun the cap. Set its placeholders as follows:

- `<S>` is `spent`.
- `<C>` is the number of candidates dispatched so far, including no-commits ones.
- `<R>` is N - C.
- `<D>` is the last batch's `delta`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" project --cap <X> --spent <S> --completed <C> --remaining <R> --last-batch-delta <D>
```

Act on the `decision` it prints:

- `continue`: dispatch the next batch.
- `stop`: record every undispatched candidate as `not dispatched` with the reason `cost cap`.
- `halt`: treat it as a failure mode. The meter recorded no spend for the last batch, so the cap cannot be enforced.

Print one status line after every batch. While candidates remain:

`speculative <step>: batch <b> done — spent $<S> of $<X>, projected $<P>, <decision>`

After the last batch, when no candidates remain:

`speculative <step>: batch <b> done — spent $<S> of $<X>, no candidates remain`

A `halt` prints the Failure modes template instead.

## Rank

Write `{"candidates": [...]}` to a file. Include the dict of every dispatched candidate, with `cost_usd` filled in. Leave out candidates that edited the plan file. They are recorded, not ranked.

If no candidate is left to rank, treat it as a `null` winner. Do not run `rank`. Otherwise, run `rank`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" rank --candidates-json <candidates-json>
```

`rank` prints `winner`, `order`, `rank`, `scenarios_met`, `disqualified`, and `reasons`. A `null` winner is a failure mode.

## Record

Write the table rows to a file as `{"rows": [...]}`, one row per candidate id. Each row is the candidate dict plus `rank`, `outcome`, and `reason`. Take `rank[<i>]` from the output of `rank`. Give a plan-file-edited candidate a rank after the last ranked one, in id order. A `not dispatched` row carries only `id`, `outcome`, and `reason`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan_summary_record.py" record --plan '<plan>' --step <step> --attempt <k> --result <rows-json>
```

Set the provisional outcomes this way:

- The winner is `kept`, with the reason `provisional (reconcile pending)`.
- Every other non-disqualified ranked candidate is `removed`. `removed` means the candidate is not kept. Its branch stays until Cleanup.
- A disqualified candidate is `disqualified`. Its reason is `reasons[<i>]` from the output of `rank`.
- A no-commits candidate and a plan-file-edited candidate are `disqualified`.
- Write the reason yourself for a no-commits candidate (`no commits`) and for a plan-file-edited candidate (`plan file edited`).
- An undispatched candidate is `not dispatched`, with the reason `cost cap`.

`record` runs before Keep. Run it again with the same attempt after Keep, to write the final outcomes. Do not run two `record` calls at the same time on one plan file.

## Keep

Merge the winner with `reconcile`. It restores the build branch on failure. Write an embedded `'` in `<suite>` as `'\''`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" reconcile --repo '<build-worktree>' --into '<build-branch>' --base <base> --test-cmd='<suite>' -- '<winner-branch>'
```

Handle its exit code:

- Exit 0: the winner is merged.
- Exit 1 with `"merged": false` in the JSON on stdout: the winner becomes `disqualified`, with the reason `reconcile failed`. Try the next non-disqualified id in `order`, from the restored branch. If none remains, halt (see Failure modes).
- Exit 2 with the pre-merge SHA named on stderr: the restore failed. Halt (see Failure modes) and name the SHA in the reason.
- Exit 1 without that JSON, exit 2 without that SHA, or any other non-zero exit: the script failed. Halt (see Failure modes).

When Keep halts, the candidate whose merge was in progress is `disqualified`, with the reason `reconcile halted: <halt reason>`. The halt template names its branch to merge by hand.

After Keep, `winner` means the candidate that `reconcile` merged.

After exit 0, rewrite the parent's `.claude/memory/build-phase.json` for the step with `phase: refactor`. Use the shape of `/build`'s Phase-state bookkeeping. This lets the tests-frozen guards cover the checkpoint's fix loop.

Fill `test_files_staged` with the step's test files, as `/build`'s TEST → REFACTOR transition does. List the files the merge changed in the build worktree:

```bash
git diff --name-only <base>..HEAD
```

Keep the test files. Run `git add` on them. Record their paths:

```bash
git add -- '<test file>'
```

```json
{"phase": "refactor", "step": "<step>", "written_at": "<ISO8601>", "test_files_staged": ["<test file>", "..."], "plan_path": "<repo-relative path of the plan file>"}
```

Then run `record` again, with the final outcomes:

- The merged candidate is `kept`, with an empty reason.
- Each candidate that failed to reconcile is `disqualified`, with the reason `reconcile failed`.
- Every other row is unchanged.

A halt's record carries these final outcomes for every row. No provisional row survives a halt.

Print:

`speculative <step>: kept candidate <i> (<branch>); removed <ids>; disqualified <ids>; not dispatched <ids>; spent $<S>`

## Cleanup

Do not run this section before the checkpoint. `/build` runs it after the step's inline checkpoint passes on the merged winner:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_candidates.py" cleanup --repo '<build-worktree>' --remove '<branch-1>' '<branch-2>'
```

List every accepted candidate branch, including the kept one. Its commits are already on the build branch. The command is idempotent. If `cleanup` fails after the checkpoint, report the remaining branches. The failure does not undo the step.

## Resume

The step continues at `/build` sub-step 4's inline checkpoint on the merged winner. That is the `complex` checkpoint. `/build` ticks Build Progress as usual.

## Failure modes

Every halt first writes the record, removes nothing, and prints the halt template.
