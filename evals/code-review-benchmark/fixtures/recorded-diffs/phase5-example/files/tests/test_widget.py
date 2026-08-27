"""Synthetic Phase-5-shaped test addition (fixture only, see meta.json)."""


def test_widget_renders_title():
    widget = {"title": "Example"}
    assert widget["title"] == "Example"


def test_widget_rejects_empty_title():
    widget = {"title": ""}
    assert widget["title"] == ""
