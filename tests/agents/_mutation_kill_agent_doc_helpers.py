"""Shared AGENT/agent_text() helpers for the mutation-kill agent's
doc-content-assertion tests (issue #1927, plan slice 1).

`AGENT` is the path to mutation-kill.md and `agent_text()` reads its full
content. `required_section` is defined in `_agent_text_helpers` and
re-exported here for the mutation-kill doc tests.

Plain constants and functions, not a `@pytest.fixture`: no shared `_*.py`
module in this repo exports a fixture for cross-module import, and doing so
here would leave `AGENT` as an unused import (Ruff F401) in files that
reference it only inside a fixture body. Each consuming file keeps its own
one-line local `text()` fixture delegating to `agent_text()`.
"""

from __future__ import annotations

from _agent_text_helpers import required_section

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "mutation-kill.md"


def agent_text() -> str:
    """Return mutation-kill.md's full content."""
    return AGENT.read_text(encoding="utf-8")


__all__ = ["AGENT", "agent_text", "required_section"]
