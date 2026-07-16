#!/usr/bin/env python3
"""Render a Markdown report to a styled PDF.

Backs the ``/report-pdf`` command and the ``--pdf`` flag on report-producing
skills. Stdlib only, Python 3.8+ (ADR 0014 / 0015). Detects a PDF engine via
runtime probes and converts Markdown -> PDF, **never raising for a missing
engine** — callers get a structured :class:`RenderResult` and the underlying
Markdown report is left untouched.

Two pipelines sit behind one abstraction:

- **pandoc-mediated** — Markdown -> self-contained HTML (with the bundled
  ``report-print.css``) via pandoc, then HTML -> PDF via headless
  Chrome/Chromium, weasyprint, or wkhtmltopdf.
- **direct** — ``md-to-pdf`` consumes Markdown directly (no pandoc).

Fallback order: Chrome/Chromium -> weasyprint -> wkhtmltopdf -> md-to-pdf. The
first three require pandoc; md-to-pdf does not.

State is read off a single :class:`RenderResult`:

- success  -> ``rendered=True``, ``engine``/``out_path`` set, reason fields None
- skip     -> ``rendered=False``, ``reason``+``install_hint`` set, ``error`` None
- failure  -> ``rendered=False``, ``error`` set, ``reason``/``install_hint`` None

CLI contract (``report_pdf.py <md> [--out <path>]``):

    stdout : a ``Rendering …`` progress line, then one result line
    exit 0 : rendered, or skipped (no engine) — the report is always safe
    exit 1 : source file not found, or an engine was present but failed
    exit 2 : usage error (no path given)
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

# Detection order. ``kind`` is the pipeline: "pandoc" engines consume HTML that
# pandoc produces; "direct" engines consume Markdown themselves.
_PANDOC = "pandoc"
_DIRECT = "direct"

# Upper bound (seconds) on any single engine/pandoc invocation. A wedged
# headless Chrome must surface as an engine failure, never an indefinite hang.
_TIMEOUT_SECONDS = 120

# PATH names probed for a Chrome/Chromium binary, in preference order.
_CHROME_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
)


@dataclass
class Engine:
    """A resolved PDF engine: its ``name``, pipeline ``kind``, and (for Chrome)
    the concrete ``binary`` path a PATH/app-path probe found."""

    name: str
    kind: str
    binary: Optional[str] = None


@dataclass
class RenderResult:
    """Outcome of a render attempt — the single contract both surfaces key off.

    See the module docstring for the field discriminant across
    success / skip / failure.
    """

    rendered: bool
    engine: Optional[str] = None
    out_path: Optional[str] = None
    reason: Optional[str] = None
    install_hint: Optional[str] = None
    error: Optional[str] = None


def _chrome_binary() -> Optional[str]:
    """Locate a Chrome/Chromium binary via runtime probes only.

    PATH names first (cross-OS), then OS-specific application paths chosen by
    ``platform.system()`` so the probe stays a runtime decision (mockable in
    tests) rather than a hard-coded constant.
    """
    for name in _CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    system = platform.system()
    candidates: List[str] = []
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Windows":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(
                    os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
                )
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def detect_engine() -> Optional[Engine]:
    """Return the first available engine in fallback order, or ``None``.

    Chrome/weasyprint/wkhtmltopdf are only offered when pandoc is present (they
    consume pandoc's HTML). md-to-pdf is offered whether or not pandoc exists —
    it must never be gated behind pandoc.
    """
    if shutil.which("pandoc"):
        chrome = _chrome_binary()
        if chrome:
            return Engine("chrome", _PANDOC, binary=chrome)
        if shutil.which("weasyprint"):
            return Engine("weasyprint", _PANDOC)
        if shutil.which("wkhtmltopdf"):
            return Engine("wkhtmltopdf", _PANDOC)
    if shutil.which("md-to-pdf"):
        return Engine("md-to-pdf", _DIRECT)
    return None


def install_hint() -> str:
    """A single, OS-appropriate install suggestion — one actionable path, not a
    menu of every engine (the report is already saved; the PDF is the extra)."""
    system = platform.system()
    if system == "Darwin":
        cmd = "brew install pandoc && brew install --cask google-chrome"
    elif system == "Windows":
        cmd = "install pandoc + Google Chrome, or `npm i -g md-to-pdf`"
    else:
        cmd = "apt-get install pandoc chromium  (or `pip install weasyprint`)"
    return (
        f"No PDF engine found. Install one, e.g.: {cmd}. "
        "Markdown report saved; PDF skipped."
    )


def default_css_path() -> Path:
    """The bundled print stylesheet shipped with the plugin."""
    return Path(__file__).resolve().parents[2] / "knowledge" / "report-print.css"


def _pandoc_html_cmd(src: Path, html: Path) -> List[str]:
    # --sandbox blocks pandoc from fetching any external resource during
    # conversion, so a report embedding an attacker-influenced remote URL
    # (report content can quote code from a reviewed repo) cannot drive an
    # outbound request at build time (SSRF). The stylesheet is injected in
    # Python afterwards (_inject_css) — sandbox would otherwise block reading
    # even an explicitly-passed --css file.
    return [
        "pandoc",
        str(src),
        "-f",
        "gfm",
        "-t",
        "html5",
        "--standalone",
        "--sandbox",
        "--metadata",
        f"title={src.stem}",
        "-o",
        str(html),
    ]


def _inject_css(html: Path, css: Optional[Path]) -> None:
    """Inline the bundled stylesheet into the pandoc HTML head.

    Done in Python (not via pandoc ``--css``) because ``--sandbox`` blocks
    pandoc from reading the CSS file. No-op when no stylesheet is available.
    """
    if not (css and css.is_file()):
        return
    try:
        css_text = css.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # An unreadable/malformed stylesheet degrades to unstyled output —
        # never raises, matching the module's graceful-degradation contract.
        return
    style = f"<style>\n{css_text}\n</style>"
    doc = html.read_text(encoding="utf-8")
    if "</head>" in doc:
        doc = doc.replace("</head>", style + "\n</head>", 1)
    else:
        doc = style + "\n" + doc
    html.write_text(doc, encoding="utf-8")


def _engine_pdf_cmd(engine: Engine, html: Path, out: Path) -> List[str]:
    # Absolute output paths so a value beginning with '-' can never be parsed
    # as an option by a positional-arg engine (weasyprint/wkhtmltopdf).
    out_abs = str(out.resolve())
    if engine.name == "chrome":
        return [
            engine.binary or "google-chrome",
            "--headless=new",
            "--disable-gpu",
            # No JavaScript: a Markdown-derived report never needs it, and it
            # closes the headless-Chrome JS-execution vector on report content.
            "--disable-javascript",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=10000",
            f"--print-to-pdf={out_abs}",
            html.resolve().as_uri(),
        ]
    if engine.name == "weasyprint":
        return ["weasyprint", str(html.resolve()), out_abs]
    if engine.name == "wkhtmltopdf":
        return ["wkhtmltopdf", str(html.resolve()), out_abs]
    raise ValueError(f"not a pandoc-mediated engine: {engine.name}")


def _mdtopdf_cmd(src: Path, css: Optional[Path]) -> List[str]:
    cmd = ["md-to-pdf", str(src)]
    if css and css.is_file():
        cmd += ["--stylesheet", str(css)]
    return cmd


def _run(runner: Callable, cmd: List[str]) -> subprocess.CompletedProcess:
    return runner(cmd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)


def _fail(engine_name: str, msg: str) -> RenderResult:
    return RenderResult(rendered=False, engine=engine_name, error=msg)


def _step_error(label: str, proc: subprocess.CompletedProcess) -> str:
    return f"{label} failed: {(proc.stderr or '').strip()}"


def _render_pandoc(
    engine: Engine, src: Path, out: Path, css: Optional[Path], runner: Callable
) -> Optional[str]:
    """pandoc-mediated pipeline (Markdown → HTML+CSS → PDF). Returns an error
    string on failure, or None on success. Always unlinks the temp HTML."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as handle:
        html = Path(handle.name)
    try:
        step1 = _run(runner, _pandoc_html_cmd(src, html))
        if step1.returncode != 0:
            return _step_error("pandoc", step1)
        _inject_css(html, css)
        step2 = _run(runner, _engine_pdf_cmd(engine, html, out))
        if step2.returncode != 0:
            return _step_error(engine.name, step2)
        return None
    finally:
        html.unlink(missing_ok=True)


def _render_direct(
    engine: Engine, src: Path, out: Path, css: Optional[Path], runner: Callable
) -> Optional[str]:
    """Direct md-to-pdf pipeline (no pandoc). Returns an error string on
    failure, or None on success."""
    produced = src.with_suffix(".pdf")
    step = _run(runner, _mdtopdf_cmd(src, css))
    if step.returncode != 0:
        return _step_error(engine.name, step)
    if produced.resolve() != out.resolve() and produced.is_file():
        shutil.move(str(produced), str(out))
    return None


def render(
    md_path: str,
    out_path: Optional[str] = None,
    *,
    engine: Optional[Engine] = None,
    css_path: Optional[str] = None,
    runner: Optional[Callable] = None,
) -> RenderResult:
    """Render ``md_path`` to a PDF, returning a :class:`RenderResult`.

    ``runner`` is injectable so tests never shell out to a real engine; it
    defaults to the module's current ``subprocess.run`` (resolved at call time,
    so a monkeypatch of it is honored).
    """
    if runner is None:
        runner = subprocess.run
    src = Path(md_path)
    if not src.is_file():
        return RenderResult(rendered=False, error=f"file not found: {md_path}")

    if engine is None:
        engine = detect_engine()
    if engine is None:
        return RenderResult(
            rendered=False, reason="no PDF engine available", install_hint=install_hint()
        )

    out = Path(out_path) if out_path else src.with_suffix(".pdf")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return RenderResult(rendered=False, engine=engine.name, error=str(exc))

    css = Path(css_path) if css_path else default_css_path()

    try:
        pipeline = _render_pandoc if engine.kind == _PANDOC else _render_direct
        err = pipeline(engine, src, out, css, runner)
        if err is not None:
            return _fail(engine.name, err)
    except subprocess.TimeoutExpired:
        return _fail(engine.name, f"{engine.name} timed out after {_TIMEOUT_SECONDS}s")
    except OSError as exc:
        return _fail(engine.name, str(exc))

    if not out.is_file():
        return _fail(engine.name, f"{engine.name} reported success but no PDF was produced")
    return RenderResult(rendered=True, engine=engine.name, out_path=str(out))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="report_pdf.py",
        description="Render a Markdown report to a styled PDF.",
    )
    parser.add_argument("path", help="path to the Markdown report (.md)")
    parser.add_argument(
        "--out", dest="out", default=None, help="output PDF path (default: next to source)"
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    src = Path(args.path)
    engine = detect_engine() if src.is_file() else None
    if engine is not None:
        print(f"Rendering PDF via {engine.name}…")
    result = render(args.path, args.out, engine=engine)

    if result.rendered:
        print(f"PDF written: {result.out_path} (engine: {result.engine})")
        return 0
    if result.error is not None:
        print(f"PDF not rendered: {result.error}", file=sys.stderr)
        return 1
    # skip (no engine) — non-fatal, the report is safe
    print(result.install_hint or result.reason or "PDF skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
