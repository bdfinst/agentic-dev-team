"""A SKILL.md call to a stdin-reading script must not be able to hang.

Several scripts read stdin by default. Run from Claude Code's `Bash` tool with
no input flag and no pipe, stdin is a socket that never reaches EOF and the
call hangs for 600 s. This file scans every shipped `SKILL.md` for such calls.

Scope: fenced blocks tagged `bash`/`sh`/`shell` and inline-code spans (see
`tests/_support/skill_calls.py` for the detection rules). Untagged fences,
plain `python`, and `commands/`, `agents/`, `knowledge/` are not scanned.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT
from tests._support.skill_calls import (
    PLACEHOLDER_TOKEN,
    InputFlag,
    find_calls,
    find_offenders,
    find_offenders_in_files,
    iter_commands,
    split_segments,
    tokenize,
)
from tests._support.stdin_harness import SUBPROCESS_TIMEOUT_SECONDS
from tests._support.stdin_scripts import INPUT_FLAGS, STDIN_SCRIPTS

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
SKILL_FILES = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
BUILD_SKILL = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"

#: Fewer calls than this across the shipped skills means the scan stopped
#: seeing them, not that the skills improved.
MIN_SHIPPED_CALLS = 10

CHANGE_IMPACT = "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/change_impact.py"
CHECKPOINT_ABORT = "$CLAUDE_PLUGIN_ROOT/scripts/checkpoint_abort.py"
REVIEW_CONTEXT_PACK = (
    "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/review_context_pack.py"
)
PY_LAUNCHER = 'sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh"'
FINDING_SIGNATURE = (
    "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/finding_signature.py"
)

#: The architectural-impact paragraph as it read before the fix.
ORIGINAL_BUILD_PARAGRAPH = """\
   **Architectural-impact gate.** The resolver's `lenses` list is narrowed
   further for structural lenses: pipe the checkpoint's diff through
   `skills/code-review/scripts/change_impact.py --files <changed files>` and
   drop any agent in its `skipLenses`.
"""


def fenced(*lines: str, tag: str = "bash", fence: str = "```") -> str:
    return f"Intro.\n\n{fence}{tag}\n" + "\n".join(lines) + f"\n{fence}\n"


def offenders(text: str, name: str = "skills/x/SKILL.md"):
    return find_offenders(name, text, INPUT_FLAGS)


def offending_scripts(text: str) -> list[str]:
    return [offender.script for offender in offenders(text)]


# -- Rejected calls ---------------------------------------------------------


def test_inline_call_without_pipe_or_flag_is_rejected():
    text = (
        "Line one.\n"
        'Lint it: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_close_keyword_lint.py"` now.\n'
    )
    [found] = offenders(text)
    assert (found.file, found.line, found.script) == (
        "skills/x/SKILL.md",
        2,
        "pr_close_keyword_lint.py",
    )


def test_fenced_call_with_an_unrelated_flag_is_rejected():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --files <changed files>')
    [found] = offenders(text)
    assert (found.line, found.script) == (4, "change_impact.py")


def test_pipe_after_the_call_does_not_excuse_it():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --files a.py | jq .')
    [found] = offenders(text)
    assert (found.line, found.script) == (4, "change_impact.py")


def test_each_call_in_one_block_is_judged_alone():
    text = fenced(
        f'python3 "{CHANGE_IMPACT}" --diff-from d.patch',
        f'python3 "{CHANGE_IMPACT}" --files a.py',
    )
    [found] = offenders(text)
    assert (found.line, found.script) == (5, "change_impact.py")


def test_the_original_build_paragraph_is_rejected():
    [found] = offenders(ORIGINAL_BUILD_PARAGRAPH)
    assert found.script == "change_impact.py"


def test_flag_must_match_as_a_whole_token():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --diff-fromage d.patch')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


def test_direct_path_execution_in_a_fence_is_a_call():
    text = fenced(f'"{CHANGE_IMPACT}" --files a.py')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


def test_launcher_form_without_pipe_or_flag_is_rejected():
    text = fenced(f'{PY_LAUNCHER} "{CHANGE_IMPACT}" --files a.py')
    [found] = offenders(text)
    assert (found.line, found.script) == (4, "change_impact.py")


def test_bash_launcher_form_is_rejected():
    text = fenced(f'bash "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "{CHANGE_IMPACT}" --files a.py')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


LAUNCHERS = [
    pytest.param("python3", id="python3"),
    pytest.param(PY_LAUNCHER, id="launcher"),
]


@pytest.mark.parametrize("launcher", LAUNCHERS)
@pytest.mark.parametrize(
    "prefix", ["(", "$(", "then ", "do ", "time ", "else ", "if ", "! ", "{ "]
)
def test_call_behind_a_leading_shell_word_is_rejected(prefix, launcher):
    text = fenced(f'{prefix}{launcher} "{CHANGE_IMPACT}" --files a.py')
    assert offending_scripts(text) == ["change_impact.py"]


@pytest.mark.parametrize(
    ("mode_args", "flag"),
    [
        pytest.param("--mode abort", "--from", id="abort-mode-with-the-outcome-flag"),
        pytest.param("", "--from", id="default-mode-with-the-outcome-flag"),
        pytest.param(
            "--mode outcome",
            "--cheap-results-from",
            id="outcome-mode-with-the-abort-flag",
        ),
        pytest.param(
            "--mode merge",
            "--cheap-results-from",
            id="merge-mode-with-the-abort-flag",
        ),
    ],
)
def test_checkpoint_abort_with_the_flag_of_another_mode_is_rejected(mode_args, flag):
    text = fenced(f'python3 "{CHECKPOINT_ABORT}" {mode_args} {flag} x.json')
    assert offending_scripts(text) == ["checkpoint_abort.py"]


@pytest.mark.parametrize("flag", ["--diff-from -", "--diff-from=-"])
def test_a_flag_whose_value_is_dash_reads_stdin_and_is_rejected(flag):
    text = fenced(f'python3 "{CHANGE_IMPACT}" {flag}')
    assert offending_scripts(text) == ["change_impact.py"]


@pytest.mark.parametrize(
    "separator",
    [
        pytest.param("&&", id="and"),
        pytest.param(";", id="semicolon"),
        pytest.param("||", id="or"),
        pytest.param("&", id="background"),
    ],
)
def test_call_after_a_separator_is_judged_on_its_own_segment(separator):
    text = fenced(f'git diff {separator} python3 "{CHANGE_IMPACT}" --files a.py')
    assert offending_scripts(text) == ["change_impact.py"]


def test_call_behind_an_env_assignment_is_rejected():
    text = fenced(f'FOO=1 python3 "{CHANGE_IMPACT}" --files a.py')
    assert offending_scripts(text) == ["change_impact.py"]


def test_call_behind_an_interpreter_option_is_rejected():
    text = fenced(f'python3 -u "{CHANGE_IMPACT}" --files a.py')
    assert offending_scripts(text) == ["change_impact.py"]


def test_a_here_string_passes_and_does_not_start_a_heredoc_body():
    text = fenced(
        f'python3 "{FINDING_SIGNATURE}" --round 1 <<< "[]"',
        f'python3 "{FINDING_SIGNATURE}" --round 2',
    )
    [found] = offenders(text)
    assert (found.line, found.script) == (5, "finding_signature.py")


def test_an_unbalanced_quote_falls_back_to_a_plain_split_and_still_finds_the_call():
    text = fenced(f"echo don't && python3 \"{CHANGE_IMPACT}\" --files a.py")
    assert offending_scripts(text) == ["change_impact.py"]


def test_an_unbalanced_quote_does_not_hide_the_input_flag():
    text = fenced(f"echo don't && python3 \"{CHANGE_IMPACT}\" --diff-from d.patch")
    assert offenders(text) == []


def test_tokenize_splits_an_unbalanced_quote_on_whitespace():
    assert tokenize("it's here") == ["it", "s", "here"]


def test_a_flag_inside_a_comment_does_not_excuse_the_call():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --files a.py # --diff-from d.patch')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


# -- Accepted calls ---------------------------------------------------------


def test_call_with_its_input_flag_passes():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --diff-from <diff-file>')
    assert offenders(text) == []


def test_flag_with_equals_value_passes():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --diff-from=d.patch')
    assert offenders(text) == []


def test_inline_call_with_a_file_placeholder_for_the_flag_passes():
    text = (
        "Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint_abort.py "
        "--mode merge --from <merge-input.json>`.\n"
    )
    assert offenders(text) == []


@pytest.mark.parametrize(
    ("mode_args", "flag"),
    [
        pytest.param("", "--cheap-results-from", id="default-mode"),
        pytest.param("--mode abort", "--cheap-results-from", id="abort-mode"),
        pytest.param("--mode outcome", "--from", id="outcome-mode"),
        pytest.param("--mode merge", "--from", id="merge-mode"),
        pytest.param("--mode=merge", "--from", id="merge-mode-with-equals"),
    ],
)
def test_checkpoint_abort_passes_with_the_flag_for_its_mode(mode_args, flag):
    text = fenced(f'python3 "{CHECKPOINT_ABORT}" {mode_args} {flag} x.json')
    assert offenders(text) == []


def test_review_context_pack_name_status_file_never_reads_stdin():
    text = fenced(f'python3 "{REVIEW_CONTEXT_PACK}" --name-status-from changes.txt')
    assert offenders(text) == []


def test_review_context_pack_name_status_dash_reads_stdin_and_is_rejected():
    text = fenced(f'python3 "{REVIEW_CONTEXT_PACK}" --name-status-from -')
    assert [o.script for o in offenders(text)] == ["review_context_pack.py"]


def test_piped_launcher_form_passes():
    text = fenced(
        "git diff --name-status \\",
        f'  | {PY_LAUNCHER} "{REVIEW_CONTEXT_PACK}" --base HEAD',
    )
    assert offenders(text) == []


def test_flag_before_a_trailing_comment_passes():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --diff-from d.patch # not "--files"')
    assert offenders(text) == []


def test_fenced_call_with_a_pipe_passes():
    text = fenced(f'git diff | python3 "{CHANGE_IMPACT}" --files a.py')
    assert offenders(text) == []


def test_pipe_on_a_continuation_line_passes():
    text = fenced("git diff \\", f'  | python3 "{CHANGE_IMPACT}" --files a.py')
    assert offenders(text) == []


def test_pipe_ending_the_previous_line_passes():
    text = fenced("git diff |", f'python3 "{CHANGE_IMPACT}" --files a.py')
    assert offenders(text) == []


def test_pipe_inside_quotes_is_not_a_pipe():
    text = fenced(f'echo "a | b" && python3 "{CHANGE_IMPACT}" --files a.py')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


def test_input_redirect_passes():
    text = fenced(f'python3 "{FINDING_SIGNATURE}" --round 1 < findings.json')
    assert offenders(text) == []


def test_heredoc_passes_and_its_body_is_not_scanned():
    text = fenced(
        f"python3 \"{FINDING_SIGNATURE}\" --round 1 <<'EOF'",
        "[]",
        f'python3 "{FINDING_SIGNATURE}" --round 2',
        "EOF",
    )
    assert offenders(text) == []


# -- Not calls --------------------------------------------------------------


def test_a_bare_mention_is_not_a_call():
    text = (
        "See change_impact.py for details.\n"
        "The script `change_impact.py` classifies a diff.\n"
        "Opt in via `scripts/review_context_pack.py`, off by default.\n"
    )
    assert offenders(text) == []


def test_untagged_fences_and_plain_python_are_ignored():
    text = (
        "```\n"
        f'python3 "{CHANGE_IMPACT}" --files a.py\n'
        "```\n"
        "\n"
        "```bash\n"
        f'python "{CHANGE_IMPACT}" --files a.py\n'
        "```\n"
    )
    assert offenders(text) == []


def test_non_shell_fence_tags_are_ignored():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --files a.py', tag="python")
    assert offenders(text) == []


@pytest.mark.parametrize("tag", ["sh", "shell", "bash"])
def test_shell_fence_tags_are_scanned(tag):
    text = fenced(f'python3 "{CHANGE_IMPACT}" --files a.py', tag=tag)
    assert offending_scripts(text) == ["change_impact.py"]


CALL_WITHOUT_INPUT = f'python3 "{CHANGE_IMPACT}" --files a.py'


def test_tilde_fences_are_scanned():
    text = fenced(CALL_WITHOUT_INPUT, fence="~~~")
    assert offending_scripts(text) == ["change_impact.py"]


@pytest.mark.parametrize(
    ("opening", "not_a_closer"),
    [
        pytest.param("````bash", "```", id="a-shorter-fence"),
        pytest.param("```bash", "~~~", id="a-fence-of-another-character"),
        pytest.param("```bash", "```python", id="a-fence-with-an-info-string"),
    ],
)
def test_a_line_that_does_not_close_the_fence_leaves_its_body_scanned(
    opening, not_a_closer
):
    text = f"{opening}\n{not_a_closer}\n{CALL_WITHOUT_INPUT}\n````\n"
    assert offending_scripts(text) == ["change_impact.py"]


@pytest.mark.parametrize(
    ("opening", "closer"),
    [
        pytest.param("```bash", "```", id="an-equal-fence"),
        pytest.param("```bash", "````", id="a-longer-fence"),
        pytest.param("~~~bash", "~~~", id="tildes"),
    ],
)
def test_text_after_the_closing_fence_is_not_scanned(opening, closer):
    text = f"{opening}\n{CALL_WITHOUT_INPUT}\n{closer}\n{CALL_WITHOUT_INPUT}\n"
    assert offending_scripts(text) == ["change_impact.py"]


def test_a_fence_that_never_closes_still_has_its_calls_scanned():
    text = f"```bash\n{CALL_WITHOUT_INPUT}\n"
    assert offending_scripts(text) == ["change_impact.py"]


# -- The shipped skills -----------------------------------------------------


def test_shipped_skills_contain_no_hanging_call():
    found = find_offenders_in_files(SKILL_FILES, INPUT_FLAGS)
    assert SKILL_FILES, "no SKILL.md files found"
    assert found == [], "\n".join(
        f"{Path(o.file).relative_to(REPO_ROOT).as_posix()}:{o.line}: {o.script}: {o.command_text}"
        for o in found
    )


def test_scan_finds_the_calls_the_shipped_skills_make():
    calls = [
        call
        for path in SKILL_FILES
        for call, _safe in find_calls(str(path), path.read_text(encoding="utf-8"), INPUT_FLAGS)
    ]
    assert len(calls) >= MIN_SHIPPED_CALLS
    assert {"review_context_pack.py", "checkpoint_abort.py"} <= {c.script for c in calls}


def _gate_section() -> list[str]:
    """Lines of the 'Architectural-impact gate' paragraph, up to the next
    bold-led paragraph, numbered item or heading."""
    lines = BUILD_SKILL.read_text(encoding="utf-8").splitlines()
    starts = [
        i for i, line in enumerate(lines) if "**Architectural-impact gate.**" in line
    ]
    assert starts, f"no '**Architectural-impact gate.**' paragraph in {BUILD_SKILL}"
    start = starts[0]
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"^\s{0,3}(\*\*|\d+\. |#)", lines[i]):
            end = i
            break
    return lines[start:end]


def test_architectural_impact_gate_shows_one_piped_bash_command():
    section = "\n".join(_gate_section())
    blocks = re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)
    piped = [
        block
        for block in blocks
        if re.search(
            r"git .* diff .*\| *python3 .*change_impact\.py", block.replace("\\\n", " ")
        )
    ]
    assert len(piped) == 1
    mentions = [line for line in section.splitlines() if "change_impact.py" in line]
    in_block = [line for line in piped[0].splitlines() if "change_impact.py" in line]
    assert len(mentions) == len(in_block), (
        "change_impact.py mentioned outside the bash block"
    )


#: The documented call, run on a small diff that touches no import, file
#: layout, manifest, or public symbol.
SMALL_DIFF = (
    "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"
)


def _documented_change_impact_argv() -> list[str]:
    """The change_impact.py segment of the build skill's documented command,
    with `python3`, the plugin root, and the file placeholder made concrete."""
    commands = [
        c
        for c in iter_commands(str(BUILD_SKILL), "\n".join(_gate_section()))
        if "change_impact.py" in c.command_text
    ]
    [command] = commands
    segment = next(
        seg
        for _, seg in split_segments(tokenize(command.command_text))
        if any("change_impact.py" in word for word in seg)
    )
    assert segment[0] == "python3"
    expand = {"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)}
    argv = []
    for word in segment:
        word = re.sub(
            r"\$\{?(\w+)\}?", lambda m: expand.get(m.group(1), m.group(0)), word
        )
        argv.append("x.py" if word == PLACEHOLDER_TOKEN else word)
    argv[0] = sys.executable
    return argv


def test_documented_change_impact_call_reads_the_piped_diff():
    argv = _documented_change_impact_argv()
    assert argv[0] == sys.executable
    assert argv[1].endswith("skills/code-review/scripts/change_impact.py")
    assert "--diff-from" not in argv
    result = subprocess.run(
        argv,
        input=SMALL_DIFF,
        capture_output=True,
        text=True,
        check=False,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
    assert result.returncode == 0, result.stderr
    result_json = json.loads(result.stdout)
    assert result_json["hasArchitecturalImpact"] is False
    assert result_json["reason"] != "diff-not-parseable-assuming-impact"


# -- Table and guard agree --------------------------------------------------


def test_checked_scripts_match_the_scripts_that_import_the_guard():
    importers = {
        path.relative_to(PLUGIN_ROOT).as_posix()
        for path in PLUGIN_ROOT.rglob("*.py")
        if path.name != "stdin_guard.py"
        and "tests" not in path.relative_to(PLUGIN_ROOT).parts
        and re.search(
            r"^\s*(from\s+stdin_guard\s+import|import\s+stdin_guard)\b",
            path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    }
    assert {row.script for row in STDIN_SCRIPTS} == importers


def test_every_row_flag_is_in_the_input_flag_table():
    table = {(rule.script, rule.flag) for rule in INPUT_FLAGS}
    expected = {
        (row.script.rsplit("/", 1)[-1], row.flag)
        for row in STDIN_SCRIPTS
        if row.needs_flag
    }
    assert expected <= table


# -- Scripts that read stdin only on an explicit `-` -------------------------

DASH_RULE = InputFlag("dash.py", "--in", stdin_only_on_dash=True)
DASH_CALL = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dash.py"'


@pytest.mark.parametrize(
    ("args", "safe"),
    [
        ("--other x", True),
        ("--in file.txt", True),
        ("--in=file.txt", True),
        ("--in -", False),
        ("--in=-", False),
        ("--in - < file.txt", True),
    ],
)
def test_dash_only_script_is_unsafe_only_when_it_is_given_a_dash(args, safe):
    text = fenced(f"{DASH_CALL} {args}")

    assert (find_offenders("skills/x/SKILL.md", text, [DASH_RULE]) == []) is safe


def test_dash_only_script_with_a_dash_is_safe_when_piped_to():
    text = fenced(f"cat a.txt | {DASH_CALL} --in -")

    assert find_offenders("skills/x/SKILL.md", text, [DASH_RULE]) == []


def test_every_dash_only_row_names_its_flag_with_a_dash_as_stdin_argv():
    dash_only = {
        (rule.script, rule.flag) for rule in INPUT_FLAGS if rule.stdin_only_on_dash
    }
    rows = {
        (row.script.rsplit("/", 1)[-1], row.flag): row.stdin_argv
        for row in STDIN_SCRIPTS
        if row.stdin_argv
    }

    assert set(rows) <= dash_only
    assert all(argv == (flag, "-") for (_, flag), argv in rows.items())
