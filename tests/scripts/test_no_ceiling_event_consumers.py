"""Telemetry-consumer check for removing the context ceiling guard (#2177 slice 7).

The guard emitted one boundary event (`hook="context_ceiling_guard"`,
`reason="context-ceiling"`). Before deleting it and its report script, pin
that no shipped reader or writer keys on those event names: any consumer that
did would silently misbehave (KeyError / zero rows) once the events stop.
Exact string constants are compared, so prose in docstrings does not count.
"""

from __future__ import annotations

import ast

from _repo_root import REPO_ROOT

_EVENT_LITERALS = {"context_ceiling_guard", "context-ceiling"}
_SCAN_ROOTS = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks",
    REPO_ROOT / "plugins" / "dev-team" / "scripts",
    REPO_ROOT / "plugins" / "dev-team" / "skills",
    REPO_ROOT / "scripts",
)
_EMITTER = "context_ceiling_guard.py"  # the producer itself, until it is deleted


def _literal_hits(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in _EVENT_LITERALS
    ]


def test_no_consumer_keys_on_the_guards_boundary_event() -> None:
    offenders = {}
    for root in _SCAN_ROOTS:
        for path in root.rglob("*.py"):
            if path.name == _EMITTER:
                continue
            hits = _literal_hits(path)
            if hits:
                offenders[str(path.relative_to(REPO_ROOT))] = hits
    assert not offenders, (
        "these files compare against the ceiling guard's boundary-event names and "
        f"would misbehave once the guard is gone: {offenders}"
    )


def test_the_scan_can_fail(tmp_path) -> None:
    probe = tmp_path / "consumer.py"
    probe.write_text('EVENT = "context-ceiling"\n', encoding="utf-8")
    assert _literal_hits(probe) == ["context-ceiling"]
