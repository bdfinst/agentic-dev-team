"""Thin connection helper over the shared PostgreSQL database."""
from contextlib import contextmanager


@contextmanager
def conn():
    raise NotImplementedError("wired at deploy time")
    yield
