"""Remove a temp directory tree, reporting what cannot be removed instead of failing."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Python 3.12 renamed rmtree's `onerror` to `onexc` and changed what it receives.
RMTREE_HAS_ONEXC = sys.version_info >= (3, 12)


def remove_tree(directory: Path) -> None:
    """Delete `directory`; print a warning to stderr for each path that stays."""
    if RMTREE_HAS_ONEXC:
        shutil.rmtree(directory, onexc=_report_cleanup_failure)
    else:
        shutil.rmtree(directory, onerror=_report_cleanup_failure)


def _report_cleanup_failure(_function, path, error) -> None:
    # `onerror` passes an exc_info tuple; `onexc` passes the exception itself.
    exception = error[1] if isinstance(error, tuple) else error
    print(f"warning: could not remove {path}: {exception}", file=sys.stderr)
