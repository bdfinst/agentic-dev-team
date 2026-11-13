"""A SKILL.md call to a stdin-reading script must not be able to hang.

Eight scripts read stdin by default. Run from Claude Code's `Bash` tool with
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

from _repo_root import REPO_ROOT

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _support.skill_calls import (
    find_offenders,
    find_offenders_in_files,
    iter_commands,
    split_segments,
    tokenize,
)
from _support.stdin_scripts import STDIN_SCRIPTS

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
SKILL_FILES = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
BUILD_SKILL = PLUGIN_ROOT / "skills" / "build" / "SKILL.md"

#: `checkpoint_abort.py --mode outcome|merge` reads stdin unless `--from` is
#: given; the table holds only the `--mode abort` flag.
EXTRA_INPUT_FLAGS = (("checkpoint_abort.py", "--from"),)

SCRIPTS = [
    (row.script.rsplit("/", 1)[-1], row.flag) for row in STDIN_SCRIPTS if row.needs_flag
] + list(EXTRA_INPUT_FLAGS)

CHANGE_IMPACT = "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/change_impact.py"
FINDING_SIG = "$CLAUDE_PLUGIN_ROOT/skills/code-review/scripts/finding_signature.py"

#: The architectural-impact paragraph as it read before the fix (#2304).
ORIGINAL_BUILD_PARAGRAPH = """\
   **Architectural-impact gate.** The resolver's `lenses` list is narrowed
   further for structural lenses: pipe the checkpoint's diff through
   `skills/code-review/scripts/change_impact.py --files <changed files>` and
   drop any agent in its `skipLenses`.
"""


def fenced(*lines: str, tag: str = "bash") -> str:
    return f"Intro.\n\n```{tag}\n" + "\n".join(lines) + "\n```\n"


def offenders(text: str, name: str = "skills/x/SKILL.md"):
    return find_offenders(name, text, SCRIPTS)


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


def test_call_after_and_and_is_judged_on_its_own_segment():
    text = fenced(f'git diff && python3 "{CHANGE_IMPACT}" --files a.py')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


def test_direct_path_execution_in_a_fence_is_a_call():
    text = fenced(f'"{CHANGE_IMPACT}" --files a.py')
    assert [o.script for o in offenders(text)] == ["change_impact.py"]


# -- Accepted calls ---------------------------------------------------------


def test_call_with_its_input_flag_passes():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --diff-from <diff-file>')
    assert offenders(text) == []


def test_flag_with_equals_value_passes():
    text = fenced(f'python3 "{CHANGE_IMPACT}" --diff-from=d.patch')
    assert offenders(text) == []


def test_checkpoint_abort_from_flag_passes_for_outcome_and_merge_modes():
    text = 'Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint_abort.py --mode merge --from <JSON: {"a": []}>`.\n'
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
    text = fenced(f'python3 "{FINDING_SIG}" --round 1 < findings.json')
    assert offenders(text) == []


def test_heredoc_passes_and_its_body_is_not_scanned():
    text = fenced(
        f"python3 \"{FINDING_SIG}\" --round 1 <<'EOF'",
        "[]",
        f'python3 "{FINDING_SIG}" --round 2',
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


def test_sh_and_shell_fence_tags_are_scanned():
    for tag in ("sh", "shell"):
        text = fenced(f'python3 "{CHANGE_IMPACT}" --files a.py', tag=tag)
        assert [o.script for o in offenders(text)] == ["change_impact.py"], tag


# -- The shipped skills -----------------------------------------------------


def test_shipped_skills_contain_no_hanging_call():
    found = find_offenders_in_files(SKILL_FILES, SCRIPTS)
    assert SKILL_FILES, "no SKILL.md files found"
    assert found == [], "\n".join(
        f"{Path(o.file).relative_to(REPO_ROOT)}:{o.line}: {o.script}: {o.command_text}"
        for o in found
    )


def _gate_section() -> list[str]:
    """Lines of the 'Architectural-impact gate' paragraph, up to the next
    bold-led paragraph, numbered item or heading."""
    lines = BUILD_SKILL.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines) if "**Architectural-impact gate.**" in line
    )
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
SMALL_DIFF_RESULT = {
    "hasArchitecturalImpact": False,
    "reason": None,
    "signals": [],
    "skipLenses": ["arch-review", "concurrency-review"],
}


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
        argv.append("x.py" if word == "PLACEHOLDER" else word)
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
        timeout=30,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == SMALL_DIFF_RESULT


# -- Table and guard agree --------------------------------------------------


def test_checked_scripts_match_the_scripts_that_import_the_guard():
    importers = {
        str(path.relative_to(PLUGIN_ROOT))
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
