# Mutation Testing — JavaScript / TypeScript (Stryker)

Tool: [Stryker Mutator](https://stryker-mutator.io/). Detection: `package.json` has `@stryker-mutator/core` or `stryker.conf.json` exists.

## Install / detect

`--save-dev` is the **local** install path — the binary resolves via `node_modules/.bin` (which `npm run` / `npx` add to `PATH` scope-locally), so no global `PATH` edit is needed. Prefer this over `npm install -g @stryker-mutator/core`, which is the silent-failure trap called out in the skill's "prefer local install" note.

```bash
npm install --save-dev @stryker-mutator/core @stryker-mutator/vitest-runner  # or jest-runner, karma-runner
npx stryker init
```

Confirm the tool resolves before configuring a run:

```bash
npx stryker --version
```

## Run (scoped)

> When capturing run output to a log file, do **not** use a bare `npx stryker run ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a tool failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

```bash
# Specific files
npx stryker run --mutate "src/calculator.ts"

# Changed files only (CI mode)
npx stryker run --mutate "$(git diff --name-only HEAD~1 -- '*.ts' | grep -v test | tr '\n' ',')"
```

### Static-mutant skip (`--skip-static-mutants`)

[`mutation-kill`](../../../../agents/mutation-kill.md#invocation)'s opt-in,
default-OFF `--skip-static-mutants` flag excludes mutants Stryker's
**native** `reports/mutation/mutation.json` report marks `"static": true`
from the survivor list handed to **the generation step only**, for that
round. The filter itself is computed by calling `survivors_by_mutator(...,
skip_static=True)` in `mutation_report.py` — invoke it through its CLI
wrapper,
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/mutation-testing/scripts/mutation_report_cli.py"
--survivors-by-mutator --skip-static --report <path> --file <path>`, rather
than re-deriving it here or importing the library directly: the CLI is
where the inapplicable-skip notice below lives — a bare library call
computes the same filtered result but emits no diagnostic. A static mutant
sits in code that runs once at module-initialization time rather than
per-test, so `coverageAnalysis: "perTest"` cannot isolate it to the tests
covering it — Stryker must re-run the entire suite to verify one, which is
what "forcing a full-suite re-run" means in practice. (This field name and
execution behavior are Stryker's own; verify against the Stryker docs for
your installed version before relying on it in an automated pipeline.)

**What the trade-off actually buys.** The filter runs *after* Stryker has
already produced the report — it cannot make Stryker's own run faster, and
does not claim to. What it saves is the generation-and-verify **rounds**
`mutation-kill` would otherwise spend chasing mutants that are expensive to
confirm killed (each needs a full-suite re-run to verify), at the cost of
deferring each skipped static mutant rather than eliminating it: a skipped
static mutant that a full-suite run would have killed stays counted as an
unaddressed survivor for this pass, folded into the accepted-survivors
accounting below rather than dropped silently.

**Scoring and convergence stay unfiltered.** The `survivors == 0`
convergence exit, the no-improvement stop predicate, and the honest/reported
scores all read the report's full, unfiltered survivor count — a file whose
only remaining survivors are static must never be written as `status:
"converged"`.

**Line-clustering counts every survivor; only the mutator-grouped generation
list narrows (#1948, resolved as Option A).** `survivors_by_line()` DOES
accept a `skip_static` parameter now, but it is a deliberate **no-op** on
the returned clusters: a static-flagged survivor still counts toward its
line's cluster weight/ranking exactly as it would without the flag, because
it's still real evidence of that line's mutation density — only the
mutator-grouped generation input (`survivors_by_mutator(...,
skip_static=True)`) actually narrows which mutants get a test written. This
is a permanent design decision, not an open gap: clustering (the first step
of generation per [`mutation-kill.md`'s priority-order
guidance](../../../../agents/mutation-kill.md#target-mutation-types-in-priority-order))
and the mutator-grouped narrowing that follows it are intentionally
decoupled.

**Reconciling a clustered-but-unfiltered ranking with a filtered generation
list in practice.** When you pick a cluster to attack (highest
survivors-per-line first, per the priority-order guidance) and
`--skip-static-mutants` is active, don't assume every survivor in that
cluster is a generation candidate — check each survivor's own `static`
field (present on the raw mutant dict `survivors_by_line()` returns) before
writing a test for it:

- If the cluster has a **mix** of static and non-static survivors, write
  the test(s) targeting the non-static ones as usual; the static ones stay
  present in the cluster (contributing to its weight) but are not
  individually targeted this round.
- If **every** survivor in the top cluster is static, that line has no
  generation candidate this round even though it ranked first — move to the
  next cluster with a non-static survivor rather than generating nothing
  for the "top" line and stopping. The all-static cluster's survivors still
  count toward the file's raw survivor total and (once folded via
  `--accepted-static-survivors --skip-static`, below) the accepted-survivors
  accounting — they are deferred, not lost.

**`adjusted_score` does account for static-skipped mutants.** After the
existing `--skip-static --survivors-by-mutator` generation call, also call
`mutation_report_cli.py --accepted-static-survivors --skip-static --report
<path> --file <path>` and fold each returned entry into the file's own
"Accepted Survivors (deferred)" table and `adjusted_score` computation,
exactly like any other `status: "accepted"` entry (see [mutation-kill.md's
Accepted survivors: raw vs adjusted
score](../../../../agents/mutation-kill.md#accepted-survivors-raw-vs-adjusted-score)).
`--skip-static` is required on this call: `accepted_static_survivors()`
returns `[]` unless its `skip_static_active` evidence is `True`, so calling
`--accepted-static-survivors` without `--skip-static` yields no accepted
entries at all, even when static survivors exist in the report. This is now
documented via the same accepted/reason mechanism used elsewhere in
`mutation-kill` — not the undocumented, adjusted-score-invisible over-count
the prior wording described. Clustering (`survivors_by_line()`) still counts
every survivor including static ones (see above) — it does not filter, so
there is nothing here for `--skip-static` to have "touched" in the first
place. **The prior "known overlap" caveat (#1948) is resolved**, not merely
narrowed: follow the reconciliation guidance above (check each survivor's
own `static` field before writing a test for it) and a static survivor
folded into this accepted table is never also independently targeted by
this same round's generation step — the two paths agree by construction, not
by coincidence.

**Fallback when the field is absent.** `mutation_report_cli.py --skip-static`
detects this itself and prints a one-line notice to stderr, distinguishing
two causes: no mutant in the matched file carries a `static` key at all (an
older Stryker version, or a report already normalized before the filter
runs), or the target file isn't present in the report at all. Either way,
skip is inapplicable; the agent's job is only to surface/relay that notice,
not re-detect the inapplicable case itself.

**Scope: interactive agent path only.** The `--skip-static-mutants`
*invocation* flag on `/mutation-kill` itself is agent-parsed prose, not an
argparse flag — there is no scripted JS/TS mutation-kill loop to add it to
(unlike the C#/Python loops' real `--headless`/`--model`/`--report` flags).
The underlying filter *computation* it drives is scripted, though: a real
argparse flag on `mutation_report_cli.py` (see above). Passed against a
non-JS/TS target in the interactive path, the invocation flag has no effect
and the agent prints a one-line ignored notice. It is **not** a flag on
`mutation_kill_loop.py`/`mutation_kill_loop_python.py`'s `--headless` CLI —
passing it there is an `unrecognized arguments` error, by design, the same
as any flag those scripts don't declare. Under `--all --parallel <n>`,
each spawned sub-agent's prompt must carry the flag explicitly; it does not
propagate automatically to Phase-4 fan-out sub-agents.

## Per-mutant timeout flag

Configure in `stryker.config.js`:

```js
{
  timeoutMS: 60000,       // hard wall-clock cap per mutant
  timeoutFactor: 2.5,     // multiplier over baseline test time
}
```

Default shipped: 60 000 ms. Set `timeoutMS` to `timeout_seconds × 1000` (formula in [`SKILL.md`](../../SKILL.md) Step 1b).

## Native report → schema mapping

Source: `reports/mutation/mutation.json`. Map `metrics` to top-level totals and `files[*].mutants[]` to `survivors[]`.

```json
{
  "schema_version": 1,
  "tool": "stryker",
  "scope": ["src/calculator.ts"],
  "captured_at": "2026-06-19T14:22:08Z",
  "total": 50,
  "killed": 41,
  "survived": 6,
  "equivalent": 3,
  "survivors": [
    { "file": "src/calculator.ts", "line": 42, "operator": "ConditionalBoundary", "status": "survived" },
    { "file": "src/calculator.ts", "line": 67, "operator": "ReturnValue",        "status": "equivalent" }
  ]
}
```

`status: "equivalent"` is set when Stryker's `status` field is `NoCoverage` paired with an operator type the triage step (`SKILL.md` Step 4) classifies as equivalent; otherwise `survived`.

## Language-specific notes

- **`coverageAnalysis: "perTest"`** — set in `stryker.config.js` to run only tests covering the mutated line. This is the single biggest knob on per-mutant time; without it, per-mutant time ≈ full suite time.
- Stryker's HTML report (`reports/mutation/index.html`) is the most useful triage view — note the path when reporting back.
