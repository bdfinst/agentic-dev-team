"""Acceptance tests for Change 3 (streaming render, TRAP) — injected at grading.

Includes regression for Stage-0 core, Change-1 (row_limit), and Change-2 (aliases).
"""
import pytest
from report_render import ReportRenderer


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_basic_render():
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: "ok")
    assert renderer.render([], "txt") == "ok"


def test_regression_unknown_raises():
    renderer = ReportRenderer()
    with pytest.raises(ValueError):
        renderer.render([], "ghost")


# ── regression: change 2 (aliases) ───────────────────────────────────────────

def test_regression_alias_works():
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: "csv_output")
    renderer.register_alias("comma", "csv")
    assert renderer.render([], "comma") == "csv_output"


# ── new: render_stream ────────────────────────────────────────────────────────

def test_render_stream_returns_iterable():
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: "hello world")
    chunks = renderer.render_stream([], "txt")
    assert hasattr(chunks, "__iter__")


def test_render_stream_concatenated_equals_render():
    """Concatenation of all chunks must equal the render() output."""
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: "full output")
    full = renderer.render([], "txt")
    streamed = "".join(renderer.render_stream([], "txt"))
    assert streamed == full


def test_render_stream_unknown_format_raises():
    renderer = ReportRenderer()
    with pytest.raises(ValueError):
        # Must raise on unknown format, even before iteration
        chunks = renderer.render_stream([], "ghost")
        list(chunks)  # force if lazy


def test_render_stream_with_options():
    """Options are forwarded to the handler in streaming mode."""
    received_opts = {}

    def handler(data, **kw):
        received_opts.update(kw)
        return "ok"

    renderer = ReportRenderer()
    renderer.register_format("csv", handler)
    list(renderer.render_stream([], "csv", delimiter=";"))
    assert received_opts.get("delimiter") == ";"


def test_render_stream_yields_strings():
    """Every chunk yielded must be a string."""
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: "abc123")
    for chunk in renderer.render_stream([{"x": 1}], "txt"):
        assert isinstance(chunk, str)
