---
name: test-improve
description: >-
  Consolidated analyze-then-improve test orchestrator. Defaults to lightweight
  ceremony; opts into heavier capabilities (Gherkin extraction, mutation
  testing, refactor-for-testability) only when the operator asks. Always
  baselines coverage (and mutation, when enabled) before any test change, runs
  the end-of-phase review loop after Phases 4 and 5, and produces a stable
  10-section executive-summary report. Use when the user says "improve our
  tests", "modernize the test suite", "upgrade our tests", or runs
  /test-improve.
argument-hint: "<repo-path> [--parent <url>] [--analyze-only] [--from-phase [<n>]] [--stack <id>]"
role: orchestrator
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash(git diff *), Bash(python3 *), Skill, Agent
---

# Test Improve

Role: orchestrator. This command sequences existing skills and agents through a
seven-phase analyze-then-improve workflow; it does **not** implement, audit, or
write tests itself. Each phase is **delegated** to the worker skill or agent
that owns it, and per-phase progress is persisted to
`memory/test-improve/<slug>/phase-<n>.md` so `/continue` (and `--from-phase`)
can resume.

You have been invoked with the `/test-improve` command.

## Orchestrator constraints

1. **Delegate every phase.** Call the owning skill or agent (`/test-health`,
   `/gherkin-derive`, `/issues-from-assessment`, `/build`, `/coverage-baseline`,
   `/coverage-delta`, `/mutation-testing`, `mutation-kill` agent,
   `/quality-targets-converge`, `/test-design`, `/code-review`, `/apply-fixes`).
   Never re-implement their logic here.
2. **Honor the human gates.** Do not advance past a gate without explicit
   approval.
3. **Confirm the approach first.** Phase 0 owns the approach contract; do not
   start work until it has completed and its answers are persisted.
4. **Baseline before changing anything.** Coverage (and mutation, when
   enabled) must land in `memory/test-improve/<slug>/` before any file under
   the stack's test directory is modified.
5. **Be concise.** Report each phase's outcome and the next gate, nothing
   more.

## Parse Arguments

- Positional: `<repo-path>` (default: cwd).
- `--parent <url>` — optional tracker parent issue URL; the host selects the
  CLI (ADO / GitHub / GitLab / Jira). Omit for **local-files mode** (the
  default), which writes to `./reports/test-improve/` and `./plans/test-improve/`.
- `--analyze-only` — run Phase 0 then Phase 1 and **exit after Phase 1** with a
  summary of the improvement plan. No baseline is captured; no code changes.
- `--from-phase [<n>]` — skips completed phases and resumes at phase `n` when
  `memory/test-improve/<slug>/phase-<n-1>.md` exists. **The number is
  optional.** Passed with **no argument**, `/test-improve` **auto-detects** the
  resume point from `memory/test-improve/<slug>/` (see the `--from-phase`
  semantics below): it resumes at the phase after the highest completed
  progress file and prints which phase it resolved to and why. An explicit
  `<n>` **overrides** auto-detection. Either form does **not** re-prompt
  Phase-0 inputs; to change them, delete
  `memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.
- `--stack <id>` — force a stack profile (e.g. `js`, `dotnet`, `java`, `go`)
  when manifest detection is ambiguous.

## Phase-start banner

At the start of every phase (0..7), print a two-line banner:

```
Phase N/7 — <phase name>
mutation: <off|kill-loop|baseline+kill-loop> · binding: <none|xunit-with-annotations|bdd-runner> · refactor: <no-refactor|refactor-allowed> · sink: <tracker|local> · report: <on|off>
```

The recap line reflects the still-active Phase-0 settings so an operator
resuming via `--from-phase` (or returning to a long-running session) sees the
current phase and active settings without scrollback archaeology.

## Steps

### Phase 0 — Approach contract

Resolve every ambiguous input in **one batch** before any work starts, then
persist the resolved inputs to `memory/test-improve/<slug>/phase-0.md`. The
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
> surviving-mutant count. Either way the Phase-6 mutation target is
> advisory-only for Go.

**Prompt battery (one batch, seven knobs).** Each prompt displays its default in
`[brackets]`; pressing **Enter accepts every default in one keystroke** — including
knob 7 (baseline-metrics report), which defaults to `no` under Enter — with
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
   `refactor-allowed` to permit production-code changes in Phase 5 (seams
   only; existing tests may not be modified or removed).
4. **Quality targets** — defaults: coverage ≥ 90% line + branch; surviving
   mutants = 0 (only when mutation mode is not `off`); determinism = 100%; wall-clock =
   fastest achievable. Any target can be overridden here; overrides land in
   `phase-0.md` and flow into Phase 6.
5. **Sink** — `--parent <url>` selects a tracker (ADO / GitHub / GitLab /
   Jira via the host CLI); missing CLI or omitted flag falls back to
   **local-files** mode (writes under `./reports/test-improve/` and
   `./plans/test-improve/`).
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
7. **Baseline-metrics report (opt-in)** — `[no]`. Ask whether to **persist
   baseline coverage and mutation metrics** so an end-of-run before/after delta
   report can be generated. This is a **distinct** decision from the mutation
   mode (knob 1) and the coverage baseline that Phase 2 always takes: the
   coverage baseline report is available **even when mutation mode is `off`**,
   and it can be **skipped under `kill-loop`** (where there is no mutation
   baseline to diff, only a final-survivor count). Default is **`no`** and this
   knob **is** part of the Enter-accepts-all gesture (unlike knob 6). On **`yes`**,
   Phase 2 writes the baseline to a git-tracked path (see Phase 2 for the path
   and the gitignore caveat); on **`no`**, it stays on the transient `memory/`
   path as today. The banner recap renders this opt-in as `report: on` / `off`
   (mapping `yes`→`on`, `no`→`off`).

**Persistence.** Write the resolved inputs to `memory/test-improve/<slug>/phase-0.md` before Phase 1 runs — Phase 1 must not start until `phase-0.md` exists. This includes the knob-6 outcome (the operator's install choice, and for each tool whether it was already present, installed, declined, or failed) and the knob-7 outcome (whether the baseline-metrics report was opted into).

**Immutability.** Phase-0 answers are **immutable** for the remainder of the
run. `--from-phase` does not re-prompt Phase-0 inputs. To change them, delete
`memory/test-improve/<slug>/phase-0.md` and re-run from Phase 0.

**`--analyze-only` semantics.** With `--analyze-only`, Phase 0 completes as
normal, Phase 1 (`/test-health`) runs, and the orchestrator **exits after
Phase 1** with a summary of the improvement plan. No baseline is captured; no
code changes.

**`--from-phase` semantics.** `--from-phase <n>` **skips** phases `0..n-1`
when their `memory/test-improve/<slug>/phase-<i>.md` files exist and resumes
at phase `n`. Phase-0 inputs are read from `phase-0.md` (never re-prompted).

**`--from-phase` with no number — auto-detect the resume point.** When
`--from-phase` is passed **without** a number, resolve the resume phase by
calling the helper — do **not** infer it in prose:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/test_improve_resume.py <repo-path>
```

The helper resolves the slug from `<repo-path>` (its last path segment), scans
**only** that slug's `memory/test-improve/<slug>/` directory for the
completed-phase progress files (`phase-0.md` … `phase-7.md`, plus
`phase-4b.md`), finds the highest completed phase (ordering `phase-4b`
between `phase-4` and `phase-5`), and prints a JSON object whose
`resolved_phase` is the phase to resume at and whose `message` reads e.g.
`Resuming at Phase 5 (latest completed: phase-4b.md).`. Print that `message`
so the operator can confirm before work starts, then resume at
`resolved_phase`. Resolution rules the helper encodes:

- A completed `phase-4.md` with **no** `phase-4b.md` resumes at **Phase 4b**;
  a completed `phase-4b.md` resumes at **Phase 6** (matching the `[b]`/`[q]`
  skip-to-6 flow); a completed `phase-5.md` resumes at **Phase 6**.
- Only `phase-0.md` present resumes at **Phase 1**.
- **No memory dir / no phase files / `phase-0.md` missing** — the helper exits
  non-zero; surface its error message (which points to running
  `/test-improve <repo-path>` from Phase 0) and do **not** silently start at
  Phase 0.
- A completed `phase-7.md` means the run is already complete (`complete:
  true`) — report it; there is nothing to resume.

To resolve an **explicit** `<n>` (including validating that `phase-0.md`
exists) the skill may pass `--explicit <n>`; an explicit `<n>` **overrides**
auto-detection. Auto-detect and explicit alike read Phase-0 inputs from
`phase-0.md` and never re-prompt them.

**Phase-4b prompt letter.** The full Phase-4b refactor-decision prompt —
shown only in `refactor-allowed` mode — uses `[y/b/q]` (not `[r]`). The
letter `r` is already claimed by mutation-kill's `[c/r/w/q]` (retry) and the
review-loop's `[r/w/q]` (revise); reusing `r` a third time at the
highest-consequence prompt in the flow would produce operator confusion.
`[y]` advances to Phase 5; `[b]` backlogs the REFACTOR_REQUIRED items and
skips to Phase 6; `[q]` quits before Phase 6. In `no-refactor` mode (the
default) Phase 4b is **informational only** — no `[y]` is offered, the
REFACTOR_REQUIRED items are auto-backlogged, and the run continues to Phase 6
(see Phase 4b).

### Phase 1 — Analyze via /test-health

Delegate the entire analysis pass to **`/test-health`** — it is the **sole
worker** for Phase 1. Invoke it exactly once with the resolved repo path from
Phase 0. `/test-health` internally orchestrates whatever sub-skills it needs
(CD-alignment audit, test-design assessment, mutation-testing roll-up); the
orchestrator must **not** invoke `/cd-test-architecture`, `/test-design`, or
`/mutation-testing` separately here. Any prior workflow that reached those
skills directly is superseded by the single `/test-health` call.

**Mutation section respects the Phase-0 mutation mode.** When `phase-0.md`
recorded mutation mode **`off`**, the rolled-up report's mutation section is
either **omitted** or marked "not enabled for this run". When it recorded
**`kill-loop`** or **`baseline+kill-loop`**, the mutation section is **present**.
`/test-health` is not invoked with a mutation flag — the mode flows through from
`phase-0.md` and the section is handled at report time.

**Output.** Persist the rolled-up analysis plus the ordered improvement plan to
`memory/test-improve/<slug>/phase-1.md`.

**Test-count-by-type snapshot.** Independent of the `/test-health` call
above (and of whether `/test-health`'s own trivial-suite short-circuit
fired for this run), perform a direct classification pass over the test
files under the `<repo-path>` Phase 0 resolved: apply
`knowledge/cd-test-architecture.md`'s
six-type criteria (Static analysis / Unit / Component / Contract /
Integration / End-to-end) directly to each test suite/file found. **One
test file counts as exactly one suite**, regardless of how many describe
blocks or test classes it contains. Tie-break rule for a file that doesn't
cleanly fit one type: classify by its dominant/highest-dependency type
(e.g. a suite exercising a real DB connection classifies as integration
even if most of its assertions read like unit-level checks); if dominance
is still tied, classify by the higher-fidelity type using this fixed
precedence: `end_to_end` > `integration` > `contract` > `component` >
`unit` (this precedence applies to test files only — `static_analysis` is
never a legitimate outcome of classifying a test file; see its own
counting rule below). Persist
`memory/test-improve/<slug>/test-counts-before.json` with the six
canonical snake_case keys, in this fixed order: `static_analysis`, `unit`,
`component`, `contract`, `integration`, `end_to_end` — each key present
even at zero, counting **test suites/files, not individual test cases or
assertions**. `static_analysis` counts configured linter/scanner tool
invocations (one per tool — e.g. ESLint, Semgrep, mypy) rather than
test-directory files, since static analysis runs over non-running code and
is rarely organized as a describe-block suite; when the repo has no
configured static-analysis tooling at all, the key is `0`, not omitted.
This pass does **not** invoke `/test-health` or `/cd-test-architecture`'s
full skill.

**Human gate.** After `/test-health` returns, present **the ordered improvement
plan** to the operator and wait for explicit approval. **Phase 2 does not run**
until the operator approves. This is the human gate for Phase 1; do not advance
past it without approval. When `phase-0.md` recorded
`refactor-mode: no-refactor`, any plan item that would require a production-code
refactor is labeled **skipped-in-no-refactor** (out of scope for this run) so
the operator sees the coverage/behavior left on the table — such items are never
presented as ordinary next steps that this run will execute.

**`/handoff` suggestion** (context-heavy analysis). Once the gate above resolves, print: `Phase 1 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 2 (or --from-phase with no number to auto-detect the resume point)`

### Phase 2 — Baseline (coverage + mutation)

Capture the objective starting point **before any file under the stack's test
directory is modified**. Baselines are the ground truth every downstream delta
compares against; running any test edit before baseline capture invalidates
the whole run.

**Coverage baseline.** Invoke `/coverage-baseline --workflow test-improve`
against the resolved repo path. Persist the result to
`baseline-coverage.json` under the **baseline write path** selected by the
knob-7 report opt-in (see below); the default (report declined) is
`memory/test-improve/<slug>/baseline-coverage.json`.

**Baseline write path (knob-7 report opt-in).** The baseline persistence
location is chosen by the Phase-0 knob-7 answer:

- **Report opted in (`yes`).** Write `baseline-coverage.json` (and, in
  `baseline+kill-loop` mode, `baseline-mutation.json`) under the **git-tracked**
  path `reports/test-improve/<slug>/` so the number is version-controlled and
  reviewable in the run's PR. `/test-improve` issues **no** git command — the
  tracked file is picked up by the run's existing commit/PR flow. **Caveat:**
  because `reports/` is commonly gitignored, the target repo must un-ignore
  `reports/test-improve/` for the baseline to appear in the PR; where it is not
  tracked, the opt-in degrades to transient.
- **Report declined (`no`, the default).** Write the baseline to the transient
  `memory/test-improve/<slug>/` path, exactly as today.

This path selection is independent of the mutation mode: a coverage baseline is
persisted in every mode, and the mutation baseline is written **only** in
`baseline+kill-loop` mode (see below) regardless of the report opt-in.

**Mutation baseline (`baseline+kill-loop` only).** When `phase-0.md` recorded
mutation mode **`baseline+kill-loop`**, invoke
`/mutation-testing --baseline --workflow test-improve`. Persist the result to
`baseline-mutation.json` under the same knob-7 baseline write path as coverage
(default, report declined: `memory/test-improve/<slug>/baseline-mutation.json`).
The file records the **honest score**: hard kills / effective total, with the
**timeout count reported separately** (timeouts are not counted as kills).

**No-baseline modes skip (`off` and `kill-loop`).** When `phase-0.md` recorded
mutation mode **`off`** or **`kill-loop`**, `/mutation-testing --baseline` is
**not invoked** and no `baseline-mutation.json` is written — `kill-loop` runs the
mutant-kill loop in Phase 4 but takes no baseline first. For `off`, the Phase-6
mutation target is later marked "not enabled", not waived; for `kill-loop`,
Phase 6 reports the final-survivor count rather than a baseline delta (see
Phase 6).

**Go advisory marker.** When the resolved stack is Go and mutation mode is
`baseline+kill-loop`, the
mutation baseline is **advisory only** — go-mutesting is alpha-quality (see the
Go advisory in Phase 0). `baseline-mutation.json` is written with the
`advisory-only: true` marker; survivor counts are not a gate.

**Ordering invariant.** Baselines land **before any test file is modified** — no file under the stack's test directory may change between Phase 0 and the creation of `baseline-coverage.json` (and `baseline-mutation.json` when applicable). Phase 2b, Phase 4, and any subsequent test edits depend on this ordering.

### Phase 2b — Derive Gherkin (conditional)

Gherkin derivation is **conditional on the Phase-0 BDD rubric answer**. It
runs only when the operator opted in to a binding mode other than `none`.

**Binding mode `none` — skipped entirely.** When `phase-0.md` recorded binding
mode `none`, Phase 2b is **skipped**: `/gherkin-derive` is **not invoked**, no
`.feature` files are written, no runner is added. Phase 3 follows Phase 2.

**Binding mode `xunit-with-annotations` — .feature files without a runner.**
Invoke `/gherkin-derive --workflow test-improve --mode xunit-with-annotations`.
The skill writes `.feature` files under `features/test-improve/`; **no runner
dependency** is added to the project. The corresponding xUnit tests (authored
in Phase 4) will carry the scenario name plus Given/When/Then leading comments
that cite the `.feature` file, but they run through the existing xUnit runner.

**Binding mode `bdd-runner` — native parser wired.** Invoke
`/gherkin-derive --workflow test-improve --mode bdd-runner`. The stack profile
selects the native parser (`cucumber-js` for JS/TS, `SpecFlow` / `Reqnroll` for
.NET, `cucumber-jvm` for Java, `godog` for Go). `/gherkin-derive`:

- adds the parser as a project dependency,
- generates pending step-definition stubs,
- writes `.feature` files under `features/test-improve/`.

**Persistence.** Record the surface inventory and (in `bdd-runner` mode) the
parser wiring to `memory/test-improve/<slug>/gherkin.md`.

**Human gate.** After Phase 2b produces `.feature` files (or parser wiring in
`bdd-runner` mode), present them to the operator for review. **Phase 3 does
not run** until the operator approves.

### Phase 3 — Triage (partition findings by gap class)

Convert Phase 1's ordered improvement plan into actionable work items.
Delegate the write to
`/issues-from-assessment --workflow test-improve --refactor-mode <value>`
(`phase-0.md`'s `no-refactor` or `refactor-allowed`); the skill routes the
memory + plan paths under `test-improve/` (per Slice 11). Threading
`--refactor-mode` lets the written plan mark refactor-requiring items
explicitly: in `no-refactor` mode the Phase-5 `[Refactor-for-testability]`
work surfaces labeled **out-of-scope / skipped-in-no-refactor**, never as
actionable Phase-4 Stories.

Every finding lands in exactly one of three **gap classes**:

- **`NO_REFACTOR`** — fixable by test edits alone. Written as **Phase-4
  Stories** to `./plans/test-improve/` (or the configured parent tracker
  when `--parent` was supplied at Phase 0).
- **`REFACTOR_REQUIRED`** — needs a production-code seam before a test can reach the behavior. REFACTOR_REQUIRED items are **deferred to Phase 5** and are **not written as Phase-4 Stories**; they surface with rationale for the operator, who decides at Phase 4b whether to enter Phase 5. Under `refactor-mode: no-refactor` they are labeled **out-of-scope (skipped-in-no-refactor)** in the plan — informational context, never an actionable Story this run will execute.
- **`LOW_VALUE`** — tests that are cheap to have but not worth fixing (e.g. duplicate coverage, trivial getters, dead-code assertions). LOW_VALUE findings are **advisory-only**: enumerated in the report, no PR is opened to delete a test flagged this way.

**Persistence.** Persist the classified finding set to
`memory/test-improve/<slug>/phase-3.md`.

**Human gate.** Present the Phase-4 Story set (NO_REFACTOR only) to the
operator. **Phase 4 does not run** until the operator approves the set.

### Phase 4 — Improve without refactoring (build + mutation-kill + review loop)

Iterate the approved Phase-4 Story set. For **each Story**:

1. **Build** — invoke `/build <story-id>`. `/build` inherits the **no-refactor**
   mode from Phase 0: production-code changes are **rejected**. A Story that
   would require a production-code change is surfaced as a REFACTOR_REQUIRED
   deferral candidate and re-classified for Phase 4b.
2. **Apply the Phase-0 binding mode.** If Phase 0 selected
   `xunit-with-annotations`, the resulting test names mirror the source
   scenario name and Given/When/Then lines appear as **leading comments**
   citing the source `.feature` file. In `bdd-runner` mode, the step
   definitions are filled in against the parser wired at Phase 2b. In `none`
   mode, the test is authored idiomatically for the stack without
   feature-file citations.
3. **Coverage delta** — after `/build` closes the Story, invoke
   `/coverage-delta --workflow test-improve --story <id>`. The delta is
   appended to `memory/test-improve/<slug>/coverage-history.json`.
4. **Mutation-kill (`kill-loop` and `baseline+kill-loop`; skipped when `off`).**
   Invoke the **`mutation-kill` agent**
   with `--file <story-file> --max-rounds 3`. Residual survivors trigger the
   **`[c]ontinue / [r]etry / [w]aive / [q]uit`** prompt — the shape is
   `[c/r/w/q]`. `[c]` accepts the residual and moves on; `[r]` re-runs one
   more mutation-kill round; `[w]` waives the residual to `waivers.json`;
   `[q]` quits Phase 4.
5. **Go mutation-kill is advisory.** On Go stacks, `mutation-kill` logs
   survivors but makes **no commit** — the operator is instructed to apply
   changes manually. Advisory-only handling matches the Phase-0 Go advisory.

#### Pending-stub gate (`bdd-runner` mode only, issue #1391)

After **all Phase-4 Stories have closed**, and only when Phase 0 selected
`bdd-runner` binding mode, run the completion gate before Phase 4 may be
reported closed — a hard gate, not prose:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gherkin_stub_gate.py --dir <step-definitions-dir>
```

(`<step-definitions-dir>` is wherever `/gherkin-derive`'s Step 2b run wrote
step-definition files — recorded in `memory/test-improve/<slug>/gherkin.md`.)

- **Exit 0 (no pending stubs)** — Phase 4 proceeds to the end-of-phase review
  loop below.
- **Non-zero (pending stubs remain)** — Phase 4 is **not done**. Surface the
  gate's listed `file:line` pending step definitions to the operator; do not
  report the phase closed. Route each remaining stub back into the per-Story
  build loop (step 2 above — fill in the step definition against the parser
  wired at Phase 2b) rather than silently leaving it pending.
- Skip entirely when binding mode is `none` or `xunit-with-annotations` (no
  step definitions exist to gate on).

#### End-of-phase review loop

After **all Phase-4 Stories have closed**, run the review loop over the
Phase-4 diff:

1. **Dispatch in parallel** — `/test-design --since <base-sha>` and
   `/code-review --since <base-sha> --internal` run **concurrently** against
   the diff between the Phase-4 base commit and HEAD. `--internal`
   (not `--json`) mirrors `/build`'s Step 6 backstop-review flag choice: it
   suppresses the `DEV_TEAM_REPORTS/code-review.md` write (this is a
   diff-scoped, phase-internal review, not a human-invoked top-level run —
   `knowledge/report-output-location.md`) while keeping the prose/
   `corrections/` output sub-step 2 depends on — `--json` would skip that
   output entirely.
2. **Apply fixes.** Run `/apply-fixes corrections/`, then **re-run
   `/code-review --internal`** to confirm.
3. **Iterate at most 2 rounds.** After **2 iterations** without clean
   `/code-review`, prompt the operator with **`[r]evise / [w]aive / [q]uit`**
   (shape `[r/w/q]`).
   - `[r]` triggers one more revise pass (may exceed the cap by operator
     consent).
   - `[w]` writes the outstanding finding set to
     `memory/test-improve/<slug>/waivers.json`, **tagged** with the finding
     list, and closes the phase.
   - `[q]` quits Phase 4 with the loop unresolved.
4. **Evidence.** Write `memory/test-improve/<slug>/phase-4-review.json` with
   the fixed schema — fields: `base_sha`, `head_sha`, `farley_score`,
   `smells`, `code_review`, `iterations`, `escalated`.

**`/handoff` suggestion** (context-heavy review). Once the loop above closes, print: `Phase 4 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 4b (or --from-phase with no number to auto-detect the resume point)`

### Phase 4b — Refactor decision (mode-gated)

With Phase 4 closed, present the **REFACTOR_REQUIRED** list deferred at
Phase 3. Each item is shown with three columns:

- **seam-needed** — the production-code seam the test would need (e.g.
  interface extraction, dependency injection, virtual method).
- **behavior-gained** — the untested behavior a Phase-5 refactor would
  unlock coverage for.
- **estimated-risk** — a qualitative risk marker (low / medium / high) for
  the specific refactor.

**Phase 4b branches on the Phase-0 `refactor-mode`.** Read `refactor-mode`
from `memory/test-improve/<slug>/phase-0.md` **before** rendering any prompt.
Entering Phase 5 *is* refactoring, so the choice made at Phase 0 governs
whether Phase 4b is a branch point at all.

**`refactor-mode: no-refactor` (the default) — informational, not a branch
point.** The operator declined refactoring at Phase 0, so the **`[y] enter
Phase 5` option does not exist** in this mode. Present the REFACTOR_REQUIRED
list as *"the following require refactoring and are out of scope in
no-refactor mode"* — the seam-needed / behavior-gained / estimated-risk
columns still render, so the operator sees the coverage and behavior left on
the table. Then **auto-backlog** every item to
`memory/test-improve/<slug>/refactor-backlog.md` (or update the parent
tracker when `--parent` was passed) and **continue to Phase 6** with the
current Phase-4 test suite as the target. The prompt collapses to a single
**acknowledge/continue** step (equivalent to today's `[b]`); when no operator
is attached, run it **non-interactively** — no keystroke is required and none
enters Phase 5. The sanctioned way to actually perform these refactors is the
Phase-6 coverage-below-90% re-run prompt, which offers a fresh
`refactor-allowed` invocation the operator explicitly opts into.

**`refactor-mode: refactor-allowed` — full decision prompt.** Prompt the
operator with **`[y] enter Phase 5 / [b] backlog and skip to Phase 6 /
[q] quit`** (shape `[y/b/q]`). The letter `y` was chosen deliberately
over `r` — `[r]` is already claimed by mutation-kill's `[c/r/w/q]` (retry) and
the review-loop's `[r/w/q]` (revise); a third `[r]` at the
highest-consequence prompt would confuse operators.

- **`[y]`** — advances to **Phase 5** (refactor-for-testability).
- **`[b]`** — writes the REFACTOR_REQUIRED items to
  `memory/test-improve/<slug>/refactor-backlog.md` (or updates the parent
  tracker when `--parent` was passed); **skips Phase 5** and runs **Phase 6**
  directly with the current Phase-4 test suite as the target.
- **`[q]`** — **quits** before Phase 6. No further phase runs; the final
  report reflects Phase-4 state only.

### Phase 5 — Refactor-for-testability (conditional)

Phase 5 runs **only when the operator picked `[y]` at Phase 4b**. If Phase 4b
returned `[b]` (backlog) or `[q]` (quit), Phase 5 is **skipped**.

**Hard mode gate — Phase 5 refuses to run under `no-refactor`.** Before any
Phase-5 work begins, `/test-improve` re-reads `refactor-mode` from
`memory/test-improve/<slug>/phase-0.md`. When it records
`refactor-mode: no-refactor`, Phase 5 **refuses to run** and is skipped —
**even if `[y]` is somehow reached**. Phase 4b offers no `[y]` in this mode,
so this gate is a defense-in-depth backstop: Phase 5 executes production-code
refactors the `no-refactor` operator declined at Phase 0, and the mode — not
the keystroke — is the final authority. Only `refactor-mode: refactor-allowed`
permits Phase 5 to execute.

**Seam-only production code changes.** `/build` in Phase 5 accepts **seam
introductions only** — interface extractions, dependency injection points,
virtual method promotions, factory wrapping. Any change beyond a seam is
rejected. Behavior modifications, refactors that alter semantics, and
opportunistic clean-ups are all out of scope.

**Existing tests are immutable.** Phase 5 **may not modify or remove existing tests** — `/build` rejects deletions and edits to any file under the stack's test directory that existed before Phase 5 started. The pre-Phase-5 suite must stay green throughout; a red pre-Phase-5 test halts the phase.

**Phase-4 precondition-check.** Each Phase-5 Story is paired with the
corresponding Phase-4 baseline Story that could not close under no-refactor.
Before `/build` runs a Phase-5 Story, `/test-improve` **verifies the paired
Phase-4 Story is closed and green**. A missing or failing Phase-4 baseline
halts that Story until the operator resolves it.

**End-of-phase review loop.** After all Phase-5 Stories close, run the
**same review loop as Phase 4** (see the Phase 4 end-of-phase review loop
above) — `/test-design --since` and `/code-review --since --internal`
dispatch in parallel over the Phase-5 diff; `/apply-fixes corrections/` then
re-run `/code-review --internal`; cap 2 iterations with `[r/w/q]`
escalation.

**Evidence.** Write `memory/test-improve/<slug>/phase-5-review.json` using
the **same fixed schema** as Phase 4 (`base_sha`, `head_sha`, `farley_score`,
`smells`, `code_review`, `iterations`, `escalated`).

**`/handoff` suggestion** (same rationale as Phase 4). Once the loop above closes, print: `Phase 5 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 6 (or --from-phase with no number to auto-detect the resume point)`

### Phase 6 — Validate (converge quality targets)

Verify the improved suite meets the Phase-0 quality targets. Delegate to
`/quality-targets-converge --workflow test-improve --refactor-mode <value>`
(`phase-0.md`'s `no-refactor` or `refactor-allowed`) — the skill routes
memory and plan paths under `test-improve/` (per Slice 11), and threading
the flag keeps the operator's no-refactor choice enforced past Phase 4b via
its own dispatch-table gating.

**Mutation target per mode.** The mutation target reads differently for each
Phase-0 mutation mode:

- **`off` — skipped (not waived).** The mutation target is **skipped** and marked
  "not enabled for this run" — it is **not waived**. Skipping and waiving are
  distinct outcomes: a waiver signals a target failed and the operator accepted
  the gap; a skip signals the target was never in scope for this run.
- **`kill-loop` — final-survivor-only.** No Phase-2 baseline was taken, so there is
  no before/after delta; the target reports the **final surviving-mutant count**
  from the Phase-4 kill loop.
- **`baseline+kill-loop` — baseline-delta.** The target reports the
  **baseline-to-achieved mutation delta** against `baseline-mutation.json`.

**Go mutation advisory.** When the resolved stack is Go and mutation is not `off`,
the mutation target is **advisory-only** (survivor count is not a gate). The
target reads with the "advisory only — go-mutesting is alpha" footnote and
the run may pass regardless of mutation numbers.

**Branch-scoped mutation validation (issue #1208).** `/quality-targets-converge`
scopes its Phase-6 mutation measurement to the **branch-vs-base cumulative
changed set** — the production source exercised by the tests this branch
changed across all its sessions — never the whole repo. It still reports a
whole-repo score by splicing the freshly-measured changed files over the
**persisted** Phase-2 baseline (`baseline-mutation.json`), and reports any
module it could not measure (OOM/timeout) as **held at baseline** rather than
omitting it. No extra flag is threaded through the delegation above — the
worker resolves the branch base itself using the same idiom as `/build`'s
Farley-Score step. The whole-repo splice is only lossless when Phase 2's
baseline was persisted to the git-tracked `reports/test-improve/<slug>/` path
(knob-7 opt-in); on decline it degrades to a branch-scoped-only whole-repo
line.

**Coverage < 90% in no-refactor mode.** When Phase 6 closes with coverage
below 90% and Phase 0 recorded `refactor-mode: no-refactor`,
`/test-improve` surfaces a **re-run prompt** shaped **`[y/n]`**: *"Coverage is
below 90% in no-refactor mode. Re-run in refactor-allowed mode to close the
gap? `[y/n]`"*. The prompt names the **backlogged REFACTOR_REQUIRED items**
that would close the gap (drawn from `memory/test-improve/<slug>/refactor-backlog.md`
when `[b]` was picked at Phase 4b, or from the Phase-3 deferred list when
Phase 4b was not reached). Whenever shown, `phase-6.md` records `coverage_reprompt_fired: true` plus the answer — the durable source Phase 7's close-out prompt reads to avoid re-asking (see below).

**Evidence.** Persist target outcomes to
`memory/test-improve/<slug>/phase-6.md`.

**Test-count-by-type recount.** Alongside the target-outcome persistence
above, perform the **identical** classification pass Phase 1's
"Test-count-by-type snapshot" defined — same six-type criteria, same
tie-break rule, same repo-path scope Phase 1 used (not a re-scoped or
differently-scoped recount) — and persist
`memory/test-improve/<slug>/test-counts-after.json` in the identical shape
as `test-counts-before.json` (same six keys, same order, zero-count keys
present). See Phase 1's own instruction for the full classification
mechanism; this pass does not restate it.

**`/handoff` suggestion** (context-heavy re-measurement). Once the recount above is persisted, print: `Phase 6 complete. Consider running /handoff to compress context before continuing. To resume: /test-improve <repo-path> --from-phase 7 (or --from-phase with no number to auto-detect the resume point)`

### Phase 7 — Executive-summary report

Produce a stable executive-summary report from the shipped template. Every
section is present in every run; empty sections **do not disappear** — they
render `_Not applicable — <reason>._` so the shape of the report never changes
between runs.

**Template source.** Copy
`plugins/dev-team/skills/test-improve/templates/executive-summary.md` to the
output path.

**Output path.** `reports/test-improve/<repo-slug>-<date>.md` — the file is
always relative to the invocation directory, whether the run used a tracker
sink or local-files mode.

**Interpolation.** Every placeholder is **interpolated** from persisted
memory files under `memory/test-improve/<slug>/` (`phase-0.md`, `phase-1.md`,
`test-counts-before.json`, `phase-3.md`,
`coverage-history.json`, `phase-4-review.json`,
`phase-5-review.json` if Phase 5 ran, `refactor-backlog.md` if Phase 4b chose
`[b]` or Phase 6 wrote a no-refactor-mode entry to it, `waivers.json`,
`phase-6.md`, `test-counts-after.json` if Phase 6 ran). No placeholder is
left literal. The **baseline artifacts** (`baseline-coverage.json`, and
`baseline-mutation.json` in `baseline+kill-loop` mode) resolve from the knob-7
baseline write path that **Phase 2 owns** (which also carries the gitignore
caveat) — so the delta report reads the same numbers wherever Phase 2 persisted
them.

**Empty-section rule.** Sections with no data render `_Not applicable —
<reason>._` (e.g. § 6 when Phase 5 was declined reads "*Phase 5 not run —
operator chose to backlog REFACTOR_REQUIRED items at Phase 4b.*"). Sections
are never omitted or hidden — this keeps the report shape stable across runs.

**Mutation row shape (per Phase-0 mutation mode).**

- `off`: `_Not applicable — mutation disabled at Phase 0._`
- `kill-loop`, non-Go: final surviving-mutant count from the Phase-4 kill loop;
  the baseline and Δ cells read `_Not applicable — no baseline run (kill-loop
  mode)._` since no Phase-2 baseline was taken.
- `baseline+kill-loop`, non-Go: honest baseline-to-achieved score (hard kills /
  effective total; timeouts reported separately) with the Δ column populated.
- Go stack (`kill-loop` or `baseline+kill-loop`): honest numbers with the
  "advisory only — go-mutesting is alpha" footnote.

**Parent-issue-or-FEATURE.md link update.** When the run used a **parent
tracker** (Phase 0 selected `--parent <url>`), the parent issue is updated
with a link to `reports/test-improve/<repo-slug>-<date>.md`. When the run
was **local-files-only**, `plans/test-improve/FEATURE.md` is updated with
the same link.

**Regeneratable-from-memory contract.** The report is a **pure function** of
`memory/test-improve/<slug>/`. Deleting the report file and re-invoking
Phase 7 against the same memory directory reproduces the report byte-for-byte
— no run-time state is consulted outside the memory directory.

### After Phase 7 — Re-run-with-refactor close-out prompt

**No prompt** when: `refactor-backlog.md` does not exist (no `REFACTOR_REQUIRED` items were ever backlogged), the file exists but has zero entries (treated the same as absent), `phase-6.md` records `coverage_reprompt_fired: true` (Phase 6's own coverage-driven `[y/n]` already fired this run — no repeating the same question twice), or `phase-0.md` recorded `refactor-mode: refactor-allowed` (a Phase-4b `[b]` backlog entry under `refactor-allowed` mode is the operator's deliberate deferral, not a no-refactor constraint to lift — re-asking "re-run with refactor-allowed mode now?" would be nonsensical when that's the mode already in use).

**Otherwise** (backlog file has ≥1 entry, Phase 6 never fired its prompt,
and `phase-0.md` recorded `refactor-mode: no-refactor`), prompt **`[y/n]`**
— distinct from Phase 6's coverage-driven, mid-run prompt, this one is
backlog-driven and fires at close-out: *"N REFACTOR_REQUIRED items remain
backlogged. Re-run with refactor-allowed mode now? `[y/n]`"* (N = entry
count). `[n]` leaves the backlog as-is. `[y]` — Phase-0 answers are
immutable per-run, so tell the operator to re-run `/test-improve
<repo-path>` fresh, choosing `refactor-allowed`; this is a new invocation,
not `--from-phase`.
