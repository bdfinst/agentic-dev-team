"""Unit tests for hooks/lib/examiner_read_audit.py (#2270, Step 3.1)."""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB_DIR = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"

if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import examiner_read_audit as era  # type: ignore[import-not-found]

ROOT = "/repo"
CWD = "/repo"


def _classify(command: str, cwd: str = CWD) -> list[era.Finding]:
    return era.audit_commands([command], ROOT, cwd)


# Each row: (command, expected [(kind, target)]); `none` rows expect [].
GHERKIN_ROWS = [
    ("pytest -q", []),
    ("pytest tests/test_app.py", []),
    ("pytest -q | tail -5", []),
    ("pytest -q 2>&1 | tail -5", []),
    ("pytest -q > out.log", [("write", "out.log")]),
    ("grep -n TODO src/app.py", [("read", "src/app.py")]),
    ("pytest -q | grep 'v1.2'", []),
    ("curl localhost:8080/health | cut -d. -f1", []),
    ("./bin/app --version | awk '{print $1/2}'", []),
    ("cat features/login.feature", []),
    ("grep TODO features/x.feature", []),
    ("ls src", []),
    ("curl localhost:8080 > /tmp/out.json; cat /tmp/out.json", []),
    ("cat src/app.py", [("read", "src/app.py")]),
    ("cat 'src/a b.py'", [("read", "src/a b.py")]),
    ("cat src/app.py features/x.feature", [("read", "src/app.py")]),
    ("head -n 5 src/a.py", [("read", "src/a.py")]),
    ("sed -n '1,5p' src/a.py", [("read", "src/a.py")]),
    ("grep -e TODO src/", [("read", "src/")]),
    ("grep -r TODO src/", [("read", "src/")]),
    ("cd repo && head -5 src/a.py", [("read", "src/a.py")]),
    ("cd src && cat app.py", [("read", "app.py")]),
    ("git show HEAD:src/app.py", [("git", "show")]),
    ("git diff", [("git", "diff")]),
    ("python3 - < tests/test_app.py", [("read", "tests/test_app.py")]),
    ("./bin/app < fixtures/in.json", [("read", "fixtures/in.json")]),
    ("find src -name '*.py' | xargs cat", [("xargs", "cat")]),
    ("sed -n '1,5p' /repo/src/app.py", [("read", "/repo/src/app.py")]),
    (
        "echo '{}' > .claude/memory/acceptance-examination-x.json",
        [("write", ".claude/memory/acceptance-examination-x.json")],
    ),
    ("pytest -q | tee run.log", [("write", "run.log")]),
    ("sed -i s/a/b/ src/app.py", [("write", "src/app.py")]),
    ("git commit -am wip", [("git", "commit")]),
    ("git stash", [("git", "stash")]),
]


@pytest.mark.parametrize(
    ("command", "expected"),
    GHERKIN_ROWS,
    ids=[command for command, _ in GHERKIN_ROWS],
)
def test_classifies_command_against_repository_root(command, expected):
    findings = _classify(command)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        (kind, target, command) for kind, target in expected
    ]


# Decisions the plan left open; each row pins the behavior chosen in Step 3.1.
DECISION_ROWS = [
    ("cd /elsewhere && cat app.py", []),
    ("cat ../outside.py", []),
    ("cat /repo2/x.py", []),
    ("cd && cat app.py", []),
    ("cd ~ && cat app.py", []),
    ("cd - && cat app.py", []),
    ("cd /elsewhere && cd /repo/src && cat app.py", [("read", "app.py")]),
    ("pytest -q 2>/dev/null", []),
    ("pytest -q 2>&1", []),
    ("pytest -q >&2", []),
    ("pytest -q 2> err.log", [("write", "err.log")]),
    ("pytest -q >> out.log", [("write", "out.log")]),
    ("pytest -q &> out.log", [("write", "out.log")]),
    ("pytest -q >out.log", [("write", "out.log")]),
    ("pytest -q > features/out.feature", []),
    ("cat src/a.py && cat src/b.py", [("read", "src/a.py"), ("read", "src/b.py")]),
    ("cat src/a.py|cat src/b.py", [("read", "src/a.py"), ("read", "src/b.py")]),
    ("pytest -q | sort src/a.py", [("read", "src/a.py")]),
    ("curl localhost | jq .status", []),
    ("tail -n 3 -f src/a.py", [("read", "src/a.py")]),
    ("rm -rf build", [("write", "build")]),
    ("cp /tmp/in.json fixtures/in.json", [("write", "fixtures/in.json")]),
    ("mv /repo/a.py /tmp/a.py", [("write", "/repo/a.py")]),
    ("sed -i.bak s/a/b/ src/app.py", [("write", "src/app.py")]),
    ("git -C /repo log", [("git", "log")]),
    ("git status", []),
    ("git branch -D old", [("git", "branch")]),
    ("find src | xargs -I{} grep TODO {}", [("xargs", "grep")]),
    ("echo src | xargs echo", []),
    ("cat -", []),
    ("cat", []),
    ("", []),
]


@pytest.mark.parametrize(
    ("command", "expected"),
    DECISION_ROWS,
    ids=[command or "<empty>" for command, _ in DECISION_ROWS],
)
def test_decided_edge_cases(command, expected):
    findings = _classify(command)

    assert [(f.kind, f.target) for f in findings] == expected


def test_cd_inside_one_command_does_not_leak_into_the_next():
    findings = era.audit_commands(["cd /elsewhere", "cat app.py"], ROOT, CWD)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        ("read", "app.py", "cat app.py")
    ]


def test_multiple_commands_keep_input_order_and_own_command_text():
    commands = ["cat src/a.py", "pytest -q", "git diff", "pytest -q > out.log"]

    findings = era.audit_commands(commands, ROOT, CWD)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        ("read", "src/a.py", "cat src/a.py"),
        ("git", "diff", "git diff"),
        ("write", "out.log", "pytest -q > out.log"),
    ]


def test_no_commands_yields_no_findings():
    assert era.audit_commands([], ROOT, CWD) == []


def test_relative_operand_resolves_against_the_given_cwd():
    findings = _classify("cat app.py", cwd="/repo/src")

    assert [(f.kind, f.target) for f in findings] == [("read", "app.py")]


def test_cwd_outside_root_makes_relative_operand_allowed():
    assert _classify("cat app.py", cwd="/tmp") == []


def test_unbalanced_quote_falls_back_to_whitespace_split():
    command = 'cat src/a.py "unterminated'

    findings = _classify(command)

    assert [(f.kind, f.target, f.command) for f in findings] == [
        ("read", "src/a.py", command),
        ("read", "unterminated", command),
    ]


def test_finding_is_a_named_tuple_of_kind_target_command():
    finding = era.Finding("read", "src/a.py", "cat src/a.py")

    assert (finding.kind, finding.target, finding.command) == (
        "read",
        "src/a.py",
        "cat src/a.py",
    )
