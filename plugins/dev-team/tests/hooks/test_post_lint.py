"""Tests for hooks/post_lint.py — the opt-in post-edit ESLint hook.

Most tests drive `evaluate()` with a fake `node` on PATH (a small Python
script) so every fail-open and skip row runs without Node installed. A few
tests run the real script as a subprocess, and the real-ESLint tests use the
template dev tree's `node_modules` (skipped with a named reason when `node` is
absent locally; a failure when `CI=true`).
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"))

import post_lint
from hermetic import scrub_ambient_environment

HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "post_lint.py"

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="fake node is a shebang script"
)

FAKE_NODE = f"""#!{sys.executable}
import json, os, subprocess, sys, time
marker = os.environ.get("FAKE_MARKER")
if marker:
    with open(marker, "w") as handle:
        json.dump({{"argv": sys.argv[1:], "typed": os.environ.get("DEVTEAM_LINT_TYPED")}}, handle)
mode = os.environ.get("FAKE_MODE", "json")
if mode == "sleep":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    pids = os.environ["FAKE_PIDS"]
    with open(pids + ".tmp", "w") as handle:
        json.dump([os.getpid(), child.pid], handle)
    os.replace(pids + ".tmp", pids)
    time.sleep(30)
elif mode == "exit2":
    sys.stderr.write("config error\\n")
    sys.exit(2)
else:
    sys.stdout.write(os.environ.get("FAKE_STDOUT", "[]"))
    sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


class Project:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_dir = root.parent / f"{root.name}-state"
        self.bin = root.parent / f"{root.name}-bin"
        self.marker = root.parent / f"{root.name}-marker.json"
        (root / "src").mkdir(parents=True)
        (root / "src" / "a.js").write_text("var a = 1;\n")
        (root / "node_modules" / "eslint" / "bin").mkdir(parents=True)
        (root / "node_modules" / "eslint" / "bin" / "eslint.js").write_text("")
        (root / post_lint.CONFIG_NAME).write_text("export default [];\n")
        self.bin.mkdir()
        self.install_node()

    def install_node(self) -> None:
        node = self.bin / "node"
        node.write_text(FAKE_NODE)
        node.chmod(node.stat().st_mode | stat.S_IXUSR)

    def env(self, **extra: str) -> dict[str, str]:
        return {
            "PATH": str(self.bin),
            "FAKE_MARKER": str(self.marker),
            **extra,
        }

    def payload(self, file_path: str = "src/a.js", **override: object) -> dict:
        return {
            "tool_name": "Edit",
            "session_id": "s1",
            "cwd": str(self.root),
            "tool_input": {"file_path": file_path},
            **override,
        }

    def run(
        self, payload: object = None, env: dict[str, str] | None = None
    ) -> post_lint.Result:
        return post_lint.evaluate(
            self.payload() if payload is None else payload,  # type: ignore[arg-type]
            self.env() if env is None else env,
            self.state_dir,
        )

    @property
    def invoked(self) -> bool:
        return self.marker.exists()


@pytest.fixture(autouse=True)
def _no_ambient_environment(monkeypatch):
    scrub_ambient_environment(monkeypatch)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return Project(tmp_path / "proj")


def _notice_text(result: post_lint.Result) -> str:
    assert result.output is not None
    return result.output["systemMessage"]


# --- normal skips are silent -------------------------------------------------


@posix_only
@pytest.mark.parametrize(
    "payload_edit",
    [
        {"tool_input": {"file_path": "src/a.py"}},
        {"tool_name": "Read"},
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        {"tool_input": {}},
        {"tool_input": {"file_path": "src/missing.js"}},
    ],
)
def test_normal_skips_are_silent_and_never_run_eslint(project, payload_edit):
    (project.root / "src" / "a.py").write_text("x = 1\n")
    result = project.run(project.payload(**payload_edit))
    assert (result.outcome, result.output) == (post_lint.SKIPPED, None)
    assert not project.invoked


@posix_only
def test_skip_records_the_declared_extension(project):
    (project.root / "src" / "a.py").write_text("x = 1\n")
    assert project.run(project.payload("src/a.py")).ext == ".py"


# --- files that must never be linted -----------------------------------------


@posix_only
def test_path_outside_project_is_skipped(project):
    other = project.root.parent / "other"
    other.mkdir()
    (other / "file.js").write_text("var a;\n")
    result = project.run(project.payload("../other/file.js"))
    assert (result.outcome, result.output) == (post_lint.SKIPPED, None)
    assert not project.invoked


@posix_only
def test_node_modules_path_is_skipped(project):
    nested = project.root / "node_modules" / "x"
    nested.mkdir()
    (nested / "index.js").write_text("var a;\n")
    result = project.run(project.payload("node_modules/x/index.js"))
    assert result.outcome == post_lint.SKIPPED
    assert not project.invoked


@posix_only
def test_symlink_resolving_outside_project_is_skipped(project):
    other = project.root.parent / "elsewhere.js"
    other.write_text("var a;\n")
    (project.root / "src" / "link.js").symlink_to(other)
    result = project.run(project.payload("src/link.js"))
    assert result.outcome == post_lint.SKIPPED
    assert not project.invoked


@posix_only
def test_symlink_resolving_into_node_modules_is_skipped(project):
    target = project.root / "node_modules" / "x.js"
    target.write_text("var a;\n")
    (project.root / "src" / "link.js").symlink_to(target)
    assert project.run(project.payload("src/link.js")).outcome == post_lint.SKIPPED


# --- fail-open conditions say why once ---------------------------------------


def _break_eslint(project: Project) -> None:
    shutil.rmtree(project.root / "node_modules")


def _break_node(project: Project) -> None:
    shutil.rmtree(project.bin)
    project.bin.mkdir()


def _break_config(project: Project) -> None:
    (project.root / post_lint.CONFIG_NAME).unlink()


# reason -> (breaks the project, extra fake-node env, the one-line notice)
FAIL_OPEN_ROWS = {
    "no-eslint": (
        _break_eslint,
        {},
        "ESLint not found in project; lint skipped",
    ),
    "no-node": (_break_node, {}, "node not found on PATH; lint skipped"),
    "no-config": (
        _break_config,
        {},
        "eslint.devteam.config.js not found in project; lint skipped",
    ),
    "no-json": (
        None,
        {"FAKE_MODE": "exit2"},
        "ESLint exited with code 2 and no JSON; lint skipped",
    ),
    "invalid-json": (
        None,
        {"FAKE_STDOUT": "not json"},
        "ESLint output was not valid JSON; lint skipped",
    ),
    "parse-error": (
        None,
        {
            "FAKE_STDOUT": json.dumps(
                [
                    {
                        "filePath": "x",
                        "messages": [
                            {"fatal": True, "ruleId": None, "message": "Parsing error"}
                        ],
                    }
                ]
            ),
            "FAKE_EXIT": "1",
        },
        "edited file has a parse error; lint skipped",
    ),
}


@posix_only
@pytest.mark.parametrize("reason", sorted(FAIL_OPEN_ROWS))
def test_fail_open_never_blocks_and_notices_once_per_session(project, reason):
    breaker, extra, notice = FAIL_OPEN_ROWS[reason]
    if breaker:
        breaker(project)
    env = project.env(**extra)

    first = project.run(env=env)
    second = project.run(env=env)

    assert first.outcome == second.outcome == post_lint.FAILED_OPEN
    assert "decision" not in (first.output or {})
    assert _notice_text(first) == f"post_lint: {notice}"
    assert second.output is None


@posix_only
def test_notice_is_repeated_in_a_new_session_and_per_reason(project):
    _break_config(project)
    first = project.run(project.payload(session_id="A"))
    other_session = project.run(project.payload(session_id="B"))
    assert first.output == other_session.output
    (project.root / post_lint.CONFIG_NAME).write_text("export default [];\n")
    _break_eslint(project)
    other_reason = project.run(project.payload(session_id="A"))
    assert "ESLint not found" in _notice_text(other_reason)


@posix_only
def test_invalid_hook_stdin_fails_open_with_one_notice(project, monkeypatch):
    monkeypatch.chdir(project.root)
    first = post_lint.evaluate(None, project.env(), project.state_dir)
    second = post_lint.evaluate(None, project.env(), project.state_dir)
    assert first.outcome == post_lint.FAILED_OPEN
    assert "not valid JSON" in _notice_text(first)
    assert second.output is None


@posix_only
def test_valid_json_wins_over_a_nonzero_exit_code(project):
    env = project.env(FAKE_STDOUT="[]", FAKE_EXIT="1")
    assert project.run(env=env).outcome == post_lint.CLEAN


# --- timeout -----------------------------------------------------------------


def _alive(pid: int) -> bool:
    """Running, not merely a zombie awaiting its parent's wait()."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


@posix_only
def test_alive_helper_treats_a_zombie_as_dead_and_a_sleeper_as_alive():
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    zombie = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _alive(zombie.pid):
            time.sleep(0.05)  # exited, not yet wait()ed: a zombie
        assert not _alive(zombie.pid)
        assert _alive(sleeper.pid)
    finally:
        sleeper.kill()
        sleeper.wait()
        zombie.wait()


def _kill_leftovers(pids_file: Path) -> None:
    if not pids_file.exists():
        return
    for pid in json.loads(pids_file.read_text()):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


@posix_only
def test_timeout_fails_open_and_terminates_the_whole_process_group(project, tmp_path):
    pids = tmp_path / "pids.json"
    env = project.env(
        FAKE_MODE="sleep", FAKE_PIDS=str(pids), DEVTEAM_POST_LINT_TIMEOUT="3"
    )
    try:
        started = time.monotonic()
        result = project.run(env=env)
        elapsed = time.monotonic() - started

        assert result.outcome == post_lint.FAILED_OPEN
        assert "timed out after 3s" in _notice_text(result)
        assert 2.5 <= elapsed < 30  # waited for the timeout, did not hang
        node_pid, grandchild_pid = json.loads(pids.read_text())
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (
            _alive(node_pid) or _alive(grandchild_pid)
        ):
            time.sleep(0.1)
        assert not _alive(node_pid)
        assert not _alive(grandchild_pid)
    finally:
        _kill_leftovers(pids)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 10.0),
        ("", 10.0),
        ("abc", 10.0),
        ("0", 10.0),
        ("-3", 10.0),
        ("2.5", 2.5),
        ("600", 600.0),
        ("inf", 10.0),
        ("-inf", 10.0),
        ("nan", 10.0),
        ("1e20", 10.0),
        ("601", 10.0),
    ],
)
def test_timeout_seconds_defaults_to_ten_on_bad_values(raw, expected):
    env = {} if raw is None else {post_lint.ENV_TIMEOUT: raw}
    assert post_lint.timeout_seconds(env) == expected


# --- command shape -----------------------------------------------------------


def test_build_command_is_node_plus_script_not_the_bin_shim(tmp_path):
    script = tmp_path / "node_modules" / "eslint" / "bin" / "eslint.js"
    config = tmp_path / post_lint.CONFIG_NAME
    target = tmp_path / "src" / "a.js"
    cmd = post_lint.build_command("/usr/bin/node", script, config, target)
    assert cmd == [
        "/usr/bin/node",
        str(script),
        "--config",
        str(config),
        "--format",
        "json",
        str(target),
    ]
    assert ".bin" not in " ".join(cmd)
    assert "--fix" not in cmd


@posix_only
def test_hook_runs_eslint_with_typed_rules_off(project):
    project.run()
    seen = json.loads(project.marker.read_text())
    assert seen["typed"] == "0"
    assert "--format" in seen["argv"] and "json" in seen["argv"]
    assert seen["argv"][0].endswith(
        os.path.join("node_modules", "eslint", "bin", "eslint.js")
    )


# --- parse_findings ----------------------------------------------------------


def test_parse_findings_keeps_rule_findings_and_drops_ruleless_messages(tmp_path):
    stdout = json.dumps(
        [
            {
                "filePath": str(tmp_path / "src" / "a.js"),
                "messages": [
                    {
                        "ruleId": "no-var",
                        "line": 3,
                        "message": "Unexpected  var,\nuse let.",
                    },
                    {
                        "ruleId": None,
                        "line": 1,
                        "message": "Unused eslint-disable directive",
                    },
                ],
            }
        ]
    )
    assert post_lint.parse_findings(stdout, 0, tmp_path) == [
        post_lint.Finding("src/a.js", 3, "no-var", "Unexpected var, use let.")
    ]


def test_parse_findings_drops_unloaded_rule_definition_messages(tmp_path):
    """ESLint reports a disable comment naming a rule that is not loaded as an
    error that carries that rule's id, but it is not a dev-team finding."""
    stdout = json.dumps(
        [
            {
                "filePath": str(tmp_path / "a.js"),
                "messages": [
                    {
                        "ruleId": "functional/immutable-data",
                        "line": 1,
                        "message": "Definition for rule 'functional/immutable-data' was not found.",
                    },
                    {"ruleId": "no-var", "line": 2, "message": "Unexpected var."},
                ],
            }
        ]
    )
    assert [f.rule_id for f in post_lint.parse_findings(stdout, 1, tmp_path)] == [
        "no-var"
    ]


@pytest.mark.parametrize(
    "stdout",
    ['{"a": 1}', "[1]", '[{"filePath": "x", "messages": [1]}]', '[{"messages": "no"}]'],
)
def test_parse_findings_rejects_wrong_shapes(stdout, tmp_path):
    with pytest.raises(post_lint.LintFailure) as caught:
        post_lint.parse_findings(stdout, 0, tmp_path)
    assert caught.value.key == "invalid-json"


# --- tools, paths, and failures around the run -------------------------------


@posix_only
def test_multiedit_is_linted_like_edit_and_write(project):
    result = project.run(project.payload(tool_name="MultiEdit"), _violating(project))
    assert result.outcome == post_lint.BLOCKED
    assert project.invoked


@posix_only
def test_an_absolute_path_inside_the_project_is_linted(project):
    absolute = str(project.root / "src" / "a.js")
    result = project.run(project.payload(absolute), _violating(project))
    assert result.outcome == post_lint.BLOCKED


@posix_only
def test_an_uppercase_suffix_is_linted(project):
    (project.root / "src" / "B.JS").write_text("var b = 1;\n")
    result = project.run(project.payload("src/B.JS"), _violating(project))
    assert result.outcome == post_lint.BLOCKED
    assert result.ext == ".js"


@posix_only
def test_a_node_that_cannot_be_started_fails_open_as_no_node(project):
    broken = project.bin / "node"
    broken.write_text("#!/nonexistent/interpreter\n")
    broken.chmod(broken.stat().st_mode | stat.S_IXUSR)

    result = project.run(env=_violating(project))

    assert result.outcome == post_lint.FAILED_OPEN
    assert _notice_text(result) == "post_lint: node not found on PATH; lint skipped"


def test_main_never_raises_when_the_hook_run_itself_crashes(monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setenv(post_lint.ENV_ENABLE, "1")
    monkeypatch.setattr(post_lint, "read_stdin_json", dict)
    monkeypatch.setattr(post_lint, "evaluate", boom)

    assert post_lint.main() == 0
    assert capsys.readouterr().out == ""


# --- off by default (real script, real stdin) --------------------------------


def _run_script(
    project: Project, stdin: str, **env: str
) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if k != post_lint.ENV_ENABLE}
    child_env = {
        **base,
        **project.env(),
        "TMPDIR": str(project.state_dir.parent),
        **env,
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=child_env,
        cwd=str(project.root),
        timeout=60,
        check=False,
    )


@posix_only
def test_default_install_does_nothing_and_enabled_install_runs_eslint(project):
    stdin = json.dumps(project.payload())

    off = _run_script(project, stdin)
    assert (off.returncode, off.stdout) == (0, "")
    assert not project.invoked

    on = _run_script(project, stdin, **{post_lint.ENV_ENABLE: "1"})
    assert on.returncode == 0
    assert project.invoked


@posix_only
def test_enabled_hook_with_garbage_stdin_exits_zero_with_a_notice(project):
    done = _run_script(project, "{not json", **{post_lint.ENV_ENABLE: "1"})
    assert done.returncode == 0
    assert json.loads(done.stdout)["systemMessage"].startswith("post_lint: ")


# --- block decision, clean pass, trimming ------------------------------------


def _eslint_json(project: Project, findings: list[tuple[str, int, str]]) -> str:
    return json.dumps(
        [
            {
                "filePath": str(project.root / "src" / "a.js"),
                "messages": [
                    {"ruleId": rule, "line": line, "severity": 1, "message": message}
                    for rule, line, message in findings
                ],
            }
        ]
    )


@posix_only
def test_a_warn_finding_blocks_with_path_line_rule_message(project):
    stdout = _eslint_json(project, [("no-var", 3, "Unexpected var, use let or const.")])
    result = project.run(env=project.env(FAKE_STDOUT=stdout, FAKE_EXIT="0"))
    assert result.outcome == post_lint.BLOCKED
    assert result.output["decision"] == "block"
    assert result.output["reason"].splitlines() == [
        "dev-team post-edit lint (set DEVTEAM_POST_LINT=0 to disable):",
        "src/a.js:3 no-var Unexpected var, use let or const.",
    ]


@posix_only
def test_a_clean_file_returns_no_decision(project):
    result = project.run(env=project.env(FAKE_STDOUT=_eslint_json(project, [])))
    assert (result.outcome, result.output) == (post_lint.CLEAN, None)


def _findings(count: int, message: str = "m") -> list[post_lint.Finding]:
    return [
        post_lint.Finding("src/a.js", n, f"rule-{n}", message)
        for n in range(1, count + 1)
    ]


def test_reason_lists_ten_findings_then_plus_n_more():
    lines = post_lint.format_reason(_findings(25)).splitlines()
    assert len(lines) == 1 + 10 + 1
    assert lines[1].startswith("src/a.js:1 rule-1 ")
    assert lines[-1] == "+15 more"


def test_reason_with_exactly_ten_findings_has_no_more_line():
    assert "more" not in post_lint.format_reason(_findings(10)).splitlines()[-1]


def test_long_messages_are_truncated_to_4000_characters_with_a_marker():
    reason = post_lint.format_reason(_findings(10, "x" * 600))
    assert len(reason) == 4000
    assert reason.endswith(post_lint.TRUNCATION_MARKER)


def test_reason_just_under_the_limit_is_untouched():
    reason = post_lint.format_reason(_findings(3, "y" * 100))
    assert not reason.endswith(post_lint.TRUNCATION_MARKER)


# --- consecutive-block cap, reset, session isolation -------------------------


def _violating(project: Project) -> dict[str, str]:
    return project.env(FAKE_STDOUT=_eslint_json(project, [("no-var", 1, "m")]))


def _clean(project: Project) -> dict[str, str]:
    return project.env(FAKE_STDOUT=_eslint_json(project, []))


@posix_only
def test_cap_releases_after_three_blocks_and_notices_once(project):
    env = _violating(project)
    results = [project.run(env=env) for _ in range(5)]

    assert [r.outcome for r in results] == [
        post_lint.BLOCKED,
        post_lint.BLOCKED,
        post_lint.BLOCKED,
        post_lint.CAPPED,
        post_lint.CAPPED,
    ]
    assert "cap 3 reached; set DEVTEAM_POST_LINT=0 to disable" in _notice_text(
        results[3]
    )
    assert "decision" not in results[3].output
    assert results[4].output is None


@posix_only
def test_clean_lint_resets_the_counter_and_sessions_are_isolated(project):
    violating, clean = _violating(project), _clean(project)
    session_a, session_b = (
        project.payload(session_id="A"),
        project.payload(session_id="B"),
    )

    for _ in range(2):
        assert project.run(session_a, violating).outcome == post_lint.BLOCKED
    assert project.run(session_a, clean).outcome == post_lint.CLEAN
    for _ in range(2):
        assert project.run(session_b, violating).outcome == post_lint.BLOCKED

    # A starts over (its first block of a new run); B is at its third.
    assert project.run(session_a, violating).outcome == post_lint.BLOCKED
    assert project.run(session_b, violating).outcome == post_lint.BLOCKED
    assert project.run(session_b, violating).outcome == post_lint.CAPPED
    assert project.run(session_a, violating).outcome == post_lint.BLOCKED


@posix_only
def test_fail_open_runs_do_not_count_toward_the_cap(project):
    _break_config(project)
    for _ in range(4):
        project.run(env=_violating(project))
    (project.root / post_lint.CONFIG_NAME).write_text("export default [];\n")
    assert project.run(env=_violating(project)).outcome == post_lint.BLOCKED


@posix_only
def test_unwritable_state_fails_open_instead_of_blocking_forever(project):
    not_a_directory = project.root.parent / "state-is-a-file"
    not_a_directory.write_text("")
    result = post_lint.evaluate(
        project.payload(), _violating(project), not_a_directory / "sub"
    )
    assert result.outcome == post_lint.FAILED_OPEN
    assert "decision" not in (result.output or {})
    assert "cannot save session state" in _notice_text(result)


@posix_only
def test_a_clean_run_reads_session_state_only_under_the_lock(project, monkeypatch):
    held = []
    real_lock, real_read = post_lint.locked_state, post_lint._read_state

    @contextlib.contextmanager
    def spy_lock(path, **kwargs):
        held.append(True)
        try:
            with real_lock(path, **kwargs):
                yield
        finally:
            held.pop()

    def spy_read(path):
        assert held, "session state was read without holding the lock"
        return real_read(path)

    monkeypatch.setattr(post_lint, "locked_state", spy_lock)
    monkeypatch.setattr(post_lint, "_read_state", spy_read)

    assert project.run(env=_clean(project)).outcome == post_lint.CLEAN


@posix_only
def test_a_block_counter_that_cannot_be_locked_fails_open_instead_of_counting(project):
    project.state_dir.mkdir(mode=0o700)
    lock = post_lint.state_path("s1", project.state_dir).with_suffix(".json.lock")
    lock.symlink_to(project.root.parent / "planted-lock")

    result = project.run(env=_violating(project))

    assert result.outcome == post_lint.FAILED_OPEN
    assert "decision" not in (result.output or {})
    assert "cannot save session state" in _notice_text(result)


@posix_only
def test_one_run_resolves_the_project_root_once(project, monkeypatch):
    calls = []
    real = post_lint.artifact_paths.git_toplevel
    monkeypatch.setattr(
        post_lint.artifact_paths,
        "git_toplevel",
        lambda *a, **k: calls.append(a) or real(*a, **k),
    )

    project.run(env=_clean(project))

    assert len(calls) == 1


# --- state directory: private per user, expiring ------------------------------


@posix_only
def test_default_state_dir_is_per_user_under_tmpdir(tmp_path):
    state_dir = post_lint.default_state_dir({"TMPDIR": str(tmp_path)})
    assert state_dir == tmp_path / f"dev-team-post-lint-{os.getuid()}"


@posix_only
def test_state_dir_is_created_private(project):
    project.run(env=_violating(project))
    assert stat.S_IMODE(project.state_dir.stat().st_mode) == 0o700


@posix_only
def test_an_existing_group_readable_state_dir_is_tightened_to_private(project):
    project.state_dir.mkdir()
    project.state_dir.chmod(0o755)
    project.run(env=_violating(project))
    assert stat.S_IMODE(project.state_dir.stat().st_mode) == 0o700


@posix_only
def test_a_symlinked_state_dir_fails_open_and_is_never_written_through(project):
    planted = project.root.parent / "planted"
    planted.mkdir()
    project.state_dir.symlink_to(planted, target_is_directory=True)

    result = project.run(env=_violating(project))

    assert result.outcome == post_lint.FAILED_OPEN
    assert "decision" not in (result.output or {})
    assert "cannot save session state" in _notice_text(result)
    assert list(planted.iterdir()) == []


@posix_only
def test_a_state_dir_owned_by_someone_else_fails_open(project, monkeypatch):
    project.state_dir.mkdir()
    monkeypatch.setattr(os, "getuid", lambda: os.stat(project.state_dir).st_uid + 1)

    result = project.run(env=_violating(project))

    assert result.outcome == post_lint.FAILED_OPEN
    assert "cannot save session state" in _notice_text(result)
    assert list(project.state_dir.iterdir()) == []


@posix_only
def test_stale_session_state_is_purged_on_write_and_fresh_state_is_kept(project):
    project.state_dir.mkdir(mode=0o700)
    stale = project.state_dir / "stale.json"
    fresh = project.state_dir / "fresh.json"
    other = project.state_dir / "keep.txt"
    for path in (stale, fresh, other):
        path.write_text("{}")
    old = time.time() - 5 * 3600
    for path in (stale, other):
        os.utime(path, (old, old))

    project.run(env=_violating(project))

    assert not stale.exists()
    assert fresh.exists() and other.exists()


@posix_only
def test_an_unchanged_state_run_still_counts_as_use_for_the_ttl(project, monkeypatch):
    _break_config(project)
    first = project.run()
    assert first.output is not None
    (state_file,) = project.state_dir.glob("*.json")
    three_hours_ago = time.time() - 3 * 3600
    os.utime(state_file, (three_hours_ago, three_hours_ago))

    second = project.run()  # notice already seen: the state does not change

    assert second.output is None
    assert state_file.stat().st_mtime > time.time() - 60
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 2 * 3600)
    third = project.run()  # 2h after last use: kept; 5h after last change: purged
    assert third.output is None


@posix_only
def test_an_unchanged_run_without_a_state_file_does_not_fail(project):
    project.run(env=_clean(project))
    assert list(project.state_dir.glob("*.json")) == []


def test_the_hook_does_not_import_another_hooks_private_module():
    imported = set()
    for node in ast.walk(ast.parse(HOOK.read_text())):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "verify_guard_state" not in imported


# --- metrics -----------------------------------------------------------------


def _metrics(project: Project) -> list[dict]:
    path = project.root / ".claude" / "metrics" / post_lint.METRICS_FILE
    return [json.loads(line) for line in path.read_text().splitlines()]


@posix_only
def test_each_run_appends_one_metrics_line_with_the_five_fields(project):
    project.run(env=_violating(project))
    project.run(env=_clean(project))
    project.run(project.payload("src/a.py"))

    rows = _metrics(project)
    assert [r["outcome"] for r in rows] == [
        post_lint.BLOCKED,
        post_lint.CLEAN,
        post_lint.SKIPPED,
    ]
    assert [r["ext"] for r in rows] == [".js", ".js", ".py"]
    for row in rows:
        assert set(row) == {"ts", "session", "ext", "wall_ms", "outcome"}
        assert row["session"] == "s1"
        assert isinstance(row["wall_ms"], int) and row["wall_ms"] >= 0
        assert row["ts"].endswith("Z")


@posix_only
def test_fail_open_and_cap_outcomes_are_recorded(project):
    for _ in range(4):
        project.run(env=_violating(project))
    _break_config(project)
    project.run(env=_clean(project))
    assert [r["outcome"] for r in _metrics(project)] == [
        post_lint.BLOCKED,
        post_lint.BLOCKED,
        post_lint.BLOCKED,
        post_lint.CAPPED,
        post_lint.FAILED_OPEN,
    ]


def _boundary_rows(project: Project) -> list[dict]:
    path = project.root / ".claude" / "metrics" / "boundary-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@posix_only
def test_a_block_and_the_cap_each_emit_a_boundary_event_with_rule_ids_only(project):
    env = _violating(project)
    for _ in range(4):
        project.run(env=env)
    project.run(env=_clean(project))

    rows = _boundary_rows(project)
    assert [(r["decision"], r["matched_rule"]) for r in rows] == [
        ("block", "lint-findings"),
        ("block", "lint-findings"),
        ("block", "lint-findings"),
        ("warn", "block-cap"),
    ]
    for row in rows:
        assert (row["hook"], row["tool"], row["session_id"]) == (
            "post_lint",
            "Edit",
            "s1",
        )
        assert "a.js" not in json.dumps(row)


@posix_only
def test_runs_that_do_not_block_emit_no_boundary_event(project):
    project.run(env=_clean(project))
    project.run(project.payload("src/a.py"))
    _break_config(project)
    project.run(env=_violating(project))
    assert _boundary_rows(project) == []


@posix_only
def test_a_failing_boundary_emit_never_changes_the_verdict(project, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("ledger broke")

    monkeypatch.setattr(post_lint, "_emit_boundary_event", boom)
    result = project.run(env=_violating(project))
    assert result.outcome == post_lint.BLOCKED
    assert result.output["decision"] == "block"


@posix_only
def test_metrics_failure_never_changes_the_verdict(project):
    (project.root / ".claude").write_text("not a directory")
    assert project.run(env=_violating(project)).outcome == post_lint.BLOCKED


@posix_only
def test_a_disabled_hook_writes_no_metrics(project):
    stdin = json.dumps(project.payload())

    _run_script(project, stdin)
    assert not (project.root / ".claude").exists()

    # Control: the same run, enabled, does write the metrics line.
    _run_script(project, stdin, **{post_lint.ENV_ENABLE: "1"})
    assert [r["outcome"] for r in _metrics(project)] == [post_lint.CLEAN]


# --- real ESLint -------------------------------------------------------------

DEV_TREE = REPO_ROOT / "plugins" / "dev-team" / "templates" / "eslint"
FIXTURES = DEV_TREE / "dev" / "fixtures"
PAYLOAD_CONFIG = DEV_TREE / "payload" / post_lint.CONFIG_NAME
# The dev tree's pinned ESLint 9 unless DEVTEAM_ESLINT_ROOT points elsewhere. The
# gate unsets it for this file: ESLint 10 runs only in the Node tests
# (`node --test`), not in these hook tests.
ESLINT_ROOT = Path(os.environ.get("DEVTEAM_ESLINT_ROOT") or DEV_TREE / "dev")


# Only the `chk_eslint_templates` gate installs the dev tree's `node_modules`
# in CI; it sets this so a missing ESLint fails there instead of skipping unseen.
ENV_REQUIRE_ESLINT = "DEVTEAM_REQUIRE_REAL_ESLINT"


def _require_real_eslint() -> str:
    """The `node` path, or a skip locally. A missing `node` fails when `CI` is
    set; a missing ESLint install fails when `DEVTEAM_REQUIRE_REAL_ESLINT` is
    set."""
    node = shutil.which("node")
    if node is None:
        reason = "node is not on PATH; the real-ESLint tests cannot run"
        if os.environ.get("CI"):
            pytest.fail(reason)
        pytest.skip(reason)
    if not (ESLINT_ROOT / "node_modules" / "eslint" / "bin" / "eslint.js").is_file():
        reason = (
            f"ESLint is not installed under {ESLINT_ROOT}/node_modules; "
            "run `npm ci` in plugins/dev-team/templates/eslint/dev"
        )
        if os.environ.get(ENV_REQUIRE_ESLINT):
            pytest.fail(reason)
        pytest.skip(reason)
    return node


@pytest.mark.parametrize(
    ("env", "node", "eslint_installed", "expected"),
    [
        ({}, None, True, "skip"),
        ({"CI": "1"}, None, True, "fail"),
        ({"CI": "true"}, None, True, "fail"),
        ({}, "/usr/bin/node", False, "skip"),
        ({"CI": "1"}, "/usr/bin/node", False, "skip"),
        ({ENV_REQUIRE_ESLINT: "1"}, "/usr/bin/node", False, "fail"),
        ({"CI": "1"}, "/usr/bin/node", True, "pass"),
    ],
)
def test_real_eslint_gate_skips_locally_and_fails_where_required(
    monkeypatch, tmp_path, env, node, eslint_installed, expected
):
    for name in ("CI", ENV_REQUIRE_ESLINT):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(shutil, "which", lambda _name: node)
    if eslint_installed:
        (tmp_path / "node_modules" / "eslint" / "bin").mkdir(parents=True)
        (tmp_path / "node_modules" / "eslint" / "bin" / "eslint.js").write_text("")
    monkeypatch.setattr(sys.modules[__name__], "ESLINT_ROOT", tmp_path)

    if expected == "pass":
        assert _require_real_eslint() == node
        return
    outcome = pytest.skip.Exception if expected == "skip" else pytest.fail.Exception
    with pytest.raises(outcome):
        _require_real_eslint()


STRIPPED_PREFIXES = ("DEVTEAM_", "ESLINT_", "GIT_")
STRIPPED_NAMES = frozenset({"NODE_OPTIONS", "CLAUDE_PROJECT_DIR"})


class RealProject:
    """A scratch project whose `node_modules` points at the dev tree's."""

    def __init__(self, root: Path, *, typed_deps: bool) -> None:
        self.root = root
        root.mkdir()
        (root / "package.json").write_text('{"type":"module"}\n')
        shutil.copy(PAYLOAD_CONFIG, root / post_lint.CONFIG_NAME)
        modules = ESLINT_ROOT / "node_modules"
        if typed_deps:
            (root / "node_modules").symlink_to(modules, target_is_directory=True)
        else:
            (root / "node_modules").mkdir()
            (root / "node_modules" / "eslint").symlink_to(
                modules / "eslint", target_is_directory=True
            )
        self.state_dir = root.parent / f"{root.name}-state"

    def write(self, name: str, text: str) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def copy_fixture(self, fixture: str, name: str) -> None:
        self.write(name, (FIXTURES / fixture).read_text())

    def env(self) -> dict[str, str]:
        """The caller's environment minus anything that changes ESLint's or the
        hook's behavior, plus a timeout generous enough for a loaded machine."""
        base = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(STRIPPED_PREFIXES) and k not in STRIPPED_NAMES
        }
        return {**base, post_lint.ENV_ENABLE: "1", post_lint.ENV_TIMEOUT: "60"}

    def run(self, file_path: str, session: str = "real") -> post_lint.Result:
        payload = {
            "tool_name": "Write",
            "session_id": session,
            "cwd": str(self.root),
            "tool_input": {"file_path": file_path},
        }
        return post_lint.evaluate(payload, self.env(), self.state_dir)


@pytest.fixture
def real(tmp_path: Path) -> RealProject:
    _require_real_eslint()
    return RealProject(tmp_path / "real", typed_deps=True)


def test_real_eslint_blocks_on_a_warn_finding(real):
    real.copy_fixture("violating.js", "src/violating.js")

    result = real.run("src/violating.js")

    expected = [
        tuple(pair)
        for pair in json.loads((FIXTURES / "expected.json").read_text())["violating.js"]
    ]
    shown = expected[: post_lint.MAX_FINDINGS]
    assert result.outcome == post_lint.BLOCKED
    assert result.output["decision"] == "block"
    lines = result.output["reason"].splitlines()
    assert lines[0].startswith("dev-team post-edit lint")
    reported = [
        (text.split()[1], int(text.split()[0].rsplit(":", 1)[1]))
        for text in lines[1 : 1 + len(shown)]
    ]
    assert reported == shown
    assert all(
        text.startswith("src/violating.js:") for text in lines[1 : 1 + len(shown)]
    )
    assert lines[1 + len(shown) :] == (
        [f"+{len(expected) - len(shown)} more"] if len(expected) > len(shown) else []
    )


def test_real_eslint_passes_a_clean_file(real):
    real.copy_fixture("clean.js", "src/clean.js")
    result = real.run("src/clean.js")
    assert (result.outcome, result.output) == (post_lint.CLEAN, None)


def test_real_eslint_parse_error_fails_open_with_a_notice(real):
    real.write("src/broken.js", "const = ;\n")
    result = real.run("src/broken.js")
    assert result.outcome == post_lint.FAILED_OPEN
    assert "parse error" in _notice_text(result)


TYPED_PROBE = """var legacy = 1;
export const build = () => {
  const out = [];
  out.push(legacy);
  return out;
};
"""


PROBE_VAR_LINE = TYPED_PROBE.splitlines().index("var legacy = 1;") + 1
PROBE_MUTATOR_LINE = TYPED_PROBE.splitlines().index("  out.push(legacy);") + 1


def _lint_directly(real: RealProject, file_path: str) -> subprocess.CompletedProcess:
    """ESLint run by hand against `file_path`, outside the hook."""
    return subprocess.run(
        [
            shutil.which("node"),
            str(real.root / "node_modules" / "eslint" / "bin" / "eslint.js"),
            "--config",
            str(real.root / post_lint.CONFIG_NAME),
            "--format",
            "json",
            file_path,
        ],
        cwd=real.root,
        env=real.env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _rule_lines(done: subprocess.CompletedProcess) -> list[tuple[str, int]]:
    messages = json.loads(done.stdout)[0]["messages"]
    return [(m["ruleId"], m["line"]) for m in messages]


def test_real_eslint_ignores_disable_comments_for_rules_that_are_not_loaded(real):
    real.write(
        "src/disables.ts",
        "// eslint-disable-next-line functional/immutable-data\n"
        "export const a = 1;\n"
        "/* eslint-disable @typescript-eslint/no-explicit-any */\n"
        "export const b = 2;\n",
    )
    # Control: ESLint itself does report both as errors carrying a rule id.
    assert {rule for rule, _ in _rule_lines(_lint_directly(real, "src/disables.ts"))} >= {
        "functional/immutable-data",
        "@typescript-eslint/no-explicit-any",
    }

    result = real.run("src/disables.ts")

    assert (result.outcome, result.output) == (post_lint.CLEAN, None)


def test_typed_rules_are_off_inside_the_hook(real):
    real.write(
        "tsconfig.json",
        json.dumps(
            {
                "compilerOptions": {"strict": True, "noEmit": True},
                "include": ["src/**/*"],
            }
        ),
    )
    real.write("src/probe.ts", TYPED_PROBE)

    # Control: the same file outside the hook does report the typed rule.
    assert ("functional/immutable-data", PROBE_MUTATOR_LINE) in _rule_lines(
        _lint_directly(real, "src/probe.ts")
    )

    result = real.run("src/probe.ts")

    assert result.outcome == post_lint.BLOCKED
    findings = result.output["reason"].splitlines()[1:]
    assert len(findings) == 1
    assert findings[0].startswith(f"src/probe.ts:{PROBE_VAR_LINE} no-var ")


def test_json_stdout_stays_parseable_when_typed_deps_are_missing(tmp_path):
    _require_real_eslint()
    bare = RealProject(tmp_path / "bare", typed_deps=False)
    bare.write("tsconfig.json", '{"include": ["src/**/*"]}')
    bare.write("src/a.js", "var a = 1;\n")
    done = _lint_directly(bare, "src/a.js")

    assert json.loads(done.stdout)[0]["messages"][0]["ruleId"] == "no-var"
    assert done.stderr.count("typed rules skipped") == 1
    assert "not installed" in done.stderr


# --- registration ------------------------------------------------------------

PLUGIN = REPO_ROOT / "plugins" / "dev-team"


def _post_edit_commands(path: Path, tool: str = "Edit") -> list[str]:
    """Commands the harness would run after `tool`: groups whose matcher
    (`*` or empty means every tool, otherwise a full-match regex) covers it."""
    hooks = json.loads(path.read_text())["hooks"]["PostToolUse"]
    return [
        hook["command"]
        for entry in hooks
        if entry.get("matcher", "*") in ("", "*")
        or re.fullmatch(entry["matcher"], tool)
        for hook in entry["hooks"]
    ]


@pytest.mark.parametrize("tool", sorted(post_lint.EDIT_TOOLS))
@pytest.mark.parametrize("registry", ["hooks/hooks.json", "settings.json"])
def test_hook_is_registered_once_for_every_edit_tool_it_accepts(registry, tool):
    commands = _post_edit_commands(PLUGIN / registry, tool)
    assert sum("post_lint.py" in command for command in commands) == 1


@pytest.mark.parametrize("registry", ["hooks/hooks.json", "settings.json"])
def test_registration_does_not_enable_the_hook(registry):
    assert post_lint.ENV_ENABLE not in (PLUGIN / registry).read_text()


def _run_registered_command(project: Project, **env: str):
    """Run the settings.json command string as the harness would."""
    command = next(
        c for c in _post_edit_commands(PLUGIN / "settings.json") if "post_lint.py" in c
    )
    base = {k: v for k, v in os.environ.items() if k != post_lint.ENV_ENABLE}
    return subprocess.run(
        command,
        shell=True,
        input=json.dumps(project.payload()),
        capture_output=True,
        text=True,
        cwd=PLUGIN,
        env={
            **base,
            **project.env(),
            "TMPDIR": str(project.state_dir.parent),
            "PATH": f"{project.bin}:{base['PATH']}",
            **env,
        },
        timeout=60,
        check=False,
    )


@posix_only
def test_registered_command_runs_nothing_by_default(project):
    done = _run_registered_command(project)
    assert (done.returncode, done.stdout) == (0, "")
    assert not project.invoked

    # Control: the same command string, opted in, does reach ESLint.
    done = _run_registered_command(project, **{post_lint.ENV_ENABLE: "1"})
    assert done.returncode == 0
    assert project.invoked
