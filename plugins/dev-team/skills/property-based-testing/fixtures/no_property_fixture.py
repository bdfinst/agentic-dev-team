"""Fixture module for hypothesis_scaffold.py's negative case (#2190).

`add_one` has no round-trip counterpart and no documented postcondition, so
neither heuristic matches — the scaffold should derive no property for it.
"""


def add_one(value: int) -> int:
    """Add one to a value."""
    return value + 1
