# Rendering a report to PDF

**Prefer the built-in command.** `/report-pdf <path.md> [--out <path>]` renders
any dev-team Markdown report (`.dev-team-reports/*.md` or `reports/*.md`) to a
styled PDF, and the `--pdf` flag on `/code-review`, `/test-health`,
`/cd-test-architecture`, `/triage`, and `/harness-audit` renders the report
that run just wrote. Both share `hooks/lib/report_pdf.py`, which bundles the
print stylesheet (`knowledge/report-print.css`), detects an engine with
graceful fallback, and skips with an install hint when none is present — see
[`report-pdf-integration.md`](report-pdf-integration.md). The recipe below is
the underlying mechanism, kept for reference and manual use.

A copy-pasteable recipe for turning any markdown report produced under
`knowledge/report-template.md`'s contract into a shareable PDF, without
assuming a LaTeX engine (`pdflatex`, `xelatex`) or a headless-rendering
package (`wkhtmltopdf`, `weasyprint`) is installed. Requires only:

- `pandoc` (`brew install pandoc` on macOS, `apt-get install pandoc` on
  Debian/Ubuntu)
- A Chrome or Chromium install (already present on most developer machines)

This is an on-request recipe, not automation — no hook runs it
automatically on every report write.

**Security note.** `report_pdf.py` hardens this recipe for report content that
may embed snippets from a repo under review: it runs pandoc with `--sandbox`
(no build-time resource fetches — blocks SSRF via a remote URL in the content),
injects the stylesheet in Python rather than via `--css` (sandbox blocks that
read), and invokes headless Chrome with `--disable-javascript`. The manual
recipe below omits these; use the command for untrusted content.

## Recipe

```bash
# 1. Markdown -> standalone HTML (self-contained: styling inlined, no external assets)
pandoc report.md -o report.html --standalone --embed-resources --metadata title="Report"

# 2. Standalone HTML -> PDF via headless Chrome's native print-to-pdf
#    macOS:
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="report.pdf" "$(pwd)/report.html"

#    Linux (path varies by distro/package: google-chrome, google-chrome-stable, chromium, chromium-browser):
google-chrome --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="report.pdf" "$(pwd)/report.html"
```

`report.pdf` is written to the current directory.

## Why this toolchain

- **No LaTeX assumption.** `pdflatex`/`xelatex` are not installed by default
  on most developer machines and are a heavy dependency to add just for
  occasional PDF export; `wkhtmltopdf`/`weasyprint` have their own native
  dependency chains (Qt WebKit, Cairo/Pango) that are equally not guaranteed
  present.
- **Chrome and pandoc are already common.** Both are already installed on
  most developer machines for unrelated reasons, so this recipe typically
  requires zero new installs.
- **`--embed-resources`** (pandoc ≥ 3.0; use `--self-contained` on older
  pandoc) inlines any CSS/images into the HTML so the print-to-pdf step has
  no external asset dependency, keeping the recipe reproducible from the
  markdown file alone.

## Related

- `knowledge/report-template.md` — the shared header/footer/empty-section
  contract most reports rendered with this recipe will already follow.
