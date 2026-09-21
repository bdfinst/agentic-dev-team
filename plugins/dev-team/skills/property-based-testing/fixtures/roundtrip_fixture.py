"""Fixture module for hypothesis_scaffold.py's round-trip heuristic (#2190).

Exposes a module-level `encode`/`decode` pair by name — the exact literal
names the scaffold's heuristic looks for. `decode(encode(x)) == x` holds for
any string because reversal is its own inverse.
"""


def encode(value: str) -> str:
    """Encode a string by reversing it."""
    return value[::-1]


def decode(value: str) -> str:
    """Decode a string produced by encode() by reversing it back."""
    return value[::-1]
