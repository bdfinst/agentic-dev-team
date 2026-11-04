"""Tests for plugins/dev-team/scripts/doctor.py and scripts/lib/doctor_report.py.

Slice 1 of plans/2272-doctor.md: the report model, the install-side checks,
the CLI and its exit codes. Checks are driven through an injected ``Context``
(temp roots, a temp config dir, a fake ``which``, a fake shim); the CLI is
driven as a subprocess against a temp plugin root so only the intended check
varies.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_codebase_recon import _hermetic_git_env

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
SCRIPTS = PLUGIN / "scripts"

sys.path.insert(0, str(SCRIPTS))
import doctor

report_model = doctor._model()
Check = report_model.Check
Report = report_model.Report
Status = report_model.Status
format_human = report_model.format_human

INSTALL_SIDE_IDS = (
    "plugin-version",
    "hook-registration",
    "interpreter",
    "python-floor",
    "required-tools",
    "optional-tools",
)
CHECK_IDS = INSTALL_SIDE_IDS + (
    "metrics-writable",
    "project-settings",
    "managed-sections",
)
ISSUES_URL = "https://github.com/bdfinst/agentic-dev-team/issues"


def _context(tmp_path: Path, **overrides) -> doctor.Context:
    """A Context over temp roots against the real plugin; nothing on PATH."""
    values = {
        "plugin_root": PLUGIN,
        "project_root": tmp_path / "project",
        "config_dir": tmp_path / "claude",
        "which": lambda name: None,
    }
    values.update(overrides)
    return doctor.Context(**values)


def _constant_check(status: Status, summary: str = "s", fix: str | None = None):
    """A check function that, like the real ones, leaves its id for the runner."""
    return lambda ctx: Check("", status, summary, fix)


def _checks_returning(*statuses: Status):
    return tuple(
        (
            f"check-{i}",
            _constant_check(status, fix=None if status is Status.OK else "/x"),
        )
        for i, status in enumerate(statuses)
    )


def _raising(exc: Exception):
    def check(ctx):
        raise exc

    return check


# ---------------------------------------------------------------------------
# Step 1.1: report model, JSON schema, per-check isolation, human output
# ---------------------------------------------------------------------------


def test_json_top_level_keys_are_exactly_the_schema_in_order(tmp_path):
    report = doctor.run(_context(tmp_path), checks=_checks_returning(Status.OK))

    assert list(report.to_json()) == [
        "schema_version",
        "plugin_root",
        "project_root",
        "checks",
        "fixed",
        "overall",
    ]


def test_json_schema_version_is_one_and_fixed_is_empty_without_fix(tmp_path):
    payload = doctor.run(
        _context(tmp_path), checks=_checks_returning(Status.OK)
    ).to_json()

    assert payload["schema_version"] == 1
    assert payload["fixed"] == []


def test_json_each_check_has_exactly_id_status_summary_fix_and_null_fix(tmp_path):
    payload = doctor.run(
        _context(tmp_path), checks=(("a", _constant_check(Status.OK, "fine")),)
    ).to_json()

    (entry,) = payload["checks"]
    assert list(entry) == ["id", "status", "summary", "fix"]
    assert entry == {"id": "a", "status": "ok", "summary": "fine", "fix": None}
    assert '"fix": null' in json.dumps(payload)


def test_json_roots_are_the_context_roots(tmp_path):
    context = _context(tmp_path)

    payload = doctor.run(context, checks=()).to_json()

    assert payload["plugin_root"] == str(context.plugin_root)
    assert payload["project_root"] == str(context.project_root)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((Status.OK, Status.OK), "ok"),
        ((Status.OK, Status.WARN), "warn"),
        ((Status.OK, Status.WARN, Status.FAIL), "fail"),
        ((Status.FAIL, Status.OK), "fail"),
        ((), "ok"),
    ],
)
def test_overall_is_the_worst_status(tmp_path, statuses, expected):
    report = doctor.run(_context(tmp_path), checks=_checks_returning(*statuses))

    assert report.to_json()["overall"] == expected


def test_checks_appear_in_table_order(tmp_path):
    table = tuple((cid, _constant_check(Status.OK)) for cid in ("z", "a", "m"))

    report = doctor.run(_context(tmp_path), checks=table)

    assert [c["id"] for c in report.to_json()["checks"]] == ["z", "a", "m"]


def test_the_table_id_replaces_whatever_id_a_check_function_returns(tmp_path):
    table = (
        ("from-table", lambda ctx: Check("self-claimed", Status.OK, "s")),
        ("also-from-table", lambda ctx: Check("", Status.OK, "s")),
    )

    report = doctor.run(_context(tmp_path), checks=table)

    assert [c.id for c in report.checks] == ["from-table", "also-from-table"]


def _nine_checks_with(failing_id: str, exc: Exception):
    return tuple(
        (cid, _raising(exc) if cid == failing_id else _constant_check(Status.OK))
        for cid in CHECK_IDS
    )


def test_a_raising_check_is_fail_with_the_issue_tracker_fix_and_others_still_report(
    tmp_path,
):
    table = _nine_checks_with("hook-registration", OSError("boom"))

    report = doctor.run(_context(tmp_path), checks=table)

    by_id = {c.id: c for c in report.checks}
    assert [c.id for c in report.checks] == list(CHECK_IDS)
    assert by_id["hook-registration"].status is Status.FAIL
    assert by_id["hook-registration"].summary == "internal error: OSError: boom"
    assert ISSUES_URL in by_id["hook-registration"].fix
    assert [c.status for c in report.checks if c.id != "hook-registration"] == [
        Status.OK
    ] * (len(CHECK_IDS) - 1)


def test_a_check_raising_import_error_points_at_upgrade(tmp_path):
    table = _nine_checks_with("plugin-version", ImportError("no module"))

    report = doctor.run(_context(tmp_path), checks=table)

    check = report.checks[0]
    assert check.status is Status.FAIL
    assert check.summary == "internal error: ImportError: no module"
    assert check.fix == "/upgrade"


def test_isolation_does_not_catch_keyboard_interrupt(tmp_path):
    table = (("a", _raising(KeyboardInterrupt())),)

    with pytest.raises(KeyboardInterrupt):
        doctor.run(_context(tmp_path), checks=table)


def _sample_report(**overrides) -> Report:
    fields = {
        "plugin_root": "/p/plugin",
        "project_root": "/p/project",
        "checks": [
            Check("alpha", Status.OK, "all good"),
            Check("beta", Status.WARN, "meh", "/setup"),
            Check("gamma", Status.FAIL, "bad", "edit /p/x"),
        ],
    }
    fields.update(overrides)
    return Report(**fields)


def test_human_output_has_header_one_line_per_check_and_overall():
    lines = format_human(_sample_report(), in_git_repository=True).splitlines()

    assert lines[:2] == ["plugin: /p/plugin", "project: /p/project"]
    assert "ok    alpha  all good" in lines
    assert "warn  beta  meh" in lines
    assert "fail  gamma  bad" in lines
    assert lines[-1] == "overall: fail"


def test_human_output_prints_a_fix_line_only_for_a_non_null_fix():
    lines = format_human(_sample_report(), in_git_repository=True).splitlines()

    fix_lines = [line.strip() for line in lines if "fix:" in line]
    assert fix_lines == ["fix: /setup", "fix: edit /p/x"]
    assert lines[lines.index("ok    alpha  all good") + 1].startswith("warn")


def test_human_output_notes_a_project_outside_git_after_the_header():
    lines = format_human(_sample_report(), in_git_repository=False).splitlines()

    assert lines[2] == "note: /p/project is not inside a git repository"


def test_human_output_has_no_note_inside_git():
    assert "note:" not in format_human(_sample_report(), in_git_repository=True)


def test_human_output_reads_fixed_none_when_fix_ran_and_nothing_was_created():
    lines = format_human(
        _sample_report(), in_git_repository=True, fix_ran=True
    ).splitlines()

    assert "fixed: none" in lines


def test_human_output_omits_the_fixed_block_without_fix():
    assert "fixed:" not in format_human(_sample_report(), in_git_repository=True)


def test_human_output_lists_what_fix_created():
    report = _sample_report(fixed=["created /p/project/.claude/metrics"])

    lines = format_human(report, in_git_repository=True, fix_ran=True).splitlines()

    assert lines[lines.index("fixed:") + 1] == "  created /p/project/.claude/metrics"


def test_human_output_prints_the_errors_block_before_overall_when_errors_exist():
    report = _sample_report(errors=["fix failed: /p/x: denied"])

    lines = format_human(report, in_git_repository=True, fix_ran=True).splitlines()

    assert lines[-3:] == ["errors:", "  fix failed: /p/x: denied", "overall: fail"]


def test_human_output_has_no_errors_block_when_there_are_none():
    assert "errors:" not in format_human(
        _sample_report(), in_git_repository=True, fix_ran=True
    )


# ---------------------------------------------------------------------------
# Step 1.2: Context and the plugin-version check
# ---------------------------------------------------------------------------

ABSENT = object()
MARKET = "bfinster"


def _config_dir(tmp_path: Path, installed=ABSENT, catalog=ABSENT) -> Path:
    """A temp CLAUDE_CONFIG_DIR with an install record and a cached catalog.

    ``ABSENT`` writes nothing; ``None`` writes a null version; a string is the
    version.
    """
    config = tmp_path / "claude"
    plugins = config / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    if installed is not ABSENT:
        record = {"plugins": {f"dev-team@{MARKET}": [{"version": installed}]}}
        (plugins / "installed_plugins.json").write_text(json.dumps(record))
    if catalog is not ABSENT:
        market_dir = tmp_path / "marketplace"
        (market_dir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (market_dir / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "dev-team", "version": catalog}]})
        )
        (plugins / "known_marketplaces.json").write_text(
            json.dumps({MARKET: {"installLocation": str(market_dir)}})
        )
    return config


def _plugin_version(tmp_path: Path, **config) -> Check:
    context = _context(tmp_path, config_dir=_config_dir(tmp_path, **config))
    return doctor.check_plugin_version(context)


@pytest.mark.parametrize(
    ("installed", "catalog", "status", "fix"),
    [
        ("14.0.0", "14.0.1", Status.WARN, "/upgrade"),
        ("14.0.9", "14.0.10", Status.WARN, "/upgrade"),
        ("14.0.10", "14.0.9", Status.OK, None),
        ("14.0.1", "14.0.0", Status.OK, None),
        ("14.0.1", "14.0.1", Status.OK, None),
    ],
)
def test_version_comparison_is_numeric(tmp_path, installed, catalog, status, fix):
    check = _plugin_version(tmp_path, installed=installed, catalog=catalog)

    assert (check.status, check.fix) == (status, fix)
    assert installed in check.summary


def test_a_healthy_install_names_the_version_in_the_summary(tmp_path):
    check = _plugin_version(tmp_path, installed="14.0.1", catalog="14.0.1")

    assert check.summary == "14.0.1 installed (catalog 14.0.1)"


def test_an_upgradable_install_names_both_versions(tmp_path):
    check = _plugin_version(tmp_path, installed="14.0.0", catalog="14.0.1")

    assert check.summary == "14.0.0 installed, 14.0.1 available"


@pytest.mark.parametrize(
    ("installed", "catalog", "summary"),
    [
        ("14.0.1", ABSENT, "catalog not cached"),
        ("14.0.1", "next", "cannot compare"),
        ("dev", "14.0.1", "cannot compare"),
    ],
)
def test_an_uncached_or_incomparable_catalog_is_ok(
    tmp_path, installed, catalog, summary
):
    check = _plugin_version(tmp_path, installed=installed, catalog=catalog)

    assert (check.status, check.fix) == (Status.OK, None)
    assert summary in check.summary


def test_a_missing_install_record_is_warn_with_the_install_command(tmp_path):
    check = _plugin_version(tmp_path)

    assert check.status is Status.WARN
    assert check.fix == "claude plugin install dev-team@bfinster"
    assert "no install record" in check.summary


@pytest.mark.parametrize(
    "record_bytes",
    [
        b"{not json",
        json.dumps({"plugins": {"dev-team@bfinster": [{"version": None}]}}).encode(),
        json.dumps({"plugins": {"other@bfinster": [{"version": "1.0.0"}]}}).encode(),
        json.dumps({"plugins": []}).encode(),
        json.dumps({"plugins": {"dev-team@bfinster": {"version": "14.0.1"}}}).encode(),
        b'{"plugins": "\xff"}',
    ],
    ids=[
        "unparsable",
        "null-version",
        "no-dev-team-entry",
        "plugins-not-an-object",
        "entry-is-an-object-not-a-list",
        "not-utf-8",
    ],
)
def test_an_unusable_install_record_is_warn_naming_the_file(tmp_path, record_bytes):
    config = _config_dir(tmp_path)
    (config / "plugins" / "installed_plugins.json").write_bytes(record_bytes)

    check = doctor.check_plugin_version(_context(tmp_path, config_dir=config))

    assert check.status is Status.WARN
    assert check.fix == "claude plugin install dev-team@bfinster"
    assert "installed_plugins.json" in check.summary
    assert "no usable version" in check.summary


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("14.0.10", (14, 0, 10)),
        ("0", (0,)),
        ("next", None),
        ("14.0.1-rc1", None),
        ("", None),
        ("14..1", None),
        ("\u0663.0", None),
        (None, None),
        (14, None),
    ],
)
def test_version_tuple_accepts_only_dotted_ascii_digits(text, expected):
    assert doctor._version_tuple(text) == expected


def _args(project: Path) -> SimpleNamespace:
    return SimpleNamespace(project=project)


def test_from_args_falls_back_to_the_real_plugin_root_for_a_non_directory(tmp_path):
    not_a_dir = tmp_path / "file"
    not_a_dir.write_text("x")

    context = doctor.Context.from_args(
        _args(tmp_path), {doctor.PLUGIN_ROOT_ENV: str(not_a_dir)}
    )

    assert context.plugin_root == PLUGIN.resolve()


def test_from_args_uses_claude_plugin_root_when_it_is_a_directory(tmp_path):
    context = doctor.Context.from_args(
        _args(tmp_path), {doctor.PLUGIN_ROOT_ENV: str(tmp_path)}
    )

    assert context.plugin_root == tmp_path.resolve()


def test_from_args_reads_the_config_dir_from_the_injected_env(tmp_path):
    context = doctor.Context.from_args(
        _args(tmp_path), {doctor.CONFIG_DIR_ENV: str(tmp_path / "cfg")}
    )

    assert context.config_dir == tmp_path / "cfg"


def test_from_args_defaults_the_config_dir_to_home_dot_claude(tmp_path):
    context = doctor.Context.from_args(_args(tmp_path), {})

    assert context.config_dir == Path.home() / ".claude"


def test_from_args_resolves_a_directory_outside_git_to_itself(tmp_path):
    context = doctor.Context.from_args(_args(tmp_path), {})

    assert context.project_root == tmp_path.resolve()


def test_from_args_defaults_the_shim_and_script_under_the_plugin_root(tmp_path):
    context = doctor.Context.from_args(
        _args(tmp_path), {doctor.PLUGIN_ROOT_ENV: str(tmp_path)}
    )

    assert context.shim == tmp_path.resolve() / "hooks" / "py.sh"
    assert context.script == tmp_path.resolve() / "scripts" / "doctor.py"


def test_a_plugin_root_without_hooks_lib_still_builds_a_context_and_fails_the_version_check(
    tmp_path,
):
    bare_root = tmp_path / "bare"
    bare_root.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    context = doctor.Context.from_args(
        _args(project), {doctor.PLUGIN_ROOT_ENV: str(bare_root)}
    )
    report = doctor.run(
        context, checks=(("plugin-version", doctor.check_plugin_version),)
    )

    assert context.project_root == project.resolve()
    (check,) = report.checks
    assert check.status is Status.FAIL
    assert check.fix == "/upgrade"
    assert "check_version_drift" in check.summary


def test_a_check_version_drift_that_raises_at_import_is_fail_naming_the_helper(
    tmp_path,
):
    root = tmp_path / "plugin"
    helper_dir = root / "skills" / "upgrade" / "scripts"
    helper_dir.mkdir(parents=True)
    (helper_dir / "check_version_drift.py").write_text('raise RuntimeError("boom")\n')

    report = doctor.run(
        _context(tmp_path, plugin_root=root),
        checks=(("plugin-version", doctor.check_plugin_version),),
    )

    (check,) = report.checks
    assert check.status is Status.FAIL
    assert check.fix == "/upgrade"
    assert "cannot load check_version_drift" in check.summary


def _completed(returncode: int) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode)


def _no_git_on_path(tmp_path: Path, monkeypatch) -> None:
    """Git cannot be started: PATH names an empty directory."""
    empty = tmp_path / "no-git-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))


def _project_dir(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def test_git_absent_means_not_in_git_and_the_human_output_notes_it(
    tmp_path, monkeypatch
):
    _no_git_on_path(tmp_path, monkeypatch)
    project = _project_dir(tmp_path)

    context = doctor.Context.from_args(_args(project), {})
    text = format_human(doctor.run(context, checks=()), context.in_git)

    assert (context.project_root, context.in_git) == (project.resolve(), False)
    assert (
        f"note: {project.resolve()} is not inside a git repository" in text.splitlines()
    )


def _raising_run(exc: Exception):
    def run_process(*args, **kwargs):
        raise exc

    return run_process


@pytest.mark.parametrize(
    ("run_process", "expected"),
    [
        (lambda *a, **k: _completed(0), True),
        (lambda *a, **k: _completed(128), False),
        (_raising_run(subprocess.TimeoutExpired("git", 1)), False),
        (_raising_run(FileNotFoundError("git")), False),
    ],
    ids=["toplevel-resolved", "not-a-repository", "timeout", "git-missing"],
)
def test_in_git_follows_the_one_git_membership_call(
    tmp_path, monkeypatch, run_process, expected
):
    _no_git_on_path(tmp_path, monkeypatch)  # the helper's own git lookup finds nothing

    context = doctor.Context.from_args(
        _args(_project_dir(tmp_path)), {}, run_process=run_process
    )

    assert context.in_git is expected


def test_an_unloadable_artifact_paths_falls_back_to_start_and_is_not_in_git(tmp_path):
    root = tmp_path / "plugin"
    (root / "hooks" / "lib").mkdir(parents=True)
    (root / "hooks" / "lib" / "artifact_paths.py").write_text("def broken(:\n")
    project = _project_dir(tmp_path)

    context = doctor.Context.from_args(
        _args(project),
        {doctor.PLUGIN_ROOT_ENV: str(root)},
        run_process=lambda *a, **k: _completed(0),
    )

    assert (context.project_root, context.in_git) == (project.resolve(), False)


def test_the_default_probe_write_removes_its_file_and_leaves_a_stale_probe(tmp_path):
    stale = tmp_path / ".doctor-probe-stale"
    stale.write_text("")

    doctor._probe_write(tmp_path)

    assert [path.name for path in tmp_path.iterdir()] == [stale.name]


def test_the_default_probe_write_raises_when_the_directory_cannot_hold_a_file(
    tmp_path,
):
    with pytest.raises(OSError):
        doctor._probe_write(tmp_path / "absent")


# ---------------------------------------------------------------------------
# Step 1.3: hook-registration
# ---------------------------------------------------------------------------


def _hook_command(script: str) -> dict:
    return {
        "type": "command",
        "command": f'sh "${{CLAUDE_PLUGIN_ROOT}}/hooks/py.sh" {script}',
    }


def _hooks_json(*commands: dict) -> dict:
    """Three-level shape of the shipped file: event -> matcher group -> hooks."""
    return {
        "hooks": {
            "SessionStart": [{"hooks": list(commands[:1])}],
            "Stop": [{"hooks": list(commands[1:])}],
        }
    }


def _plugin_with_hooks(tmp_path: Path, hooks_json: object, *existing: str) -> Path:
    """A temp plugin root whose hooks/hooks.json is ``hooks_json`` (str kept verbatim)."""
    root = tmp_path / "plugin"
    (root / "hooks").mkdir(parents=True, exist_ok=True)
    text = hooks_json if isinstance(hooks_json, str) else json.dumps(hooks_json)
    (root / "hooks" / "hooks.json").write_text(text)
    for relative in ("hooks/py.sh", *existing):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("")
    return root


def _hook_registration(tmp_path: Path, hooks_json: object, *existing: str) -> Check:
    root = _plugin_with_hooks(tmp_path, hooks_json, *existing)
    return doctor.check_hook_registration(_context(tmp_path, plugin_root=root))


def test_hooks_whose_scripts_all_exist_are_ok(tmp_path):
    hooks = _hooks_json(
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/a.py"'),
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/b.py"'),
    )

    check = _hook_registration(tmp_path, hooks, "hooks/a.py", "hooks/b.py")

    assert (check.status, check.fix) == (Status.OK, None)


def test_missing_scripts_in_later_commands_are_all_named(tmp_path):
    hooks = _hooks_json(
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/a.py"'),
        _hook_command("hooks/missing_a.py"),
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/missing_b.sh"'),
    )

    check = _hook_registration(tmp_path, hooks, "hooks/a.py")

    assert (check.status, check.fix) == (Status.FAIL, "/upgrade")
    assert check.summary == "missing: hooks/missing_a.py, hooks/missing_b.sh"


def test_a_script_missing_from_several_commands_is_named_once(tmp_path):
    hooks = _hooks_json(_hook_command("hooks/gone.py"), _hook_command("hooks/gone.py"))

    check = _hook_registration(tmp_path, hooks)

    assert check.summary == "missing: hooks/gone.py"


def test_a_command_without_a_script_token_and_an_absolute_script_are_ok(tmp_path):
    outside = tmp_path / "elsewhere" / "tool.sh"
    outside.parent.mkdir()
    outside.write_text("")
    hooks = _hooks_json(
        {"type": "command", "command": "echo hi"},
        {"type": "command", "command": f"sh {outside}"},
    )

    check = _hook_registration(tmp_path, hooks)

    assert check.status is Status.OK


def test_an_absolute_script_that_does_not_exist_is_named_by_its_absolute_path(tmp_path):
    gone = tmp_path / "elsewhere" / "gone.sh"
    hooks = _hooks_json(
        {"type": "command", "command": "echo hi"},
        {"type": "command", "command": f"sh {gone}"},
    )

    check = _hook_registration(tmp_path, hooks)

    assert (check.status, check.summary) == (Status.FAIL, f"missing: {gone}")


def test_a_quoted_script_path_containing_a_space_resolves(tmp_path):
    hooks = _hooks_json(
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/my hooks/a.py"'),
        {"type": "command", "command": "echo hi"},
    )

    check = _hook_registration(tmp_path, hooks, "my hooks/a.py")

    assert check.status is Status.OK


def test_a_command_with_an_unbalanced_quote_still_has_its_script_checked(tmp_path):
    hooks = _hooks_json(
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/a.py'),
        {"type": "command", "command": "echo hi"},
    )

    check = _hook_registration(tmp_path, hooks)

    assert check.summary == "missing: hooks/a.py"


@pytest.mark.parametrize(
    ("command", "tokens"),
    [
        ("echo hi", []),
        (
            'sh "${CLAUDE_PLUGIN_ROOT}/hooks/py.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/a.py"',
            ["${CLAUDE_PLUGIN_ROOT}/hooks/py.sh", "${CLAUDE_PLUGIN_ROOT}/hooks/a.py"],
        ),
        ("python3 -c 'print(1)'", []),
        ("sh x.pyc", []),
    ],
)
def test_script_tokens_keep_only_py_and_sh_words_unquoted(command, tokens):
    assert doctor._script_tokens(command) == tokens


def test_commands_are_collected_from_any_depth_in_document_order():
    node = {
        "A": [{"hooks": [{"command": "one"}, {"command": 7}]}],
        "B": {"command": "two"},
    }

    assert doctor._commands(node) == ["one", "two"]


@pytest.mark.parametrize(
    ("hooks_json", "summary"),
    [
        ("{not json", "hooks/hooks.json: invalid JSON"),
        ("[]", "hooks/hooks.json: not an object"),
        ({"hooks": {}}, "hooks/hooks.json: no hook commands"),
        ({}, "hooks/hooks.json: no hooks object"),
        ({"hooks": []}, "hooks/hooks.json: no hooks object"),
        ({"hooks": "x"}, "hooks/hooks.json: no hooks object"),
    ],
    ids=["unparsable", "array", "empty-hooks", "no-key", "list", "string"],
)
def test_an_unusable_hooks_json_is_fail_with_a_pinned_summary(
    tmp_path, hooks_json, summary
):
    check = _hook_registration(tmp_path, hooks_json)

    assert (check.status, check.fix, check.summary) == (
        Status.FAIL,
        "/upgrade",
        summary,
    )


def test_an_absent_hooks_json_is_fail_missing(tmp_path):
    root = tmp_path / "plugin"
    root.mkdir()

    check = doctor.check_hook_registration(_context(tmp_path, plugin_root=root))

    assert (check.status, check.fix, check.summary) == (
        Status.FAIL,
        "/upgrade",
        "hooks/hooks.json: missing",
    )


def test_a_hooks_json_with_invalid_utf8_is_invalid_json(tmp_path):
    root = _plugin_with_hooks(tmp_path, {})
    (root / "hooks" / "hooks.json").write_bytes(b'{"hooks": "\xff"}')

    check = doctor.check_hook_registration(_context(tmp_path, plugin_root=root))

    assert check.summary == "hooks/hooks.json: invalid JSON"


def test_the_shipped_hooks_json_resolves_every_command_against_the_real_plugin(
    tmp_path,
):
    raw = (PLUGIN / "hooks" / "hooks.json").read_text()
    command_count = raw.count('"command":')

    check = doctor.check_hook_registration(_context(tmp_path))

    assert command_count > 0
    assert len(doctor._commands(json.loads(raw)["hooks"])) == command_count
    assert (check.status, check.summary) == (
        Status.OK,
        f"{command_count} hook commands, every script present",
    )


# ---------------------------------------------------------------------------
# Step 1.4: interpreter self-probe and python-floor
# ---------------------------------------------------------------------------

DOCTOR = SCRIPTS / "doctor.py"
REPORT_MODULE = SCRIPTS / "lib" / "doctor_report.py"
REAL_SHIM = PLUGIN / "hooks" / "py.sh"


def _probe_env() -> dict[str, str]:
    """PATH for sh and friends; py.sh pinned to the interpreter running pytest."""
    return {"PATH": os.environ["PATH"], "DEV_TEAM_PYTHON": sys.executable}


def _shim(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "shim.sh"
    path.write_text(body)
    return path


def _probe_context(tmp_path: Path, shim: Path, **overrides) -> doctor.Context:
    values = {"shim": shim, "script": DOCTOR, "env": _probe_env()}
    values.update(overrides)
    return _context(tmp_path, **values)


def _both(context: doctor.Context) -> tuple[Check, Check]:
    return doctor.check_interpreter(context), doctor.check_python_floor(context)


def test_a_shim_that_execs_this_interpreter_is_ok_and_names_the_path(tmp_path):
    shim = _shim(tmp_path, f'exec "{sys.executable}" "$@"\n')

    interpreter, floor = _both(_probe_context(tmp_path, shim))

    assert (interpreter.status, interpreter.fix) == (Status.OK, None)
    assert sys.executable in interpreter.summary
    assert (floor.status, floor.fix) == (Status.OK, None)


def test_the_real_shim_with_the_real_script_resolves_an_interpreter(tmp_path):
    interpreter, floor = _both(_probe_context(tmp_path, REAL_SHIM))

    assert interpreter.summary == f"py.sh resolved {sys.executable}"
    assert floor.status is Status.OK


@pytest.mark.parametrize(
    ("version", "status"),
    [
        ("2.7.18", Status.FAIL),
        ("3.9.18", Status.FAIL),
        ("3.10.0", Status.OK),
        ("3.12.1", Status.OK),
        ("4.0.0", Status.OK),
    ],
)
def test_the_floor_boundary_is_exactly_3_10_0(tmp_path, version, status):
    shim = _shim(tmp_path, f'echo "/usr/bin/python3 {version}"\n')

    check = doctor.check_python_floor(_probe_context(tmp_path, shim))

    assert check.status is status
    assert version in check.summary


def test_a_version_below_the_floor_names_the_path_and_the_floor_and_the_fix(tmp_path):
    shim = _shim(tmp_path, 'echo "/opt/py 3.9.18"\n')

    check = doctor.check_python_floor(_probe_context(tmp_path, shim))

    assert check.summary == "/opt/py is 3.9.18; floor is 3.10"
    assert check.fix == "install Python 3.10+ (ADR 0031)"


def test_an_interpreter_path_containing_a_space_is_kept_whole(tmp_path):
    shim = _shim(tmp_path, 'echo "/opt/my python/bin/python3 3.12.1"\n')

    probe = _probe_context(tmp_path, shim).probe()

    assert (probe.path, probe.version) == ("/opt/my python/bin/python3", (3, 12, 1))


@pytest.mark.parametrize(
    ("body", "summary"),
    [
        ('echo "no python" >&2\nexit 2\n', "py.sh found no interpreter: no python"),
        ("echo Traceback >&2\nexit 1\n", "probe exited 1: Traceback"),
        ("exit 7\n", "probe exited 7"),
        ("exit 2\n", "py.sh found no interpreter"),
        ("echo hello\n", "probe printed no version line"),
        ("exit 0\n", "probe printed no version line"),
        ('echo "/usr/bin/python3 3.12"\n', "probe printed no version line"),
    ],
    ids=[
        "exit-2",
        "exit-1-traceback",
        "exit-7",
        "exit-2-silent",
        "garbage",
        "empty",
        "two-part-version",
    ],
)
def test_a_probe_without_a_version_fails_both_checks_with_a_distinct_summary(
    tmp_path, body, summary
):
    context = _probe_context(tmp_path, _shim(tmp_path, body))

    interpreter, floor = _both(context)

    assert (interpreter.status, interpreter.summary) == (Status.FAIL, summary)
    assert interpreter.fix == "set DEV_TEAM_PYTHON to a Python 3 path"
    assert (floor.status, floor.summary) == (Status.FAIL, "no interpreter resolved")
    assert floor.fix == "install Python 3.10+ (ADR 0031)"


def test_a_probe_that_outlives_its_timeout_fails_both_checks_naming_the_timeout(
    tmp_path,
):
    shim = _shim(tmp_path, "exec sleep 5\n")
    context = _probe_context(tmp_path, shim, probe_timeout=0.2)

    interpreter, floor = _both(context)

    assert (interpreter.status, interpreter.summary) == (
        Status.FAIL,
        "probe timed out after 0.2 s",
    )
    assert floor.summary == "no interpreter resolved"


def test_a_missing_shim_file_fails_without_running_anything(tmp_path):
    gone = tmp_path / "no-such-shim.sh"

    interpreter, floor = _both(_probe_context(tmp_path, gone))

    assert interpreter.status is Status.FAIL
    assert interpreter.summary == f"shim not found: {gone}"
    assert interpreter.fix == "set DEV_TEAM_PYTHON to a Python 3 path"
    assert floor.summary == "no interpreter resolved"


def test_a_valid_version_line_is_ignored_when_the_shim_exits_nonzero(
    tmp_path,
):
    shim = _shim(tmp_path, 'echo "/usr/bin/python3 3.12.1"\nexit 1\n')

    interpreter, floor = _both(_probe_context(tmp_path, shim))

    assert interpreter.summary == "probe exited 1"
    assert floor.summary == "no interpreter resolved"


def test_a_missing_sh_is_reported_as_cannot_run_sh(tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    shim = _shim(tmp_path, "exit 0\n")
    context = _probe_context(tmp_path, shim, env={"PATH": str(empty)})

    interpreter, floor = _both(context)

    assert interpreter.status is Status.FAIL
    assert "cannot run sh" in interpreter.summary
    assert floor.status is Status.FAIL


def test_python_floor_alone_gives_the_same_verdict_as_after_interpreter(tmp_path):
    shim = _shim(tmp_path, 'echo "/usr/bin/python3 3.9.18"\n')

    alone = doctor.check_python_floor(_probe_context(tmp_path, shim))
    after = _both(_probe_context(tmp_path, shim))[1]

    assert alone == after


def test_both_checks_share_one_probe_subprocess(tmp_path):
    marker = tmp_path / "invocations"
    shim = _shim(tmp_path, f'echo run >> "{marker}"\necho "/usr/bin/python3 3.12.1"\n')

    _both(_probe_context(tmp_path, shim))

    assert marker.read_text().splitlines() == ["run"]


def test_the_probe_runs_the_shim_with_the_script_and_probe_flag(tmp_path):
    seen = tmp_path / "args"
    shim = _shim(tmp_path, f'echo "$@" > "{seen}"\necho "/usr/bin/python3 3.12.1"\n')

    _probe_context(tmp_path, shim).probe()

    assert seen.read_text().split() == [str(DOCTOR), "--probe"]


def test_the_probe_gives_the_shim_a_private_cache_not_the_session_cache(tmp_path):
    seen = tmp_path / "cache-path"
    shim = _shim(
        tmp_path,
        f'echo "$DEV_TEAM_PY_CACHE" > "{seen}"\necho "/usr/bin/python3 3.12.1"\n',
    )

    _probe_context(tmp_path, shim).probe()

    cache = Path(seen.read_text().strip())
    assert cache != Path("/tmp/.dev-team-python")
    assert cache.name == "python"
    assert not cache.parent.exists()  # the scratch directory is gone afterwards


def test_the_probe_preserves_the_caller_env_for_the_shim(tmp_path):
    seen = tmp_path / "marker"
    shim = _shim(
        tmp_path,
        f'echo "$DOCTOR_TEST_MARKER" > "{seen}"\necho "/usr/bin/python3 3.12.1"\n',
    )
    context = _probe_context(
        tmp_path, shim, env={**_probe_env(), "DOCTOR_TEST_MARKER": "kept"}
    )

    context.probe()

    assert seen.read_text().strip() == "kept"


def _run_script(script: Path, *args: str, cwd: Path, env: dict | None = None):
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env if env is not None else {**os.environ},
    )


def test_probe_mode_prints_one_line_and_creates_no_claude_directory(tmp_path):
    done = _run_script(DOCTOR, "--probe", "--fix", "--json", cwd=tmp_path)

    assert done.returncode == 0
    assert re.fullmatch(r"\S+ \d+\.\d+\.\d+\n", done.stdout)
    assert done.stdout.split()[0] == sys.executable
    assert not (tmp_path / ".claude").exists()


def test_probe_mode_returns_before_the_lib_import(tmp_path):
    copy = tmp_path / "scripts"
    copy.mkdir()
    shutil.copy(DOCTOR, copy / "doctor.py")  # deliberately without scripts/lib

    done = _run_script(copy / "doctor.py", "--probe", cwd=tmp_path)

    assert (done.returncode, done.stderr) == (0, "")
    assert done.stdout.startswith(sys.executable)


@pytest.mark.parametrize("module", [DOCTOR, REPORT_MODULE], ids=lambda m: m.name)
def test_module_top_level_parses_as_python_3_8(module):
    ast.parse(module.read_text(), feature_version=(3, 8))


# ---------------------------------------------------------------------------
# Step 1.5: tools, CLI flags, exit codes, import hygiene
# ---------------------------------------------------------------------------

OPTIONAL_TOOLS = ("gh", "semgrep", "adr", "shellcheck", "uv")


def _which_finding(*present: str):
    return lambda name: f"/usr/bin/{name}" if name in present else None


def test_jq_absent_is_warn_with_setup_fix_and_the_manual_install_hint(tmp_path):
    check = doctor.check_required_tools(_context(tmp_path, which=_which_finding()))

    assert check.status is Status.WARN
    assert check.fix == "/setup"
    assert check.summary == "jq not on PATH (manual: brew install jq)"


def test_jq_present_is_ok_with_no_fix(tmp_path):
    check = doctor.check_required_tools(_context(tmp_path, which=_which_finding("jq")))

    assert (check.status, check.fix) == (Status.OK, None)


@pytest.mark.parametrize(
    ("present", "summary"),
    [
        (("gh", "uv"), "present: gh, uv; absent: semgrep, adr, shellcheck"),
        ((), "present: none; absent: gh, semgrep, adr, shellcheck, uv"),
        (OPTIONAL_TOOLS, "present: gh, semgrep, adr, shellcheck, uv; absent: none"),
        (("uv", "gh"), "present: gh, uv; absent: semgrep, adr, shellcheck"),
    ],
    ids=["gh-and-uv", "nothing", "everything", "lookup-order-irrelevant"],
)
def test_optional_tools_never_change_the_status_and_list_in_declared_order(
    tmp_path, present, summary
):
    context = _context(tmp_path, which=_which_finding(*present))

    check = doctor.check_optional_tools(context)

    assert (check.status, check.fix, check.summary) == (Status.OK, None, summary)


def test_the_registered_checks_start_with_the_install_side_ids_in_order():
    ids = tuple(check_id for check_id, _ in doctor.CHECKS)

    assert ids[: len(INSTALL_SIDE_IDS)] == INSTALL_SIDE_IDS


def _install_side(checks):
    """The install-side subset of a report's checks, in report order."""
    return [c for c in checks if c.id in INSTALL_SIDE_IDS]


def test_a_healthy_install_reports_every_install_side_check_ok(tmp_path):
    config = _config_dir(tmp_path, installed="14.0.1", catalog="14.0.1")
    root = _temp_plugin(tmp_path)
    context = _context(
        tmp_path,
        plugin_root=root,
        config_dir=config,
        env=_probe_env(),
        shim=REAL_SHIM,
        script=DOCTOR,
        which=_which_finding("jq"),
    )

    checks = _install_side(doctor.run(context).checks)

    assert [c.id for c in checks] == list(INSTALL_SIDE_IDS)
    assert [c.status for c in checks] == [Status.OK] * len(INSTALL_SIDE_IDS)
    assert [c.fix for c in checks] == [None] * len(INSTALL_SIDE_IDS)
    by_id = {c.id: c for c in checks}
    assert sys.executable in by_id["interpreter"].summary
    assert "14.0.1" in by_id["plugin-version"].summary


# -- CLI as a subprocess against a temp plugin root ----------------------------


def _healthy_hooks_json() -> dict:
    return _hooks_json(
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/a.py"'),
        _hook_command('"${CLAUDE_PLUGIN_ROOT}/hooks/b.py"'),
    )


def _temp_plugin(tmp_path: Path, hooks_json: object | None = None) -> Path:
    """A minimal plugin: the real shim, helpers and doctor, plus a controlled hooks.json."""
    root = _plugin_with_hooks(
        tmp_path,
        _healthy_hooks_json() if hooks_json is None else hooks_json,
        "hooks/a.py",
        "hooks/b.py",
    )
    copies = {
        REAL_SHIM: "hooks/py.sh",
        PLUGIN / "hooks" / "lib" / "artifact_paths.py": "hooks/lib/artifact_paths.py",
        PLUGIN
        / "skills"
        / "upgrade"
        / "scripts"
        / "check_version_drift.py": "skills/upgrade/scripts/check_version_drift.py",
        DOCTOR: "scripts/doctor.py",
        REPORT_MODULE: "scripts/lib/doctor_report.py",
    }
    for source, relative in copies.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
    return root


def _cli_env(tmp_path: Path, plugin: Path, config: Path) -> dict[str, str]:
    """A hermetic env: stub jq first on PATH, py.sh pinned, temp HOME and config."""
    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir(exist_ok=True)
    jq = stub_bin / "jq"
    jq.write_text("#!/bin/sh\nexit 0\n")
    jq.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
        "DEV_TEAM_PYTHON": sys.executable,
        "CLAUDE_PLUGIN_ROOT": str(plugin),
        "CLAUDE_CONFIG_DIR": str(config),
        "HOME": str(home),
    }


def _run_cli(
    tmp_path: Path,
    *args: str,
    plugin: Path | None = None,
    config: Path | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    plugin = plugin or _temp_plugin(tmp_path)
    config = config or _config_dir(tmp_path, installed="14.0.1", catalog="14.0.1")
    workdir = cwd or tmp_path / "cwd"
    workdir.mkdir(exist_ok=True)
    return _run_script(
        plugin / "scripts" / "doctor.py",
        *args,
        cwd=workdir,
        env=_cli_env(tmp_path, plugin, config),
    )


@pytest.mark.parametrize("flags", [(), ("--json",)], ids=["human", "json"])
def test_a_healthy_install_exits_0(tmp_path, flags):
    done = _run_cli(tmp_path, *flags)

    assert (done.returncode, done.stderr) == (0, "")


def test_a_healthy_install_prints_json_with_every_install_check_ok(tmp_path):
    done = _run_cli(tmp_path, "--json")

    payload = json.loads(done.stdout)
    checks = [c for c in payload["checks"] if c["id"] in INSTALL_SIDE_IDS]
    assert [c["id"] for c in checks] == list(INSTALL_SIDE_IDS)
    assert {c["status"] for c in checks} == {"ok"}
    assert payload["overall"] == "ok"


def _plugin_missing_hook_script(tmp_path: Path) -> Path:
    """A temp plugin whose hooks.json names hooks/gone.py, which does not exist."""
    return _temp_plugin(
        tmp_path,
        _hooks_json(_hook_command("hooks/gone.py"), _hook_command("hooks/a.py")),
    )


@pytest.mark.parametrize("flags", [(), ("--json",)], ids=["human", "json"])
def test_a_broken_hooks_json_exits_1(tmp_path, flags):
    plugin = _plugin_missing_hook_script(tmp_path)

    done = _run_cli(tmp_path, *flags, plugin=plugin)

    assert done.returncode == 1


def test_a_broken_hooks_json_is_the_only_fail_in_the_json(tmp_path):
    plugin = _plugin_missing_hook_script(tmp_path)

    done = _run_cli(tmp_path, "--json", plugin=plugin)

    failing = [
        c["id"] for c in json.loads(done.stdout)["checks"] if c["status"] == "fail"
    ]
    assert failing == ["hook-registration"]
    assert json.loads(done.stdout)["overall"] == "fail"


def test_a_broken_hooks_json_prints_the_fail_row_and_its_fix_in_human_output(tmp_path):
    plugin = _plugin_missing_hook_script(tmp_path)

    done = _run_cli(tmp_path, plugin=plugin)

    assert "fail  hook-registration  missing: hooks/gone.py" in done.stdout
    assert "      fix: /upgrade" in done.stdout
    assert done.stdout.endswith("overall: fail\n")


def _behind_the_catalog(tmp_path: Path) -> Path:
    """A config dir whose install record is one patch behind the cached catalog."""
    return _config_dir(tmp_path, installed="14.0.0", catalog="14.0.1")


def test_a_warn_only_run_exits_0_with_json(tmp_path):
    done = _run_cli(tmp_path, "--json", config=_behind_the_catalog(tmp_path))

    statuses = {c["id"]: c["status"] for c in json.loads(done.stdout)["checks"]}
    assert statuses["interpreter"] == "ok"  # guard: only plugin-version varies
    assert statuses["plugin-version"] == "warn"
    assert done.returncode == 0


def test_a_warn_only_run_exits_0_in_human_output(tmp_path):
    done = _run_cli(tmp_path, config=_behind_the_catalog(tmp_path))

    rows = [line.split()[:2] for line in done.stdout.splitlines()]
    assert ["ok", "interpreter"] in rows  # guard: only plugin-version varies
    assert ["warn", "plugin-version"] in rows
    assert done.returncode == 0


def test_an_unknown_flag_exits_2_naming_it(tmp_path):
    done = _run_cli(tmp_path, "--bogus")

    assert done.returncode == 2
    assert "--bogus" in done.stderr


def test_an_abbreviated_flag_exits_2(tmp_path):
    done = _run_cli(tmp_path, "--js")

    assert done.returncode == 2
    assert "--js" in done.stderr


def test_a_missing_project_directory_exits_2_naming_the_path(tmp_path):
    done = _run_cli(tmp_path, "--project", "/no/such/dir")

    assert done.returncode == 2
    assert "/no/such/dir" in done.stderr


def test_help_names_the_exit_codes_and_hides_the_internal_probe_flag(tmp_path):
    done = _run_cli(tmp_path, "--help")

    text = " ".join(done.stdout.split())
    assert done.returncode == 0
    assert "0 when the overall status is ok or warn" in text
    assert "1 when a check failed or a --fix action failed" in text
    assert "2 on a usage error" in text
    assert "--probe" not in text


def test_a_project_outside_git_resolves_to_itself_and_the_human_output_notes_it(
    tmp_path,
):
    project = tmp_path / "plain"
    project.mkdir()
    elsewhere = tmp_path / "elsewhere"

    as_json = _run_cli(tmp_path, "--project", str(project), "--json", cwd=elsewhere)
    as_text = _run_cli(tmp_path, "--project", str(project), cwd=elsewhere)

    assert json.loads(as_json.stdout)["project_root"] == str(project.resolve())
    assert (
        f"note: {project.resolve()} is not inside a git repository"
        in as_text.stdout.splitlines()
    )


def _git_repo(path: Path) -> None:
    """``git init`` ``path`` under a scrubbed env, so ambient GIT_* never leak in."""
    subprocess.run(
        ["git", "init", "-q", str(path)],
        check=True,
        capture_output=True,
        env=_hermetic_git_env(path.parent),
    )


def test_a_subdirectory_of_a_git_repository_resolves_to_the_toplevel(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src" / "app").mkdir(parents=True)
    _git_repo(repo)
    plugin = _temp_plugin(tmp_path)

    as_json = _run_cli(
        tmp_path, "--project", str(repo / "src" / "app"), "--json", plugin=plugin
    )
    as_text = _run_cli(tmp_path, "--project", str(repo / "src" / "app"), plugin=plugin)

    assert json.loads(as_json.stdout)["project_root"] == str(repo.resolve())
    assert as_text.stdout.splitlines()[:2] == [
        f"plugin: {plugin.resolve()}",
        f"project: {repo.resolve()}",
    ]
    assert "note:" not in as_text.stdout


def test_json_roots_are_absolute(tmp_path):
    payload = json.loads(_run_cli(tmp_path, "--json").stdout)

    assert Path(payload["plugin_root"]).is_absolute()
    assert Path(payload["project_root"]).is_absolute()


def test_fix_is_accepted_and_changes_nothing_in_slice_one(tmp_path):
    done = _run_cli(tmp_path, "--fix", "--json")

    assert (done.returncode, json.loads(done.stdout)["fixed"]) == (0, [])


# -- import hygiene --------------------------------------------------------------

PLUGIN_HELPERS = {"artifact_paths", "autocompact_config", "check_version_drift"}


def _module_level_imports(module: Path) -> list[str]:
    """Top-level names imported at import time (function bodies excluded)."""
    found: list[str] = []

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(child, ast.Import):
                found.extend(alias.name.split(".")[0] for alias in child.names)
            elif isinstance(child, ast.ImportFrom):
                found.append((child.module or "").split(".")[0])
            visit(child)

    visit(ast.parse(module.read_text()))
    return found


@pytest.mark.parametrize("module", [DOCTOR, REPORT_MODULE], ids=lambda m: m.name)
def test_module_level_imports_are_standard_library_or_doctor_report(module):
    imported = _module_level_imports(module)

    assert imported != []
    assert [
        name
        for name in imported
        if name not in sys.stdlib_module_names and name != "doctor_report"
    ] == []
    assert PLUGIN_HELPERS.isdisjoint(imported)
