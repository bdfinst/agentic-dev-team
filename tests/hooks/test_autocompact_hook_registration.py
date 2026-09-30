"""Registration of the autocompact hooks in both manifests (#2177 slice 6).

hooks.json/settings.json agreement is pinned by test_plugin_hooks_json.py;
this file pins the exact matchers and that the removed context ceiling guard,
its report script and its validation doc are gone.
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
def test_context_ceiling_guard_is_not_registered_anywhere(name):
    assert "context_ceiling_guard" not in MANIFESTS[name].read_text(encoding="utf-8")


def test_guard_report_and_validation_doc_are_deleted():
    assert not (PLUGIN / "hooks" / "context_ceiling_guard.py").exists()
    assert not (PLUGIN / "tests" / "hooks" / "test_context_ceiling_guard.py").exists()
    assert not (REPO_ROOT / "scripts" / "context_ceiling_report.py").exists()
    assert not (REPO_ROOT / "tests" / "scripts" / "test_context_ceiling_report.py").exists()
    assert not (REPO_ROOT / "docs" / "context-ceiling-validation.md").exists()
