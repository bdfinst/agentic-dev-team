"""Scripts fail fast, not hang, when stdin never reaches EOF.

Each row runs a real script as a subprocess with the stdin kind under test:
a socket whose peer stays open, a pseudo-terminal, a pipe, ``/dev/null``, a
regular file. A regression that blocks on stdin fails the row with a timeout
instead of hanging the run. Goldens for the pipe and ``/dev/null`` rows were
captured from the scripts before the guard was wired in (see
``tests/_support/stdin_scripts.py``). ``orchestrator.py`` has no input flag;
its in-process stdin matrix is in ``test_orchestrator_stdin.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT
from tests._support.stdin_harness import (
    NO_PTY_ON_WINDOWS,
    NO_SOCKETS_ON_WINDOWS,
    REFUSAL,
    SUBPROCESS_TIMEOUT_SECONDS,
    assert_refused,
    endless_socket,
    fallback_lines,
    terminal,
)
from tests._support.stdin_scripts import (
    INPUT_FLAGS,
    ORCHESTRATOR_RUNS_STDERR,
    STDIN_SCRIPTS,
    Golden,
    StdinScript,
)

PLUGIN_DIR = REPO_ROOT / "plugins" / "dev-team"


def _name(row: StdinScript) -> str:
    return Path(row.script).name


FLAG_ROWS = [row for row in STDIN_SCRIPTS if row.needs_flag]
GOLDEN_ROWS = [row for row in STDIN_SCRIPTS if row.piped and row.devnull]
GOLDEN_ROW_PARAMS = [pytest.param(row, id=_name(row)) for row in GOLDEN_ROWS]
NEEDS_FLAG = [pytest.param(row, id=_name(row)) for row in FLAG_ROWS]
ROW_BY_NAME = {_name(row): row for row in STDIN_SCRIPTS}
#: One case per (script, argv) that reads stdin through a flag other than the
#: row's primary one.
SECOND_FLAG_CASES = [
    pytest.param(
        ROW_BY_NAME[rule.script],
        rule.flag,
        argv,
        id=f"{Path(rule.script).stem}-{'-'.join(argv)}",
    )
    for rule in INPUT_FLAGS
    for argv in rule.stdin_argvs
]
#: One case per secondary flag: the argv that gives it a file, with
#: ``{file}`` standing for that file, and the file's content.
SECOND_FLAG_FILE_CASES = [
    pytest.param(
        "review_context_pack.py",
        "--name-status-from",
        ("--name-status-from", "{file}"),
        "M\ta.py\n",
        id="review_context_pack-name-status-from",
    ),
    pytest.param(
        "select_lenses.py",
        "--added-from",
        ("--added-from", "{file}"),
        "a.py\n",
        id="select_lenses-added-from",
    ),
    pytest.param(
        "review_round_log.py",
        "--fix-diff",
        ("--fix-diff", "{file}"),
        "--- a/x\n+++ b/x\n",
        id="review_round_log-fix-diff",
    ),
    pytest.param(
        "checkpoint_abort.py",
        "--from",
        ("--mode", "outcome", "--from", "{file}"),
        json.dumps({"aborted": False, "redispatched": False, "findings": []}),
        id="checkpoint_abort-outcome-from",
    ),
    pytest.param(
        "checkpoint_abort.py",
        "--from",
        ("--mode", "merge", "--from", "{file}"),
        json.dumps({"existing": [], "new": []}),
        id="checkpoint_abort-merge-from",
    ),
]


def _run(
    row: StdinScript,
    cwd: Path,
    *,
    stdin=None,
    text_in: str | None = None,
    leading_argv: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    # A subcommand (first word not a flag) stays first; an input flag goes after it.
    lead_at = 1 if row.argv and not row.argv[0].startswith("-") else 0
    row_argv = list(row.argv)
    row_argv[lead_at:lead_at] = leading_argv
    if not leading_argv:
        row_argv += row.stdin_argv
    argv = [sys.executable, str(PLUGIN_DIR / row.script), *row_argv]
    try:
        return subprocess.run(
            argv,
            stdin=stdin,
            input=text_in,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{row.script}: no result in {SUBPROCESS_TIMEOUT_SECONDS} s "
            "(hang or slow host)"
        )


def _assert_matches(result: subprocess.CompletedProcess, golden: Golden) -> None:
    assert result.returncode == golden.exit_status, result.stderr
    if golden.json_keys is None:
        assert result.stdout == golden.stdout
    else:
        actual = json.loads(result.stdout)
        assert {key: actual.get(key) for key in golden.json_keys} == json.loads(
            golden.stdout
        )
    if golden.stderr_fragment is None:
        assert REFUSAL not in result.stderr
    else:
        assert golden.stderr_fragment in result.stderr


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_script_refuses_an_endless_socket_stdin_and_names_its_flag(row, tmp_path):
    with endless_socket() as reader:
        result = _run(row, tmp_path, stdin=reader)

    assert_refused(result, row.flag)


@NO_PTY_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_script_refuses_a_terminal_stdin_and_names_its_flag(row, tmp_path):
    with terminal() as slave:
        result = _run(row, tmp_path, stdin=slave)

    assert_refused(result, row.flag)


@pytest.mark.parametrize("row", GOLDEN_ROW_PARAMS)
def test_piped_fixture_gives_the_pre_guard_exit_stdout_and_stderr(row, tmp_path):
    result = _run(row, tmp_path, text_in=row.fixture)

    _assert_matches(result, row.piped)


@pytest.mark.parametrize("row", GOLDEN_ROW_PARAMS)
def test_regular_file_stdin_gives_the_piped_exit_stdout_and_stderr(row, tmp_path):
    fixture_file = tmp_path / "stdin.txt"
    fixture_file.write_text(row.fixture, encoding="utf-8")

    with open(fixture_file, encoding="utf-8") as stream:
        result = _run(row, tmp_path, stdin=stream)

    _assert_matches(result, row.piped)


@pytest.mark.parametrize("row", GOLDEN_ROW_PARAMS)
def test_null_device_gives_the_pre_guard_exit_stdout_and_stderr(row, tmp_path):
    result = _run(row, tmp_path, stdin=subprocess.DEVNULL)

    _assert_matches(result, row.devnull)


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize("row", NEEDS_FLAG)
def test_primary_input_flag_wins_over_an_endless_socket_stdin(row, tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text(row.fixture, encoding="utf-8")

    with endless_socket() as reader:
        result = _run(
            row, tmp_path, stdin=reader, leading_argv=(row.flag, str(input_file))
        )

    _assert_matches(result, row.piped)


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize(
    ("script", "flag", "argv_template", "content"), SECOND_FLAG_FILE_CASES
)
def test_secondary_input_flag_with_a_file_never_reads_an_endless_socket_stdin(
    script, flag, argv_template, content, tmp_path
):
    input_file = tmp_path / "input.txt"
    input_file.write_text(content, encoding="utf-8")
    argv = tuple(
        str(input_file) if word == "{file}" else word for word in argv_template
    )

    with endless_socket() as reader:
        result = _run(ROW_BY_NAME[script], tmp_path, stdin=reader, leading_argv=argv)

    assert result.returncode == 0, result.stderr
    assert REFUSAL not in result.stderr


@NO_SOCKETS_ON_WINDOWS
def test_an_empty_name_status_file_reports_no_files_instead_of_reading_stdin(tmp_path):
    empty = tmp_path / "name-status.txt"
    empty.write_text("", encoding="utf-8")

    with endless_socket() as reader:
        result = _run(
            ROW_BY_NAME["review_context_pack.py"],
            tmp_path,
            stdin=reader,
            leading_argv=("--name-status-from", str(empty)),
        )

    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["error"] == "no files given"
    assert REFUSAL not in result.stderr


def test_every_secondary_input_flag_has_a_file_case():
    in_table = {(rule.script, rule.flag) for rule in INPUT_FLAGS if rule.stdin_argvs}
    covered = {(case.values[0], case.values[1]) for case in SECOND_FLAG_FILE_CASES}
    assert covered == in_table


@NO_SOCKETS_ON_WINDOWS
@pytest.mark.parametrize(("row", "flag", "argv"), SECOND_FLAG_CASES)
def test_a_second_stdin_flag_on_one_script_is_named_when_it_is_the_one_used(
    row, flag, argv, tmp_path
):
    with endless_socket() as reader:
        result = _run(row, tmp_path, stdin=reader, leading_argv=argv)

    assert_refused(result, flag)


# orchestrator.py has no input flag: an endless stdin falls back to the default
# request and says so on stderr, instead of failing. One subprocess test proves
# the wiring end to end.


@NO_SOCKETS_ON_WINDOWS
def test_orchestrator_falls_back_and_says_so_on_an_endless_socket_stdin(tmp_path):
    with endless_socket() as reader:
        result = _run(ROW_BY_NAME["orchestrator.py"], tmp_path, stdin=reader)

    fallback = fallback_lines(result.stderr)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert len(fallback) == 1
    assert "default request" in fallback[0]
    assert ORCHESTRATOR_RUNS_STDERR in result.stderr
