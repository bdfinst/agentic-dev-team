---
name: report-pdf
description: >-
  Render a dev-team Markdown report to a polished, shareable PDF. Use when the
  user says "make a PDF of the report", "export the code-review report as PDF",
  "turn DEV_TEAM_REPORTS/code-review.md into a PDF", or wants any
  DEV_TEAM_REPORTS or reports Markdown file as a styled document to attach to a
  ticket or hand to a non-terminal stakeholder.
argument-hint: "<path.md> [--out <path>]"
user-invocable: true
allowed-tools: Bash
---

# Report PDF

Role: worker. This command renders one Markdown report to a styled PDF via the
shared render module. It is a mechanical wrapper — no reasoning, no file-by-file
searching. It never modifies the source Markdown.

You have been invoked with the `/report-pdf` command.

## Arguments

- `<path.md>` (required) — path to the Markdown report to render (for example
  `DEV_TEAM_REPORTS/code-review.md` or `reports/test-health-2026-07-16.md`).
- `--out <path>` (optional) — output PDF path. Defaults to the source path with
  a `.pdf` extension, next to the source. A missing parent directory is created.

If no path argument is supplied, report `path required — usage: /report-pdf <path.md> [--out <path>]` and stop.

## Steps

Invoke the shared render module through `hooks/py.sh` (never `python3`
directly — the shim resolves a real Python 3 on Windows too), passing the
arguments through verbatim:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/report_pdf.py" <path.md> [--out <path>]
```

The module detects a PDF engine (fallback order: pandoc + headless
Chrome/Chromium → pandoc + weasyprint → pandoc + wkhtmltopdf → md-to-pdf) via
runtime probes, converts the report with the bundled `report-print.css`, and
prints a `Rendering PDF via <engine>…` progress line followed by one result
line. Report its output as-is:

- **Exit 0, `PDF written: …`** — the styled PDF was produced; report the output
  path and engine verbatim.
- **Exit 0, skip message (`No PDF engine found. Install one, …`)** — no engine
  was available. Report the skip message verbatim, including the single install
  hint. This is non-fatal: the source Markdown is untouched.
- **Exit 1, `PDF not rendered: …`** — the source file was missing, or an engine
  was present but conversion failed. Surface the stderr message verbatim.
- **Exit 2** — usage error (argparse); surface the message verbatim.

Do not add commentary beyond the module's own lines.

## Related

- `hooks/lib/report_pdf.py` — the shared render module this command wraps; the
  same module backs the `--pdf` flag on report-producing skills (see
  [`../../knowledge/report-pdf-integration.md`](../../knowledge/report-pdf-integration.md)).
- [`../../knowledge/report-to-pdf.md`](../../knowledge/report-to-pdf.md) — the
  underlying pandoc + headless-Chrome recipe and why this toolchain.
- [`../../knowledge/report-output-location.md`](../../knowledge/report-output-location.md)
  — where each report-producing skill writes its Markdown.
