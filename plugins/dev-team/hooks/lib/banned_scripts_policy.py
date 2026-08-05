"""banned_scripts_policy — shared policy constants and checkout-shape probe
for the #1755 banned-script hook pair (`scan_bash_for_banned_scripts.py`,
`scan_banned_scripts.py`).

Both hooks independently defined identical `BANNED_EXTENSIONS`/
`SCOPED_PREFIX`/`ALLOWED_RELATIVE_PATHS` constants (#1850). This module is
the shared extraction so the policy can't drift between the PreToolUse
command-string scan and the PostToolUse working-tree backstop.

Stdlib-only. See ADR 0014/0015.
"""

from __future__ import annotations

from pathlib import Path

# The extensions this repo's CLAUDE.md forbids under plugins/dev-team/.
BANNED_EXTENSIONS = (".sh", ".bash", ".bat", ".cmd", ".ps1")

SCOPED_PREFIX = "plugins/dev-team/"

# The two documented bootstrap-shim exceptions (repo CLAUDE.md § Script
# authoring — Python only): install.sh can't itself be Python because it
# must run before an interpreter is guaranteed on PATH, and hooks/py.sh is
# the trampoline that resolves one. Every other invocation under
# plugins/dev-team/ routes through py.sh, never a bare interpreter.
ALLOWED_RELATIVE_PATHS = {
    "plugins/dev-team/install.sh",
    "plugins/dev-team/hooks/py.sh",
}


def looks_like_monorepo_checkout(start: Path) -> bool:
    """Cheap, non-git check: does ``plugins/dev-team/`` exist under ``start``
    or any of its ancestors? Pure filesystem walk — never shells out — so a
    downstream install (where this is always False) pays nothing before
    either hook's early exit (#1861).
    """
    start_resolved = start.resolve()
    for candidate in (start_resolved, *start_resolved.parents):
        if (candidate / "plugins" / "dev-team").is_dir():
            return True
    return False


__all__ = (
    "ALLOWED_RELATIVE_PATHS",
    "BANNED_EXTENSIONS",
    "SCOPED_PREFIX",
    "looks_like_monorepo_checkout",
)
