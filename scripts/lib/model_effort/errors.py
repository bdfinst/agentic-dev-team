"""Errors shared across the A/B harness package."""


class UsageError(Exception):
    """A pre-run refusal; the message says what is wrong and how to fix it."""
