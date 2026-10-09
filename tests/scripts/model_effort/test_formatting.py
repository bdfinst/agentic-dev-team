"""Text formatting helpers (model_effort.formatting)."""

from __future__ import annotations

import pytest
from model_effort.formatting import escape_unprintable, format_usd


class TestFormatUsd:
    @pytest.mark.parametrize(
        ("amount", "text"),
        [(0.004664, "$0.0047"), (0, "$0.0000"), (12.5, "$12.5000")],
    )
    def test_amounts_show_four_decimals(self, amount, text):
        assert format_usd(amount) == text


class TestEscapeUnprintable:
    @pytest.mark.parametrize(
        ("raw", "shown"),
        [
            ("\x1b[31m", "\\x1b[31m"),
            ("\x9b31m", "\\x9b31m"),
            ("a\x85b", "a\\x85b"),
            ("a\x7fb", "a\\x7fb"),
            ("a\tb", "a\\tb"),
            ("a\nb", "a\\nb"),
            ("a\u202eb", "a\\u202eb"),
        ],
        ids=["esc", "c1-csi", "c1-nel", "delete", "tab", "newline", "bidi-override"],
    )
    def test_control_characters_are_shown_as_their_escape_not_emitted(self, raw, shown):
        assert escape_unprintable(raw) == shown

    def test_printable_non_ascii_text_is_kept(self):
        assert escape_unprintable("café 日本") == "café 日本"
