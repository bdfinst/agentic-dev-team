"""Fixture module for hypothesis_scaffold.py's invariant heuristic (#2190).

`sort_values`'s docstring documents a "returns sorted" postcondition next to
a type-hinted return value — the exact narrow signal the scaffold's
invariant heuristic looks for.
"""


def sort_values(values: list[int]) -> list[int]:
    """Sort a list of integers.

    Returns sorted output: a non-decreasing list containing the same
    elements as ``values``.
    """
    return sorted(values)
