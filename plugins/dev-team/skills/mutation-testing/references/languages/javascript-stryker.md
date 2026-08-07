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
skip_static=True)` in `mutation_report.py` — or its CLI wrapper,
`python3 mutation_report_cli.py --survivors-by-mutator --skip-static --report
<path> --file <path>` — rather than re-deriving it here. A static mutant
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
confirm killed (each needs a full-suite re-run to verify), at the cost of a
small, documented survivor over-count: a skipped static mutant that a
full-suite run would have killed stays counted as an unaddressed survivor
for this pass.

**Scoring and convergence stay unfiltered.** Only the generation step's
input narrows. The `survivors == 0` convergence exit, the no-improvement
stop predicate, and the honest/reported scores all read the report's full,
unfiltered survivor count — a file whose only remaining survivors are
static must never be written as `status: "converged"`.

**Fallback when the field is absent.** If no mutant in the report carries
a `static` key at all (an older Stryker version, or a report already
normalized before the filter runs), the skip is inapplicable — print a
one-line notice rather than proceeding as if nothing had been skipped.

**Scope: interactive agent path only.** This is agent-parsed prose, not an
argparse flag — there is no scripted JS/TS loop to add it to (unlike the
C#/Python loops' real `--headless`/`--model`/`--report` flags). Passed
against a non-JS/TS target in the interactive path, it has no effect and
the agent prints a one-line ignored notice. It is **not** a flag on
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
