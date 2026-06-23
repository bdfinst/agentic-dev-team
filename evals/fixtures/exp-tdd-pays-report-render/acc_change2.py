"""Acceptance tests for Change 2 (format aliases) — injected at grading time only.

Includes regression for Stage-0 core and Change-1 (row_limit).
"""
import pytest
from report_render import ReportRenderer


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_basic_render():
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: "hi")
    assert renderer.render([], "txt") == "hi"


def test_regression_unknown_raises():
    renderer = ReportRenderer()
    with pytest.raises(ValueError):
        renderer.render([], "ghost")


# ── regression: change 1 (row_limit) ─────────────────────────────────────────

def test_regression_row_limit_truncates():
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "")
    renderer.render([{"i": i} for i in range(5)], "txt", row_limit=2)
    assert len(received[0]) == 2


# ── new: aliases ──────────────────────────────────────────────────────────────

def test_alias_resolves_to_same_handler():
    log = []
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: log.append("csv") or "result")
    renderer.register_alias("comma", "csv")
    out = renderer.render([], "comma")
    assert out == "result"
    assert "csv" in log


def test_alias_for_unknown_format_raises():
    renderer = ReportRenderer()
    with pytest.raises(ValueError):
        renderer.register_alias("alias", "ghost")


def test_alias_appears_in_available_formats():
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: "")
    renderer.register_alias("comma", "csv")
    assert "comma" in renderer.available_formats()


def test_alias_with_options_forwarded():
    received_opts = {}
    renderer = ReportRenderer()

    def handler(data, **kw):
        received_opts.update(kw)
        return ""

    renderer.register_format("csv", handler)
    renderer.register_alias("tsv", "csv")
    renderer.render([], "tsv", delimiter="\t")
    assert received_opts.get("delimiter") == "\t"


def test_register_format_over_alias_replaces_alias():
    """Registering a format name that was an alias replaces the alias."""
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: "original")
    renderer.register_alias("comma", "csv")
    renderer.register_format("comma", lambda data, **kw: "new")
    assert renderer.render([], "comma") == "new"
