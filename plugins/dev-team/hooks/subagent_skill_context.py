#!/usr/bin/env python3
"""subagent_skill_context.py — PreToolUse hook injecting skill-loading
context into an Agent/Task dispatch (#2187, Slice 1 Step 1.2).

Registered in the existing `PreToolUse` `"Agent|Task"` matcher (alongside
`context_ceiling_guard.py` and `agent_dispatch_ledger.py`). Reads
`tool_input.subagent_type`, resolves its declared skills via
`hooks/lib/agent_skill_hints.py::skills_for_agent_type` (frontmatter
`skills:` is the single source of truth — ADR 0028), and when that list is
non-empty, emits `hookSpecificOutput.updatedInput` naming those skills as an
`additionalContext` note appended to the dispatch's `tool_input` — the
original `tool_input` keys are preserved unchanged, never replaced.

No collision with `context_ceiling_guard.py`: that hook never emits
`hookSpecificOutput`/`updatedInput` on this matcher today, only plain stderr
text and an exit code, so this hook is the sole supplier of `updatedInput`
for `Agent|Task` PreToolUse.

Fail-open throughout, matching every other hook in this plugin:
  - `tool_name` not in {"Agent", "Task"} -> exit 0, no stdout.
  - `tool_input.subagent_type` missing or not a non-empty string -> exit 0,
    no stdout, no `updatedInput`.
  - unrecognized agent type / no declared skills -> exit 0, no stdout.
  - malformed/missing stdin -> exit 0 (mirrors `read_stdin_json`'s own
    fail-open contract exactly).

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: JSON on stdout carrying `hookSpecificOutput.updatedInput` when a
             skill hint applies; otherwise no stdout. Always exits 0.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOKS_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from agent_skill_hints import skills_for_agent_type  # type: ignore[import-not-found]
from review_agent_registry import strip_plugin_prefix  # type: ignore[import-not-found]
from stdin_json import read_stdin_json  # type: ignore[import-not-found]

# hooks/subagent_skill_context.py -> hooks -> plugin root -> agents
_DEFAULT_AGENTS_DIR = _HOOKS_DIR.parent / "agents"

_DISPATCH_TOOLS = frozenset({"Agent", "Task"})


def _build_note(skills: list[str]) -> str:
    return (
        "Relevant skills for this dispatch (per the agent's own frontmatter "
        f"`skills:` list): {', '.join(skills)}."
    )


def resolve_updated_input(
    payload: dict, agents_dir: Path | None = None
) -> dict | None:
    """Compute the `updatedInput` dict for a PreToolUse payload, or `None`
    when no hint applies. Split from `main()` for testability.

    `agents_dir` defaults to the module-level `_DEFAULT_AGENTS_DIR`, read at
    call time (not bound as a mutable default) so tests can
    `monkeypatch.setattr(hook, "_DEFAULT_AGENTS_DIR", tmp_path)` and have it
    take effect.
    """
    if agents_dir is None:
        agents_dir = _DEFAULT_AGENTS_DIR

    tool_name = payload.get("tool_name")
    if tool_name not in _DISPATCH_TOOLS:
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    subagent_type = tool_input.get("subagent_type")
    if not isinstance(subagent_type, str) or not subagent_type:
        return None
    subagent_type = strip_plugin_prefix(subagent_type)

    skills = skills_for_agent_type(subagent_type, agents_dir)
    if not skills:
        return None

    return {**tool_input, "additionalContext": _build_note(skills)}


def main() -> int:
    try:
        payload = read_stdin_json()
        if payload is None:
            # Empty or malformed stdin -> silent pass, same as every other hook.
            return 0

        updated_input = resolve_updated_input(payload)
        if updated_input is None:
            return 0

        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "updatedInput": updated_input,
                    }
                }
            )
        )
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
