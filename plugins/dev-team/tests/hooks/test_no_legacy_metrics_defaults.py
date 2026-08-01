"""Content-guard: no shipped hooks/scripts default to a legacy bare-path
runtime artifact location (Slice 5, Step 5.5, plan
opt-in-metrics-and-claude-scoped-artifacts.md).

Sweeps `hooks/` and `scripts/` for `default="metrics/...`,
`default="memory/...`, `default="plans/...` (and `Path("metrics/...` /
`Path("memory/...` / `Path("plans/...` equivalents) — the shape a call site
takes when it has not yet been migrated to `artifact_paths`.

Steps 5.7 (`build_slice_scope.py`) and 5.8 (`test_improve_resume.py`) have
both landed, and `contract_version_guard.py` no longer matches this pattern
either — re-verified by re-running this file's own sweep against current
`hooks/`/`scripts/` (zero matches across all three previously-allowlisted
files, and zero elsewhere). If a new entry is ever added here, it must
carry an assertion that the entry actually still matches
`_LEGACY_DEFAULT_RE` — an allowlist entry that no longer matches the
pattern it exists to exempt is stale and should be removed, not carried
forward on faith.

`scripts/eval_ablation.py` joined the allowlist in #1653, when it moved
into the plugin. Its `--jsonl` default of `metrics/eval-ablation.jsonl` is
NOT the case this guard exists to catch: it is not a per-user-project
runtime artifact this repo's own `.claude/metrics/` scoping was built for
(see the plan this docstring cites). It is this MONOREPO's own dev-eval-
corpus data stream — every producer and consumer of it
(`agent-eval/SKILL.md`'s `--append`, `harness-audit/SKILL.md`'s
`--find-latest`, `knowledge/telemetry-schema.md`'s `eval-ablation.jsonl`
entry) already agrees on this exact bare, repo-root-relative path, and
changing the default to route through `artifact_paths.metrics_dir()`
would silently redirect it to `.claude/metrics/eval-ablation.jsonl` —
breaking every one of those already-documented invocations, not fixing
an oversight.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_DIR = _REPO_ROOT / "plugins" / "dev-team"

_ALLOWLIST: set[str] = {"scripts/eval_ablation.py"}

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


def test_allowlist_entries_still_match_the_pattern_they_exempt():
    """An allowlist entry whose file no longer contains a legacy bare-path
    default has become stale slack, not a documented exception — the module
    docstring's own stated rule. Every entry must still trip
    `_LEGACY_DEFAULT_RE` when the allowlist filter in
    `_production_py_files()` is bypassed, or it should be removed instead of
    carried forward on faith."""
    for rel in _ALLOWLIST:
        text = (_PLUGIN_DIR / rel).read_text(encoding="utf-8")
        assert _LEGACY_DEFAULT_RE.search(text), (
            f"{rel} is in _ALLOWLIST but no longer matches _LEGACY_DEFAULT_RE "
            "— remove this stale entry"
        )
