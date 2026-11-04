"""Shared AGENT/agent_text()/required_section() helpers for the mutation-kill
agent's doc-content-assertion tests (issue #1927, plan slice 1).

Six `tests/agents/test_mutation_kill_*.py` files each redefined an identical
`AGENT` path constant, a `text()` fixture reading that file, and an
"extract a section via `skill_doc_helpers.section()`, then assert non-empty"
idiom. This module is the single shared source for the constant and the
read, following this repo's established convention for cross-file test
helpers (`tests/agents/_plugin_dirs.py`, `tests/scripts/_mutation_test_helpers.py`):
export a plain constant and plain functions, not a `@pytest.fixture` — no
shared `_*.py` module in this repo exports a fixture for cross-module
import, and doing so here would also leave `AGENT` as an unused import
(Ruff F401) in files that reference it only inside a fixture body. Each
consuming file keeps its own one-line local `text()` fixture delegating to
`agent_text()`.
"""

from __future__ import annotations

from _agent_text_helpers import required_section

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "mutation-kill.md"


def agent_text() -> str:
    """Return mutation-kill.md's full content."""
    return AGENT.read_text(encoding="utf-8")


__all__ = ["AGENT", "agent_text", "required_section"]
