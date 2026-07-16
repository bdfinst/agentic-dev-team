# Sliced large-repo review

Orchestration reference for `/code-review`'s large-repo path. `SKILL.md` routes
here when sliced mode engages (see its Scope-validation step); the deterministic
work is done by `scripts/partition.py`, `scripts/activation.py`,
`scripts/ledger.py`, and `scripts/consolidate.py`, all pure-function-tested.

The design keeps orchestrator context **flat regardless of repo size**: each
slice is reviewed, its findings persisted to disk, and then dropped from context
— only a one-line tally is retained. A final consolidation pass reads the
persisted artifacts back and produces one deduplicated report.

## Terminology

**Slice** and **section** are the same unit. A *slice* is the in-flight review
unit; its persisted artifact on disk is `raw/section-<id>.json`, where `<id>` is
the slice id. An operator inspecting `DEV_TEAM_REPORTS/code-review/raw/` needs no
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

<!-- The sections below are filled by later slices: per-slice panel selection
     (Slice 2), persist-and-drop + ledger (Slice 3), resume (Slice 4), and
     consolidation (Slice 5). -->

## Per-slice review panel

Select each slice's review panel from its `is_declarative` flag (set by
`partition.py` → `is_declarative_slice`, a conservative name/extension
heuristic — any doubt yields non-declarative):

- **Declarative slice** (`is_declarative: true` — pure interface/type/DTO/
  constant/model/schema/enum files, no behavioral tokens): run the **reduced
  panel** — `correctness-review` and `structure-review` only. The six-lens
  semantic panel is wasted on declaration files.
- **Non-declarative slice**: run the **full panel** — the standard agent
  eligibility rules from `SKILL.md` steps 3–4 (self-declared `scope:`,
  framework reactivity lens, ai-provenance), scoped to the slice's files.

The exact declarative rule is owned by `partition.py`; this file does not
re-encode it. **Disclose the panel per slice**: record which panel ran in the
slice's section artifact (see the next section), and the consolidated report
names the slices that ran the reduced panel so a reader can tell "fewer
findings" from "fewer reviewers ran."

## Persist-and-drop and the progress ledger

At the start of a sliced run, initialize the ledger from the partitioned slices:
`scripts/ledger.py` → `init_ledger(slices, cap, root)` writes
`DEV_TEAM_REPORTS/code-review/ledger.json` with every slice `pending` and the
partition cap recorded.

Review slices in **bounded parallelism — 2–3 slices at a time** (not the whole
repo at once). For each slice, once its panel (per the section above) completes:

1. **Persist** its findings: `write_section(slice, findings, panel, root)` writes
   `raw/section-<id>.json` (findings + the panel that ran) and flips the slice's
   ledger status to `done`.
2. **Drop** the findings from orchestrator context. **Retain only a one-line tally per slice** — e.g. `section-0001: 3 findings (1 error, 2 warnings)`. This
   is the move that keeps context flat regardless of repo size: never hold more
   than the tallies plus the slices currently in flight.
3. **Report progress**: emit `slice k of N done` as each slice completes, so a
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
2. **Review only the pending slices**: `pending_slices(slices, root)` returns the
   slices whose `section-<id>.json` does **not** yet exist. Slices whose artifact
   already exists are skipped and reused as-is — disk is the source of truth
   (a slice with an artifact is done even if the ledger still says `pending`).
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

- Write the consolidated prose report to `DEV_TEAM_REPORTS/code-review.md` and
  per-issue correction prompts to `./corrections/` (for `/apply-fixes` to act
  on later). Both paths are repo-relative to the target repo's working
  directory.
- In `--json` mode, emit the single consolidated aggregate object to **stdout**
  and write **no** file — the existing `--json` contract (SKILL.md step 7),
  now carrying the consolidated `topFindings` / `recurringThemes` /
  `reducedPanelSlices`.
