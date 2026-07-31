"""Temporary file for #1635's live-fire verification — deleted in the next
commit on this branch. Confirms the "Python 3.8 floor" CI job actually goes
red on a real post-3.8 construct, not just that it runs."""

from collections.abc import Callable

Runner = Callable[[str], int]
