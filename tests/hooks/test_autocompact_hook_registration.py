"""Registration of the autocompact hooks in both manifests (#2177 slice 6).

hooks.json and settings.json must agree (also pinned by
test_plugin_hooks_json.py); this file pins the exact matchers and that the
removed context ceiling guard is gone from both.
"""

from __future__ import annotations

import json

import pytest

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
MANIFESTS = {
    "hooks.json": PLUGIN / "hooks" / "hooks.json",
    "settings.json": PLUGIN / "settings.json",
}


def _session_start(path):
    return json.loads(path.read_text(encoding="utf-8"))["hooks"]["SessionStart"]


def _groups_running(path, script):
    return [g for g in _session_start(path) if any(script in h["command"] for h in g["hooks"])]


@pytest.mark.parametrize("name", MANIFESTS)
@pytest.mark.parametrize(
    "script,matcher",
    [
        ("autocompact_setup_nudge.py", "startup|resume|clear"),
        ("post_compact_state_reinject.py", "compact"),
    ],
)
def test_hook_registered_once_with_its_exact_matcher(name, script, matcher):
    groups = _groups_running(MANIFESTS[name], script)
    assert [g.get("matcher") for g in groups] == [matcher]
    assert (PLUGIN / "hooks" / script).is_file()


@pytest.mark.parametrize("name", MANIFESTS)
def test_nudge_matcher_does_not_cover_compact(name):
    import re

    (group,) = _groups_running(MANIFESTS[name], "autocompact_setup_nudge.py")
    assert not re.fullmatch(group["matcher"], "compact")
    (reinject,) = _groups_running(MANIFESTS[name], "post_compact_state_reinject.py")
    for source in ("startup", "resume", "clear"):
        assert not re.fullmatch(reinject["matcher"], source)


@pytest.mark.parametrize("name", MANIFESTS)
def test_context_ceiling_guard_is_not_registered_anywhere(name):
    assert "context_ceiling_guard" not in MANIFESTS[name].read_text(encoding="utf-8")


def test_guard_script_and_its_test_are_deleted():
    assert not (PLUGIN / "hooks" / "context_ceiling_guard.py").exists()
    assert not (PLUGIN / "tests" / "hooks" / "test_context_ceiling_guard.py").exists()


def test_both_manifests_register_the_same_autocompact_hooks():
    shapes = []
    for path in MANIFESTS.values():
        shapes.append(
            sorted(
                (g.get("matcher"), sorted(h["command"].split("/")[-1].strip('"') for h in g["hooks"]))
                for g in _session_start(path)
                if g.get("matcher") in ("compact", "startup|resume|clear")
            )
        )
    assert shapes[0] == shapes[1] and len(shapes[0]) == 2
