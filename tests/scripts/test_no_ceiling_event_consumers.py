"""Telemetry-consumer check for removing the context ceiling guard (#2177 slice 7).

The guard emitted one boundary event (`hook="context_ceiling_guard"`,
`reason="context-ceiling"`). Pin that no shipped reader or writer keys on those
event names: any consumer that did would silently misbehave (KeyError / zero
rows) now that the events have stopped.

Python files are compared by exact string constant (AST), so prose in
docstrings does not count; a file that does not parse is itself a finding,
since it cannot be vouched for. Shell/JSON/JS/TS files have no cheap AST, so
they are searched as raw text.
"""

from __future__ import annotations

import ast

from _repo_root import REPO_ROOT

_EVENT_LITERALS = ("context_ceiling_guard", "context-ceiling")
_RAW_SUFFIXES = {".sh", ".json", ".js", ".ts"}
_SCAN_ROOTS = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks",
    REPO_ROOT / "plugins" / "dev-team" / "scripts",
    REPO_ROOT / "plugins" / "dev-team" / "skills",
    REPO_ROOT / "scripts",
    REPO_ROOT / "evals",
)
_SKIP_PARTS = {"__pycache__", "node_modules", ".git"}


def _literal_hits(path):
    """Event-name hits in one file, or a marker string when it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"<unreadable: {type(exc).__name__}>"]
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError) as exc:
            return [f"<unparseable: {type(exc).__name__}>"]
        return [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and node.value in _EVENT_LITERALS
        ]
    return [literal for literal in _EVENT_LITERALS if literal in text]


def _scan(roots):
    offenders: dict[str, list[str]] = {}
    visited = 0
    for root in roots:
        assert root.is_dir(), f"scan root missing: {root}"
        for path in root.rglob("*"):
            if not path.is_file() or _SKIP_PARTS.intersection(path.parts):
                continue
            if path.suffix != ".py" and path.suffix not in _RAW_SUFFIXES:
                continue
            visited += 1
            hits = _literal_hits(path)
            if hits:
                offenders[str(path.relative_to(root.parent))] = hits
    return offenders, visited


def test_no_consumer_keys_on_the_guards_boundary_event() -> None:
    offenders, visited = _scan(_SCAN_ROOTS)
    assert visited > 100, f"scan visited only {visited} files"
    assert not offenders, (
        "these files compare against the ceiling guard's boundary-event names (or "
        f"could not be checked) and would misbehave now the guard is gone: {offenders}"
    )


def test_the_scan_can_fail(tmp_path) -> None:
    """Run the full `_scan` (not just the helper) against a seeded tree."""
    root = tmp_path / "tree"
    root.mkdir()
    (root / "consumer.py").write_text('EVENT = "context-ceiling"\n', encoding="utf-8")
    (root / "prose.py").write_text('"""mentions context-ceiling"""\nX = 1\n', encoding="utf-8")
    (root / "broken.py").write_text("def (:\n", encoding="utf-8")
    (root / "hook.sh").write_text("grep context_ceiling_guard log\n", encoding="utf-8")
    (root / "cfg.json").write_text('{"hook": "context-ceiling"}\n', encoding="utf-8")
    (root / "app.ts").write_text('const e = "context-ceiling";\n', encoding="utf-8")
    (root / "clean.py").write_text("X = 1\n", encoding="utf-8")
    offenders, visited = _scan([root])
    assert visited == 7
    assert sorted(offenders) == [
        "tree/app.ts",
        "tree/broken.py",
        "tree/cfg.json",
        "tree/consumer.py",
        "tree/hook.sh",
    ]
    assert offenders["tree/broken.py"] == ["<unparseable: SyntaxError>"]


def test_a_missing_scan_root_is_an_error(tmp_path) -> None:
    import pytest

    with pytest.raises(AssertionError, match="scan root missing"):
        _scan([tmp_path / "nope"])
