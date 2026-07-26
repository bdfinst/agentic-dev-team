# The `--pdf` flag on report-producing skills

The single contract for the `--pdf` pass-through, shared by every skill that
writes a Markdown report (`/code-review`, `/test-health`,
`/cd-test-architecture`, `/triage`, `/harness-audit`). Each skill references
this file rather than restating the behavior, so the wording never drifts.

This file defines *how `--pdf` behaves*. `hooks/lib/report_pdf.py` is the render
engine it calls; [`report-to-pdf.md`](report-to-pdf.md) is the underlying
recipe; [`report-output-location.md`](report-output-location.md) details the
`.dev-team-reports/` write rules — the per-skill paths are in the table below.

## Contract

When a skill is invoked with `--pdf`:

1. **Render the report this run actually wrote — not a fixed path.** After the
   skill has written its Markdown report, resolve the concrete path that run
   produced (each skill knows its own — see the table below) and render it:

   ```bash
   sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" <the-report-path-just-written>
   ```

   The module prints a `Rendering PDF via <engine>…` progress line (the
   render can take several seconds on a cold headless-Chrome start), then one
   result line. Surface the output; on success it states the sibling PDF path
   and the engine used.

2. **No report written → no-op with a message, never an error.** If the run
   wrote no Markdown report (see the no-file modes below), do **not** invoke the
   module. State plainly: `--pdf: no report file was written this run, nothing to render.` and continue. This is a no-op, not a failure.

3. **No engine available → skip, never fail.** If `report_pdf.py` finds no PDF
   engine it exits 0 with an install hint and leaves the Markdown untouched.
   `--pdf` never changes the skill's own exit status or primary output — PDF is
   strictly additive.

4. **`--json` output stays pure.** When a skill also runs in a machine-readable
   `--json` mode, all `--pdf` status text (progress, skip, no-op) goes to
   **stderr** so stdout remains valid JSON for scripted callers.

**Distinct wording — keep these two cases lexically separate** so a reader can
self-diagnose which they hit:

- **skip** (no engine): `No PDF engine found. Install one, …` (from the module).
- **no-op** (no report file written): `--pdf: no report file was written this run, nothing to render.`

## Per-skill report path and no-file modes

| Skill | Report path this run wrote | `--pdf` no-op when |
|-------|----------------------------|--------------------|
| `/code-review` | `.dev-team-reports/code-review.md` | `--json` or `--internal` (no file written) |
| `/triage` | `.dev-team-reports/triage/<slug>.md` (the path just written) | never — it always writes a file |
| `/test-health` | `.dev-team-reports/test-health-<date>.md` | never — it always writes a file |
| `/cd-test-architecture` | `.dev-team-reports/cd-test-architecture-<app>.md` | single-component **chat-only** run (no file) |
| `/harness-audit` | `.dev-team-reports/harness-audit-<date>.md`, or the `--output <path>` override | never — it always writes a file |

A new report-producing skill inherits `--pdf` by adding a row here, documenting
`--pdf` in its `argument-hint`, and calling `report_pdf.py` on the path it wrote
— no new render logic.
