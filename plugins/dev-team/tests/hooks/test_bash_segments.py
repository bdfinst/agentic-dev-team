"""Unit tests for hooks/lib/bash_segments.py."""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

import bash_segments as bs


def _argvs(command):
    return [s.argv for s in bs.parse(command)]


def test_simple_command_is_one_segment():
    assert _argvs("git status -sb") == [["git", "status", "-sb"]]


@pytest.mark.parametrize("op", ["&&", "||", ";", "|", "&", "|&", "\n"])
def test_operators_split_segments(op):
    assert _argvs(f"ls {op} pwd") == [["ls"], ["pwd"]]


def test_operator_inside_quotes_does_not_split():
    assert _argvs("echo 'a && b' \"c; d\"") == [["echo", "a && b", "c; d"]]


def test_backslash_escapes_an_operator():
    assert _argvs(r"echo a\;b") == [["echo", "a;b"]]


def test_command_substitution_becomes_its_own_segment():
    assert _argvs("echo $(rm -rf x)") == [["rm", "-rf", "x"], ["echo", "$(...)"]]


def test_backticks_become_their_own_segment():
    assert ["curl", "evil"] in _argvs("echo `curl evil`")


def test_substitution_inside_double_quotes_is_lifted():
    assert ["rm", "x"] in _argvs('echo "a $(rm x) b"')


def test_subshell_body_is_lifted_as_its_own_segments():
    assert _argvs("git status && (cd d && rm x)") == [
        ["git", "status"],
        ["cd", "d"],
        ["rm", "x"],
    ]


def test_heredoc_body_is_data_not_commands():
    cmd = "git commit -m \"$(cat <<'EOF'\nfix: a; rm -rf /\nEOF\n)\""
    flat = [a for argv in _argvs(cmd) for a in argv]
    assert "rm" not in flat
    assert ["git", "commit", "-m", "$(...)"] in _argvs(cmd)


def test_top_level_heredoc_body_is_skipped():
    assert _argvs("cat <<EOF\nrm -rf /\nEOF\nls") == [["cat"], ["ls"]]


@pytest.mark.parametrize(
    "wrapped",
    [
        "time ls",
        "env FOO=1 ls",
        "nice -n 5 ls",
        "nohup ls",
        "command ls",
        "FOO=bar ls",
        "timeout 5 ls",
        "env -i A=b ls",
    ],
)
def test_wrappers_are_stripped(wrapped):
    assert _argvs(wrapped) == [["ls"]]


def test_xargs_wrapper_is_stripped_with_its_flags():
    assert _argvs("ls | xargs -I {} -n 1 rm {}") == [["ls"], ["rm", "{}"]]


def test_bash_dash_c_recurses_into_the_script():
    assert _argvs("bash -c 'ls && rm -rf x'") == [["ls"], ["rm", "-rf", "x"]]


def test_nested_shell_wrappers_recurse():
    assert ["rm", "x"] in _argvs("sh -c \"bash -c 'rm x'\"")


def test_variable_as_command_is_opaque():
    [seg] = bs.parse("$CMD arg")
    assert seg.opaque_reason


def test_plain_command_is_not_opaque():
    assert bs.parse("ls")[0].opaque_reason == ""


def test_output_redirect_is_recorded_apart_from_argv():
    [seg] = bs.parse("echo hi > out.txt")
    assert seg.argv == ["echo", "hi"] and seg.redirects == ["> out.txt"]


def test_fd_duplication_is_not_a_file_redirect():
    [seg] = bs.parse("make 2>&1")
    assert seg.argv == ["make"] and seg.redirects == []


def test_redirect_to_dev_null_is_recorded():
    [seg] = bs.parse("ls > /dev/null 2>&1")
    assert seg.redirects == ["> /dev/null"]


@pytest.mark.parametrize(
    "broken",
    ["echo 'open", 'echo "open', "echo $(open", "echo `open", "ls (", "echo a\\"],
)
def test_unparseable_commands_raise(broken):
    with pytest.raises(bs.Unparseable):
        bs.parse(broken)


def test_deep_nesting_raises():
    cmd = "ls"
    for _ in range(12):
        cmd = f"bash -c '{cmd}'".replace("'ls'", "ls")
        cmd = "bash -c " + repr(cmd)
    with pytest.raises(bs.Unparseable):
        bs.parse(cmd)


@pytest.mark.parametrize(
    "command",
    [
        "env -S 'curl x'",
        "env --split-string='curl x'",
        "env",
        "time",
        "FOO=1 ls",
        "xargs find . -delete",
        "exec -a x ls",
        "ls ${X:--delete}",
        "echo {a,b}",
        "env --unset=A ls",
        "time -o out ls",
    ],
)
def test_unknowable_command_or_arguments_are_flagged(command):
    segments = bs.parse(command)
    assert any(s.opaque_reason or s.untrusted_reason for s in segments), command


@pytest.mark.parametrize("command", ["ls -la", "git status", "bash script.sh -c x"])
def test_plain_commands_are_not_flagged(command):
    seg = bs.parse(command)[-1]
    assert not seg.opaque_reason and not seg.untrusted_reason


def test_reserved_words_are_stripped():
    assert bs.parse("if true; then rm -rf x; fi")[-1].argv[0] != "then"
    assert [s.argv[0] for s in bs.parse("! rm x")] == ["rm"]


def test_bash_c_keeps_wrapper_redirects():
    assert any(">" in r for r in bs.parse("bash -c 'ls' > out")[0].redirects)


def test_quoted_redirect_target_and_clobber():
    assert bs.parse("ls > 'a b'")[0].redirects == ["> a b"]
    assert bs.parse("ls >| out")[0].redirects == [">| out"]


def test_escaped_heredoc_delimiter_is_unquoted():
    assert [s.argv[0] for s in bs.parse("cat <<\\EOF\nrm -rf x\nEOF\nls")] == [
        "cat",
        "ls",
    ]


def test_substitution_output_in_arguments_is_untrusted():
    assert bs.parse("echo $(date)")[-1].untrusted_reason
