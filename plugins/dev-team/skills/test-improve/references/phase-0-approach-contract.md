Resolve every ambiguous input in **one batch** before any work starts, then
persist the resolved inputs to `.claude/memory/test-improve/<slug>/phase-0.md`. The
file must exist **before Phase 1** runs.

**Detect language(s) and stack profile.** Inspect manifests for JS/TS
(`package.json`), Java (`pom.xml` / `build.gradle`), C# (`*.csproj`), and Go
(`go.mod`). If `--stack` was passed, honor it. Record the resolved stack in
`phase-0.md`.

**Go advisory (shown before the mutation prompt when Go is detected).**

> Mutation testing on Go uses **go-mutesting**, which is **alpha**-quality.
> Survivor count is **not a gate** on Go — treat it as advisory. For real
> confidence in Go tests, prefer `go test -fuzz` on the parts of the code
> that reward it. In `baseline+kill-loop` mode the orchestrator records
> baseline and delta numbers; in `kill-loop` it records only the final
> surviving-mutant count. Either way the Phase-8 mutation target is
> advisory-only for Go.

**Prompt battery (one batch, six knobs).** Each prompt displays its default in
`[brackets]`; pressing **Enter accepts every default in one keystroke** — with
**one deliberate exception**: knob 6 (code-lookup install) is **not** part of the
Enter-accepts-all gesture, because accepting it mutates the filesystem (and, for
Graphify, the repo's `CLAUDE.md`). Knob 6 is the **sole** exception; it requires an
explicit `y`/`n` and a blank response **re-prompts** rather than defaulting either
way. This is called out in the knob-6 prompt itself so the divergence is never a
silent surprise.

1. **Mutation mode** — `[kill-loop]`. A three-way choice; the value recorded in
   `phase-0.md` and shown in the banner is the canonical token (`off` /
   `kill-loop` / `baseline+kill-loop`), used verbatim in both places:
   - `off` — no mutation testing (lightweight ceremony).
   - `kill-loop` (**default**) — run the mutant-kill loop and produce a final
     report of surviving mutants, **without** a separate baseline run first.
   - `baseline+kill-loop` — run the mutation baseline first, then the mutant-kill
     loop (a before/after mutation delta).

   **Default change — mutation now runs by default.** The old knob defaulted to
   `off` (no mutation work on Enter-through); under `kill-loop` an Enter-through
   run **now performs the mutant-kill loop**. The prompt flags this so it is
   never a silent surprise.
2. **BDD rubric** — five yes/no questions from
   `knowledge/references/bdd-value-guide.md`. **Default `none`** if the
   operator declines to answer. Scoring: ≥3 yes → `bdd-runner` recommended;
   1–2 yes → `xunit-with-annotations` recommended; 0 yes → `none`.
3. **Refactor mode** — `[no-refactor]`. Default is **`no-refactor`**. Choose
   `refactor-allowed` to permit production-code changes in Phase 7 (seams
   only; existing tests may not be modified or removed).
4. **Quality targets** — defaults: coverage ≥ 90% line + branch; surviving
   mutants = 0 (only when mutation mode is not `off`); determinism = 100%; wall-clock =
   fastest achievable. Any target can be overridden here; overrides land in
   `phase-0.md` and flow into Phase 8.
5. **Sink** — `--parent <url>` selects a tracker (ADO / GitHub / GitLab /
   Jira via the host CLI); missing CLI or omitted flag falls back to
   **local-files** mode (writes under `.dev-team-reports/test-improve/` and
   `.claude/plans/test-improve/`).
6. **Code-lookup tools (all-or-none install)** — offer to install the three
   code-lookup tools (**CodeGraph**, **Repowise**, **Graphify**) so the review
   and analysis agents read verified skeletons and resolved call graphs instead
   of re-reading whole files. **Recommended: yes** when any of the three is
   missing. This knob is an **explicit `y`/`n`** (see the Enter-accepts-all
   exception above); a blank answer re-prompts. The prompt names the three tools
   and discloses that Graphify writes a `## graphify` section into this repo's
   `CLAUDE.md` and installs git hooks.
   - **Idempotent / missing-subset.** Detect which of the three are already
     present; offer only the **missing** subset. When all three are present,
     do not prompt — record `code_lookup_tools: already present`.
   - **Delegate the install — never reimplement it.** On `y`, delegate to
     `/project-init`'s Step 4c graph-tools group (the canonical installer); do
     not duplicate install commands or probes here.
   - **Decline is visibly confirmed.** On `n`, install nothing and print
     `Code-lookup tools: skipped — agents fall back to Read/Grep/Glob.`
   - **Partial failure is recorded, not masked.** If the delegated install
     partially fails, record per-tool success/failure in `phase-0.md` and do
     not claim full install success.

**Coverage-target vs refactor-mode conflict check (issue #1787).** A stated
coverage percentage (**knob 4**) and `refactor-mode: no-refactor` (**knob 3**)
can be structurally incompatible, and Pass 1 held both at once without ever
saying so: mutation-kill work cannot raise line or branch coverage on code that
has no tests at all, and a layer at near-zero coverage generally needs a
production-code seam before any test can reach it. Resolve this **before** any
work starts — **never by waiving a gate later**, which is what happened when
branch-90 was quietly waived at a later gate while coverage-90 stayed a stated
goal to the end.

Run the check; do not judge it in prose:

```
sh "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/coverage_gap_ranking.py" \
  --report <existing coverage report> --repo-root <repo-path> \
  --target-line-pct <line target> --target-branch-pct <branch target> --json
```

- **A coverage report is discoverable** — a prior run's
  `.dev-team-reports/test-improve/<slug>/data/baseline-coverage.json`'s
  `raw_report`, or a report artifact already on disk (`lcov.info`,
  `coverage.json`, `cobertura.xml`, `jacoco.csv`, `coverage-summary.json`).
  The script's `verdict` decides:
  - **`unreachable_without_seams` (exit 3)** — the target cannot be reached even
    if every module that already has a test seam went to 100%. Present the
    explicit three-way choice **`[w] waive the target / [s] switch to
    refactor-allowed / [c] continue as-is`** (shape `[w/s/c]`), naming the
    script's own numbers — `lines_needed`, `reachable_uncovered_lines`, and the
    top seam-blocked modules — so the operator sees the arithmetic, not an
    opinion. `[w]` records the target as **waived at Phase 0** with this reason
    (Phase 8 then reports it waived up front instead of discovering it); `[s]`
    records `refactor-mode: refactor-allowed` (Phase 0 is still resolving its
    own answers here, so this is not an immutability exception); `[c]` proceeds
    with `coverage_target_conflict: acknowledged` recorded. A **non-interactive**
    run **does not silently pick a stance** — it records
    `coverage_target_conflict: unresolved`, prints the same three options, and
    the conflict is restated at Phase 8 rather than resolved by default.
  - **`reachable` / `already_met` (exit 0)** — record
    `coverage_target_conflict: none` and continue.
- **No coverage report is discoverable** — do **not** fabricate a verdict from
  no data. Record `coverage_target_conflict: deferred` and run this identical
  check at Phase 2 against the freshly captured baseline, **before** Phase 1
  consumes the ranking (see the coverage-gap ranking step in
  `phase-2-baseline.md`). Deferred means
  *checked one phase later against real numbers* — never dropped, and never
  first surfaced in the Phase-9 report.

This check is skipped entirely when knob 4 left no coverage percentage target
active, or when knob 3 selected `refactor-allowed` (there is no mode conflict
to surface).

**Persistence.** Write the resolved inputs to `.claude/memory/test-improve/<slug>/phase-0.md` before Phase 1 runs — Phase 1 must not start until `phase-0.md` exists. This includes the knob-6 outcome (the operator's install choice, and for each tool whether it was already present, installed, declined, or failed).

**Immutability.** Phase-0 answers are **immutable** for the remainder of the
run. `--from-phase` does not re-prompt Phase-0 inputs. To change them, delete
`.claude/memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.

**`--analyze-only` semantics.** With `--analyze-only`, Phase 0 completes as
normal, Phase 1 (`/test-health`) runs, and the orchestrator **exits after Phase 1**
with a summary of the improvement plan. This is a deliberate carve-out:
Phase 1 runs **directly**, bypassing the default Baseline (Phase 2) / Derive
Gherkin (Phase 3) ordering (`0 → 2 → 3 → 1 → 4 → ...`) — not a contradiction
of it. No baseline is captured; no code changes.

**`--from-phase` semantics.** `--from-phase <n>` resumes **at** phase `n` and
skips every phase that precedes `n` in the **execution** sequence
`0, 2, 3, 1, 4, 5, 6, 7, 8, 9` (not identity order — e.g. `--from-phase 1`
skips Phases 0, 2, and 3, not just 0). Phase-0 inputs are read from
`phase-0.md` (never re-prompted). **An explicit `<n>` is not validated
against this sequence** beyond requiring `phase-0.md` to exist — e.g.
`--from-phase 1` does not check that Phase 2 (Baseline) has actually run
first, so an operator passing an out-of-sequence `<n>` by hand can skip a
phase whose output later phases depend on (Baseline before any test-file
change, in particular). Prefer `--from-phase` with no number
(auto-detect, below) unless there's a specific reason to name a phase
explicitly.

**`--from-phase` with no number — auto-detect the resume point.** When
`--from-phase` is passed **without** a number, resolve the resume phase by
calling the helper — do **not** infer it in prose:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_improve_resume.py" <repo-path>
```

The helper resolves the slug from `<repo-path>` (its last path segment), scans
**only** that slug's `.claude/memory/test-improve/<slug>/` directory for the
completed-phase progress files (`phase-0.md` … `phase-9.md`, excluding
`phase-3.md` — Phase 3 is conditional and tracked via `gherkin.md` instead,
never a numbered progress file), finds the highest completed phase in
**execution** order (`0, 2, 1, 4, 5, 6, 7, 8, 9` — Phase 3 excluded, matching
the progress-file scan above), and prints a JSON object whose
`resolved_phase` is the phase to resume at and whose `message` reads e.g.
`Resuming at Phase 8 (latest completed: phase-6.md).`. Print that `message`
so the operator can confirm before work starts, then resume at
`resolved_phase`. Resolution rules the helper encodes:

- A completed `phase-5.md` with **no** `phase-6.md` resumes at **Phase 6**;
  a completed `phase-6.md` resumes at **Phase 8** (matching the `[b]`/`[q]`
  skip-to-8 flow); a completed `phase-7.md` resumes at **Phase 8**.
- Only `phase-0.md` present resumes at **Phase 2** (Baseline — the phase that
  now executes immediately after Phase 0).
- A completed `phase-2.md` with **no** `phase-1.md` resumes at **Phase 1**
  (Phase 3 has no tracked progress file, so the auto-detect skips over it —
  see `test_improve_resume.py`'s module docstring). A completed `phase-1.md`
  resumes at **Phase 4**.
- **No memory dir / no phase files / `phase-0.md` missing** — the helper exits
  non-zero; surface its error message (which points to running
  `/test-improve <repo-path>` from Phase 0) and do **not** silently start at
  Phase 0.
- A completed `phase-9.md` means the run is already complete (`complete:
  true`) — report it; there is nothing to resume.

To resolve an **explicit** `<n>` (including validating that `phase-0.md`
exists) the skill may pass `--explicit <n>`; an explicit `<n>` **overrides**
auto-detection. Auto-detect and explicit alike read Phase-0 inputs from
`phase-0.md` and never re-prompt them.

**Phase-6 prompt letter.** The full Phase-6 refactor-decision prompt —
shown only in `refactor-allowed` mode — uses `[y/b/q]` (not `[r]`; see
`phase-6-refactor-decision.md` for why `r` was avoided). `[y]` advances to
Phase 7; `[b]` backlogs the REFACTOR_REQUIRED items and
skips to Phase 8; `[q]` quits before Phase 8. In `no-refactor` mode (the
default) Phase 6 is **informational only** — no `[y]` is offered, the
REFACTOR_REQUIRED items are auto-backlogged, and the run continues to Phase 8
(see `phase-6-refactor-decision.md` for the full branch mechanics
and `phase-7-refactor.md` for the hard-mode-gate backstop that
enforces this same `no-refactor` restriction if Phase 7 is somehow reached).
