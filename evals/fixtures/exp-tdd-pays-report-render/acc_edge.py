"""Edge-case acceptance tests for report_render.py — injected at grading time only.

Tests behaviours described in spec_clear.md but OMITTED from spec_vague.md.
"""
import pytest
from report_render import ReportRenderer


def test_re_register_replaces_handler():
    """Re-registering the same format name replaces the old handler."""
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: "v1")
    renderer.register_format("csv", lambda data, **kw: "v2")
    assert renderer.render([], "csv") == "v2"


def test_none_values_passed_as_is_to_handler():
    """None values in row dicts reach the handler unchanged."""
    received = []
    renderer = ReportRenderer()
    renderer.register_format("txt", lambda data, **kw: received.append(data) or "")
    renderer.render([{"a": None, "b": 1}], "txt")
    assert received[0][0]["a"] is None


def test_handler_exception_propagates():
    """Handler exceptions are not caught by the renderer."""
    renderer = ReportRenderer()
    renderer.register_format("bad", lambda data, **kw: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        renderer.render([], "bad")


def test_column_order_follows_first_row_key_order():
    """Column order must reflect the insertion order of keys in the first row."""
    received = []
    renderer = ReportRenderer()

    def capture(data, **kw):
        received.append(list(data[0].keys()))
        return ""

    renderer.register_format("cols", capture)
    renderer.render([{"z": 1, "a": 2, "m": 3}], "cols")
    assert received[0] == ["z", "a", "m"]


def test_available_formats_after_re_register():
    """Re-registering should not duplicate the format name."""
    renderer = ReportRenderer()
    renderer.register_format("csv", lambda data, **kw: "")
    renderer.register_format("csv", lambda data, **kw: "v2")
    names = renderer.available_formats()
    assert names.count("csv") == 1
