"""Unit tests for hooks/lib/report_pdf.py (#1114).

Covers the Slice 1 acceptance criteria for the shared PDF render module:

- engine detection follows the fallback order (AC5)
- both pipeline branches render: pandoc-mediated and direct md-to-pdf (AC9)
- md-to-pdf is never gated behind pandoc (Risks)
- skip-with-single-install-hint when no engine (AC6)
- render-failure when an engine is present but conversion fails (AC9)
- --out handling incl. parent-directory creation (AC2)
- source file not found (AC9)
- detection uses runtime probes only — no hard-coded OS paths (AC7)
- CLI exit-code contract (AC6/AC9)

All subprocess/engine calls are mocked; no real pandoc/Chrome is invoked.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import report_pdf

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def make_runner(fail_on=None):
    """Return a fake subprocess runner that creates the output file a real
    engine would produce and returns success — unless ``fail_on`` (a substring)
    appears in the command, in which case it reports a non-zero exit."""

    def runner(cmd, capture_output=True, text=True, timeout=None):
        joined = " ".join(cmd)
        if fail_on is not None and fail_on in joined:
            return subprocess.CompletedProcess(cmd, 1, "", f"boom: {fail_on}")
        # pandoc -o <html>
        if cmd[0] == "pandoc" and "-o" in cmd:
            Path(cmd[cmd.index("-o") + 1]).write_text("<html><head></head><body></body></html>")
        # chrome --print-to-pdf=<out>
        for arg in cmd:
            if arg.startswith("--print-to-pdf="):
                Path(arg.split("=", 1)[1]).write_bytes(b"%PDF-1.4 fake")
        # weasyprint/wkhtmltopdf <html> <out>
        if cmd[0] in ("weasyprint", "wkhtmltopdf"):
            Path(cmd[-1]).write_bytes(b"%PDF-1.4 fake")
        # md-to-pdf <src.md> -> <src.pdf>
        if cmd[0] == "md-to-pdf":
            Path(cmd[1]).with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    return runner


def _which_map(mapping):
    """Build a shutil.which replacement from a name->path/None mapping."""

    def which(name):
        return mapping.get(name)

    return which


@pytest.fixture
def report(tmp_path):
    src = tmp_path / "code-review.md"
    src.write_text("# Report\n\n| file | line |\n|------|------|\n| `a/very/long/path.py` | 12 |\n")
    return src


# ---------------------------------------------------------------------------
# detect_engine — fallback order (AC5)
# ---------------------------------------------------------------------------


def test_detect_prefers_chrome_when_pandoc_and_chrome_present(monkeypatch):
    monkeypatch.setattr(report_pdf.shutil, "which", _which_map({"pandoc": "/p"}))
    monkeypatch.setattr(report_pdf, "_chrome_binary", lambda: "/chrome")
    engine = report_pdf.detect_engine()
    assert engine.name == "chrome"
    assert engine.kind == report_pdf._PANDOC
    assert engine.binary == "/chrome"


def test_detect_falls_back_to_weasyprint_then_wkhtmltopdf(monkeypatch):
    monkeypatch.setattr(report_pdf, "_chrome_binary", lambda: None)
    monkeypatch.setattr(
        report_pdf.shutil, "which", _which_map({"pandoc": "/p", "weasyprint": "/w"})
    )
    assert report_pdf.detect_engine().name == "weasyprint"

    monkeypatch.setattr(
        report_pdf.shutil, "which", _which_map({"pandoc": "/p", "wkhtmltopdf": "/wk"})
    )
    assert report_pdf.detect_engine().name == "wkhtmltopdf"


def test_detect_uses_mdtopdf_without_pandoc(monkeypatch):
    """md-to-pdf must be offered even when pandoc is absent (Risks item)."""
    monkeypatch.setattr(report_pdf, "_chrome_binary", lambda: None)
    monkeypatch.setattr(report_pdf.shutil, "which", _which_map({"md-to-pdf": "/m"}))
    engine = report_pdf.detect_engine()
    assert engine.name == "md-to-pdf"
    assert engine.kind == report_pdf._DIRECT


def test_detect_returns_none_when_nothing_available(monkeypatch):
    monkeypatch.setattr(report_pdf, "_chrome_binary", lambda: None)
    monkeypatch.setattr(report_pdf.shutil, "which", _which_map({}))
    assert report_pdf.detect_engine() is None


def test_pandoc_alone_does_not_short_circuit_skip(monkeypatch):
    """pandoc present but no consuming engine and no md-to-pdf -> no engine."""
    monkeypatch.setattr(report_pdf, "_chrome_binary", lambda: None)
    monkeypatch.setattr(report_pdf.shutil, "which", _which_map({"pandoc": "/p"}))
    assert report_pdf.detect_engine() is None


# ---------------------------------------------------------------------------
# detection uses runtime probes only (AC7)
# ---------------------------------------------------------------------------


def test_detection_is_probe_driven_no_hardcoded_paths(monkeypatch):
    monkeypatch.setattr(report_pdf.platform, "system", lambda: "Linux")
    monkeypatch.setattr(report_pdf.shutil, "which", _which_map({}))
    # No PATH hit and (Linux) no app-path candidates -> None, purely from probes.
    assert report_pdf.detect_engine() is None
    # A PATH hit alone flips the result — proof detection is driven by probes.
    monkeypatch.setattr(
        report_pdf.shutil, "which", _which_map({"pandoc": "/p", "chromium": "/c"})
    )
    assert report_pdf.detect_engine().name == "chrome"


def test_chrome_binary_probes_darwin_app_path(monkeypatch):
    """When nothing is on PATH, the macOS app-path probe is exercised."""
    monkeypatch.setattr(report_pdf.shutil, "which", _which_map({}))
    monkeypatch.setattr(report_pdf.platform, "system", lambda: "Darwin")
    app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    monkeypatch.setattr(report_pdf.os.path, "isfile", lambda p: p == app)
    monkeypatch.setattr(report_pdf.os, "access", lambda p, mode: p == app)
    assert report_pdf._chrome_binary() == app


# ---------------------------------------------------------------------------
# render — pandoc-mediated happy path (AC1/AC9)
# ---------------------------------------------------------------------------


def test_render_pandoc_mediated_happy_path(report):
    engine = report_pdf.Engine("chrome", report_pdf._PANDOC, binary="/chrome")
    result = report_pdf.render(str(report), engine=engine, runner=make_runner())
    assert result.rendered is True
    assert result.engine == "chrome"
    assert result.out_path == str(report.with_suffix(".pdf"))
    assert report.with_suffix(".pdf").is_file()


def test_render_direct_mdtopdf_never_invokes_pandoc(report):
    calls = []

    def recording_runner(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd[0])
        return make_runner()(cmd, capture_output=capture_output, text=text, timeout=timeout)

    engine = report_pdf.Engine("md-to-pdf", report_pdf._DIRECT)
    result = report_pdf.render(str(report), engine=engine, runner=recording_runner)
    assert result.rendered is True
    assert result.engine == "md-to-pdf"
    assert "pandoc" not in calls


# ---------------------------------------------------------------------------
# skip / failure / errors (AC6/AC9)
# ---------------------------------------------------------------------------


def test_render_skips_with_single_install_hint_when_no_engine(report, monkeypatch):
    monkeypatch.setattr(report_pdf, "detect_engine", lambda: None)
    result = report_pdf.render(str(report), runner=make_runner())
    assert result.rendered is False
    assert result.error is None
    assert result.install_hint and "Install one" in result.install_hint
    assert not report.with_suffix(".pdf").exists()


def test_render_reports_failure_when_engine_present_but_conversion_fails(report):
    engine = report_pdf.Engine("wkhtmltopdf", report_pdf._PANDOC)
    result = report_pdf.render(
        str(report), engine=engine, runner=make_runner(fail_on="wkhtmltopdf")
    )
    assert result.rendered is False
    assert result.error and "wkhtmltopdf" in result.error
    assert result.install_hint is None


def test_render_reports_pandoc_step1_failure(report):
    engine = report_pdf.Engine("chrome", report_pdf._PANDOC, binary="/chrome")
    result = report_pdf.render(
        str(report), engine=engine, runner=make_runner(fail_on="pandoc")
    )
    assert result.rendered is False
    assert result.error and result.error.startswith("pandoc failed")


def test_render_reports_direct_mdtopdf_failure(report):
    engine = report_pdf.Engine("md-to-pdf", report_pdf._DIRECT)
    result = report_pdf.render(
        str(report), engine=engine, runner=make_runner(fail_on="md-to-pdf")
    )
    assert result.rendered is False
    assert result.error and "md-to-pdf" in result.error


def test_render_guards_engine_success_but_no_pdf(report):
    """Engine exits 0 but writes no file -> the false-success guard fires."""

    def silent_runner(cmd, capture_output=True, text=True, timeout=None):
        if cmd[0] == "pandoc":
            Path(cmd[cmd.index("-o") + 1]).write_text("<html><head></head></html>")
        # engine step: return 0 but write nothing
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    engine = report_pdf.Engine("weasyprint", report_pdf._PANDOC)
    result = report_pdf.render(str(report), engine=engine, runner=silent_runner)
    assert result.rendered is False
    assert result.error and "no PDF was produced" in result.error


def test_render_direct_moves_produced_pdf_to_custom_out(report, tmp_path):
    out = tmp_path / "elsewhere" / "final.pdf"
    stylesheet_flag = {}

    def runner(cmd, capture_output=True, text=True, timeout=None):
        if cmd[0] == "md-to-pdf":
            stylesheet_flag["seen"] = "--stylesheet" in cmd
            Path(cmd[1]).with_suffix(".pdf").write_bytes(b"%PDF fake")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    engine = report_pdf.Engine("md-to-pdf", report_pdf._DIRECT)
    result = report_pdf.render(str(report), str(out), engine=engine, runner=runner)
    assert result.rendered is True
    assert out.is_file()
    # the produced sibling pdf was moved, not left behind
    assert not report.with_suffix(".pdf").exists()
    assert stylesheet_flag["seen"] is True


def test_render_file_not_found(tmp_path):
    result = report_pdf.render(str(tmp_path / "missing.md"), runner=make_runner())
    assert result.rendered is False
    assert result.error and "file not found" in result.error


def test_render_out_creates_missing_parent_dir(report, tmp_path):
    out = tmp_path / "nested" / "deep" / "out.pdf"
    engine = report_pdf.Engine("weasyprint", report_pdf._PANDOC)
    result = report_pdf.render(
        str(report), str(out), engine=engine, runner=make_runner()
    )
    assert result.rendered is True
    assert out.is_file()


# ---------------------------------------------------------------------------
# hardening: sandbox / injected CSS / no-JS Chrome / timeout (security + correctness review)
# ---------------------------------------------------------------------------


def test_pandoc_cmd_is_sandboxed_and_omits_css_flag():
    cmd = report_pdf._pandoc_html_cmd(Path("a.md"), Path("a.html"))
    assert "--sandbox" in cmd
    # CSS is injected in Python, not via pandoc --css (sandbox would block it).
    assert "--css" not in cmd


def test_css_is_injected_into_html_head(report):
    engine = report_pdf.Engine("weasyprint", report_pdf._PANDOC)
    captured = {}

    def runner(cmd, capture_output=True, text=True, timeout=None):
        if cmd[0] == "pandoc":
            Path(cmd[cmd.index("-o") + 1]).write_text("<html><head></head><body></body></html>")
        if cmd[0] == "weasyprint":
            # the html passed to the engine should already carry the inlined CSS
            captured["html"] = Path(cmd[1]).read_text()
            Path(cmd[-1]).write_bytes(b"%PDF fake")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    result = report_pdf.render(str(report), engine=engine, runner=runner)
    assert result.rendered is True
    assert "<style>" in captured["html"]
    assert "overflow-wrap" in captured["html"]


def test_chrome_cmd_disables_javascript():
    engine = report_pdf.Engine("chrome", report_pdf._PANDOC, binary="/chrome")
    cmd = report_pdf._engine_pdf_cmd(engine, Path("a.html"), Path("out.pdf"))
    assert "--disable-javascript" in cmd
    # the output path is passed absolute so a leading-dash value can't be a flag
    printed = [a for a in cmd if a.startswith("--print-to-pdf=")][0]
    assert printed.split("=", 1)[1].startswith("/")


def test_render_reports_timeout_as_engine_failure(report):
    def hanging_runner(cmd, capture_output=True, text=True, timeout=None):
        raise subprocess.TimeoutExpired(cmd, timeout or 1)

    engine = report_pdf.Engine("chrome", report_pdf._PANDOC, binary="/chrome")
    result = report_pdf.render(str(report), engine=engine, runner=hanging_runner)
    assert result.rendered is False
    assert result.error and "timed out" in result.error


# ---------------------------------------------------------------------------
# install_hint / css
# ---------------------------------------------------------------------------


def test_install_hint_is_os_specific_single_path(monkeypatch):
    monkeypatch.setattr(report_pdf.platform, "system", lambda: "Darwin")
    assert "brew install" in report_pdf.install_hint()
    monkeypatch.setattr(report_pdf.platform, "system", lambda: "Linux")
    assert "apt-get" in report_pdf.install_hint()
    monkeypatch.setattr(report_pdf.platform, "system", lambda: "Windows")
    assert "md-to-pdf" in report_pdf.install_hint()


def test_inject_css_no_op_without_stylesheet(tmp_path):
    html = tmp_path / "x.html"
    html.write_text("<html><head></head><body></body></html>")
    report_pdf._inject_css(html, tmp_path / "missing.css")  # not a file
    assert "<style>" not in html.read_text()


def test_inject_css_prepends_when_no_head(tmp_path):
    html = tmp_path / "x.html"
    html.write_text("<body>no head here</body>")
    css = tmp_path / "s.css"
    css.write_text("body{color:red}")
    report_pdf._inject_css(html, css)
    text = html.read_text()
    assert text.startswith("<style>")
    assert "color:red" in text


def test_bundled_css_exists_and_wraps_wide_cells():
    css = report_pdf.default_css_path()
    assert css.is_file()
    text = css.read_text()
    # wide file:line cells must wrap, not clip
    assert "overflow-wrap" in text
    assert "word-break" in text
    assert "page-break-inside" in text


# ---------------------------------------------------------------------------
# CLI contract (AC6/AC9)
# ---------------------------------------------------------------------------


def test_cli_exit_zero_on_skip(report, monkeypatch, capsys):
    monkeypatch.setattr(report_pdf, "detect_engine", lambda: None)
    rc = report_pdf.main([str(report)])
    assert rc == 0
    assert "Install one" in capsys.readouterr().out


def test_cli_exit_one_on_missing_file(tmp_path, capsys):
    rc = report_pdf.main([str(tmp_path / "nope.md")])
    assert rc == 1
    assert "not rendered" in capsys.readouterr().err


def test_cli_exit_two_on_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        report_pdf.main([])  # no path positional
    assert exc.value.code == 2


def test_cli_success_prints_progress_and_result(report, monkeypatch, capsys):
    engine = report_pdf.Engine("chrome", report_pdf._PANDOC, binary="/chrome")
    monkeypatch.setattr(report_pdf, "detect_engine", lambda: engine)
    monkeypatch.setattr(
        report_pdf.subprocess, "run", make_runner()
    )
    rc = report_pdf.main([str(report)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Rendering PDF via chrome" in out
    assert "PDF written" in out
