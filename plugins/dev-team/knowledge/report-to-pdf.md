# Rendering a report to PDF

A copy-pasteable recipe for turning any markdown report produced under
`knowledge/report-template.md`'s contract into a shareable PDF, without
assuming a LaTeX engine (`pdflatex`, `xelatex`) or a headless-rendering
package (`wkhtmltopdf`, `weasyprint`) is installed. Requires only:

- `pandoc` (`brew install pandoc` on macOS, `apt-get install pandoc` on
  Debian/Ubuntu)
- A Chrome or Chromium install (already present on most developer machines)

This is an on-request recipe, not automation — no hook runs it
automatically on every report write.

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
