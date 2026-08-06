Capture the objective starting point **before any file under the stack's test
directory is modified**. Baselines are the ground truth every downstream delta
compares against; running any test edit before baseline capture invalidates
the whole run.

**Coverage baseline.** Invoke `/coverage-baseline --workflow test-improve`
against the resolved repo path. `/coverage-baseline` owns its own
existing-baseline guard and persist step — see `../../coverage-baseline/SKILL.md`'s
"Existing-baseline guard" and "Persist the baseline" steps for the full
mechanics. The result lands directly and atomically at
`.dev-team-reports/test-improve/<slug>/data/baseline-coverage.json`; there is
no `.claude/memory/` write and no later copy step for this file — that skill
has no opt-in awareness of its own, and this write is **unconditional**.

This is independent of the mutation mode: a coverage baseline is persisted in
every mode, and the mutation baseline is written **only** in
`baseline+kill-loop` mode (see below).

**Coverage-gap ranking — the targeting input for Phases 1, 4, and 5 (issue
#1786).** As soon as `baseline-coverage.json` lands, compute the per-module
uncovered-line breakdown from the same report the baseline was parsed from
(its `raw_report` field). This runs in **every mutation mode** — it is the
coverage targeting input, independent of whether mutation work happens at
all — and it is computed by script, never estimated in prose:

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_gap_ranking.py" \
  --report <baseline raw_report> --repo-root <repo-path> \
  --target-line-pct <line target> --target-branch-pct <branch target> \
  --top 0 --json \
  --out .dev-team-reports/test-improve/<slug>/data/coverage-gap-ranking.json
```

Always pass `--repo-root <repo-path>`: several coverage writers (istanbul/nyc
`coverage-final.json` among them) emit **absolute** source paths, and without a
root to strip they would all bucket together — one module makes the seam
classification a single global comparison, so the check silently stops
discriminating. The script derives the shared path prefix itself as a fallback,
and flags `grouping_degenerate: true` whenever many files still land in one
bucket; treat that flag as "the ranking could not resolve modules", never as a
verdict.

The script buckets every source file into a package/assembly/module and ranks
the buckets by **uncovered lines descending**, marking each bucket's `seam`
as `established` (coverage at or above the seam threshold — a test-only change
is proven to reach it) or `absent` (near-zero coverage — nothing there is
proven reachable without a production-code seam). `--out` writes the payload
atomically (temp-file-then-rename), so `coverage-gap-ranking.json` lands in
the same git-tracked `data/` sibling as the baselines and is read directly
from there by Phase 1, Phase 4, and Phase 5.

**Mutation survivors are not an input to this ranking, and must not become
one.** A surviving mutant can only exist on a line a test already executes, so
a survivor-ordered priority list structurally *excludes* the 0%-covered layers
that hold most of the missing coverage. That is the failure this ranking
exists to prevent: a Pass-1 run spent its entire Phase 5 adding mutation-kill
assertions to layers already at 88-95% line coverage while the layer holding
~93% of the lines needed to reach the coverage target sat at 0-11% and was
never targeted.

**A deferred Phase-0 conflict check resolves here (issue #1787).** When
`phase-0.md` recorded `coverage_target_conflict: deferred` (no coverage report
was discoverable at Phase 0), *this* invocation is that check — now with real
numbers. A `verdict` of `unreachable_without_seams` (exit 3) surfaces the same
explicit choice Phase 0 defines, **before Phase 1 runs**, with one letter
changed: **`[w] waive the target / [s] stop and re-run in refactor-allowed mode
/ [c] continue as-is`**. Phase-0 answers are **immutable** for the rest of the
run, so `[s]` here **stops the run** and tells the operator to re-invoke
`/test-improve <repo-path>` choosing `refactor-allowed` — it must **never
rewrite `refactor-mode`** in `phase-0.md` mid-run. Record the outcome in
`phase-2.md`. A **non-interactive** run at this point follows Phase 0's rule
unchanged: record `coverage_target_conflict: unresolved` in `phase-2.md`, print
the same three options, and continue to Phase 1 — it never auto-stops and never
auto-waives, and Phase 8 restates the unresolved conflict.

**A missing or unparseable report is not a clean ranking.** **Exit 2** means
the script found nothing to rank (report absent, unrecognized, or parsed to
zero coverage records) — never an all-clear. Name the report path it tried and
resolve it (re-run `/coverage-baseline`, or point `--report` at the artifact
the coverage tool actually emitted) before Phase 1 runs. **Do not proceed with
mutation survivors as a stand-in ordering.**

**Mutation baseline (`baseline+kill-loop` only).** When `phase-0.md` recorded
mutation mode **`baseline+kill-loop`**, check for an existing tracked baseline
before invoking `/mutation-testing --baseline` — this is Phase 2's own
existing-baseline guard for `baseline-mutation.json`, needed here (unlike the
coverage case) because `/mutation-testing` owns no persistence of its own: it
has no `--baseline`-specific write path of its own to guard. This
existing-baseline guard is this phase's application of the shared
existing-tracked-artifact re-capture guard — the canonical definition and
rationale live once in `knowledge/decision-defaults.md`'s "Re-capture: keep
vs. overwrite an existing tracked artifact" axis; applied here:

- **No existing file, or overwrite chosen** — invoke `/mutation-testing --baseline --workflow test-improve` and persist the result (below).
- **Existing file, interactive session** — prompt keep/overwrite (default keep). An answer that is neither "keep" nor "overwrite" (case-insensitive) re-prompts with the identical choice — never falls back silently to either option, no retry limit, no timeout.
- **Existing file, non-interactive** (no usable TTY, or `DEV_TEAM_AUTO_APPROVE=1`) — keep the existing baseline automatically; both log the auto-decision and echo it to Phase 2's own progress output, naming the reused baseline's `captured_at` — reporting parity with the coverage-baseline case, not a silent reuse.
- **Existing file is malformed or corrupt** (fails to parse as JSON — e.g. left over from a prior interrupted write) — treat it as absent, never as a baseline to keep. Emit a warning naming why a fresh capture is happening, then invoke `/mutation-testing --baseline --workflow test-improve`.
- **On keep** — do not invoke `/mutation-testing --baseline`; reuse the existing file's fields and report its `captured_at` instead of a freshly captured timestamp.

Persist a freshly captured result directly and atomically (temp-file-then-rename:
write to `<path>.tmp` then `mv -f <path>.tmp <path>`) to
`.dev-team-reports/test-improve/<slug>/data/baseline-mutation.json` — never a
direct, non-atomic write. The file records the **honest score**: hard kills /
effective total, with the **timeout count reported separately** (timeouts are
not counted as kills).

**No-baseline modes skip (`off` and `kill-loop`).** When `phase-0.md` recorded
mutation mode **`off`** or **`kill-loop`**, `/mutation-testing --baseline` is
**not invoked** and no `baseline-mutation.json` is written — `kill-loop` runs the
mutant-kill loop in Phase 5 but takes no baseline first. For `off`, the Phase-8
mutation target is later marked "not enabled", not waived; for `kill-loop`,
Phase 8 reports the final-survivor count rather than a baseline delta (see
Phase 8).

**Go advisory marker.** When the resolved stack is Go and mutation mode is
`baseline+kill-loop`, the
mutation baseline is **advisory only** — go-mutesting is alpha-quality (see the
Go advisory in Phase 0). `baseline-mutation.json` is written with the
`advisory-only: true` marker; survivor counts are not a gate.

**Ordering invariant.** Baselines land **before any test file is modified** — no file under the stack's test directory may change between Phase 0 and the creation of `baseline-coverage.json` (and `baseline-mutation.json` when applicable). Phase 3, Phase 5, and any subsequent test edits depend on this ordering.
