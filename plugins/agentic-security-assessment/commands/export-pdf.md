---
name: export-pdf
description: Convert a Markdown report to PDF using pandoc (preferred) or weasyprint (fallback). Uses the bundled CSS stylesheet for A4 layout, confidentiality footer, and executive-audience styling. Skips gracefully if neither tool is installed.
argument-hint: "<report.md> [--output <report.pdf>] [--css <path>]"
user-invocable: true
allowed-tools: Read, Bash
---

# /export-pdf

You have been invoked with the `/export-pdf` command.

## Role

Converter from Markdown to PDF. Uses `pandoc` when available (cleaner tables, wider Markdown support); falls back to `weasyprint` when pandoc is absent; skips with a warning when neither is installed.

Used for:
- Executive reports from `/security-assessment` (`memory/report-<slug>.md`)
- Red-team reports from `/redteam-model` (`harness/redteam/results/adversarial-report.md`)
- Cross-repo summaries from `/cross-repo-analysis`
- Any Markdown produced by this plugin's agents

## Parse arguments

Arguments: $ARGUMENTS

**Positional:** `<report.md>` — path to the input Markdown file.

**Flags:**
- `--output <path>`: output PDF path. Default: same basename with `.pdf` extension.
- `--css <path>`: custom CSS stylesheet. Default: `plugins/agentic-security-assessment/templates/report-css/default.css`.

## Steps

### 1. Validate inputs

- Input file exists and is readable.
- If `--output` is passed, its parent directory exists.
- If `--css` is passed, the CSS file exists.

### 2. Detect available converter

Check in order:

1. `pandoc` + `wkhtmltopdf` (or pandoc with `--pdf-engine=weasyprint` if weasyprint is installed).
2. `weasyprint` with a small markdown-to-html wrapper.
3. Neither → skip.

### 3. Convert

**Preferred (pandoc):**

```bash
pandoc "$INPUT" \
  --pdf-engine=weasyprint \
  --css="$CSS" \
  --standalone \
  --metadata title="$(basename "$INPUT" .md)" \
  -o "$OUTPUT"
```

**Fallback (weasyprint + python-markdown):**

```bash
python3 -c "
import sys, markdown
from weasyprint import HTML, CSS
with open('$INPUT') as f:
    md_text = f.read()
html_body = markdown.markdown(md_text, extensions=['tables', 'fenced_code', 'codehilite'])
html = f'<html><head><meta charset=\"utf-8\"></head><body>{html_body}</body></html>'
HTML(string=html).write_pdf('$OUTPUT', stylesheets=[CSS(filename='$CSS')])
"
```

### 4. Report

On success:
```
PDF written: /absolute/path/to/report.pdf
```

Print the **absolute** path — some downstream tooling expects an absolute path.

On graceful skip (neither tool):
```
SKIP: pandoc and weasyprint both absent; PDF not produced.
      Install one:
        brew install pandoc weasyprint   (macOS)
        apt install pandoc               (Linux)
        pip install weasyprint           (any)
      The markdown report remains at: $INPUT
```

Exit 0 in both cases (skip is not a failure).

## Escalation

Stop and ask the user when:
- Input file does not exist.
- Output directory is not writable.
- CSS file specified by `--css` does not exist (default CSS should always exist; if missing, report as a plugin install issue).

## CSS stylesheet

The bundled CSS at `plugins/agentic-security-assessment/templates/report-css/default.css` is modelled on the `opus_repo_scan_test` reference's `utilities/convert_report.py` CSS:

- A4 page size, 2cm × 1.5cm margins
- Page footer: confidentiality notice (center) + page N of M (right)
- Red accent (`#c00`) on H1 underline and blockquote border
- Zebra-striped tables
- Monospace code blocks; syntax highlighting via `codehilite`
- Muted color scheme, no decorative images

Override via `--css <path>` for organization-specific branding.

## Integration

- Runs after `/security-assessment` produces `memory/report-<slug>.md`.
- Runs after `/redteam-model` produces `harness/redteam/results/adversarial-report.md`.
- Not run automatically — user invokes at their discretion.
