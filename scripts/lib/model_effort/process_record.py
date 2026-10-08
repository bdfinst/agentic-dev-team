"""The raw result of one `claude` process, shared by the runner that makes it and `outcome` that reads it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrialProcessRecord:
    """Raw result of one CLI process. `exit_code` is None when it timed out.

    `cwd` is the directory the process ran in, so text it printed can be scrubbed of it.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    cwd: Path | None = None
