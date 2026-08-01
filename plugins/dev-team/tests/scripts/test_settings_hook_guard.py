"""Unit tests for scripts/lib/settings_hook_guard.py (#1367).

Validates the scan -> relocate guard project-init's Step 4c wraps around
`graphify install --project`, and that runs standalone as a repo audit (the
same check `/setup` should re-run against a repo that was already
graphify-installed before this guard existed). Does NOT exercise the real
graphify binary (not installed in this sandbox) — it stubs installers that
reproduce graphify's real behavior (additively append a machine-specific
absolute-path PreToolUse hook alongside whatever was already in the file)
and asserts the guard relocates that entry to `.claude/settings.local.json`
without disturbing anything pre-existing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))

import settings_hook_guard

ALICE_EXE = "/Users/alice/.local/bin/graphify"
BOB_EXE = "/home/bob/.local/share/uv/tools/graphifyy/bin/graphify"
WINDOWS_EXE = r"C:\Users\alice\.local\bin\graphify.exe"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _pollute_installer(settings_path: Path, exe: str = ALICE_EXE) -> None:
    """Reproduce graphify's real behavior: additively append a machine-
    specific PreToolUse hook to whatever is already in the file."""
    settings = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
    pre_tool_use = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre_tool_use.append(
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": f"{exe} hook-guard search"}],
        }
    )
    pre_tool_use.append(
        {
            "matcher": "Read|Glob",
            "hooks": [{"type": "command", "command": f"{exe} hook-guard read"}],
        }
    )
    _write_json(settings_path, settings)


def _clean_installer(settings_path: Path) -> None:
    """A well-behaved installer that relies on PATH, not an absolute path."""
    settings = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
    pre_tool_use = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre_tool_use.append(
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "graphify hook-guard search"}],
        }
    )
    _write_json(settings_path, settings)


def test_find_absolute_graphify_entries_detects_polluting_entry():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": f"{ALICE_EXE} hook-guard search"}
                    ],
                }
            ]
        }
    }

    found = settings_hook_guard.find_absolute_graphify_entries(settings)

    assert len(found) == 1
    assert found[0]["matcher"] == "Bash"


def test_find_absolute_graphify_entries_ignores_path_relative_command():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "graphify hook-guard search"}],
                }
            ]
        }
    }

    assert settings_hook_guard.find_absolute_graphify_entries(settings) == []


def test_find_absolute_graphify_entries_ignores_unrelated_absolute_command():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [{"type": "command", "command": "/usr/bin/env echo preexisting"}],
                }
            ]
        }
    }

    assert settings_hook_guard.find_absolute_graphify_entries(settings) == []


def test_find_absolute_graphify_entries_detects_windows_path():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": f"{WINDOWS_EXE} hook-guard search"}
                    ],
                }
            ]
        }
    }

    found = settings_hook_guard.find_absolute_graphify_entries(settings)

    assert len(found) == 1


def test_find_absolute_graphify_entries_detects_forward_slash_windows_path():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "c:/Users/alice/.local/bin/graphify.exe hook-guard search"}
                    ],
                }
            ]
        }
    }

    assert len(settings_hook_guard.find_absolute_graphify_entries(settings)) == 1


def test_find_absolute_graphify_entries_detects_unc_path():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": r"\\server\share\graphify hook-guard search"}
                    ],
                }
            ]
        }
    }

    assert len(settings_hook_guard.find_absolute_graphify_entries(settings)) == 1


def test_find_absolute_graphify_entries_detects_case_insensitive_basename():
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/Graphify hook-guard search"}],
                },
                {
                    "matcher": "Read|Glob",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/GRAPHIFY.EXE hook-guard read"}],
                },
            ]
        }
    }

    assert len(settings_hook_guard.find_absolute_graphify_entries(settings)) == 2


def test_find_absolute_graphify_entries_relocates_whole_entry_even_with_one_clean_command():
    """Relocation is per-entry, not per-command — an entry with a mix of a
    polluting and a clean command still moves as a unit (#1367 test-review)."""
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": f"{ALICE_EXE} hook-guard search"},
                        {"type": "command", "command": "echo also-runs-here"},
                    ],
                }
            ]
        }
    }

    found = settings_hook_guard.find_absolute_graphify_entries(settings)

    assert len(found) == 1
    assert [h["command"] for h in found[0]["hooks"]] == [
        f"{ALICE_EXE} hook-guard search",
        "echo also-runs-here",
    ]


def test_find_absolute_graphify_entries_ignores_entry_with_no_hooks_key():
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash"}]}}

    assert settings_hook_guard.find_absolute_graphify_entries(settings) == []


def test_fix_settings_relocates_two_different_prior_installs(tmp_path: Path):
    """Two teammates' machines both polluted the same file over time —
    both distinct absolute paths must be found and relocated together."""
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(
        settings_path,
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": f"{ALICE_EXE} hook-guard search"}],
                    },
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": f"{BOB_EXE} hook-guard search"}],
                    },
                ]
            }
        },
    )

    fixed = settings_hook_guard.fix_settings(settings_path, local_settings_path)

    assert fixed is True
    shared = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "PreToolUse" not in shared.get("hooks", {})

    local = json.loads(local_settings_path.read_text(encoding="utf-8"))
    local_commands = [
        h["command"] for entry in local["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert local_commands == [
        f"{ALICE_EXE} hook-guard search",
        f"{BOB_EXE} hook-guard search",
    ]


def test_fix_settings_does_not_duplicate_entry_already_relocated(tmp_path: Path):
    """A re-poisoned shared file whose polluting entry already exists in the
    local file (from an earlier relocation) must not create a duplicate."""
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    entry = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": f"{ALICE_EXE} hook-guard search"}],
    }
    _write_json(settings_path, {"hooks": {"PreToolUse": [entry]}})
    _write_json(local_settings_path, {"hooks": {"PreToolUse": [dict(entry)]}})

    fixed = settings_hook_guard.fix_settings(settings_path, local_settings_path)

    assert fixed is True
    local = json.loads(local_settings_path.read_text(encoding="utf-8"))
    assert local["hooks"]["PreToolUse"] == [entry]


def test_guard_relocates_polluting_hook_from_live_install(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(
        settings_path,
        {
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}],
                "PreToolUse": [
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": "echo preexisting"}],
                    }
                ],
            },
            "enabledPlugins": {"foo": True},
        },
    )

    relocated = settings_hook_guard.run_install_with_guard(
        settings_path,
        local_settings_path,
        installer=lambda: _pollute_installer(settings_path),
    )

    assert relocated is True

    shared = json.loads(settings_path.read_text(encoding="utf-8"))
    # Pre-existing content survives untouched.
    assert shared["enabledPlugins"] == {"foo": True}
    assert shared["hooks"]["SessionStart"] == [
        {"hooks": [{"type": "command", "command": "echo hi"}]}
    ]
    shared_commands = [
        h["command"] for entry in shared["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert shared_commands == ["echo preexisting"]
    assert not any(ALICE_EXE in c for c in shared_commands)

    local = json.loads(local_settings_path.read_text(encoding="utf-8"))
    local_commands = [
        h["command"] for entry in local["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert local_commands == [
        f"{ALICE_EXE} hook-guard search",
        f"{ALICE_EXE} hook-guard read",
    ]


def _raising_pollute_installer(settings_path: Path, exe: str = ALICE_EXE) -> None:
    """Appends the machine-specific hook entry and then fails partway
    through, like a build error after the polluting write already
    happened."""
    _pollute_installer(settings_path, exe)
    raise RuntimeError("simulated installer failure")


def test_guard_relocates_polluting_hook_even_when_installer_raises(tmp_path: Path):
    """If `installer()` raises after already writing the polluting entry,
    `fix_settings` must still run (not be skipped because the installer
    never returned), and the original exception must still propagate to the
    caller rather than being swallowed."""
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(
        settings_path,
        {
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}],
                "PreToolUse": [
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": "echo preexisting"}],
                    }
                ],
            },
            "enabledPlugins": {"foo": True},
        },
    )

    try:
        settings_hook_guard.run_install_with_guard(
            settings_path,
            local_settings_path,
            installer=lambda: _raising_pollute_installer(settings_path),
        )
        raise AssertionError("expected the installer's RuntimeError to propagate")
    except RuntimeError as exc:
        assert "simulated installer failure" in str(exc)

    shared = json.loads(settings_path.read_text(encoding="utf-8"))
    # Pre-existing content survives untouched.
    assert shared["enabledPlugins"] == {"foo": True}
    assert shared["hooks"]["SessionStart"] == [
        {"hooks": [{"type": "command", "command": "echo hi"}]}
    ]
    shared_commands = [
        h["command"] for entry in shared["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert shared_commands == ["echo preexisting"]
    assert not any(ALICE_EXE in c for c in shared_commands)

    local = json.loads(local_settings_path.read_text(encoding="utf-8"))
    local_commands = [
        h["command"] for entry in local["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert local_commands == [
        f"{ALICE_EXE} hook-guard search",
        f"{ALICE_EXE} hook-guard read",
    ]


def test_guard_leaves_clean_install_untouched(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(settings_path, {})

    relocated = settings_hook_guard.run_install_with_guard(
        settings_path,
        local_settings_path,
        installer=lambda: _clean_installer(settings_path),
    )

    assert relocated is False
    assert not local_settings_path.exists()

    shared = json.loads(settings_path.read_text(encoding="utf-8"))
    shared_commands = [
        h["command"] for entry in shared["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert shared_commands == ["graphify hook-guard search"]


def test_guard_merges_into_existing_local_settings(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(settings_path, {})
    _write_json(
        local_settings_path,
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit",
                        "hooks": [{"type": "command", "command": "echo local-preexisting"}],
                    }
                ]
            }
        },
    )

    relocated = settings_hook_guard.run_install_with_guard(
        settings_path,
        local_settings_path,
        installer=lambda: _pollute_installer(settings_path),
    )

    assert relocated is True

    local = json.loads(local_settings_path.read_text(encoding="utf-8"))
    local_commands = [
        h["command"] for entry in local["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert local_commands == [
        "echo local-preexisting",
        f"{ALICE_EXE} hook-guard search",
        f"{ALICE_EXE} hook-guard read",
    ]


def test_fix_settings_audits_pollution_left_by_a_teammates_prior_install(tmp_path: Path):
    """The core regression scenario (#1367): a repo already carries a
    hardcoded path from *someone else's* machine — a fresh /setup run (no
    live installer call) must still detect and relocate it."""
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(
        settings_path,
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": f"{BOB_EXE} hook-guard search"}],
                    },
                    {
                        "matcher": "Read|Glob",
                        "hooks": [{"type": "command", "command": f"{BOB_EXE} hook-guard read"}],
                    },
                ]
            }
        },
    )

    fixed = settings_hook_guard.fix_settings(settings_path, local_settings_path)

    assert fixed is True
    shared = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "PreToolUse" not in shared.get("hooks", {})

    local = json.loads(local_settings_path.read_text(encoding="utf-8"))
    local_commands = [
        h["command"] for entry in local["hooks"]["PreToolUse"] for h in entry["hooks"]
    ]
    assert local_commands == [f"{BOB_EXE} hook-guard search", f"{BOB_EXE} hook-guard read"]


def test_fix_settings_noop_when_settings_file_absent(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"

    assert settings_hook_guard.fix_settings(settings_path, local_settings_path) is False
    assert not local_settings_path.exists()


def test_guard_does_not_mask_installer_exception_when_relocation_also_fails(
    tmp_path: Path, monkeypatch, capsys
):
    """A secondary failure while relocating (e.g. a permission error writing
    settings.json back) must never replace installer()'s own in-flight
    exception — the caller needs the REAL failure, not an unrelated one from
    the relocation path itself."""
    settings_path = tmp_path / "settings.json"
    local_settings_path = tmp_path / "settings.local.json"
    _write_json(
        settings_path,
        {"hooks": {}, "enabledPlugins": {"foo": True}},
    )

    # The installer's own polluting write must still succeed (call #1); only
    # the guard's later relocation-write (call #2) should fail, so the
    # sequence actually reaches the masking scenario under test.
    real_write_text = Path.write_text
    call_count = {"n": 0}

    def _write_text_fails_on_second_call(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise OSError("simulated relocation-write failure")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _write_text_fails_on_second_call)

    try:
        settings_hook_guard.run_install_with_guard(
            settings_path,
            local_settings_path,
            installer=lambda: _raising_pollute_installer(settings_path),
        )
        raise AssertionError("expected the installer's RuntimeError to propagate")
    except RuntimeError as exc:
        assert "simulated installer failure" in str(exc)

    # The secondary relocation failure is still surfaced (not silently
    # dropped), just not as the exception that propagates to the caller.
    assert "simulated relocation-write failure" in capsys.readouterr().err
