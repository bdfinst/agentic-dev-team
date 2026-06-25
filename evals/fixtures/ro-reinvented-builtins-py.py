# FAIL: hand-rolls Python built-ins the same way the TS fixture hand-rolls JS ones.
# Cross-language proof that the reinvent-the-platform rule is not TS-specific.

from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float


# Reinvents min() / max() with a manual scan.
def bounding_box(polygon):
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for p in polygon:
        if p.x < min_x:
            min_x = p.x
        if p.y < min_y:
            min_y = p.y
        if p.x > max_x:
            max_x = p.x
        if p.y > max_y:
            max_y = p.y
    return (min_x, min_y, max_x, max_y)


# Reinvents sum() with an accumulator loop.
def total_x(polygon):
    running = 0.0
    for p in polygon:
        running = running + p.x
    return running
