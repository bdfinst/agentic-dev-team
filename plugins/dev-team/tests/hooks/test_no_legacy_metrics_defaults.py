"""Content-guard: no shipped hooks/scripts default to a legacy bare-path
runtime artifact location (Slice 5, Step 5.5, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

Sweeps `hooks/` and `scripts/` for `default="metrics/...`,
`default="memory/...`, `default="plans/...` (and `Path("metrics/...` /
`Path("memory/...` / `Path("plans/...` equivalents) — the shape a call site
takes when it has not yet been migrated to `artifact_paths`. A small,
explicitly named allowlist covers files this slice's later, dedicated steps
own:

  - `contract_version_guard.py` — deliberately unaffected (Step 4.6): it
    protects the plugin's OWN knowledge file within this same repo checkout,
    not a downstream project's runtime artifacts, and resolves its audit log
    relative to its own `__file__`, never a project root.
  - `build_slice_scope.py` — its `memory/**`/`metrics/**` bookkeeping-allowlist
    glob strings are Step 5.7's target, not this step's.
  - `test_improve_resume.py` — its `--memory-root` default is Step 5.8's
    target (paired with `migrate_dir()` wiring), not this step's.

Re-verify this allowlist shrinks to empty once Steps 5.7/5.8 land.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"

_ALLOWLIST = {
    "hooks/contract_version_guard.py",
    "scripts/build_slice_scope.py",
    "scripts/test_improve_resume.py",
}

_LEGACY_DEFAULT_RE = re.compile(
    r"""(default\s*=\s*["']|Path\(["'])(metrics|memory|plans)/"""
)


def _production_py_files():
    for sub in ("hooks", "scripts"):
        root = _PLUGIN_DIR / sub
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(_PLUGIN_DIR).as_posix()
            if rel in _ALLOWLIST:
                continue
            yield rel, path


def test_no_bare_legacy_metrics_memory_plans_defaults_remain():
    offenders = []
    for rel, path in _production_py_files():
        text = path.read_text(encoding="utf-8")
        for match in _LEGACY_DEFAULT_RE.finditer(text):
            offenders.append(f"{rel}: {match.group(0)}")
    assert not offenders, (
        "Legacy bare-path runtime-artifact defaults found outside the "
        f"documented allowlist: {offenders}"
    )


def test_allowlist_entries_still_exist_on_disk():
    """The allowlist names real files, not stale/typo'd paths."""
    for rel in _ALLOWLIST:
        assert (_PLUGIN_DIR / rel).is_file(), f"allowlisted path missing: {rel}"
