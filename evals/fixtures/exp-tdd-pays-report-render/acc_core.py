"""Core acceptance tests for report_render.py — injected at grading time only.

Tests behaviours stated in both spec_clear.md and spec_vague.md.
"""
import pytest
from report_render import ReportRenderer


def test_register_and_render_calls_handler():
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "ok")
    result = renderer.render([{"a": 1}], "txt")
    assert result == "ok"
    assert received[0] == [{"a": 1}]


def test_render_returns_handler_string():
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: "header\nrow1")
    assert renderer.render([], "csv") == "header\nrow1"


def test_unknown_format_raises_value_error():
    renderer = ReportRenderer()
    with pytest.raises(ValueError):
        renderer.render([{"a": 1}], "nonexistent")


def test_available_formats_lists_registered_names():
    renderer = ReportRenderer()
    renderer.register_format("json", lambda data, **kw: "[]")
    renderer.register_format("csv", lambda data, **kw: "")
    names = renderer.available_formats()
    assert "json" in names
    assert "csv" in names


def test_empty_data_calls_handler():
    called = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: called.append(data) or "")
    renderer.render([], "txt")
    assert called[0] == []


def test_options_forwarded_to_handler():
    received_opts = {}
    renderer = ReportRenderer()

    def handler(data, **kw):
        received_opts.update(kw)
        return ""

    renderer.register_format("csv", handler)
    renderer.render([{"x": 1}], "csv", delimiter=";", quote_char='"')
    assert received_opts.get("delimiter") == ";"


def test_two_formats_both_registered():
    renderer = ReportRenderer()
    renderer.register_format("json", lambda data, **kw: "[]")
    renderer.register_format("csv", lambda data, **kw: "")
    result_json = renderer.render([], "json")
    result_csv = renderer.render([], "csv")
    assert result_json == "[]"
    assert result_csv == ""
