#!/usr/bin/env python3
"""code_intelligence_nudge — Claude Code PreToolUse hook.

Renamed/generalized from codegraph_nudge.py (#593 / #572 Phase 3, #1368)
now that this hook is growing beyond a single tool: it will nudge agents
toward whichever of CodeGraph, Repowise, and Graphify are indexed in the
project, not CodeGraph alone. `_detect_present_tools()` already reports
all three; the single-tool CodeGraph-only nudge below is the still-current
runtime behavior until multi-tool message composition and main() wiring
land in a follow-up step of the same slice.

Runs before Read, Grep, Glob tool calls. Single-file Read calls, Grep with
a file `path`, and Glob with a literal `pattern` pass silently.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: warning on stderr when exploration is detected
    Exit  : 0 = allow (silent or warn). 2 = block (careful mode only).

Posture: fail-open. Any internal error → exit 0. The hook is a nudge,
never a gate.

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def read_stdin_json() -> Optional[dict]:  # type: ignore[misc]
        return None

try:
    from turn_identity import count_user_lines, transcript_id  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def transcript_id(path: str) -> str:  # type: ignore[misc]
        return Path(path).stem

    def count_user_lines(transcript_path: Path) -> int:  # type: ignore[misc]
        return 0


WARN_MSG = (
    "[codegraph-nudge] CodeGraph is initialized in this project. Prefer "
    "codegraph_context or codegraph_explore for multi-file exploration; "
    "Grep/Glob/Read for confirming a specific detail."
)


CUES = {
    "graphify": (
        'graphify query "<question>" — cross-artifact: code + docs + schemas + '
        "infra (non-code content; not a faster CodeGraph/Repowise)"
    ),
    "repowise": (
        "repowise get_context / get_risk / get_why — risk, rationale, code "
        "health, dead code (not raw call-graph structure)"
    ),
    "codegraph": (
        "codegraph_explore — structure, call graph, blast radius (not risk, "
        "rationale, or non-code content)"
    ),
}

_LABELS = {"graphify": "Graphify", "repowise": "Repowise", "codegraph": "CodeGraph"}

# Fixed message order — never the filesystem/detection order the caller passes in.
_PRECEDENCE = ["graphify", "repowise", "codegraph"]

_CLOSING_LINE = "Grep/Glob/Read for confirming a specific detail."


def _cue_line(tool: str, *, bulleted: bool) -> str:
    """Format one tool's cue — bulleted for the combined message, bare for
    the single-tool message. Shared by both `_compose_message` branches so
    the underlying cue text can't drift between the two message shapes."""
    return f"- {CUES[tool]}" if bulleted else CUES[tool]


def _compose_message(qualifying: list) -> Optional[str]:
    """Compose the nudge message for the given qualifying tools.

    `qualifying` is reordered by `_PRECEDENCE` before composing — the
    message's tool order never varies with filesystem/detection order.
    Zero qualifying tools → None (full suppression).
    """
    ordered = [tool for tool in _PRECEDENCE if tool in qualifying]
    if not ordered:
        return None

    if len(ordered) == 1:
        tool = ordered[0]
        return (
            f"[code-intelligence-nudge] {_LABELS[tool]} is initialized in this "
            f"project. Prefer {_cue_line(tool, bulleted=False)} for multi-file "
            f"exploration; {_CLOSING_LINE}"
        )

    bullets = "\n".join(_cue_line(tool, bulleted=True) for tool in ordered)
    return (
        "[code-intelligence-nudge] Multiple code-intelligence indexes found. "
        f"Pick whichever matches your question:\n{bullets}\n{_CLOSING_LINE}"
    )


def _codegraph_used_this_turn(cwd: Path, transcript_path: str) -> bool:
    """True when a codegraph_* MCP tool ran earlier in the current turn.

    Signature parity with codegraph-nudge.sh's `codegraph_used_this_turn`:
    reads $cwd/.claude/codegraph-turn-state.json, cross-checks against the
    transcript_id (basename minus extension) and turn_counter (count of
    `"type":"user"` markers in the last 1 MiB of the transcript).

    Any parse or filesystem error → False (fail-open, matching the .sh's
    `return 1`).
    """
    sentinel = cwd / ".claude" / "codegraph-turn-state.json"
    if not sentinel.is_file():
        return False
    if not transcript_path:
        return False
    tx = Path(transcript_path)
    if not tx.is_file():
        return False
    try:
        sentinel_data = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    sentinel_tid = str(sentinel_data.get("transcript_id") or "")
    sentinel_tc = sentinel_data.get("turn_counter")
    if not sentinel_tid or sentinel_tc is None:
        return False

    current_tid = transcript_id(transcript_path)
    current_tc = count_user_lines(tx)
    return sentinel_tid == current_tid and int(sentinel_tc) == current_tc


def _is_multi_grep(tool_input: dict) -> bool:
    """Grep is multi-file unless `path` is set AND points at a regular file."""
    path = str(tool_input.get("path") or "")
    if not path:
        return True
    return not Path(path).is_file()


def _is_multi_glob(tool_input: dict) -> bool:
    """Glob is multi when the pattern contains a glob metacharacter."""
    pattern = str(tool_input.get("pattern") or "")
    return any(c in pattern for c in ("*", "?", "["))


def _detect_present_tools(cwd: Path) -> list:
    """Return which of codegraph/repowise/graphify are indexed in `cwd`.

    codegraph: `.codegraph/` directory. repowise: `.repowise/` directory.
    graphify: `graphify-out/graph.json` regular file. Each check is wrapped
    so any OSError (wrong type — e.g. a file where a dir is expected, or a
    permission error) is treated as "not present," never raised — this
    hook is a nudge, never a gate.
    """
    present = []
    try:
        if (cwd / ".codegraph").is_dir():
            present.append("codegraph")
    except OSError:
        pass
    try:
        if (cwd / ".repowise").is_dir():
            present.append("repowise")
    except OSError:
        pass
    try:
        if (cwd / "graphify-out" / "graph.json").is_file():
            present.append("graphify")
    except OSError:
        pass
    return present


def _careful_active(hook_dir: Path) -> bool:
    """Read careful-state.json adjacent to the hook script; True iff `.active`."""
    state_file = hook_dir / "careful-state.json"
    if not state_file.is_file():
        return False
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("active") is True


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0

    cwd_str = str(payload.get("cwd") or "").strip()
    cwd = Path(cwd_str) if cwd_str else Path.cwd()

    # Only act when this project has a CodeGraph index.
    if not (cwd / ".codegraph").is_dir():
        return 0

    tool_name = str(payload.get("tool_name") or "")

    # Read always targets exactly one file_path — never exploration.
    if tool_name == "Read":
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    if tool_name == "Grep":
        is_multi = _is_multi_grep(tool_input)
    elif tool_name == "Glob":
        is_multi = _is_multi_glob(tool_input)
    else:
        # Other tools — defensive default, pass silently.
        return 0

    if not is_multi:
        return 0

    transcript_path = str(payload.get("transcript_path") or "")
    if _codegraph_used_this_turn(cwd, transcript_path):
        return 0

    hook_dir = Path(__file__).resolve().parent
    if _careful_active(hook_dir):
        print(f"{WARN_MSG} [blocked by /careful]", file=sys.stderr)
        return 2

    print(WARN_MSG, file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open on any unexpected error — the hook is a nudge, never a gate.
        sys.exit(0)
