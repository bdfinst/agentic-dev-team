"""Tests for hooks/autocompact_setup_nudge.py (#2177 slice 3, AC 5).

Every case runs the hook as a real subprocess so exit code and stdout are
what Claude Code would see.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOK = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "autocompact_setup_nudge.py"
KEY = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"

ABSENT_LINE = (
    "dev-team: context autocompact is not configured for this repo; run /dev-team:setup "
    "to set it (default 40%). Silence: DEV_TEAM_AUTOCOMPACT_NUDGE=0 or create "
    ".claude/memory/autocompact-nudge-off\n"
)


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    return p


def _run(proj, stdin="", extra_env=None, project_dir_env=True, cwd=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "DEV_TEAM_"))}
    env["HOME"] = str(proj.parent / "home")
    if project_dir_env:
        env["CLAUDE_PROJECT_DIR"] = str(proj)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd or proj),
        check=False,
    )


def _settings(proj, name="settings.json", value=None, raw=None):
    path = proj / ".claude" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps({"env": {KEY: value}}), "utf-8")
    return path


def _payload(**kw):
    return json.dumps({"hook_event_name": "SessionStart", **kw})


def test_absent_prints_the_exact_advisory_line(proj):
    r = _run(proj, _payload(source="startup"))
    assert (r.returncode, r.stdout, r.stderr) == (0, ABSENT_LINE, "")


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_valid_value_is_silent(proj, name):
    _settings(proj, name, "40")
    r = _run(proj, _payload(source="startup"))
    assert (r.returncode, r.stdout) == (0, "")


def test_valid_value_in_process_env_is_silent(proj):
    r = _run(proj, _payload(source="startup"), extra_env={KEY: "55"})
    assert (r.returncode, r.stdout) == (0, "")


@pytest.mark.parametrize("bad", ["abc", "0", "101"])
def test_invalid_value_prints_corrective_line(proj, bad):
    _settings(proj, value=bad)
    r = _run(proj, _payload(source="startup"))
    assert r.returncode == 0
    assert r.stdout == (
        f"dev-team: {KEY}='{bad}' is invalid (need integer 1-100); re-run /dev-team:setup\n"
    )


def test_opt_out_env_is_silent(proj):
    r = _run(proj, _payload(source="startup"), extra_env={"DEV_TEAM_AUTOCOMPACT_NUDGE": "0"})
    assert (r.returncode, r.stdout) == (0, "")


def test_opt_out_marker_is_silent(proj):
    marker = proj / ".claude" / "memory" / "autocompact-nudge-off"
    marker.parent.mkdir(parents=True)
    marker.touch()
    r = _run(proj, _payload(source="startup"))
    assert (r.returncode, r.stdout) == (0, "")


@pytest.mark.parametrize("source", ["startup", "resume", "clear", None])
def test_fires_on_non_compact_sources(proj, source):
    payload = _payload() if source is None else _payload(source=source)
    assert _run(proj, payload).stdout == ABSENT_LINE


def test_never_fires_on_compact(proj):
    r = _run(proj, _payload(source="compact"))
    assert (r.returncode, r.stdout) == (0, "")


def test_project_dir_env_unset_falls_back_to_payload_cwd(proj):
    r = _run(proj, _payload(source="startup", cwd=str(proj)), project_dir_env=False, cwd=proj.parent)
    assert (r.returncode, r.stdout, r.stderr) == (0, ABSENT_LINE, "")


def test_project_dir_env_unset_and_no_cwd_uses_process_cwd(proj):
    _settings(proj, value="40")
    r = _run(proj, _payload(source="startup"), project_dir_env=False, cwd=proj)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("stdin", ["", "   \n", "\x00{{", "[1,2]", '"x"', "null"])
def test_fail_open_on_empty_or_garbage_stdin(proj, stdin):
    r = _run(proj, stdin)
    assert r.returncode == 0
    assert "Traceback" not in r.stderr


def test_malformed_settings_fail_open(proj):
    _settings(proj, raw="{not json")
    r = _run(proj, _payload(source="startup"))
    assert r.returncode == 0 and "Traceback" not in r.stderr
    assert r.stdout == ABSENT_LINE


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 is not enforced for root / Windows",
)
def test_unreadable_settings_fail_open(proj):
    path = _settings(proj, value="40")
    path.chmod(0)
    try:
        r = _run(proj, _payload(source="startup"))
        assert r.returncode == 0 and "Traceback" not in r.stderr
    finally:
        path.chmod(0o644)


def test_hook_never_imports_from_dot_claude_lib():
    text = _HOOK.read_text(encoding="utf-8")
    assert "session_start_common" not in text
    assert ".claude/lib" not in text
