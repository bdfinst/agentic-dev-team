"""Guard against machine-specific paths from graphify's Claude hook (#1367).

`graphify install --project` (via its `claude install` step) appends
PreToolUse hook entries to the target repo's shared, git-tracked
`.claude/settings.json`, using the absolute path to the graphify binary on
the installing machine (e.g. `/Users/alice/.local/bin/graphify`). If that
file is committed, it bakes one developer's home-directory path into the
repo and silently breaks for every other clone/teammate whose graphify
binary lives somewhere else (different username, different install method —
`uv tool`, `pipx`, `--user pip`, ... all resolve to different paths).

This module scans `.claude/settings.json` for any `PreToolUse` hook entry
that invokes graphify via an absolute filesystem path — instead of relying
on PATH — and relocates it into `.claude/settings.local.json` (already
gitignored, personal-machine scope). The scan is unconditional: it fixes a
repo that already carries the pollution from a past install just as well as
one guarding a fresh install, so `/project-init`/`/setup` can run it as a
standing check rather than only wrapping a live installer call.

No upstream flag exists to make `graphify` emit a bare, PATH-resolved
command instead of an absolute path (checked against installed graphify
0.9.8's `_resolve_graphify_exe`): it is a deliberate design choice, to keep
the hook working in environments where the venv Scripts/ directory isn't on
PATH (e.g. the VS Code Codex extension on Windows). Relocation, not an
upstream flag, is therefore the fix.

Stdlib-only, per ADR 0014/0015 (Python for cross-OS scripts).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable


_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")
_PRE_TOOL_USE_KEY = "PreToolUse"


def _pre_tool_use(settings: dict) -> list[dict]:
    return settings.get("hooks", {}).get(_PRE_TOOL_USE_KEY, [])


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {}


def _dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _command_is_absolute_graphify(command: str) -> bool:
    token = command.strip().split(" ", 1)[0] if command.strip() else ""
    if not token:
        return False
    is_absolute = token.startswith("/") or bool(_WINDOWS_ABSOLUTE.match(token))
    if not is_absolute:
        return False
    basename = re.split(r"[\\/]", token)[-1]
    if basename.lower().endswith(".exe"):
        basename = basename[: -len(".exe")]
    return basename.lower() == "graphify"


def find_absolute_graphify_entries(settings: dict) -> list[dict]:
    """Return `PreToolUse` entries whose command invokes graphify via an
    absolute filesystem path rather than a bare, PATH-resolved `graphify`.
    """
    polluting = []
    for entry in _pre_tool_use(settings):
        commands = (h.get("command", "") for h in entry.get("hooks", []))
        if any(_command_is_absolute_graphify(c) for c in commands):
            polluting.append(entry)
    return polluting


def fix_settings(settings_path: Path, local_settings_path: Path) -> bool:
    """Scan `settings_path` for absolute-path graphify hook entries and
    relocate them into `local_settings_path`.

    Returns True if anything was relocated, False if `settings_path` was
    already clean (including when it doesn't exist).
    """
    settings = _load_json(settings_path)
    polluting = find_absolute_graphify_entries(settings)
    if not polluting:
        return False

    remaining = [e for e in _pre_tool_use(settings) if e not in polluting]
    if remaining:
        settings.setdefault("hooks", {})[_PRE_TOOL_USE_KEY] = remaining
    else:
        settings.get("hooks", {}).pop(_PRE_TOOL_USE_KEY, None)
    _dump_json(settings_path, settings)

    local_settings = _load_json(local_settings_path)
    local_pre_tool_use = local_settings.setdefault("hooks", {}).setdefault(
        _PRE_TOOL_USE_KEY, []
    )
    for entry in polluting:
        if entry not in local_pre_tool_use:
            local_pre_tool_use.append(entry)
    _dump_json(local_settings_path, local_settings)

    return True


def run_install_with_guard(
    settings_path: Path,
    local_settings_path: Path,
    installer: Callable[[], None],
) -> bool:
    """Run `installer()` against `settings_path`, then apply `fix_settings`.

    Returns True if a machine-specific hook entry was detected and relocated
    to `local_settings_path`, False if the installer's output was left as-is.
    """
    installer()
    return fix_settings(settings_path, local_settings_path)
