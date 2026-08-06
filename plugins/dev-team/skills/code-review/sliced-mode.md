# Sliced large-repo review

Orchestration reference for `/code-review`'s large-repo path. `SKILL.md` routes
here when sliced mode engages (see its Scope-validation step); the deterministic
work is done by `scripts/partition.py`, `scripts/activation.py`,
`scripts/ledger.py`, and `scripts/consolidate.py` — all unit-tested
(partition/activation/consolidate as pure functions; ledger against a temp root).

The design keeps orchestrator context **flat regardless of repo size**: each
slice is reviewed, its findings persisted to disk, and then dropped from context
— only a one-line tally is retained. A final consolidation pass reads the
persisted artifacts back and produces one deduplicated report.

## Terminology

**Slice** and **section** are the same unit. A *slice* is the in-flight review
unit; its persisted artifact on disk is `raw/section-<id>.json`, where `<id>` is
the slice id. An operator inspecting `.dev-team-reports/code-review/raw/` needs no
mental remapping — `section-<id>.json` is slice `<id>`.

## When sliced mode engages (activation)

Call `scripts/activation.py` → `should_slice(scope_kind, file_count, threshold,
slice_flag, no_slice_flag)`. It returns `(engage, cap)` with this precedence:

1. **`--no-slice`** always wins — never slice (legacy single pass).
2. **`--slice <N>`** always engages, cap `N` (a positive integer), at any size.
3. **Auto-engage** only when scope is full-repo **and** `file_count > threshold`
   (the existing `>500` tier). Exactly at the threshold does not engage.
4. Otherwise do not slice.

Non-full-repo scopes (`--path`, `--since`, auto-scoped uncommitted changes)
never auto-engage — they run the legacy path unchanged, no matter how many files
match.

On engagement, report the slice count to the operator (e.g. `Sliced mode: N
slices`).

## Partitioning

Call `scripts/partition.py` → `partition_files(files, cap)`. Files are grouped by
directory (module boundary); a directory larger than `cap` splits across
consecutive slices; small sibling directories coalesce up to `cap`. Slice ids are
stable and deterministic — the same file set always partitions into the same ids
mapped to the same files, which is what makes `--resume` (below) safe.

After partitioning, call `activation.check_slice_ceiling(slice_count)`. When the
count is very high it returns an advisory warning suggesting a larger `--slice`
cap; report it and proceed (it never blocks).

## Per-slice review panel

Select each slice's review panel from its `is_declarative` flag (set by
`partition.py` → `is_declarative_slice`, a conservative name/extension
heuristic — any doubt yields non-declarative):

- **Declarative slice** (`is_declarative: true` — pure interface/type/DTO/
  constant/model/schema/enum files, no behavioral tokens): run the **reduced
  panel** — `correctness-review` and `structure-review` only. The six-lens
  semantic panel is wasted on declaration files.
- **Non-declarative slice**: run the **full panel** — the standard agent
  eligibility rules from `SKILL.md` steps 3–4 (self-declared `Scope:`,
  framework reactivity lens, ai-provenance), scoped to the slice's files.

The exact declarative rule is owned by `partition.py`; this file does not
re-encode it. **Disclose the panel per slice**: record which panel ran in the
slice's section artifact (see the next section), and the consolidated report
names the slices that ran the reduced panel so a reader can tell "fewer
findings" from "fewer reviewers ran."

**Wave-bound the panel dispatch (issue #1762).** Before dispatching either
panel (reduced or full), compute its wave split via `dispatch_waves.py` —
the same `maxParallel` resolution the legacy path uses
(`DEV_TEAM_MAX_PARALLEL_REVIEW_AGENTS`, default 10; see `SKILL.md` Step 4):

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/dispatch_waves.py" --agents "<this slice's panel agent names, in order>"
```

Dispatch one wave at a time, waiting for each wave to fully return before
dispatching the next — same discipline as the legacy path. A reduced panel
(2 agents) never exceeds a single wave at the default cap; a full panel can,
on a slice with many eligible lens/framework agents.

## Persist-and-drop and the progress ledger

At the start of a sliced run, initialize the ledger from the partitioned slices:
`scripts/ledger.py` → `init_ledger(slices, cap, root)` writes
`.dev-team-reports/code-review/ledger.json` with every slice `pending` and the
partition cap recorded.

Review slices in **bounded parallelism — 2–3 slices at a time** (not the whole
repo at once). This slice-level concurrency heuristic is unchanged by the
panel-level wave cap above — the two bound different things: how many slices
are in flight at once, versus how many agents one slice's own panel dispatches
in a single message.

For each slice, once its panel's waves (per the section above) return:

1. **Reconcile dispatched vs. returned, per wave**: use `dispatch_reconcile.py`
   — the same CLI as the legacy path (`SKILL.md` Step 4), scoped to this
   slice's dispatched agents for that wave:
   ```bash
   sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/dispatch_reconcile.py" --dispatched "<this wave's dispatched agent names>" --returned "<this wave's contract-valid agent names>"
   ```
   Every name in the resulting `"missing"` array is a dispatch failure for
   this slice's current wave.
2. **Retry once per agent**: retry each missing agent exactly once,
   individually — same policy as `SKILL.md` Step 4, see there for rationale.
   A recovered dispatch (fails once, retry succeeds) writes an empty
   `dispatchFailures` list and emits no boundary event, mirroring the legacy
   path's own guarantee. **Accumulate unrecovered failures across every wave
   of this slice's panel** (a panel can span more than one wave when it's
   larger than `maxParallel` — see the section above): a wave-1 failure is
   never dropped just because wave 2 returned cleanly — carry the running
   list forward and pass the union to step 3, once, after the slice's last
   wave returns.
3. **Persist** its findings: `write_section`'s CLI (`ledger.py write-section`)
   writes `raw/section-<id>.json` (findings + the panel that ran) and flips
   the slice's ledger status to `done`. Pass `--dispatch-failures` with the
   slice's still-unrecovered failures, accumulated across all its waves —
   an empty list (or the flag omitted) when every agent recovered on retry.
   Each entry has the same shape as the legacy path's `dispatchFailures`
   entries (`output-format.md`): `{"agentName": "<name>", "attempts": 2,
   "error": "<message>"}` — never a different key for the agent name.
4. **Emit the boundary event for each unrecovered failure**: at the same
   moment step 3 records the failure, emit the `dispatch-failure` boundary
   event (Slice 1's shared CLI), bound to the `subject_hash` in effect for
   that slice's dispatch (the cosmetic-delta carry-forward lens this used to
   also bind a normalized hash for was specific to the retired commit-time
   gate and was deleted in #1904 — sliced mode never wrote that gate file to
   begin with, so the normalized hash never had a consumer on this path):
   ```bash
   HASH=$(python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/review_gate_hash.py")
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/lib/boundary_events.py" --event dispatch-failure --agent "<name>" --subject-hash "$HASH"
   ```
5. **Drop** the findings from orchestrator context. **Retain only a one-line tally per slice** — e.g. `section-0001: 3 findings (1 error, 2 warnings)`. This
   is the move that keeps context flat regardless of repo size: never hold more
   than the tallies plus the slices currently in flight.
6. **Report progress**: emit `slice k of N done` as each slice completes, so a
   long monorepo run is observably advancing.

If the run is interrupted, the ledger and the already-written section artifacts
remain on disk and stay valid. Tell the operator the review is incomplete and
can be continued: **rerun with `--resume`** to review only the remaining slices.

## Resuming an interrupted run

When `--resume` is given, do **not** re-initialize the ledger. Instead:

1. **Guard the cap**: call `ledger.py` → `check_resume_cap(root, cap)`. If the
   `--slice` cap differs from the cap the interrupted run recorded in the
   ledger, **stop with that error** — repartitioning at a different cap would
   desync the new slice ids from the `section-<id>.json` files already on disk.
   Rerun with the recorded cap (or no `--slice`), or start fresh.
2. **Review only the pending slices**: `pending_slices(slices, root)` returns
   the slices needing (re-)review. A slice whose `section-<id>.json` does not
   yet exist is pending, same as before — **and, as of issue #1762, a slice
   whose artifact already exists but carries a non-empty `dispatchFailures`
   list is also pending**: it is **not** treated as done on `--resume`; its
   panel is re-dispatched, same as a slice with no artifact at all, so the
   previously-failed agent(s) get a real chance to produce a superseding
   result, per the retry-once policy in `SKILL.md`'s "Dispatch failure
   handling" (Step 4) — see there for the full mechanics, not restated here.
   Every other slice keeps today's rule unchanged: an artifact
   exists with an empty `dispatchFailures` list is skipped and reused as-is
   — disk is the source of truth (a slice with a clean artifact is done even
   if the ledger still says `pending`).
3. Consolidation (below) reads **all** section artifacts — the ones reused from
   the prior run and the ones this resume produced.

Without `--resume`, a fresh sliced run re-initializes the ledger and reviews
every slice.

## Consolidation

Once every slice has a section artifact (a fresh run's full set, or a
`--resume` run's reused + newly-written set), consolidate:

1. Run `scripts/consolidate.py` (its `main()` reads every
   `raw/section-*.json`) → the consolidated aggregate (schema in
   [`output-format.md`](output-format.md#consolidated-aggregate-sliced-mode)):
   findings **deduped by `file:line`** with reporting agents merged, a
   **recurring-theme rollup** (dimensions recurring across ≥2 slices), and the
   `reducedPanelSlices` disclosure. A malformed artifact is reported by name,
   never silently dropped.
2. Apply `ACCEPTED-RISKS.md` at this consolidation step exactly as the
   legacy path does (SKILL.md step 5a) — suppression happens once, over the
   merged findings.

**Report-only.** Sliced mode does **not** run the interactive review-fix loop.
It is a reporting/consolidation pass:

- Write the consolidated prose report to `.dev-team-reports/code-review.md` and
  per-issue correction prompts to `./corrections/` (for `/apply-fixes` to act
  on later). Both paths are repo-relative to the target repo's working
  directory.
- In `--json` mode, emit the single consolidated aggregate object to **stdout**
  and write **no** file — the existing `--json` contract (SKILL.md step 7),
  now carrying the consolidated `topFindings` / `recurringThemes` /
  `reducedPanelSlices`.
