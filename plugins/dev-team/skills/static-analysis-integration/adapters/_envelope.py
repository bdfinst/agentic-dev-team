"""Shared helpers for the bespoke finding adapters in this directory.

Adapters are invoked as standalone scripts (`python3 adapters/<x>-adapter.py`),
so `sys.path[0]` is already this directory and a plain `import _envelope`
resolves with no path manipulation.

Extracted once the second adapter needed the same path normalization: two
byte-identical copies of it were exactly the kind of finding the duplication
lane these adapters serve exists to report.
"""

from __future__ import annotations

import os


def rel(path: str) -> str:
    """Repo-relative POSIX path — unified-finding-v1 forbids absolute paths.

    Relativizes against the current working directory, so adapters must be
    run from the repo root (as the documented lane invocations are).
    """
    text = (path or "").replace("\\", "/")
    if os.path.isabs(text):
        text = os.path.relpath(text, os.getcwd()).replace("\\", "/")
    return text.removeprefix("./")
