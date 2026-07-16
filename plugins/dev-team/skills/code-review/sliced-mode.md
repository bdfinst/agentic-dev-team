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

_(Authored in Slice 2.)_

## Persist-and-drop and the progress ledger

_(Authored in Slice 3.)_

## Resuming an interrupted run

_(Authored in Slice 4.)_

## Consolidation

_(Authored in Slice 5.)_
