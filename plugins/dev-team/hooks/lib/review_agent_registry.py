"""hooks/lib/review_agent_registry.py — shared *-review agent glob discovery (#1461).

Both `scripts/check_review_agent_mcp_tools.py` (MCP tool-grant auditing) and
`hooks/agent_dispatch_ledger.py` (the dispatch-ledger PreToolUse hook, #1461)
need the same closed set of registered review-agent names: every
`agents/*-review.md` file's stem. This module is the single extraction point
so a hook never reaches into `scripts/` — the correct dependency direction is
`scripts/` -> `hooks/lib/`, never the reverse (a hook must be import-safe
without any `scripts/` module on its path).

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

from pathlib import Path

# This plugin's own marketplace-qualified prefix. A real Agent-tool dispatch
# of one of this plugin's registered review agents, once installed, is named
# "dev-team:<agent-name>" (e.g. "dev-team:doc-review") — the closed set below
# is built from bare `agents/*-review.md` file stems, so an unstripped
# qualified name never matches it (#1461 follow-up: this silently dropped
# every dispatch's ledger record for the plugin's normal, installed
# invocation form). A prefix for a DIFFERENT plugin is left untouched — it
# is never one of this registry's own agents.
_PLUGIN_PREFIX = "dev-team:"


def strip_plugin_prefix(subagent_type: str) -> str:
    """Normalize a dispatch's `subagent_type` to the bare agent name this
    registry's closed set uses, stripping only this plugin's own
    `dev-team:` qualifier."""
    if subagent_type.startswith(_PLUGIN_PREFIX):
        return subagent_type[len(_PLUGIN_PREFIX) :]
    return subagent_type


def find_review_agent_files(agents_dir: Path) -> list[Path]:
    """Return the read-only review agent files (agents/*-review.md), sorted.

    Glob-discovery logic extracted verbatim from
    `scripts/check_review_agent_mcp_tools.py::find_review_agents` (#1461) —
    behavior-identical, so existing callers/tests of that function regress
    against this implementation unchanged.
    """
    return sorted(Path(agents_dir).glob("*-review.md"))


def registered_review_agent_names(agents_dir: Path) -> frozenset[str]:
    """Return the closed set of registered review-agent names (file stems).

    This is the authoritative closed vocabulary `hooks/agent_dispatch_ledger.py`
    checks an Agent-tool dispatch's `subagent_type` against before recording a
    ledger event — a name outside this set is never a real review agent, and
    is never written to the ledger, not even as a rejected/flagged entry.
    """
    return frozenset(path.stem for path in find_review_agent_files(agents_dir))


def default_agents_dir() -> Path:
    """The plugin's own `agents/` directory (#1904 item 3) — the single
    source of truth every review-agent registry consumer resolves against,
    never the caller's own project `cwd`.

    Always `.resolve()`d: several call sites that once built this path by
    hand (`scripts/check_agent_tool_mapping.py`,
    `scripts/check_review_agent_mcp_tools.py`,
    `skills/code-review/scripts/repo_invariants.py`,
    `scripts/check_agent_scope.py`) previously did so without `.resolve()` —
    a latent behavioral difference under a symlinked checkout — now fixed by
    construction, since each delegates here instead of re-deriving its own
    copy. Not yet exhaustive: `scripts/verify_tier.py` still derives its own
    `_AGENTS_DIR` independently (its `_PLUGIN_ROOT` is already resolved via
    `Path(__file__).resolve()`, so it does not carry the same symlink bug,
    but it remains a duplicate resolution path this module has not yet
    absorbed).
    """
    # hooks/lib/review_agent_registry.py -> hooks/lib -> hooks -> plugin root
    # -> agents
    return Path(__file__).resolve().parents[2] / "agents"


def read_registered_review_agent_names(agents_dir: Path) -> frozenset[str] | None:
    """Checked variant of `registered_review_agent_names()` that owns the
    read-failure-vs-empty distinction (#1904 item 1) instead of forcing every
    consumer to reinvent it.

    Returns `None` on a read failure (a missing or unreadable `agents_dir`);
    a genuine `frozenset()` on a successful read that legitimately finds zero
    `*-review.md` files. The two states require OPPOSITE treatment depending
    on which side of a corroboration check consumes them: for POSITIVE
    evidence (e.g. "which agents dispatched"), a caller may safely collapse
    `None` to an empty set — narrowing corroboration can only ever narrow,
    never widen, what counts as a passing gate. For NEGATIVE evidence (e.g.
    "which agents have an unsuperseded dispatch failure"), collapsing `None`
    to empty would WIDEN the result instead — every genuine negative-evidence
    entry would be filtered out by an empty "registered" set, producing an
    all-clear indistinguishable from "provably none". See
    `hooks/lib/review_gate_corroboration.py`'s own docstring for the full
    account of this asymmetry.

    Two failure modes are checked EXPLICITLY here, not left to an exception:
    `registered_review_agent_names()` globs `agents_dir.glob("*-review.md")`,
    and `Path.glob()` does not raise for either — it silently yields nothing
    for a missing directory and swallows a permission error. Without the
    explicit `is_dir()` check, a missing/unreadable `agents_dir` would
    produce an empty `frozenset()`, not `None`, defeating the very
    distinction this function's contract promises.
    """
    path = Path(agents_dir)
    if not path.is_dir():
        return None
    try:
        return registered_review_agent_names(path)
    except Exception:  # noqa: BLE001 - caller decides how to fail closed for its own evidence direction
        return None
