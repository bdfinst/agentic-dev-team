"""Acceptance tests for Change 1 (row_limit) — injected at grading time only.

Includes regression for Stage-0 core behaviour.
"""
import pytest
from report_render import ReportRenderer


# ── regression: core ──────────────────────────────────────────────────────────

def test_regression_render_calls_handler():
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: "ok")
    assert renderer.render([], "txt") == "ok"


def test_regression_unknown_format_raises():
    renderer = ReportRenderer()
    with pytest.raises(ValueError):
        renderer.render([], "ghost")


def test_regression_available_formats():
    renderer = ReportRenderer()
    renderer.register_format("json", lambda data, **kw: "")
    assert "json" in renderer.available_formats()


# ── new: row_limit ────────────────────────────────────────────────────────────

def test_row_limit_truncates_data_passed_to_handler():
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "")
    data = [{"i": i} for i in range(5)]
    renderer.render(data, "txt", row_limit=3)
    assert len(received[0]) == 3


def test_row_limit_none_passes_all_rows():
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "")
    data = [{"i": i} for i in range(5)]
    renderer.render(data, "txt", row_limit=None)
    assert len(received[0]) == 5


def test_row_limit_larger_than_data_passes_all_rows():
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "")
    data = [{"i": i} for i in range(3)]
    renderer.render(data, "txt", row_limit=100)
    assert len(received[0]) == 3


def test_row_limit_zero_passes_empty_list():
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "")
    renderer.render([{"a": 1}], "txt", row_limit=0)
    assert received[0] == []


def test_row_limit_not_forwarded_to_handler_as_option():
    """row_limit must NOT appear in the **options the handler receives."""
    received_opts = {}
    renderer = ReportRenderer()

    def capture(data, **kw):
        received_opts.update(kw)
        return ""

    renderer.register_format("txt", capture)
    renderer.render([{"a": 1}], "txt", row_limit=2, delimiter=";")
    assert "row_limit" not in received_opts
    assert received_opts.get("delimiter") == ";"
