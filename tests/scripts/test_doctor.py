"""Tests for plugins/dev-team/scripts/doctor.py and scripts/lib/doctor_report.py.

Slices 1-2 of plans/2272-doctor.md: the report model, the install and project checks,
the CLI and its exit codes. Checks are driven through an injected ``Context``
(temp roots, a temp config dir, a fake ``which``, a fake shim); the CLI is
driven as a subprocess against a temp plugin root so only the intended check
varies.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from _mutation_test_helpers import hermetic_git_env

from _repo_root import REPO_ROOT

PLUGIN = REPO_ROOT / "plugins" / "dev-team"
SCRIPTS = PLUGIN / "scripts"

sys.path.insert(0, str(SCRIPTS))
import doctor

report_model = doctor._model()
doctor_checks = doctor._checks()
doctor_files = sys.modules["doctor_files"]
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
FIFO_READ_DEADLINE_SECONDS = 5


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


def _every_check_with(failing_id: str, exc: Exception):
    return tuple(
        (cid, _raising(exc) if cid == failing_id else _constant_check(Status.OK))
        for cid in CHECK_IDS
    )


def test_a_raising_check_is_fail_with_the_issue_tracker_fix_and_others_still_report(
    tmp_path,
):
    table = _every_check_with("hook-registration", OSError("boom"))

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
    table = _every_check_with("plugin-version", ImportError("no module"))

    report = doctor.run(_context(tmp_path), checks=table)

    check = report.checks[0]
    assert check.status is Status.FAIL
    assert check.summary == "internal error: ImportError: no module"
    assert check.fix == "/upgrade"


def test_a_check_returning_none_is_fail_under_its_table_id_and_others_still_report(
    tmp_path,
):
    table = (
        ("first", _constant_check(Status.OK)),
        ("returns-none", lambda ctx: None),
        ("last", _constant_check(Status.OK)),
    )

    report = doctor.run(_context(tmp_path), checks=table)

    by_id = {c.id: c for c in report.checks}
    assert [c.id for c in report.checks] == ["first", "returns-none", "last"]
    assert by_id["returns-none"].status is Status.FAIL
    assert by_id["returns-none"].summary.startswith("internal error: TypeError: ")
    assert by_id["returns-none"].fix == f"report this at {ISSUES_URL}"
    assert [by_id["first"].status, by_id["last"].status] == [Status.OK, Status.OK]


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
    return doctor_checks.check_plugin_version(context)


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


@pytest.mark.parametrize(
    "catalog_bytes",
    [b"\xff", b'{"plugins": 5}'],
    ids=["not-utf-8", "plugins-not-a-list"],
)
def test_an_unreadable_catalog_is_ok_and_not_cached(tmp_path, catalog_bytes):
    config = _config_dir(tmp_path, installed="14.0.1", catalog="14.0.1")
    market_json = tmp_path / "marketplace" / ".claude-plugin" / "marketplace.json"
    market_json.write_bytes(catalog_bytes)

    check = doctor_checks.check_plugin_version(_context(tmp_path, config_dir=config))

    assert (check.status, check.fix) == (Status.OK, None)
    assert "catalog not cached" in check.summary


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

    check = doctor_checks.check_plugin_version(_context(tmp_path, config_dir=config))

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
    assert doctor_checks._version_tuple(text) == expected


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
        _args(project),
        {doctor.PLUGIN_ROOT_ENV: str(bare_root)},
        run_process=lambda *a, **k: _completed(0, f"{project}\n"),
    )
    report = doctor.run(
        context, checks=(("plugin-version", doctor_checks.check_plugin_version),)
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
        checks=(("plugin-version", doctor_checks.check_plugin_version),),
    )

    (check,) = report.checks
    assert check.status is Status.FAIL
    assert check.fix == "/upgrade"
    assert "cannot load check_version_drift" in check.summary


def test_a_helper_that_declares_a_dataclass_loads_and_leaves_nothing_in_sys_modules(
    monkeypatch,
):
    monkeypatch.delitem(sys.modules, "autocompact_config", raising=False)

    module = doctor._load_helper(PLUGIN, "autocompact_config")

    assert module.KEY == "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
    assert "autocompact_config" not in sys.modules


def test_a_helper_load_restores_a_module_of_the_same_name_already_imported(
    monkeypatch,
):
    sentinel = SimpleNamespace(marker="already-imported")
    monkeypatch.setitem(sys.modules, "autocompact_config", sentinel)

    doctor._load_helper(PLUGIN, "autocompact_config")

    assert sys.modules["autocompact_config"] is sentinel


def _completed(returncode: int, stdout: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout)


def _project_dir(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def _raising_run(exc: Exception):
    def run_process(*args, **kwargs):
        raise exc

    return run_process


def test_git_absent_means_not_in_git_and_the_human_output_notes_it(tmp_path):
    project = _project_dir(tmp_path)

    context = doctor.Context.from_args(
        _args(project), {}, run_process=_raising_run(FileNotFoundError("git"))
    )
    text = format_human(doctor.run(context, checks=()), context.in_git)

    assert (context.project_root, context.in_git) == (project.resolve(), False)
    assert (
        f"note: {project.resolve()} is not inside a git repository" in text.splitlines()
    )


def test_a_git_free_path_reports_the_project_outside_git_end_to_end(tmp_path):
    project = _project_dir(tmp_path)
    no_git_bin = tmp_path / "no-git-bin"
    no_git_bin.mkdir()
    env = {"PATH": str(no_git_bin), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}

    completed = _run_script(
        DOCTOR, "--project", str(project), "--json", cwd=tmp_path, env=env
    )

    assert json.loads(completed.stdout)["project_root"] == str(project.resolve())
    as_text = _run_script(DOCTOR, "--project", str(project), cwd=tmp_path, env=env)
    assert (
        f"note: {project.resolve()} is not inside a git repository"
        in as_text.stdout.splitlines()
    )


def test_a_git_toplevel_is_the_project_root_and_in_git(tmp_path):
    top = tmp_path / "top"
    top.mkdir()

    context = doctor.Context.from_args(
        _args(_project_dir(tmp_path)),
        {},
        run_process=lambda *a, **k: _completed(0, f"{top}\n"),
    )

    assert (context.project_root, context.in_git) == (top.resolve(), True)


@pytest.mark.parametrize(
    "run_process",
    [
        lambda *a, **k: _completed(128),
        lambda *a, **k: _completed(0, "\n"),
        _raising_run(subprocess.TimeoutExpired("git", 1)),
        _raising_run(FileNotFoundError("git")),
    ],
    ids=["not-a-repository", "exit-0-empty-output", "timeout", "git-missing"],
)
def test_no_git_toplevel_means_the_directory_itself_and_not_in_git(
    tmp_path, run_process
):
    project = _project_dir(tmp_path)

    context = doctor.Context.from_args(_args(project), {}, run_process=run_process)

    assert (context.project_root, context.in_git) == (project.resolve(), False)


def _recorded_git_call(tmp_path: Path):
    """Run ``from_args`` with a recording fake; return ``(project, command, kwargs)``."""
    calls = []

    def run_process(command, **kwargs):
        calls.append((command, kwargs))
        return _completed(0, f"{tmp_path}\n")

    project = _project_dir(tmp_path)
    doctor.Context.from_args(_args(project), {}, run_process=run_process)
    ((command, kwargs),) = calls
    return project, command, kwargs


def test_from_args_asks_git_once_for_the_toplevel_of_the_project(tmp_path):
    project, command, _ = _recorded_git_call(tmp_path)

    assert command == [
        "git",
        "-C",
        str(project.resolve()),
        "rev-parse",
        "--show-toplevel",
    ]


def test_the_git_call_uses_its_own_timeout_constant(tmp_path):
    _, _, kwargs = _recorded_git_call(tmp_path)

    assert kwargs["timeout"] == doctor.GIT_TIMEOUT_SECONDS


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
    return doctor_checks.check_hook_registration(_context(tmp_path, plugin_root=root))


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
    assert doctor_checks._script_tokens(command) == tokens


def test_commands_are_collected_from_any_depth_in_document_order():
    node = {
        "A": [{"hooks": [{"command": "one"}, {"command": 7}]}],
        "B": {"command": "two"},
    }

    assert doctor_checks._commands(node) == ["one", "two"]


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

    check = doctor_checks.check_hook_registration(_context(tmp_path, plugin_root=root))

    assert (check.status, check.fix, check.summary) == (
        Status.FAIL,
        "/upgrade",
        "hooks/hooks.json: missing",
    )


def test_a_hooks_json_with_invalid_utf8_is_invalid_json(tmp_path):
    root = _plugin_with_hooks(tmp_path, {})
    (root / "hooks" / "hooks.json").write_bytes(b'{"hooks": "\xff"}')

    check = doctor_checks.check_hook_registration(_context(tmp_path, plugin_root=root))

    assert check.summary == "hooks/hooks.json: invalid JSON"


def test_the_shipped_hooks_json_resolves_every_command_against_the_real_plugin(
    tmp_path,
):
    raw = (PLUGIN / "hooks" / "hooks.json").read_text()
    command_count = raw.count('"command":')

    check = doctor_checks.check_hook_registration(_context(tmp_path))

    assert command_count > 0
    assert len(doctor_checks._commands(json.loads(raw)["hooks"])) == command_count
    assert (check.status, check.summary) == (
        Status.OK,
        f"{command_count} hook commands, every script present",
    )


# ---------------------------------------------------------------------------
# Step 1.4: interpreter self-probe and python-floor
# ---------------------------------------------------------------------------

DOCTOR = SCRIPTS / "doctor.py"
REPORT_MODULE = SCRIPTS / "lib" / "doctor_report.py"
CHECKS_MODULE = SCRIPTS / "lib" / "doctor_checks.py"
PROBE_MODULE = SCRIPTS / "lib" / "doctor_probe.py"
FILES_MODULE = SCRIPTS / "lib" / "doctor_files.py"
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
    return doctor_checks.check_interpreter(context), doctor_checks.check_python_floor(
        context
    )


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

    check = doctor_checks.check_python_floor(_probe_context(tmp_path, shim))

    assert check.status is status
    assert version in check.summary


def test_a_version_below_the_floor_names_the_path_and_the_floor_and_the_fix(tmp_path):
    shim = _shim(tmp_path, 'echo "/opt/py 3.9.18"\n')

    check = doctor_checks.check_python_floor(_probe_context(tmp_path, shim))

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

    alone = doctor_checks.check_python_floor(_probe_context(tmp_path, shim))
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


@pytest.mark.parametrize(
    "module",
    [DOCTOR, REPORT_MODULE, CHECKS_MODULE, PROBE_MODULE, FILES_MODULE],
    ids=lambda m: m.name,
)
def test_module_top_level_parses_as_python_3_8(module):
    ast.parse(module.read_text(), feature_version=(3, 8))


# ---------------------------------------------------------------------------
# Step 1.5: tools, CLI flags, exit codes, import hygiene
# ---------------------------------------------------------------------------

OPTIONAL_TOOLS = ("gh", "semgrep", "adr", "shellcheck", "uv")


def _which_finding(*present: str):
    return lambda name: f"/usr/bin/{name}" if name in present else None


def test_jq_absent_is_warn_with_setup_fix_and_the_manual_install_hint(tmp_path):
    check = doctor_checks.check_required_tools(
        _context(tmp_path, which=_which_finding())
    )

    assert check.status is Status.WARN
    assert check.fix == "/setup"
    assert check.summary == "jq not on PATH (manual: brew install jq)"


def test_jq_present_is_ok_with_no_fix(tmp_path):
    check = doctor_checks.check_required_tools(
        _context(tmp_path, which=_which_finding("jq"))
    )

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

    check = doctor_checks.check_optional_tools(context)

    assert (check.status, check.fix, check.summary) == (Status.OK, None, summary)


def test_the_registered_checks_start_with_the_install_side_ids_in_order():
    ids = tuple(check_id for check_id, _ in doctor_checks.CHECKS)

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
        PLUGIN
        / "hooks"
        / "lib"
        / "autocompact_config.py": "hooks/lib/autocompact_config.py",
        PLUGIN
        / "skills"
        / "upgrade"
        / "scripts"
        / "check_version_drift.py": "skills/upgrade/scripts/check_version_drift.py",
        DOCTOR: "scripts/doctor.py",
        REPORT_MODULE: "scripts/lib/doctor_report.py",
        CHECKS_MODULE: "scripts/lib/doctor_checks.py",
        PROBE_MODULE: "scripts/lib/doctor_probe.py",
        FILES_MODULE: "scripts/lib/doctor_files.py",
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
        env=hermetic_git_env(home=path.parent),
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


# -- import hygiene --------------------------------------------------------------

PLUGIN_HELPERS = {"autocompact_config", "check_version_drift"}


def _is_type_checking_guard(node: ast.AST) -> bool:
    """``if TYPE_CHECKING:`` or ``if typing.TYPE_CHECKING:``."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    is_bare = isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
    is_qualified = (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )
    return is_bare or is_qualified


def _imported_names(source: str, include_function_bodies: bool) -> list[str]:
    """Top-level names ``source`` imports; the body of a ``TYPE_CHECKING`` guard is skipped.

    Its ``else`` branch is real code, so it is visited. Function bodies are
    visited only when ``include_function_bodies``.
    """
    found: list[str] = []

    def handle(node: ast.AST) -> None:
        if not include_function_bodies and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            return
        if isinstance(node, ast.Import):
            found.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "").split(".")[0])
        if _is_type_checking_guard(node):
            for statement in node.orelse:
                handle(statement)
            return
        for child in ast.iter_child_nodes(node):
            handle(child)

    handle(ast.parse(source))
    return found


def _module_level_imports(module: Path) -> list[str]:
    """Names imported at import time (function bodies and type-only blocks excluded)."""
    return _imported_names(module.read_text(), include_function_bodies=False)


@pytest.mark.parametrize(
    ("source", "include_function_bodies", "expected"),
    [
        ("if TYPE_CHECKING:\n    import a\nelse:\n    import b\n", False, ["b"]),
        ("import typing\nif typing.TYPE_CHECKING:\n    import a\n", False, ["typing"]),
        ("def f():\n    import a\n", False, []),
        ("def f():\n    import a\n", True, ["a"]),
        ("if TYPE_CHECKING:\n    import a\ndef f():\n    import b\n", True, ["b"]),
    ],
    ids=[
        "else-branch",
        "typing-attribute",
        "function-skipped",
        "function-visited",
        "guard-body-skipped",
    ],
)
def test_the_import_scan_skips_only_type_checking_bodies_and_optionally_functions(
    source, include_function_bodies, expected
):
    assert _imported_names(source, include_function_bodies) == expected


#: The plugin-local modules each module may import at import time; no other
#: lib module is imported eagerly, and none imports ``doctor`` itself.
ALLOWED_LOCAL_IMPORTS = {
    DOCTOR: set(),
    REPORT_MODULE: set(),
    PROBE_MODULE: set(),
    FILES_MODULE: set(),
    CHECKS_MODULE: {"doctor_report", "doctor_files"},
}


@pytest.mark.parametrize("module", ALLOWED_LOCAL_IMPORTS, ids=lambda m: m.name)
def test_module_level_imports_are_standard_library_or_the_allowed_local_modules(
    module,
):
    imported = _module_level_imports(module)

    assert imported != []
    assert [
        name
        for name in imported
        if name not in sys.stdlib_module_names
        and name not in ALLOWED_LOCAL_IMPORTS[module]
    ] == []
    assert PLUGIN_HELPERS.isdisjoint(imported)


@pytest.mark.parametrize(
    "module", sorted((SCRIPTS / "lib").glob("doctor_*.py")), ids=lambda m: m.name
)
def test_no_lib_module_imports_doctor_even_inside_a_function(module):
    imported = _imported_names(module.read_text(), include_function_bodies=True)

    assert "doctor" not in imported


def test_importing_doctor_loads_no_lib_module():
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import doctor; "
        "print(sorted(m for m in sys.modules if m.startswith('doctor_')))"
    )

    done = subprocess.run(
        [sys.executable, "-c", code, str(SCRIPTS)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert (done.returncode, done.stdout.strip(), done.stderr) == (0, "[]", "")


# ---------------------------------------------------------------------------
# Step 2.1: metrics-writable and project-settings
# ---------------------------------------------------------------------------


def _project_context(tmp_path: Path, **overrides) -> doctor.Context:
    """A Context over an existing, empty temp project against the real plugin."""
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    return _context(tmp_path, project_root=project, **overrides)


def _metrics_path(context: doctor.Context) -> Path:
    return context.project_root / ".claude" / "metrics"


def _denying_writer(directory: Path) -> None:
    raise PermissionError("denied")


def test_abs_path_names_a_relative_path_by_its_absolute_form():
    assert report_model.abs_path(Path("some") / "dir") == str(
        Path.cwd() / "some" / "dir"
    )


def test_a_missing_metrics_directory_is_warn_naming_the_absolute_path_and_fix_flag(
    tmp_path,
):
    context = _project_context(tmp_path)

    check = doctor_checks.check_metrics_writable(context)

    assert check.status is Status.WARN
    assert check.fix == "/doctor --fix"
    assert check.summary == f"{_metrics_path(context)} missing"


def test_a_denied_probe_write_is_fail_with_chmod_on_the_absolute_path(tmp_path):
    context = _project_context(tmp_path, probe_write=_denying_writer)
    _metrics_path(context).mkdir(parents=True)

    check = doctor_checks.check_metrics_writable(context)

    assert check.status is Status.FAIL
    assert check.fix == f"chmod u+w {_metrics_path(context)}"
    assert check.summary == f"{_metrics_path(context)}: denied"


def _file_at_metrics(context: doctor.Context) -> Path:
    """A regular file at ``.claude/metrics``; returns the blocking path."""
    metrics = _metrics_path(context)
    metrics.parent.mkdir()
    metrics.write_text("")
    return metrics


def _dangling_metrics(context: doctor.Context) -> Path:
    """A symlink at ``.claude/metrics`` whose target does not exist."""
    metrics = _metrics_path(context)
    metrics.parent.mkdir()
    metrics.symlink_to(context.project_root / "gone")
    return metrics


def _file_at_claude(context: doctor.Context) -> Path:
    """A regular file where ``.claude`` belongs; returns the blocking path."""
    claude_dir = context.project_root / ".claude"
    claude_dir.write_text("a file, not a directory")
    return claude_dir


def _dangling_claude(context: doctor.Context) -> Path:
    """A symlink at ``.claude`` whose target does not exist."""
    claude_dir = context.project_root / ".claude"
    claude_dir.symlink_to(context.project_root / "gone")
    return claude_dir


BLOCKER_IDS = [
    "file-at-metrics",
    "dangling-symlink",
    "file-at-claude",
    "dangling-claude-symlink",
]
#: Each builder makes the blocker and returns the path that blocks.
BLOCKERS = pytest.mark.parametrize(
    "build_blocker",
    [_file_at_metrics, _dangling_metrics, _file_at_claude, _dangling_claude],
    ids=BLOCKER_IDS,
)
#: The same cases with the runtime directories ``--fix`` can still create beside the blocker.
FIX_BLOCKERS = pytest.mark.parametrize(
    ("build_blocker", "created"),
    [
        (_file_at_metrics, ("memory",)),
        (_dangling_metrics, ("memory",)),
        (_file_at_claude, ()),
        (_dangling_claude, ()),
    ],
    ids=BLOCKER_IDS,
)


@BLOCKERS
def test_a_non_directory_in_the_way_is_fail_with_mv_then_fix(tmp_path, build_blocker):
    context = _project_context(tmp_path)
    blocker = build_blocker(context)

    check = doctor_checks.check_metrics_writable(context)

    assert check.status is Status.FAIL
    assert check.fix == f"mv {blocker} {blocker}.bak && /doctor --fix"
    assert check.summary == f"{blocker} is not a directory"


def _stat_denied_on_metrics(monkeypatch, filename: str | None) -> None:
    """Make ``Path.lstat`` raise ``PermissionError`` for a path called ``metrics``."""
    real_lstat = Path.lstat

    def lstat(self):
        if self.name == "metrics":
            raise PermissionError(13, "denied", filename)
        return real_lstat(self)

    monkeypatch.setattr(Path, "lstat", lstat)


def test_an_os_error_without_a_filename_is_fail_with_chmod_on_the_project_root(
    tmp_path, monkeypatch
):
    context = _project_context(tmp_path)
    _stat_denied_on_metrics(monkeypatch, None)

    check = doctor_checks.check_metrics_writable(context)

    assert check.status is Status.FAIL
    assert check.summary == f"{_metrics_path(context)}: PermissionError"
    assert check.fix == f"chmod u+rwx {context.project_root}"


def test_an_os_error_with_a_filename_is_fail_with_chmod_on_that_files_parent(
    tmp_path, monkeypatch
):
    context = _project_context(tmp_path)
    metrics = _metrics_path(context)
    _stat_denied_on_metrics(monkeypatch, str(metrics))

    check = doctor_checks.check_metrics_writable(context)

    assert check.fix == f"chmod u+rwx {metrics.parent}"


def _looping_metrics(context: doctor.Context) -> Path:
    """``.claude/metrics`` a symlink to itself, with ``.claude/memory`` already present."""
    claude_dir = context.project_root / ".claude"
    (claude_dir / "memory").mkdir(parents=True)
    metrics = claude_dir / "metrics"
    os.symlink("metrics", metrics)
    return metrics


def test_a_self_looping_symlink_in_place_of_metrics_is_a_blocker_to_check_and_fix(
    tmp_path,
):
    context = _project_context(tmp_path)
    metrics = _looping_metrics(context)

    check = doctor_checks.check_metrics_writable(context)
    fixed: list[str] = []
    errors: list[str] = []
    doctor_checks.apply_fixes(context, fixed, errors)

    assert (check.status, check.summary, check.fix) == (
        Status.FAIL,
        f"{metrics} is not a directory",
        f"mv {metrics} {metrics}.bak && /doctor --fix",
    )
    assert (fixed, errors) == (
        [],
        [f"fix failed: {metrics}: not a directory, move it aside"],
    )
    assert metrics.readlink() == Path("metrics")


@FIX_BLOCKERS
def test_fix_never_replaces_a_blocker_and_reports_it_exactly_once(
    tmp_path, build_blocker, created
):
    context = _project_context(tmp_path)
    blocker = build_blocker(context)

    report = doctor.run(
        context,
        fix=True,
        checks=(("metrics-writable", doctor_checks.check_metrics_writable),),
    )

    (check,) = report.checks
    line = f"fix failed: {blocker}: not a directory, move it aside"
    assert report.fixed == _created(context, *created)
    assert report.errors == [line]
    assert blocker.is_symlink() or blocker.is_file()
    assert (check.status, check.fix) == (
        Status.FAIL,
        f"mv {blocker} {blocker}.bak && /doctor --fix",
    )


def _awkward_project_context(tmp_path: Path, **overrides) -> doctor.Context:
    """A project whose directory name holds a space and a shell ``;``."""
    project = tmp_path / "my proj; touch pwned"
    project.mkdir()
    return _context(tmp_path, project_root=project, **overrides)


def test_the_mv_fix_quotes_a_path_with_a_space_and_a_semicolon(tmp_path):
    context = _awkward_project_context(tmp_path)
    metrics = _metrics_path(context)
    metrics.parent.mkdir()
    metrics.write_text("")

    check = doctor_checks.check_metrics_writable(context)

    awkward_metrics = f"{tmp_path}/my proj; touch pwned/.claude/metrics"
    assert check.fix == (
        f"mv '{awkward_metrics}' '{awkward_metrics}.bak' && /doctor --fix"
    )
    assert shlex.split(check.fix.split(" && ")[0]) == [
        "mv",
        str(metrics),
        f"{metrics}.bak",
    ]


def test_the_chmod_fix_quotes_a_path_with_a_space_and_a_semicolon(tmp_path):
    context = _awkward_project_context(tmp_path, probe_write=_denying_writer)
    metrics = _metrics_path(context)
    metrics.mkdir(parents=True)

    check = doctor_checks.check_metrics_writable(context)

    assert shlex.split(check.fix) == ["chmod", "u+w", str(metrics)]
    assert check.fix == (f"chmod u+w '{tmp_path}/my proj; touch pwned/.claude/metrics'")


def test_the_chmod_search_fix_quotes_a_path_with_a_space_and_a_semicolon(
    tmp_path, monkeypatch
):
    context = _awkward_project_context(tmp_path)
    metrics = _metrics_path(context)
    _stat_denied_on_metrics(monkeypatch, str(metrics))

    check = doctor_checks.check_metrics_writable(context)

    assert shlex.split(check.fix) == ["chmod", "u+rwx", str(metrics.parent)]
    assert check.fix == f"chmod u+rwx '{tmp_path}/my proj; touch pwned/.claude'"


def test_a_writable_metrics_directory_is_ok_and_a_stale_probe_file_is_left_alone(
    tmp_path,
):
    context = _project_context(tmp_path)
    metrics = _metrics_path(context)
    metrics.mkdir(parents=True)
    stale = metrics / ".doctor-probe-stale"
    stale.write_text("")

    check = doctor_checks.check_metrics_writable(context)

    assert (check.status, check.fix) == (Status.OK, None)
    assert check.summary == f"{metrics} writable"
    assert [path.name for path in metrics.iterdir()] == [stale.name]


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root can write into a read-only directory",
)
def test_a_read_only_metrics_directory_fails_with_the_default_writer(tmp_path, request):
    context = _project_context(tmp_path)
    metrics = _metrics_path(context)
    metrics.mkdir(parents=True)
    request.addfinalizer(lambda: metrics.chmod(0o700))
    metrics.chmod(0o500)

    check = doctor_checks.check_metrics_writable(context)

    assert (check.status, check.fix) == (Status.FAIL, f"chmod u+w {metrics}")


def _write_settings(context: doctor.Context, text: str) -> Path:
    path = context.project_root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _settings_check(tmp_path: Path, text: str | None) -> tuple[Check, Path]:
    context = _project_context(tmp_path)
    path = context.project_root / ".claude" / "settings.json"
    if text is not None:
        _write_settings(context, text)
    return doctor_checks.check_project_settings(context), path


def _autocompact_settings(value) -> str:
    return json.dumps({"env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": value}})


@pytest.mark.parametrize(
    ("value", "status", "fix"),
    [
        ("40", Status.OK, None),
        ("1", Status.OK, None),
        ("100", Status.OK, None),
        ("", Status.WARN, "/setup"),
        (None, Status.WARN, "/setup"),
        ("abc", Status.WARN, "/setup"),
        ("0", Status.WARN, "/setup"),
        ("101", Status.WARN, "/setup"),
        (" 40", Status.WARN, "/setup"),
        (40, Status.WARN, "/setup"),
    ],
    ids=["40", "1", "100", "empty", "null", "abc", "0", "101", "space-40", "int-40"],
)
def test_the_autocompact_value_is_validated(tmp_path, value, status, fix):
    check, _ = _settings_check(tmp_path, _autocompact_settings(value))

    assert (check.status, check.fix) == (status, fix)


def test_an_invalid_autocompact_value_is_named_by_type_and_length_not_echoed(
    tmp_path,
):
    secret = "sk-not-a-percent-0123456789"
    check, _ = _settings_check(tmp_path, _autocompact_settings(secret))

    assert check.summary == (
        "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE has type str and length 27,"
        " expected a percent string 1-100"
    )
    assert secret not in check.summary


def test_a_non_string_autocompact_value_is_named_by_its_type(tmp_path):
    check, _ = _settings_check(tmp_path, _autocompact_settings(40))

    assert check.summary == (
        "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE has type int and length 2,"
        " expected a percent string 1-100"
    )


def test_a_valid_autocompact_value_is_named_in_the_ok_summary(tmp_path):
    check, _ = _settings_check(tmp_path, _autocompact_settings("40"))

    assert check.summary == "env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE is '40'"


def test_absent_project_settings_are_warn_with_the_setup_fix(tmp_path):
    check, path = _settings_check(tmp_path, None)

    assert (check.status, check.fix) == (Status.WARN, "/setup")
    assert check.summary == f"{path}: missing"


@pytest.mark.parametrize(
    "content",
    ['{"permissions": {}}', '{"env": {}}', '{"env": {"OTHER": "1"}}'],
    ids=["no-env", "empty-env", "env-without-the-key"],
)
def test_settings_without_the_key_are_warn_naming_it(tmp_path, content):
    check, _ = _settings_check(tmp_path, content)

    assert (check.status, check.fix) == (Status.WARN, "/setup")
    assert check.summary == "env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE not set"


@pytest.mark.parametrize(
    ("content", "phrase"),
    [
        ("{oops", "invalid JSON"),
        ("[]", "not an object"),
        ('{"env": "x"}', "env is not an object"),
        ('{"env": [1]}', "env is not an object"),
        ('{"env": null}', "env is not an object"),
    ],
    ids=["invalid-json", "top-level-array", "env-string", "env-array", "env-null"],
)
def test_unusable_project_settings_are_fail_with_the_path_in_summary_and_fix(
    tmp_path, content, phrase
):
    check, path = _settings_check(tmp_path, content)

    assert check.status is Status.FAIL
    assert check.fix == f"edit {path}"
    assert check.summary == f"{path}: {phrase}"


def test_project_settings_with_invalid_utf8_are_fail_invalid_json(tmp_path):
    context = _project_context(tmp_path)
    path = _write_settings(context, "{}")
    path.write_bytes(b'{"env": "\xff"}')

    check = doctor_checks.check_project_settings(context)

    assert (check.status, check.summary) == (Status.FAIL, f"{path}: invalid JSON")


def test_unreadable_project_settings_are_fail_naming_the_path_and_error_type(
    tmp_path, monkeypatch
):
    context = _project_context(tmp_path)
    path = _write_settings(context, "{}")

    def denied(_path):
        raise PermissionError("denied")

    monkeypatch.setattr(doctor_checks, "load_json", denied)

    check = doctor_checks.check_project_settings(context)

    assert check.status is Status.FAIL
    assert check.summary == f"cannot read {path}: PermissionError"
    assert check.fix == f"edit {path}"


def test_a_plugin_root_without_hooks_lib_fails_project_settings_with_upgrade(
    tmp_path,
):
    bare_root = tmp_path / "bare"
    bare_root.mkdir()
    context = _project_context(tmp_path, plugin_root=bare_root)

    report = doctor.run(
        context,
        checks=(("project-settings", doctor_checks.check_project_settings),),
    )

    (check,) = report.checks
    assert (check.status, check.fix) == (Status.FAIL, "/upgrade")
    assert "internal error: ImportError" in check.summary


# ---------------------------------------------------------------------------
# doctor_files: the bounded reader
# ---------------------------------------------------------------------------


def test_project_settings_that_are_a_directory_are_fail_not_a_regular_file(tmp_path):
    context = _project_context(tmp_path)
    path = context.project_root / ".claude" / "settings.json"
    path.mkdir(parents=True)

    check = doctor_checks.check_project_settings(context)

    assert (check.status, check.summary, check.fix) == (
        Status.FAIL,
        f"{path}: not a regular file",
        f"edit {path}",
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX named pipes")
def test_project_settings_that_are_a_fifo_are_fail_not_a_regular_file_without_blocking(
    tmp_path,
):
    context = _project_context(tmp_path)
    path = context.project_root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    os.mkfifo(path)
    outcomes: list[Check | Exception] = []

    def read() -> None:
        try:
            outcomes.append(doctor_checks.check_project_settings(context))
        except Exception as exc:  # noqa: BLE001 -- handed to the test thread
            outcomes.append(exc)

    worker = threading.Thread(
        target=read,
        daemon=True,  # a blocked read must not hold the test run open
    )

    worker.start()
    worker.join(timeout=FIFO_READ_DEADLINE_SECONDS)

    if worker.is_alive():
        pytest.fail("read blocked on FIFO")
    (outcome,) = outcomes
    if isinstance(outcome, Exception):
        raise outcome
    assert (outcome.status, outcome.summary) == (
        Status.FAIL,
        f"{path}: not a regular file",
    )


def test_project_settings_over_the_size_limit_are_fail_too_large(tmp_path):
    context = _project_context(tmp_path)
    path = _write_settings(context, "{}")
    path.write_bytes(b" " * (doctor_files.MAX_FILE_BYTES + 1))

    check = doctor_checks.check_project_settings(context)

    assert (check.status, check.summary, check.fix) == (
        Status.FAIL,
        f"{path}: too large",
        f"edit {path}",
    )


def test_project_settings_exactly_at_the_size_limit_are_still_read(tmp_path):
    context = _project_context(tmp_path)
    path = _write_settings(context, "{}")
    path.write_bytes(b"{}" + b" " * (doctor_files.MAX_FILE_BYTES - 2))

    check = doctor_checks.check_project_settings(context)

    assert check.summary == "env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE not set"


class _ReadRecorder:
    """A file handle that records the size of every ``read`` and delegates."""

    def __init__(self, handle, sizes: list[int]):
        self._handle = handle
        self._sizes = sizes

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._handle.close()

    def fileno(self) -> int:
        return self._handle.fileno()

    def read(self, size: int = -1) -> bytes:
        self._sizes.append(size)
        return self._handle.read(size)


def test_the_reader_asks_for_at_most_one_byte_past_the_limit(tmp_path, monkeypatch):
    path = tmp_path / "big.json"
    path.write_bytes(b" " * (doctor_files.MAX_FILE_BYTES + 10))
    sizes: list[int] = []

    def recording_open(target, mode, **kwargs):
        return _ReadRecorder(open(target, mode, **kwargs), sizes)

    monkeypatch.setattr(doctor_files, "open", recording_open, raising=False)

    result = doctor_files.read_bounded(path)

    assert result.kind is doctor_files.LoadKind.TOO_LARGE
    assert sizes == [doctor_files.MAX_FILE_BYTES + 1]


# ---------------------------------------------------------------------------
# Step 2.2: managed-sections
# ---------------------------------------------------------------------------

CLAUDE_MD = ".claude/CLAUDE.md"
GITIGNORE = ".gitignore"
MANAGED_FILES = [section.path for section in doctor_checks.MANAGED_SECTIONS]

CLAUDE_MD_MARKER = "<!-- dev-team: concise-response preference{suffix} -->"
#: What ``/setup`` writes after the versioned marker on the same line.
GITIGNORE_MARKER_TRAILER = (
    " (regeneratable; not deliverables — issues #1101, #1377, #1406, #1412)"
)
GITIGNORE_MARKER = (
    "# dev-team workflow runtime artifacts (.claude/-scoped + .dev-team-reports/, "
    "#1406){suffix}" + GITIGNORE_MARKER_TRAILER
)


def _section(relative: str) -> doctor_checks.ManagedSection:
    return next(s for s in doctor_checks.MANAGED_SECTIONS if s.path == relative)


def _current_version(relative: str) -> int:
    """The version ``/doctor`` treats as current for the managed file ``relative``."""
    return _section(relative).current_version


def _marker(template: str, version: int | None) -> str:
    """The marker line at ``version``; ``None`` writes it with no ``v<N>`` suffix."""
    return template.format(suffix="" if version is None else f" v{version}")


def _write_managed(context: doctor.Context, relative: str, text: str | bytes) -> Path:
    path = context.project_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8", newline="")
    return path


def _managed_check(tmp_path: Path, claude_md=None, gitignore=None) -> Check:
    """Run managed-sections; ``None`` leaves the file absent, a str/bytes writes it."""
    context = _project_context(tmp_path)
    if claude_md is not None:
        _write_managed(context, CLAUDE_MD, claude_md)
    if gitignore is not None:
        _write_managed(context, GITIGNORE, gitignore)
    return doctor_checks.check_managed_sections(context)


def _claude_md_at(version: int | None) -> str:
    return "# Notes\n\n" + _marker(CLAUDE_MD_MARKER, version) + "\nbe concise\n"


def _gitignore_at(version: int | None) -> str:
    return (
        "node_modules/\n" + _marker(GITIGNORE_MARKER, version) + "\n.claude/metrics/\n"
    )


def _opted_in(relative: str, version: int) -> str:
    return f"{relative} at v{version}"


def _stale(relative: str, version: int) -> str:
    return f"{_opted_in(relative, version)} (current v{_current_version(relative)})"


CLAUDE_CURRENT_VERSION = _current_version(CLAUDE_MD)
GITIGNORE_CURRENT_VERSION = _current_version(GITIGNORE)


@pytest.mark.parametrize(
    ("claude_md", "gitignore", "summary"),
    [
        (
            _claude_md_at(CLAUDE_CURRENT_VERSION),
            _gitignore_at(GITIGNORE_CURRENT_VERSION),
            (
                f"opted in: {_opted_in(CLAUDE_MD, CLAUDE_CURRENT_VERSION)}, "
                f"{_opted_in(GITIGNORE, GITIGNORE_CURRENT_VERSION)}"
            ),
        ),
        (None, None, "not opted in"),
        (
            _claude_md_at(CLAUDE_CURRENT_VERSION),
            _gitignore_at(GITIGNORE_CURRENT_VERSION + 1),
            (
                f"opted in: {_opted_in(CLAUDE_MD, CLAUDE_CURRENT_VERSION)}, "
                f"{_opted_in(GITIGNORE, GITIGNORE_CURRENT_VERSION + 1)}"
            ),
        ),
    ],
    ids=["both-current", "both-absent", "gitignore-newer"],
)
def test_current_absent_or_newer_managed_sections_are_ok(
    tmp_path, claude_md, gitignore, summary
):
    check = _managed_check(tmp_path, claude_md, gitignore)

    assert (check.status, check.fix, check.summary) == (Status.OK, None, summary)


def test_a_file_without_the_marker_is_not_opted_in(tmp_path):
    check = _managed_check(
        tmp_path, "# just notes\n", _gitignore_at(GITIGNORE_CURRENT_VERSION)
    )

    assert (check.status, check.summary) == (
        Status.OK,
        f"opted in: {_opted_in(GITIGNORE, GITIGNORE_CURRENT_VERSION)}",
    )


def test_an_upgraded_gitignore_with_the_older_line_before_the_current_one_is_current(
    tmp_path,
):
    older_then_current = _gitignore_at(GITIGNORE_CURRENT_VERSION - 1) + _gitignore_at(
        GITIGNORE_CURRENT_VERSION
    )

    check = _managed_check(tmp_path, None, older_then_current)

    assert (check.status, check.fix) == (Status.OK, None)
    assert (
        check.summary == f"opted in: {_opted_in(GITIGNORE, GITIGNORE_CURRENT_VERSION)}"
    )


@pytest.mark.parametrize(
    ("claude_md", "gitignore", "summary"),
    [
        (
            "# just notes\n",
            _gitignore_at(GITIGNORE_CURRENT_VERSION - 1),
            f"stale: {_stale(GITIGNORE, GITIGNORE_CURRENT_VERSION - 1)}",
        ),
        (
            _claude_md_at(None),
            _gitignore_at(GITIGNORE_CURRENT_VERSION),
            f"stale: {_stale(CLAUDE_MD, 0)}",
        ),
        (
            _claude_md_at(CLAUDE_CURRENT_VERSION),
            _gitignore_at(None),
            f"stale: {_stale(GITIGNORE, 0)}",
        ),
        (
            _claude_md_at(CLAUDE_CURRENT_VERSION - 1),
            _gitignore_at(GITIGNORE_CURRENT_VERSION - 1),
            (
                f"stale: {_stale(CLAUDE_MD, CLAUDE_CURRENT_VERSION - 1)}, "
                f"{_stale(GITIGNORE, GITIGNORE_CURRENT_VERSION - 1)}"
            ),
        ),
        (
            _claude_md_at(0),
            _gitignore_at(GITIGNORE_CURRENT_VERSION - 1),
            (
                f"stale: {_stale(CLAUDE_MD, 0)}, "
                f"{_stale(GITIGNORE, GITIGNORE_CURRENT_VERSION - 1)}"
            ),
        ),
    ],
    ids=[
        "stale-gitignore",
        "suffix-less-claude-md-marker",
        "suffix-less-gitignore-marker",
        "both-stale",
        "explicit-v0-claude-md-and-stale-gitignore",
    ],
)
def test_a_stale_managed_section_is_warn_naming_each_stale_file(
    tmp_path, claude_md, gitignore, summary
):
    check = _managed_check(tmp_path, claude_md, gitignore)

    assert (check.status, check.fix, check.summary) == (Status.WARN, "/setup", summary)


def test_crlf_line_endings_give_the_same_result_as_lf(tmp_path):
    lf = _managed_check(
        tmp_path / "lf", _claude_md_at(0), _gitignore_at(GITIGNORE_CURRENT_VERSION)
    )
    crlf = _managed_check(
        tmp_path / "crlf",
        _claude_md_at(0).replace("\n", "\r\n"),
        _gitignore_at(GITIGNORE_CURRENT_VERSION).replace("\n", "\r\n"),
    )

    assert crlf == lf
    assert crlf.status is Status.WARN


@pytest.mark.parametrize("relative", MANAGED_FILES)
def test_an_undecodable_managed_file_is_fail_naming_the_file_and_the_error_type(
    tmp_path, relative
):
    context = _project_context(tmp_path)
    path = _write_managed(context, relative, b"\xff\xfe not utf-8")

    check = doctor_checks.check_managed_sections(context)

    assert check.status is Status.FAIL
    assert check.summary == f"cannot read {relative}: UnicodeDecodeError"
    assert "internal error" not in check.summary
    assert check.fix == f"edit {path}"


def test_an_undecodable_gitignore_outranks_a_stale_claude_md(tmp_path):
    context = _project_context(tmp_path)
    _write_managed(context, CLAUDE_MD, _claude_md_at(CLAUDE_CURRENT_VERSION - 1))
    _write_managed(context, GITIGNORE, b"\xff")

    check = doctor_checks.check_managed_sections(context)

    assert (check.status, check.summary) == (
        Status.FAIL,
        "cannot read .gitignore: UnicodeDecodeError",
    )


def test_an_undecodable_gitignore_fails_managed_sections_and_no_other_check_in_a_whole_run(
    tmp_path,
):
    context = _project_context(
        tmp_path,
        plugin_root=_temp_plugin(tmp_path),
        config_dir=_config_dir(tmp_path, installed="14.0.1", catalog="14.0.1"),
        env=_probe_env(),
        shim=REAL_SHIM,
        script=DOCTOR,
        which=_which_finding("jq"),
    )
    _write_managed(context, GITIGNORE, b"\xff\xfe not utf-8")

    report = doctor.run(context)

    by_id = {c.id: c for c in report.checks}
    assert [c.id for c in report.checks] == list(CHECK_IDS)
    assert (by_id["managed-sections"].status, by_id["managed-sections"].summary) == (
        Status.FAIL,
        "cannot read .gitignore: UnicodeDecodeError",
    )
    assert [c.id for c in report.checks if "internal error" in c.summary] == []
    assert [by_id[check_id].status for check_id in INSTALL_SIDE_IDS] == [
        Status.OK
    ] * len(INSTALL_SIDE_IDS)
    # The fixture project has no .claude directory: both project checks warn.
    assert by_id["project-settings"].status is Status.WARN
    assert by_id["metrics-writable"].status is Status.WARN


def test_when_both_managed_files_are_unreadable_the_first_is_the_one_named(tmp_path):
    context = _project_context(tmp_path)
    _write_managed(context, CLAUDE_MD, b"\xff")
    _write_managed(context, GITIGNORE, b"\xff")

    check = doctor_checks.check_managed_sections(context)

    assert check.summary == "cannot read .claude/CLAUDE.md: UnicodeDecodeError"


@pytest.mark.parametrize("relative", MANAGED_FILES)
def test_a_managed_file_that_is_a_directory_is_fail_not_a_regular_file(
    tmp_path, relative
):
    context = _project_context(tmp_path)
    path = context.project_root / relative
    path.mkdir(parents=True)

    check = doctor_checks.check_managed_sections(context)

    assert (check.status, check.summary, check.fix) == (
        Status.FAIL,
        f"{path}: not a regular file",
        f"edit {path}",
    )


@pytest.mark.parametrize("relative", MANAGED_FILES)
def test_a_managed_file_over_the_size_limit_is_fail_too_large(tmp_path, relative):
    context = _project_context(tmp_path)
    path = _write_managed(context, relative, b" " * (doctor_files.MAX_FILE_BYTES + 1))

    check = doctor_checks.check_managed_sections(context)

    assert (check.status, check.summary, check.fix) == (
        Status.FAIL,
        f"{path}: too large",
        f"edit {path}",
    )


@pytest.mark.parametrize("relative", MANAGED_FILES)
def test_an_unreadable_managed_file_is_fail_naming_the_file_and_the_error_type(
    tmp_path, monkeypatch, relative
):
    context = _project_context(tmp_path)
    path = _write_managed(context, relative, "x")
    real_read = doctor_checks.read_bounded

    def read(target):
        if target == path:
            raise PermissionError("denied")
        return real_read(target)

    monkeypatch.setattr(doctor_checks, "read_bounded", read)

    check = doctor_checks.check_managed_sections(context)

    assert (check.status, check.summary, check.fix) == (
        Status.FAIL,
        f"cannot read {relative}: PermissionError",
        f"edit {path}",
    )


def test_hooks_json_that_is_a_directory_is_fail_not_a_regular_file(tmp_path):
    root = _plugin_with_hooks(tmp_path, {})
    (root / "hooks" / "hooks.json").unlink()
    (root / "hooks" / "hooks.json").mkdir()

    check = doctor_checks.check_hook_registration(_context(tmp_path, plugin_root=root))

    assert (check.status, check.fix, check.summary) == (
        Status.FAIL,
        "/upgrade",
        "hooks/hooks.json: not a regular file",
    )


def test_a_claude_path_that_is_a_regular_file_means_no_managed_sections(tmp_path):
    context = _project_context(tmp_path)
    (context.project_root / ".claude").write_text("a file, not a directory")

    check = doctor_checks.check_managed_sections(context)

    assert (check.status, check.summary) == (Status.OK, "not opted in")


CLAUDE_MD_PATTERN = _section(CLAUDE_MD).marker_pattern
OLDER_LINE = "<!-- dev-team: concise-response preference v1 -->"
NEWER_LINE = "<!-- dev-team: concise-response preference v7 -->"


@pytest.mark.parametrize(
    ("text", "version"),
    [
        ("no marker", None),
        ("", None),
        ("<!-- dev-team: concise-response preference -->", 0),
        (NEWER_LINE, 7),
        ("<!-- dev-team: concise-response preference v10 -->", 10),
        ("<!-- dev-team: concise-response preference vX -->", None),
        (f"{OLDER_LINE}\n{NEWER_LINE}", 7),
        (f"{NEWER_LINE}\n{OLDER_LINE}", 7),
    ],
    ids=[
        "no-marker",
        "empty",
        "no-suffix",
        "v7",
        "v10",
        "non-numeric-suffix",
        "older-line-first",
        "newer-line-first",
    ],
)
def test_marker_version_is_none_without_a_marker_zero_without_a_suffix_and_the_highest_match(
    text, version
):
    assert doctor_checks._marker_version(text, CLAUDE_MD_PATTERN) == version


SETUP_SKILL = PLUGIN / "skills" / "setup" / "SKILL.md"


def _written_markers() -> list[str]:
    """Every ``MARKER="..."`` line the setup skill shows for appending a managed section."""
    markers = re.findall(
        r'^MARKER="([^"]+)"$', SETUP_SKILL.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert markers, f'no MARKER="..." line found in {SETUP_SKILL}'
    return markers


@pytest.mark.parametrize(
    "section", doctor_checks.MANAGED_SECTIONS, ids=lambda section: section.path
)
def test_each_managed_section_regex_matches_the_marker_setup_writes_at_its_version(
    section,
):
    versions = {
        doctor_checks._marker_version(marker, section.marker_pattern)
        for marker in _written_markers()
        if re.search(section.marker_pattern, marker)
    }

    assert versions == {section.current_version}, f"{section.path} vs {SETUP_SKILL}"


def test_the_registered_checks_are_the_nine_documented_ids_in_order():
    assert tuple(check_id for check_id, _ in doctor_checks.CHECKS) == CHECK_IDS


# ---------------------------------------------------------------------------
# Step 2.3: --fix creates the missing runtime directories
# ---------------------------------------------------------------------------


def _tree_snapshot(root: Path) -> dict[str, str]:
    """``{relative path: sha256}`` of every file under ``root``."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _created(context: doctor.Context, *names: str) -> list[str]:
    return [f"created {context.project_root / '.claude' / name}" for name in names]


def _project_with_settings(context: doctor.Context) -> Path:
    claude_dir = context.project_root / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text(_autocompact_settings("40"))
    return claude_dir


@pytest.mark.parametrize(
    ("seed", "kept"),
    [(_project_with_settings, ["settings.json"]), (lambda context: None, [])],
    ids=["with-settings", "bare-project"],
)
def test_fix_creates_exactly_the_two_runtime_directories_and_lists_them(
    tmp_path, seed, kept
):
    context = _project_context(tmp_path)
    seed(context)

    report = doctor.run(context, fix=True, checks=())

    claude_dir = context.project_root / ".claude"
    assert report.fixed == _created(context, *doctor_checks.RUNTIME_DIRS)
    assert sorted(path.name for path in claude_dir.iterdir()) == sorted(
        [*doctor_checks.RUNTIME_DIRS, *kept]
    )


def test_fix_changes_no_file_under_claude(tmp_path):
    context = _project_context(tmp_path)
    claude_dir = _project_with_settings(context)
    before = _tree_snapshot(claude_dir)

    doctor.run(context, fix=True, checks=())

    assert _tree_snapshot(claude_dir) == before


def test_metrics_writable_reports_ok_in_the_same_run_as_the_fix(tmp_path):
    context = _project_context(tmp_path)

    report = doctor.run(
        context,
        fix=True,
        checks=(("metrics-writable", doctor_checks.check_metrics_writable),),
    )

    (check,) = report.checks
    assert check.status is Status.OK


def test_without_fix_nothing_is_created_and_fixed_is_empty(tmp_path):
    context = _project_context(tmp_path)

    report = doctor.run(context, checks=())

    assert report.fixed == []
    assert not (context.project_root / ".claude").exists()


def test_fix_with_one_directory_present_lists_only_the_other(tmp_path):
    context = _project_context(tmp_path)
    (context.project_root / ".claude" / "metrics").mkdir(parents=True)

    report = doctor.run(context, fix=True, checks=())

    assert report.fixed == _created(context, "memory")


def test_a_second_fix_run_creates_nothing_and_changes_no_file(tmp_path):
    context = _project_context(tmp_path)
    claude_dir = _project_with_settings(context)
    doctor.run(context, fix=True, checks=())
    before = _tree_snapshot(claude_dir)

    report = doctor.run(context, fix=True, checks=())

    assert (report.fixed, report.errors) == ([], [])
    assert _tree_snapshot(claude_dir) == before


def _apply_fixes(context: doctor.Context) -> tuple[list[str], list[str]]:
    """Run ``doctor_checks.apply_fixes`` into fresh lists; return ``(fixed, errors)``."""
    fixed: list[str] = []
    errors: list[str] = []
    doctor_checks.apply_fixes(context, fixed, errors)
    return fixed, errors


def _as_absolute(context: doctor.Context) -> doctor.Context:
    return context


def _as_relative(context: doctor.Context) -> doctor.Context:
    """The same project, named relative to the current directory (its parent)."""
    return dataclasses.replace(context, project_root=Path("project"))


@pytest.mark.parametrize(
    "as_given", [_as_absolute, _as_relative], ids=["absolute-root", "relative-root"]
)
def test_a_regular_file_in_place_of_memory_is_an_error_named_by_absolute_path_and_not_in_fixed(
    tmp_path, monkeypatch, as_given
):
    context = _project_context(tmp_path)
    memory = context.project_root / ".claude" / "memory"
    memory.parent.mkdir(parents=True)
    memory.write_text("not a directory")
    monkeypatch.chdir(tmp_path)

    fixed, errors = _apply_fixes(as_given(context))

    assert fixed == _created(context, "metrics")
    assert errors == [f"fix failed: {memory}: not a directory, move it aside"]
    assert memory.read_text() == "not a directory"


def test_a_failed_fix_for_one_directory_does_not_stop_the_next(tmp_path):
    context = _project_context(tmp_path)
    metrics = context.project_root / ".claude" / "metrics"
    metrics.parent.mkdir(parents=True)
    metrics.write_text("not a directory")

    fixed, errors = _apply_fixes(context)

    assert fixed == _created(context, "memory")
    assert errors == [f"fix failed: {metrics}: not a directory, move it aside"]


def _dangling_memory(project_root: Path) -> Path:
    """``.claude/metrics`` present, ``.claude/memory`` a symlink to a missing target."""
    claude_dir = project_root / ".claude"
    (claude_dir / "metrics").mkdir(parents=True)
    memory = claude_dir / "memory"
    memory.symlink_to(project_root / "gone")
    return memory


def test_a_symlink_in_place_of_memory_is_one_error_and_nothing_is_created(tmp_path):
    context = _project_context(tmp_path)
    memory = _dangling_memory(context.project_root)

    fixed, errors = _apply_fixes(context)

    assert (fixed, errors) == (
        [],
        [f"fix failed: {memory}: not a directory, move it aside"],
    )
    assert memory.is_symlink()
    assert not (context.project_root / "gone").exists()


def test_fix_needs_no_plugin_helper_to_find_the_runtime_directories(tmp_path):
    bare_root = tmp_path / "bare"
    bare_root.mkdir()
    context = _project_context(tmp_path, plugin_root=bare_root)

    report = doctor.run(context, fix=True, checks=())

    assert (report.fixed, report.errors) == (
        _created(context, *doctor_checks.RUNTIME_DIRS),
        [],
    )


def test_metrics_writable_needs_no_plugin_helper_to_find_the_directory(tmp_path):
    bare_root = tmp_path / "bare"
    bare_root.mkdir()
    context = _project_context(tmp_path, plugin_root=bare_root)
    _metrics_path(context).mkdir(parents=True)

    check = doctor_checks.check_metrics_writable(context)

    assert check.status is Status.OK


def test_help_names_each_directory_fix_creates(tmp_path):
    done = _run_cli(tmp_path, "--help")

    text = " ".join(done.stdout.split())
    assert [
        name for name in doctor_checks.RUNTIME_DIRS if f".claude/{name}" not in text
    ] == []


def _mkdir_raising_on(name: str, exc: Exception):
    """A ``Path.mkdir`` replacement that raises ``exc`` for a directory called ``name``."""
    real_mkdir = Path.mkdir

    def mkdir(self, *args, **kwargs):
        if self.name == name:
            raise exc
        return real_mkdir(self, *args, **kwargs)

    return mkdir


def test_an_unexpected_exception_while_fixing_is_one_error_and_the_checks_still_run(
    tmp_path, monkeypatch
):
    context = _project_context(tmp_path)
    monkeypatch.setattr(
        Path, "mkdir", _mkdir_raising_on("metrics", ValueError("bad root"))
    )

    report = doctor.run(context, fix=True, checks=(("a", _constant_check(Status.OK)),))

    assert report.errors == ["fix failed: ValueError: bad root"]
    assert report.fixed == []
    assert [c.id for c in report.checks] == ["a"]


def test_a_raise_on_the_second_directory_keeps_what_the_first_one_created(
    tmp_path, monkeypatch
):
    context = _project_context(tmp_path)
    monkeypatch.setattr(Path, "mkdir", _mkdir_raising_on("memory", ValueError("boom")))

    report = doctor.run(context, fix=True, checks=())

    assert report.fixed == _created(context, "metrics")
    assert report.errors == ["fix failed: ValueError: boom"]


def _fix_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(_autocompact_settings("40"))
    return project


def test_fix_json_run_lists_the_created_directories_and_exits_0(tmp_path):
    project = _fix_project(tmp_path)

    done = _run_cli(tmp_path, "--fix", "--json", "--project", str(project))

    payload = json.loads(done.stdout)
    assert (done.returncode, done.stderr) == (0, "")
    assert payload["fixed"] == [
        f"created {project.resolve() / '.claude' / name}"
        for name in ("metrics", "memory")
    ]
    assert payload["overall"] == "ok"


def test_a_second_fix_run_on_the_command_line_reports_fixed_none_and_exits_0(tmp_path):
    project = _fix_project(tmp_path)
    _run_cli(tmp_path, "--fix", "--project", str(project))

    done = _run_cli(tmp_path, "--fix", "--project", str(project))

    lines = done.stdout.splitlines()
    assert done.returncode == 0
    assert "fixed: none" in lines
    assert [line for line in lines if "created " in line] == []


def test_json_lists_the_nine_documented_check_ids_in_order(tmp_path):
    project = _fix_project(tmp_path)

    done = _run_cli(tmp_path, "--json", "--project", str(project))

    payload = json.loads(done.stdout)
    assert [c["id"] for c in payload["checks"]] == list(CHECK_IDS)


@pytest.mark.parametrize(
    ("flags", "overall_line"),
    [((), "overall: ok"), (("--json",), '"overall": "ok"')],
    ids=["human", "json"],
)
def test_a_failed_fix_exits_1_and_names_the_error_on_stderr_though_no_check_failed(
    tmp_path, flags, overall_line
):
    project = _fix_project(tmp_path)
    claude_dir = project.resolve() / ".claude"
    (claude_dir / "memory").write_text("not a directory")

    done = _run_cli(tmp_path, "--fix", *flags, "--project", str(project))

    assert done.returncode == 1
    assert done.stderr.splitlines() == [
        f"fix failed: {claude_dir / 'memory'}: not a directory, move it aside"
    ]
    assert overall_line in done.stdout
    assert f"created {claude_dir / 'metrics'}" in done.stdout


def test_a_failed_fix_is_in_the_human_errors_block_on_stdout_and_on_stderr(tmp_path):
    project = _fix_project(tmp_path)
    memory = project.resolve() / ".claude" / "memory"
    memory.write_text("not a directory")
    error = f"fix failed: {memory}: not a directory, move it aside"

    done = _run_cli(tmp_path, "--fix", "--project", str(project))

    lines = done.stdout.splitlines()
    assert "errors:" in lines
    assert f"  {error}" in lines
    assert done.stderr.splitlines() == [error]


def test_a_symlink_in_place_of_memory_exits_1_with_one_error_and_creates_nothing(
    tmp_path,
):
    project = tmp_path / "project"
    memory = _dangling_memory(project)
    resolved_memory = project.resolve() / ".claude" / "memory"

    done = _run_cli(tmp_path, "--fix", "--project", str(project))

    assert done.returncode == 1
    assert done.stderr.splitlines() == [
        f"fix failed: {resolved_memory}: not a directory, move it aside"
    ]
    assert memory.is_symlink()
    assert not (project / "gone").exists()


def test_the_bare_project_reports_warn_for_the_project_checks_and_exits_0(tmp_path):
    project = tmp_path / "bare-project"
    project.mkdir()

    done = _run_cli(tmp_path, "--json", "--project", str(project))

    payload = json.loads(done.stdout)
    statuses = {c["id"]: c["status"] for c in payload["checks"]}
    assert (statuses["metrics-writable"], statuses["project-settings"]) == (
        "warn",
        "warn",
    )
    assert statuses["managed-sections"] == "ok"
    assert (payload["overall"], done.returncode) == ("warn", 0)


@pytest.mark.parametrize("flag", ["--json", "--fix"])
def test_a_project_that_is_a_regular_file_exits_2_naming_it_and_changes_nothing(
    tmp_path, flag
):
    not_a_directory = tmp_path / "a-file"
    not_a_directory.write_text("unchanged")

    done = _run_cli(tmp_path, flag, "--project", str(not_a_directory))

    assert done.returncode == 2
    assert str(not_a_directory) in done.stderr
    assert not_a_directory.read_text() == "unchanged"
    assert not (tmp_path / "cwd" / ".claude").exists()
