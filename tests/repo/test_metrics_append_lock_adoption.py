"""Enforces that every `.claude/metrics/*.jsonl` writer under
plugins/dev-team/hooks/ and plugins/dev-team/scripts/ appends via
`atomic_state.append_line_locked` rather than a bare, unlocked
`open(path, "a")` (issue #1896).

A bare append-mode `open()` on a shared metrics stream can interleave two
concurrent writers' bytes mid-line and corrupt the JSONL file for every
downstream consumer — the same race `atomic_state.append_line_locked` was
introduced to close (#1889/#1891/#1894/#1897/#1898). This is a mechanical,
AST-based sensor so a future PR that reintroduces a bare unlocked append on
a metrics stream fails a test instead of shipping unnoticed, the same
enforcement shape as `test_hermetic_adoption.py`'s git-hermeticity scan.

Detection is deliberately best-effort, NOT full data-flow (same disclosed
tradeoff as `test_hermetic_adoption.py`): it flags an append-mode
`open(...)`/`<expr>.open(...)` call whose target argument's un-parsed
source — either directly, or via the nearest same-name assignment anywhere
else in the file — contains a quoted `"metrics"` string literal or an
`artifact_paths.metrics_dir(` call. A call reached only through an
argparse default, a renamed parameter threaded through another function, or
any other indirection this scan doesn't trace can still slip through — see
the allowlist below for the one confirmed such gap.
"""

from __future__ import annotations

import ast
import re

from _repo_root import REPO_ROOT

_SCAN_DIRS = ("plugins/dev-team/hooks", "plugins/dev-team/scripts")

_METRICS_TARGET_RE = re.compile(r"""(['"])metrics\1|metrics_dir\(""")

# Files with a confirmed, legitimately-exempt bare append-mode open() on a
# metrics-shaped target. One line each — no silent/bulk exemptions.
_ALLOWLIST: dict[str, str] = {
    "plugins/dev-team/hooks/lib/boundary_events.py": (
        "_append_line_locked already holds atomic_state.locked_state for "
        "the whole open+write+close critical section (#1874) — it predates "
        "append_line_locked() and reimplements its exact contract manually, "
        "it does not bypass it"
    ),
    "plugins/dev-team/hooks/pre_commit_review.py": (
        "the flagged open() is inside this module's own degraded-import "
        "fallback shim for atomic_state.append_line_locked (used only when "
        "atomic_state itself fails to import) — it mirrors that helper's "
        "exact fail-open/fail-closed contract rather than bypassing it"
    ),
    "plugins/dev-team/hooks/mutation_testing_smoke_gate.py": (
        "same degraded-import fallback shim pattern as pre_commit_review.py "
        "above — mirrors atomic_state.append_line_locked's contract for the "
        "case where atomic_state itself can't be imported"
    ),
    "plugins/dev-team/scripts/gherkin_effectiveness_rollup.py": (
        "known pre-existing gap, out of scope for #1896's 7-site batch: its "
        "default output path is under .claude/metrics/ but the actual "
        "target is threaded through an argparse --out default, which this "
        "scan's same-name backward-slice does not trace through — surfaced "
        "here rather than silently excluded, not yet fixed"
    ),
}


def _is_open_call(func: ast.expr) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "open"
    if isinstance(func, ast.Attribute):
        return func.attr == "open"
    return False


def _open_call_target(call: ast.Call) -> ast.expr | None:
    """The path expression an open()/<expr>.open() call targets."""
    if isinstance(call.func, ast.Attribute):
        # <expr>.open(...) — the target is the object itself (e.g. a Path).
        return call.func.value
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg in ("file", "path"):
            return kw.value
    return None


def _open_call_mode(call: ast.Call) -> str | None:
    """The literal mode string, if statically determinable."""
    is_method = isinstance(call.func, ast.Attribute)
    positional_index = 0 if is_method else 1
    if len(call.args) > positional_index:
        arg = call.args[positional_index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(
            kw.value.value, str
        ):
            return kw.value.value
    return None


def _is_metrics_target_text(text: str) -> bool:
    return bool(_METRICS_TARGET_RE.search(text))


def _metrics_append_offenders(text: str) -> list[int]:
    """Line numbers of append-mode open() calls whose target looks like a
    `.claude/metrics/` path (direct literal, or same-name backward slice)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    metrics_vars: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        rhs_text = ast.unparse(node.value)
        if not _is_metrics_target_text(rhs_text):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                metrics_vars.add(target.id)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_open_call(node.func):
            continue
        mode = _open_call_mode(node)
        if not mode or not mode.startswith("a"):
            continue
        target = _open_call_target(node)
        if target is None:
            continue
        is_metrics_target = isinstance(target, ast.Name) and target.id in metrics_vars
        if not is_metrics_target:
            is_metrics_target = _is_metrics_target_text(ast.unparse(target))
        if is_metrics_target:
            offenders.append(node.lineno)
    return offenders


def test_metrics_append_offenders_flags_a_synthetic_bare_open() -> None:
    """Proves the detector can actually fire — not just stay quiet on a clean tree."""
    src = (
        "import artifact_paths\n"
        "METRICS_PATH = artifact_paths.metrics_dir(cwd) / 'example.jsonl'\n"
        "def _write(line):\n"
        "    with open(METRICS_PATH, 'a') as fh:\n"
        "        fh.write(line)\n"
    )
    assert _metrics_append_offenders(src) == [4]


def test_metrics_append_offenders_ignores_a_locked_append() -> None:
    src = (
        "from atomic_state import append_line_locked\n"
        "METRICS_PATH = 'metrics/example.jsonl'\n"
        "def _write(line):\n"
        "    append_line_locked(METRICS_PATH, line)\n"
    )
    assert _metrics_append_offenders(src) == []


def test_metrics_append_offenders_ignores_a_non_metrics_bare_open() -> None:
    src = (
        "def _write(line):\n"
        "    with open('reports/output.txt', 'a') as fh:\n"
        "        fh.write(line)\n"
    )
    assert _metrics_append_offenders(src) == []


def test_metrics_jsonl_appenders_route_through_append_line_locked() -> None:
    offenders = []
    for scan_dir in _SCAN_DIRS:
        for f in sorted((REPO_ROOT / scan_dir).rglob("*.py")):
            rel = f.relative_to(REPO_ROOT).as_posix()
            if rel in _ALLOWLIST:
                continue
            lines = _metrics_append_offenders(f.read_text(encoding="utf-8"))
            offenders.extend(f"{rel}:{lineno}" for lineno in lines)

    assert not offenders, (
        "The following bare append-mode open() calls target a "
        ".claude/metrics/ path without going through "
        "atomic_state.append_line_locked (#1896). Route them through the "
        "shared helper, or add a one-line rationale to _ALLOWLIST above if "
        "genuinely exempt.\n" + "\n".join(f"  {o}" for o in offenders)
    )
