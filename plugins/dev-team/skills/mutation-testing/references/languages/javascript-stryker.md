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
