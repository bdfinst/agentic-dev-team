"""Text the operator sees: dollar amounts, and transcript-derived text made safe for a terminal."""

from __future__ import annotations


def format_usd(amount_usd: float) -> str:
    """Four decimals, so a sub-cent haiku estimate does not read as $0.00."""
    return f"${amount_usd:.4f}"


def escape_unprintable(text: str) -> str:
    """Replace control characters with their escaped form, so text cannot drive the terminal.

    Text from a transcript or an exception can carry escape sequences (ESC, the C1
    controls). Printed raw they can retitle the window or rewrite earlier lines.
    """
    return "".join(char if char.isprintable() else repr(char)[1:-1] for char in text)
