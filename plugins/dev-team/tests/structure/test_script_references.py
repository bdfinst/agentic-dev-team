"""Structural guard: scripts referenced by skills, agents, and hooks must exist.

This is the coverage gap that let #1078 ship — `skills/version/SKILL.md`
invoked `$CLAUDE_PLUGIN_ROOT/hooks/lib/plugin_version.py`, a file that did not
exist, and nothing in the suite noticed because skills are agent-followed prose
that CI never executes and no unit test referenced the missing file.

Two high-signal, low-false-positive checks:

1. Every ``$CLAUDE_PLUGIN_ROOT``-relative ``.py``/``.sh`` reference in any
   SKILL.md or agent .md resolves to a real file (those paths unambiguously
   point at plugin-internal files, unlike bare example commands that may target
   the user's own project).
2. Every script path in a ``settings.json`` hook command exists.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# $CLAUDE_PLUGIN_ROOT/... or ${CLAUDE_PLUGIN_ROOT}/... ending in .py or .sh.
_PLUGIN_ROOT_REF = re.compile(
    r"\$\{?CLAUDE_PLUGIN_ROOT\}?/([^\s\"'`)]+?\.(?:py|sh))(?![a-zA-Z0-9])"
)


def _doc_files():
    yield from PLUGIN_ROOT.glob("skills/**/SKILL.md")
    yield from PLUGIN_ROOT.glob("agents/*.md")


def test_plugin_root_script_references_exist():
    missing = []
    for doc in _doc_files():
        text = doc.read_text(encoding="utf-8")
        for rel in _PLUGIN_ROOT_REF.findall(text):
            if not (PLUGIN_ROOT / rel).is_file():
                missing.append(f"{doc.relative_to(PLUGIN_ROOT)} -> {rel}")
    assert not missing, "Referenced scripts do not exist:\n" + "\n".join(sorted(missing))


def _hook_commands():
    settings = json.loads((PLUGIN_ROOT / "settings.json").read_text())
    found = []

    def walk(node):
        if isinstance(node, dict):
            cmd = node.get("command")
            if isinstance(cmd, str):
                found.append(cmd)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(settings.get("hooks", {}))
    return found


def test_hook_command_scripts_exist():
    missing = []
    for cmd in _hook_commands():
        for tok in shlex.split(cmd):
            if tok.startswith("-") or "=" in tok:
                continue
            if tok.endswith((".py", ".sh")):
                # Hook commands run with the plugin root as cwd, so relative
                # paths resolve against it.
                if not (PLUGIN_ROOT / tok).is_file():
                    missing.append(f"{cmd!r} -> {tok}")
    assert not missing, "Hook command scripts do not exist:\n" + "\n".join(sorted(missing))


def test_scanner_actually_finds_references():
    """Guard the guard: the regex must match a known-good reference, so a
    silently-broken pattern can't turn this suite into a no-op."""
    version_skill = (PLUGIN_ROOT / "skills" / "version" / "SKILL.md").read_text()
    refs = _PLUGIN_ROOT_REF.findall(version_skill)
    assert "hooks/py.sh" in refs
    assert "hooks/lib/plugin_version.py" in refs
