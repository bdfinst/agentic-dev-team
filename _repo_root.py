"""Shared repo-root constant for test files.

Every test file used to independently compute its own repo root via
``Path(__file__).resolve().parents[N]``, with N depending on that file's own
directory depth — a single-point-of-change risk (152 files touched if the
repo layout ever moved, each with its own easy-to-miscount N). Importing
``REPO_ROOT`` from here instead means the depth is computed in exactly one
place, regardless of where the importing test file lives.

Named ``_repo_root`` (not ``conftest``) to avoid any ambiguity with pytest's
own conftest.py fixture-collection mechanism; it is a plain importable
module, not a pytest plugin. Follows this repo's existing convention for
cross-directory test helpers (``tests/agents/_plugin_dirs.py``,
``tests/stack_aware/_stack_aware_helpers.py``), just scoped to the repo root via the
``pythonpath = .`` entry in ``pytest.ini`` instead of a per-directory one.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
