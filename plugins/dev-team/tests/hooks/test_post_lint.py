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
import re
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
    _run_script(project, json.dumps(project.payload()))
    assert not (project.root / ".claude").exists()


# --- real ESLint -------------------------------------------------------------

DEV_TREE = REPO_ROOT / "plugins" / "dev-team" / "templates" / "eslint"
FIXTURES = DEV_TREE / "dev" / "fixtures"
PAYLOAD_CONFIG = DEV_TREE / "payload" / post_lint.CONFIG_NAME
# Same switch the Node tests use, so one run can target ESLint 9 or 10.
ESLINT_ROOT = Path(os.environ.get("DEVTEAM_ESLINT_ROOT") or DEV_TREE / "dev")


def _require_real_eslint() -> str:
    node = shutil.which("node")
    if node is None:
        reason = "node is not on PATH; the real-ESLint tests cannot run"
        if os.environ.get("CI") == "true":
            pytest.fail(reason)
        pytest.skip(reason)
    if not (ESLINT_ROOT / "node_modules" / "eslint" / "bin" / "eslint.js").is_file():
        pytest.skip(
            f"ESLint is not installed under {ESLINT_ROOT}/node_modules; "
            "run `npm ci` in plugins/dev-team/templates/eslint/dev"
        )
    return node


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
        base = {k: v for k, v in os.environ.items() if k != post_lint.ENV_TYPED}
        return {**base, post_lint.ENV_ENABLE: "1"}

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

    assert result.outcome == post_lint.BLOCKED
    assert result.output["decision"] == "block"
    lines = result.output["reason"].splitlines()
    assert lines[0].startswith("dev-team post-edit lint")
    assert lines[1].startswith("src/violating.js:3 no-var ")
    assert lines[-1] == "+2 more"
    assert len(lines) == 12  # header, 10 findings, +N more


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


def _lint_directly(real: RealProject, file_path: str) -> list[tuple[str, int]]:
    done = subprocess.run(
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
        check=False,
    )
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
    assert {rule for rule, _ in _lint_directly(real, "src/disables.ts")} >= {
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
    assert ("functional/immutable-data", 4) in _lint_directly(real, "src/probe.ts")

    result = real.run("src/probe.ts")

    assert result.outcome == post_lint.BLOCKED
    findings = result.output["reason"].splitlines()[1:]
    assert len(findings) == 1
    assert findings[0].startswith("src/probe.ts:1 no-var ")


def test_json_stdout_stays_parseable_when_typed_deps_are_missing(tmp_path):
    _require_real_eslint()
    bare = RealProject(tmp_path / "bare", typed_deps=False)
    bare.write("tsconfig.json", '{"include": ["src/**/*"]}')
    bare.write("src/a.js", "var a = 1;\n")
    node = shutil.which("node")

    done = subprocess.run(
        [
            node,
            str(bare.root / "node_modules" / "eslint" / "bin" / "eslint.js"),
            "--config",
            str(bare.root / post_lint.CONFIG_NAME),
            "--format",
            "json",
            "src/a.js",
        ],
        cwd=bare.root,
        capture_output=True,
        text=True,
        check=False,
        env={k: v for k, v in os.environ.items() if k != post_lint.ENV_TYPED},
    )

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


@posix_only
def test_registered_command_runs_nothing_by_default(project):
    """Run the settings.json command string as the harness would, minus the opt-in."""
    command = next(
        c for c in _post_edit_commands(PLUGIN / "settings.json") if "post_lint.py" in c
    )
    base = {k: v for k, v in os.environ.items() if k != post_lint.ENV_ENABLE}
    done = subprocess.run(
        command,
        shell=True,
        input=json.dumps(project.payload()),
        capture_output=True,
        text=True,
        cwd=PLUGIN,
        env={**base, **project.env(), "PATH": f"{project.bin}:{base['PATH']}"},
        check=False,
    )
    assert (done.returncode, done.stdout) == (0, "")
    assert not project.invoked
