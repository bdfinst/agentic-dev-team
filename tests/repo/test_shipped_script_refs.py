"""Shipped-script / hook reference sensor.

The bug this prevents: a shipped skill, agent, or prompt references a helper
script or hook by a path that resolves in THIS dev monorepo but not inside
the INSTALLED plugin. The classic form is
`${CLAUDE_PLUGIN_ROOT}/../../scripts/x.sh` - at dev time CLAUDE_PLUGIN_ROOT
is plugins/dev-team/, so `../../scripts/` lands on repo-root scripts/; once
installed, CLAUDE_PLUGIN_ROOT is the cache dir and `../../scripts/` points
at a nonexistent sibling. The skill then fails silently on the user's
machine (plan-waves.sh / git-origin-host.sh, this PR).

Three invariants, each model-free and deterministic:
  1. every ${CLAUDE_PLUGIN_ROOT}/(scripts|hooks)/<path> reference in a
     shipped file resolves to a real file under plugins/dev-team/;
  2. no shipped skill uses the plugin-escaping ${CLAUDE_PLUGIN_ROOT}/../../
     form - except a documented allowlist of maintainer-only skills;
  3. every hook command registered in settings.json resolves to a shipped
     file.

Allowlist (invariant 2): /session-review is a maintainer tool that operates
on THIS repo's own infrastructure (session transcripts). It only ever runs
from the dev checkout, where ../../scripts/ resolves, and its helpers
(session_extract.py et al.) are coupled repo-root tooling that is
intentionally not shipped. A NEW ../../ reference in ANY OTHER skill is a
shipping bug - add the helper under plugins/dev-team/scripts/ and reference
it as ${CLAUDE_PLUGIN_ROOT}/scripts/<name> instead of exempting it.

/agent-eval was in this allowlist until #1637: it's the same kind of
maintainer-only, repo-self-referential tool, but its `allowed-tools`
frontmatter hardcodes its script invocations as BARE `scripts/<name>.py`
Bash permission patterns (not `${CLAUDE_PLUGIN_ROOT}/../../scripts/<name>`),
so its body must use the bare form to match — see
tests/repo/test_agent_implemented_by_resolves.py's
`INTENTIONAL_BARE_INVOCATION` set for that guard.

Ported from tests/repo/shipped_script_refs_test.bats (#673).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
SHIPPED_DIRS = [PLUGIN / "skills", PLUGIN / "agents", PLUGIN / "prompts"]

# Skills permitted to reference repo-root tooling via ../../ (see header).
ESCAPE_ALLOWLIST = ["skills/session-review/"]

_REF_RE = re.compile(
    r"\$\{CLAUDE_PLUGIN_ROOT\}/(scripts|hooks)/[a-zA-Z0-9_./-]+\.(sh|py)"
)
_ESCAPE_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/\.\./")
_CMD_PATH_RE = re.compile(
    r"(\$\{CLAUDE_PLUGIN_ROOT\}/)?(hooks|scripts)/[a-zA-Z0-9_./-]+\.(sh|py)"
)


def _iter_files() -> list[Path]:
    files = []
    for d in SHIPPED_DIRS:
        if d.is_dir():
            files.extend(f for f in d.rglob("*") if f.is_file())
    return files


def test_every_plugin_root_scripts_or_hooks_reference_resolves_to_a_shipped_file() -> (
    None
):
    refs = set()
    for f in _iter_files():
        for match in _REF_RE.finditer(f.read_text(errors="ignore")):
            refs.add(match.group(0))

    missing = []
    for ref in sorted(refs):
        rel = ref[len("${CLAUDE_PLUGIN_ROOT}/") :]
        if not (PLUGIN / rel).is_file():
            missing.append(
                f"{rel}  (referenced but not present under plugins/dev-team/)"
            )

    assert not missing, (
        "Unresolvable shipped script/hook reference(s):\n"
        + "\n".join(missing)
        + "\nAdd the file under plugins/dev-team/ or correct the reference."
    )


def test_no_shipped_skill_escapes_the_plugin_outside_the_allowlist() -> None:
    skills_dir = PLUGIN / "skills"
    offenders = []
    for f in sorted(skills_dir.rglob("*")) if skills_dir.is_dir() else []:
        if not f.is_file():
            continue
        relpath = str(f.relative_to(PLUGIN))
        allowed = any(relpath.startswith(ok) for ok in ESCAPE_ALLOWLIST)
        if allowed:
            continue
        for lineno, line in enumerate(
            f.read_text(errors="ignore").splitlines(), start=1
        ):
            if _ESCAPE_RE.search(line):
                offenders.append(f"{relpath}:{lineno}: {line}")

    assert not offenders, (
        "Plugin-escaping reference(s) - won't resolve in an installed plugin:\n"
        + "\n".join(offenders)
        + "\nMove the helper under plugins/dev-team/scripts/ and use "
        "${CLAUDE_PLUGIN_ROOT}/scripts/<name>."
    )


def test_every_hook_command_in_settings_json_resolves_to_a_shipped_file() -> None:
    settings_path = PLUGIN / "settings.json"
    if not settings_path.is_file():
        return
    settings = json.loads(settings_path.read_text())
    commands = []
    for event_hooks in (settings.get("hooks") or {}).values():
        if not isinstance(event_hooks, list):
            continue  # e.g. a "_comment" string sibling key
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
            path.removeprefix("${CLAUDE_PLUGIN_ROOT}/")
        )
        if not (PLUGIN / rel).is_file():
            missing.append(f"{rel}  (registered in settings.json but not present)")

    assert not missing, "Hook command(s) referencing a missing file:\n" + "\n".join(
        missing
    )
