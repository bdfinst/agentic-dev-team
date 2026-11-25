"""Tests for hooks/post_lint.py — the opt-in post-edit ESLint hook.

Most tests drive `evaluate()` with a fake `node` on PATH (a small Python
script) so every fail-open and skip row runs without Node installed. A few
tests run the real script as a subprocess, and the real-ESLint tests use the
template dev tree's `node_modules` (skipped with a named reason when `node` is
absent locally; a failure when `CI=true`).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "hooks"))

import post_lint

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
    with open(os.environ["FAKE_PIDS"], "w") as handle:
        json.dump([os.getpid(), child.pid], handle)
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


FAIL_OPEN_ROWS = {
    "no-eslint": (_break_eslint, {}),
    "no-node": (_break_node, {}),
    "no-config": (_break_config, {}),
    "no-json": (None, {"FAKE_MODE": "exit2"}),
    "invalid-json": (None, {"FAKE_STDOUT": "not json"}),
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
    ),
}


@posix_only
@pytest.mark.parametrize("reason", sorted(FAIL_OPEN_ROWS))
def test_fail_open_never_blocks_and_notices_once_per_session(project, reason):
    breaker, extra = FAIL_OPEN_ROWS[reason]
    if breaker:
        breaker(project)
    env = project.env(**extra)

    first = project.run(env=env)
    second = project.run(env=env)

    assert first.outcome == second.outcome == post_lint.FAILED_OPEN
    assert "decision" not in (first.output or {})
    assert _notice_text(first).startswith("post_lint: ")
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
def test_invalid_hook_stdin_fails_open_with_one_notice(project):
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
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@posix_only
def test_timeout_fails_open_and_terminates_the_whole_process_group(project, tmp_path):
    pids = tmp_path / "pids.json"
    env = project.env(
        FAKE_MODE="sleep", FAKE_PIDS=str(pids), DEVTEAM_POST_LINT_TIMEOUT="1"
    )

    started = time.monotonic()
    result = project.run(env=env)
    elapsed = time.monotonic() - started

    assert result.outcome == post_lint.FAILED_OPEN
    assert "timed out after 1s" in _notice_text(result)
    assert elapsed < 10
    node_pid, grandchild_pid = json.loads(pids.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and (_alive(node_pid) or _alive(grandchild_pid)):
        time.sleep(0.05)
    assert not _alive(node_pid)
    assert not _alive(grandchild_pid)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 10.0), ("", 10.0), ("abc", 10.0), ("0", 10.0), ("-3", 10.0), ("2.5", 2.5)],
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


@pytest.mark.parametrize(
    "stdout",
    ['{"a": 1}', "[1]", '[{"filePath": "x", "messages": [1]}]', '[{"messages": "no"}]'],
)
def test_parse_findings_rejects_wrong_shapes(stdout, tmp_path):
    with pytest.raises(post_lint.LintFailure) as caught:
        post_lint.parse_findings(stdout, 0, tmp_path)
    assert caught.value.key == "invalid-json"


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
