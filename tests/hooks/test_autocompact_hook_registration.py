"""Registration of the autocompact hooks in both manifests (#2177 slice 6).

hooks.json/settings.json agreement is pinned by test_plugin_hooks_json.py;
this file pins the exact matchers and that the removed context ceiling guard,
its report script and its validation doc are gone.
"""

from __future__ import annotations

import json
import re

import pytest

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
MANIFESTS = {
    "hooks.json": PLUGIN / "hooks" / "hooks.json",
    "settings.json": PLUGIN / "settings.json",
}
PROJECT_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
NOT_ON_COMPACT = "startup|resume|clear"
COMPACT_ONLY_HOOK = "post_compact_state_reinject.py"


def _session_start(path):
    return json.loads(path.read_text(encoding="utf-8"))["hooks"]["SessionStart"]


def _groups_running(path, script):
    return [g for g in _session_start(path) if any(script in h["command"] for h in g["hooks"])]


@pytest.mark.parametrize("name", MANIFESTS)
@pytest.mark.parametrize(
    "script,matcher",
    [
        ("autocompact_setup_nudge.py", NOT_ON_COMPACT),
        ("pending_review_notify.py", NOT_ON_COMPACT),
        ("repo_review_nudge.py", NOT_ON_COMPACT),
        ("mcp_json_repowise_nudge.py", NOT_ON_COMPACT),
        ("codegraph_bootstrap.py", NOT_ON_COMPACT),
        (COMPACT_ONLY_HOOK, "compact"),
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


def _fires_on_compact(group):
    """A group with no matcher fires on every source, compact included."""
    matcher = group.get("matcher")
    return not matcher or re.fullmatch(matcher, "compact") is not None


@pytest.mark.parametrize("name", MANIFESTS)
def test_only_the_state_reinject_hook_fires_on_compact(name):
    """Any other SessionStart group re-fires on compact and repeats its nudges."""
    firing = [
        [h["command"] for h in g["hooks"]]
        for g in _session_start(MANIFESTS[name])
        if _fires_on_compact(g) and not any(COMPACT_ONLY_HOOK in h["command"] for h in g["hooks"])
    ]
    assert firing == []


def test_project_install_hook_runs_on_startup_only():
    groups = _groups_running(PROJECT_SETTINGS, "install-dev-team.sh")
    assert [g.get("matcher") for g in groups] == ["startup"]

