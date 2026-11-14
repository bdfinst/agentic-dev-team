"""Split a list of items into fixed-size pages."""


def page_count(total: int, size: int) -> int:
    if size < 1:
        raise ValueError("size must be at least 1")
    return total // size


def page(items: list, number: int, size: int) -> list:
    if size < 1:
        raise ValueError("size must be at least 1")
    start = number * size - size + 1
    return items[start : start + size - 1]
