"""Benefit evaluation tooling: logic behind scripts/benefit_eval_cli.py.

The shipped plugin's helper libraries are put on ``sys.path`` here, so any submodule
imports on its own with only ``scripts/lib`` on the path.
"""

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "dev-team"
for _dir in (_PLUGIN_ROOT / "hooks" / "lib", _PLUGIN_ROOT / "scripts" / "lib"):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))
