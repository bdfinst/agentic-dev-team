"""Shipped-script / hook reference sensor - security-assessment plugin.

Companion to test_shipped_script_refs.py (which guards plugins/dev-team).
Same bug class: a shipped skill, agent, or command references a helper
script or tool by a path that resolves in THIS dev monorepo but not inside
the INSTALLED plugin. Skills/agents/commands are executed by the agent from
the USER's working directory, not the plugin root, so any script they
invoke must be addressed as ${CLAUDE_PLUGIN_ROOT}/<path> to be discoverable
once installed. (settings.json hook commands are the exception - the
harness runs those from the plugin root, so the bare `hooks/<name>` form is
correct and is checked to resolve under the plugin in the last test.)

Four invariants, each model-free and deterministic:
  1. every ${CLAUDE_PLUGIN_ROOT}/(scripts|hooks|tools|harness)/<path>
     reference in a shipped file resolves to a real file under
     plugins/security-assessment/;
  2. no shipped file uses the plugin-escaping
     ${CLAUDE_PLUGIN_ROOT}/../../ form;
  3. every hook command registered in settings.json resolves to a shipped
     file;
  4. no build/test tooling is shipped inside the plugin (the test suite
     lives at tests/security-assessment/, the semgrep audit at repo-root
     scripts/).

Ported from tests/repo/shipped_script_refs_security_assessment_test.bats
(#673).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugins" / "security-assessment"
SHIPPED_DIRS = [
    PLUGIN / "skills",
    PLUGIN / "agents",
    PLUGIN / "commands",
    PLUGIN / "hooks",
    PLUGIN / "harness",
]

_REF_RE = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}/(scripts|hooks|tools|harness)/[a-zA-Z0-9_./-]+\.(sh|py|md)"
)
_ESCAPE_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/\.\./")
_CMD_PATH_RE = re.compile(
    r"(\$\{CLAUDE_PLUGIN_ROOT\}/)?(hooks|scripts)/[a-zA-Z0-9_./-]+\.(sh|py)"
)

_BAD_NAMES = {"run-all.sh", "audit-semgrep-fixtures.py"}
_BAD_SUFFIXES = (".test.sh", "_test.sh", ".bats")


def _iter_files() -> List[Path]:
    files = []
    for d in SHIPPED_DIRS:
        if d.is_dir():
            files.extend(f for f in d.rglob("*") if f.is_file())
    return files


def test_every_plugin_root_reference_resolves_to_a_shipped_file() -> None:
    refs = set()
    for f in _iter_files():
        for match in _REF_RE.finditer(f.read_text(errors="ignore")):
            refs.add(match.group(0))

    missing = []
    for ref in sorted(refs):
        rel = ref[len("${CLAUDE_PLUGIN_ROOT}/") :]
        if not (PLUGIN / rel).exists():
            missing.append(
                f"{rel}  (referenced but not present under plugins/security-assessment/)"
            )

    assert not missing, (
        "Unresolvable shipped script/tool reference(s):\n"
        + "\n".join(missing)
        + "\nAdd the file under plugins/security-assessment/ or correct the reference."
    )


def test_no_shipped_file_escapes_the_plugin() -> None:
    offenders = []
    for f in _iter_files():
        relpath = str(f.relative_to(PLUGIN))
        for lineno, line in enumerate(
            f.read_text(errors="ignore").splitlines(), start=1
        ):
            if _ESCAPE_RE.search(line):
                offenders.append(f"{relpath}:{lineno}: {line}")

    assert not offenders, (
        "Plugin-escaping reference(s) - won't resolve in an installed plugin:\n"
        + "\n".join(offenders)
        + "\nMove the helper under plugins/security-assessment/ and use "
        "${CLAUDE_PLUGIN_ROOT}/<path>."
    )


def test_every_hook_command_in_settings_json_resolves_to_a_shipped_file() -> None:
    settings_path = PLUGIN / "settings.json"
    if not settings_path.is_file():
        return
    settings = json.loads(settings_path.read_text())
    commands = []
    for event_hooks in (settings.get("hooks") or {}).values():
        if not isinstance(event_hooks, list):
            continue  # e.g. the "_comment" string sibling key
        for entry in event_hooks:
            for hook in entry.get("hooks", []) or []:
                cmd = hook.get("command")
                if cmd:
                    commands.append(cmd)

    missing = []
    for cmd in commands:
        match = _CMD_PATH_RE.search(cmd)
        if not match:
            continue
        path = match.group(0)
        rel = (
            path[len("${CLAUDE_PLUGIN_ROOT}/") :]
            if path.startswith("${CLAUDE_PLUGIN_ROOT}/")
            else path
        )
        if not (PLUGIN / rel).is_file():
            missing.append(f"{rel}  (registered in settings.json but not present)")

    assert not missing, "Hook command(s) referencing a missing file:\n" + "\n".join(
        missing
    )


def test_no_build_test_scripts_are_shipped_inside_the_plugin() -> None:
    # Test runners, test cases, and CI/audit tooling must live outside the
    # plugin tree (the plugin ships wholesale via its git-subdir source). The
    # shell test suite lives at tests/security-assessment/; the
    # semgrep-fixtures audit at repo-root scripts/audit-semgrep-fixtures.py.
    offenders = []
    if PLUGIN.is_dir():
        for f in PLUGIN.rglob("*"):
            if not f.is_file():
                continue
            if f.name in _BAD_NAMES or f.name.endswith(_BAD_SUFFIXES):
                offenders.append(str(f))

    assert not offenders, (
        "Build/test script(s) shipped inside the plugin:\n"
        + "\n".join(offenders)
        + "\nRelocate them outside plugins/security-assessment/ (tests/ or repo-root scripts/)."
    )
