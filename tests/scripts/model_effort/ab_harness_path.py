"""Put the A/B harness (scripts/model_effort_ab.py, scripts/lib/model_effort/) on `sys.path`.

The harness test helpers import this first, so `model_effort` resolves however a test is run.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT

for _path in (REPO_ROOT / "scripts", REPO_ROOT / "scripts" / "lib"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
