#!/usr/bin/env python3
"""validate_agent_contract.py — repo-root wrapper for dev-team's own
self-audit (used by /agent-audit). The one real implementation ships with
marketplace-dev (plugins/marketplace-dev/scripts/validate_agent_contract.py)
so it stays installable standalone in other repos; this wrapper just imports
it, mirroring the sys.path pattern hooks/agent_model_resolve.py already uses
for its sibling lib — one implementation, no drift between two copies.

CLI usage:
  python3 scripts/validate_agent_contract.py <agent.md> [<agent.md> ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

_MARKETPLACE_DEV_SCRIPTS = (
    Path(__file__).resolve().parent
    / ".."
    / "plugins"
    / "marketplace-dev"
    / "scripts"
)

if str(_MARKETPLACE_DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_MARKETPLACE_DEV_SCRIPTS))

from validate_agent_contract import main  # type: ignore[import-not-found]  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
