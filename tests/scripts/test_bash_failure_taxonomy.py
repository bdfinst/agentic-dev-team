"""Unit tests for scripts/bash_failure_taxonomy.py Steps 1.1-1.3 (issue #2038):
self-contained Bash tool_use/tool_result pairing, the six-bucket failure
classifier, and corpus distribution + excluded-denominator reporting.

Step 1.1 TEST list (self-contained pairing):
(a) a synthetic Bash tool_use + failing tool_result pair yields both texts
    together, (b) a successful Bash call is excluded, (c) a non-Bash tool's
    error is excluded, (d) an orphaned tool_result is reported unpaired
    rather than matched to an unrelated command, (e) a transcript file with
    one well-formed pair plus one corrupt (non-JSON) line still yields the
    well-formed pair and does not raise, (f) the script's
    `argparse.ArgumentParser` exposes exactly the attribute names
    `resolve_transcripts`/`resolve_all_transcripts` require, (g) a
    transcript line that decodes as valid JSON but is a non-dict value, or
    a dict missing `type`/`content`/`tool_use_id`, is skipped without
    raising -- mirroring `session_extract.py::_read_synced_records`'s
    `isinstance(rec, dict)` guard.

Step 1.2 TEST list (`classify(command, error_text) -> str`): table-driven
coverage with at least 2 real-shaped examples per class (all six),
including timeout and genuine-command-error; the tool-not-present vs.
working-directory disambiguation on an overlapping "No such file or
directory" string; a bare-exit-code-only string asserting `unclassified`
(not `genuine-command-error`); a truly unclassifiable string; and a
boundary case pinning exactly which side of the ">10 character" stderr
threshold a 10-character and an 11-character message fall on.

Step 1.3 TEST list (`build_distribution`/`build_distribution_from_corpus`):
a fixture corpus with a known mix of all 6 buckets asserting counts and
that the excluded classes (`timeout`, `genuine-command-error`) are absent
from the addressable-percentage denominator; a second fixture where the
denominator is zero (every error in an excluded class, and separately an
empty corpus) asserting no exception and a well-defined percentage; a
negative privacy test asserting a distinctive marker string never appears
in the serialized JSON distribution; and a docstring-content test asserting
the module docstring names both excluded classes alongside
"excluded"/"denominator" language.

No import from `session_extract.py` beyond the two path-discovery
functions the plan names as reusable -- see the module docstring under
test for the privacy-contract rationale.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bash_failure_taxonomy as bft


def _assistant(blocks: list[dict]) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def _user(blocks: list[dict]) -> dict:
    return {"type": "user", "message": {"role": "user", "content": blocks}}


def _tool_use(tool_id: str, name: str, command: str | None = None) -> dict:
    block = {"type": "tool_use", "id": tool_id, "name": name}
    if command is not None:
        block["input"] = {"command": command}
    return block


def _tool_result(tool_id: str, text: str, *, is_error: bool) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_id,
        "content": text,
        "is_error": is_error,
    }


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) a synthetic Bash tool_use + failing tool_result pair yields both texts
# ---------------------------------------------------------------------------


def test_bash_error_paired_with_originating_command(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Bash", "grep foo bar.txt")]),
            _user([_tool_result("t1", "grep: bar.txt: No such file or directory", is_error=True)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.command == "grep foo bar.txt"
    assert pair.error_text == "grep: bar.txt: No such file or directory"
    assert pair.tool_use_id == "t1"
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (b) a successful Bash call is excluded
# ---------------------------------------------------------------------------


def test_successful_bash_call_excluded(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Bash", "ls")]),
            _user([_tool_result("t1", "file1\nfile2", is_error=False)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert result.pairs == []
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (c) a non-Bash tool's error is excluded
# ---------------------------------------------------------------------------


def test_non_bash_tool_error_excluded(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Edit")]),
            _user([_tool_result("t1", "old_string not found in file", is_error=True)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert result.pairs == []
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (d) an orphaned tool_result is reported unpaired, not matched to an
#     unrelated command
# ---------------------------------------------------------------------------


def test_orphaned_tool_result_reported_unpaired(tmp_path):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            # An unrelated, successfully-paired Bash command earlier in the
            # transcript -- the orphaned result below must NOT be matched to
            # this command's text.
            _assistant([_tool_use("t1", "Bash", "echo hello")]),
            _user([_tool_result("t1", "hello", is_error=False)]),
            # tool_use_id "t99" never appears as a tool_use in this
            # transcript (truncated/orphaned).
            _user([_tool_result("t99", "some error with no origin", is_error=True)]),
        ],
    )

    result = bft.pair_bash_errors([path])

    assert result.pairs == []
    assert len(result.unpaired) == 1
    assert result.unpaired[0].tool_use_id == "t99"
    assert result.unpaired[0].error_text == "some error with no origin"


# ---------------------------------------------------------------------------
# (e) a corrupt (non-JSON) line does not abort the run
# ---------------------------------------------------------------------------


def test_corrupt_json_line_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    good_pair = [
        _assistant([_tool_use("t1", "Bash", "cat missing.txt")]),
        _user([_tool_result("t1", "cat: missing.txt: No such file or directory", is_error=True)]),
    ]
    lines = [json.dumps(r) for r in good_pair]
    lines.insert(1, "{not valid json,,,")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "cat missing.txt"
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# (f) argparse.ArgumentParser attribute-name contract with
#     resolve_transcripts/resolve_all_transcripts
# ---------------------------------------------------------------------------


def test_arg_parser_exposes_attributes_resolve_functions_require(tmp_path):
    empty_root = tmp_path / "empty-projects-root"
    empty_root.mkdir()

    parser = bft.build_arg_parser()
    args = parser.parse_args(["--projects-root", str(empty_root)])

    # Must not raise AttributeError -- these functions duck-type on
    # args.transcript / args.project_dir / args.projects_root / args.cwd.
    assert bft.resolve_transcripts(args) == []
    assert bft.resolve_all_transcripts(args) == []


def test_arg_parser_transcript_flag_is_repeatable_and_attribute_named_transcript(tmp_path):
    transcript = tmp_path / "one.jsonl"
    _write_transcript(transcript, [])

    parser = bft.build_arg_parser()
    args = parser.parse_args(["--transcript", str(transcript)])

    assert args.transcript == [str(transcript)]
    assert bft.resolve_transcripts(args) == [Path(transcript)]


# ---------------------------------------------------------------------------
# (g) a malformed-but-JSON-valid record (non-dict, or a dict missing
#     type/content/tool_use_id) is skipped without raising
# ---------------------------------------------------------------------------


def test_non_dict_top_level_record_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    good_pair = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    lines = [json.dumps(r) for r in good_pair]
    # A record that decodes as valid JSON but is not a dict (a bare array).
    lines.insert(1, json.dumps([1, 2, 3]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# Test-review coverage gaps
# ---------------------------------------------------------------------------


def test_tool_result_content_as_list_of_content_blocks(tmp_path):
    # The real Claude Code transcript wire format for tool_result content is
    # a LIST of content blocks (`[{"type": "text", "text": "..."}]`), not a
    # plain string -- this shape had zero coverage in the pairing tests.
    path = tmp_path / "session.jsonl"
    records = [
        _assistant([_tool_use("t1", "Bash", "cat missing.txt")]),
        _user(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "is_error": True,
                    "content": [{"type": "text", "text": "cat: missing.txt: No such file or directory"}],
                }
            ]
        ),
    ]
    _write_transcript(path, records)

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "cat missing.txt"
    assert result.pairs[0].error_text == "cat: missing.txt: No such file or directory"
    assert result.unpaired == []


def test_message_field_non_dict_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    good_pair = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    lines = [json.dumps(r) for r in good_pair]
    # A record whose "message" field is not a dict.
    lines.insert(1, json.dumps({"type": "user", "message": "not-a-dict"}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []


def test_content_field_non_list_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    good_pair = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    lines = [json.dumps(r) for r in good_pair]
    # A record whose "message.content" field is not a list.
    lines.insert(1, json.dumps({"type": "user", "message": {"role": "user", "content": "not-a-list"}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []


def test_non_dict_item_inside_content_list_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        # A content list containing a non-dict item alongside the real
        # tool_result block.
        _user(["not-a-dict-block", _tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    _write_transcript(path, records)

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []


def test_pair_bash_errors_nonexistent_file_returns_empty_without_raising(tmp_path):
    missing = tmp_path / "does-not-exist.jsonl"

    result = bft.pair_bash_errors([missing])

    assert result.pairs == []
    assert result.unpaired == []


def test_iter_json_records_nonexistent_file_yields_nothing(tmp_path):
    missing = tmp_path / "does-not-exist.jsonl"

    assert list(bft._iter_json_records(missing)) == []


def test_classify_bare_exit_code_line_followed_by_real_stderr_is_genuine_error():
    # A bare exit-code line stripped away must not swallow real,
    # descriptive multi-line stderr text that follows it -- the combination
    # should still classify as genuine-command-error, not unclassified.
    error_text = "1\nfatal: not a git repository (or any of the parent directories): .git"

    assert bft.classify("git status", error_text) == "genuine-command-error"


# ---------------------------------------------------------------------------
# Security review: raw text must never leak through repr() (privacy contract)
# ---------------------------------------------------------------------------


def test_bash_error_pair_repr_never_contains_command_or_error_text():
    marker_command = "echo REPR-MARKER-COMMAND-XYZ"
    marker_error = "REPR-MARKER-ERROR-XYZ: command not found"
    pair = bft.BashErrorPair(tool_use_id="t1", command=marker_command, error_text=marker_error)

    rendered = repr(pair)

    assert "REPR-MARKER-COMMAND-XYZ" not in rendered
    assert "REPR-MARKER-ERROR-XYZ" not in rendered


def test_module_import_appends_not_prepends_scripts_dir_and_does_not_duplicate():
    # sys.path.insert(0, ...) at import time would place scripts/ ahead of
    # stdlib for the whole process; the fix appends (guarded on membership)
    # so stdlib always wins and re-import doesn't duplicate the entry.
    #
    # Loaded via importlib.util.spec_from_file_location in a fresh
    # subprocess, deliberately WITHOUT pre-adding scripts/ to sys.path --
    # this is the one scenario that actually exercises the module's own
    # guard (the test harness's own sys.path.insert(0, ...) at the top of
    # this file, and Python's implicit "script's own dir" entry when run
    # directly, both already have scripts/ on sys.path *before* the module
    # body runs, which would make the guard a no-op either way).
    here = str((REPO_ROOT / "scripts" / "bash_failure_taxonomy.py").resolve())
    scripts_dir = str((REPO_ROOT / "scripts").resolve())
    script = f"""
import sys, importlib.util
assert {scripts_dir!r} not in sys.path

def load():
    spec = importlib.util.spec_from_file_location("bft_isolated", {here!r})
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bft_isolated"] = mod
    spec.loader.exec_module(mod)
    return mod

sentinel = "/definitely-not-a-real-dir-ahead-of-scripts"
sys.path.insert(0, sentinel)

load()
count_1 = sys.path.count({scripts_dir!r})
index_1 = sys.path.index({scripts_dir!r})
sentinel_index = sys.path.index(sentinel)

load()
count_2 = sys.path.count({scripts_dir!r})

print(count_1, index_1 > sentinel_index, count_2)
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    count_1, appended_after_sentinel, count_2 = result.stdout.split()
    assert count_1 == "1"
    assert appended_after_sentinel == "True", (
        "scripts/ must be appended (after existing entries), not inserted at index 0"
    )
    assert count_2 == "1", "re-import must not duplicate the scripts/ sys.path entry"


def test_unpaired_tool_result_repr_never_contains_error_text():
    marker_error = "REPR-MARKER-UNPAIRED-XYZ: something failed"
    unpaired = bft.UnpairedToolResult(tool_use_id="t99", error_text=marker_error)

    rendered = repr(unpaired)

    assert "REPR-MARKER-UNPAIRED-XYZ" not in rendered


# ---------------------------------------------------------------------------
# Step 1.2: six-bucket classifier core
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "error_text", "expected"),
    [
        # -- quoting: unbalanced quotes / shell syntax error -----------------
        (
            "echo 'unterminated",
            "bash: -c: line 1: unexpected EOF while looking for matching quote",
            "quoting",
        ),
        (
            "grep 'foo bar.txt",
            "sh: 1: Syntax error: Unterminated quoted string",
            "quoting",
        ),
        # -- tool-not-present: PATH lookup failure on the command itself -----
        (
            "foobarbaz --version",
            "bash: foobarbaz: command not found",
            "tool-not-present",
        ),
        (
            "widget --help",
            "sh: 1: widget: not found",
            "tool-not-present",
        ),
        # -- working-directory: cd failure, or a missing-file argument -------
        (
            "cat bar.txt",
            "cat: bar.txt: No such file or directory",
            "working-directory",
        ),
        (
            "cd ./nonexistent-dir",
            "bash: cd: ./nonexistent-dir: No such file or directory",
            "working-directory",
        ),
        # -- timeout -----------------------------------------------------------
        (
            "sleep 300",
            "Command timed out after 120000ms",
            "timeout",
        ),
        (
            "curl https://example.com",
            "curl: (28) Operation timed out after 30000 milliseconds",
            "timeout",
        ),
        # -- genuine-command-error: well-formed, descriptive stderr ----------
        (
            "git status",
            "fatal: not a git repository (or any of the parent directories): .git",
            "genuine-command-error",
        ),
        (
            "npm run build",
            "npm ERR! missing script: build",
            "genuine-command-error",
        ),
    ],
)
def test_classify_two_real_shaped_examples_per_class(command, error_text, expected):
    assert bft.classify(command, error_text) == expected


def test_classify_disambiguates_tool_not_present_from_working_directory():
    # "No such file or directory" for a relative-path invocation of a
    # binary that also does not exist on PATH -- the missing token IS the
    # invoked command itself, so tool-not-present takes precedence over
    # working-directory even though the phrasing overlaps with an
    # argument-path failure.
    command = "./missing-tool arg.txt"
    error_text = "bash: ./missing-tool: No such file or directory"

    assert bft.classify(command, error_text) == "tool-not-present"


def test_classify_compound_command_attributes_to_the_last_sub_command():
    """Backstop review finding (#2038/#2039 checkpoint): `classify()` used to
    tokenize the WHOLE command line, so a `&&`-chain's first sub-command was
    always treated as "the invoked binary" and every later token -- including
    a later sub-command's own binary name -- as "its argument". Here `cd`
    (the first sub-command) succeeds; `./missing-tool` (the second, and the
    one that actually produced the error) genuinely does not exist. Before
    the fix this misclassified as `working-directory` purely because the
    command happened to start with `cd`; it must be `tool-not-present`."""
    command = "cd /tmp && ./missing-tool --flag"
    error_text = "bash: ./missing-tool: No such file or directory"

    assert bft.classify(command, error_text) == "tool-not-present"


def test_classify_compound_command_working_directory_argument_still_works():
    """The other half of the same fix: a missing-argument error for a
    resolvable LAST sub-command in a chain must still land in
    `working-directory`, matching the single-command case -- the fix must
    not simply flip every compound command to `tool-not-present`."""
    command = "cd /tmp && cat missing.txt"
    error_text = "cat: missing.txt: No such file or directory"

    assert bft.classify(command, error_text) == "working-directory"


def test_classify_compound_command_attributes_to_an_earlier_sub_command_too():
    """/pr gate finding: a first fix attempt keyed off only the LAST shell
    segment, which just moved the same bug to the mirror case -- `&&` means
    `rm` never runs when `cat` fails first, so the FAILING sub-command here
    is the FIRST one, not the last. `_invoked_binaries`/`_all_arguments`
    must check every segment in the chain, not pick one end of it."""
    command = "cat missing.txt && rm -rf /tmp/foo"
    error_text = "cat: missing.txt: No such file or directory"

    assert bft.classify(command, error_text) == "working-directory"


def test_classify_bare_exit_code_only_is_unclassified_not_genuine_error():
    assert bft.classify("false", "1") == "unclassified"


def test_classify_truly_unclassifiable_string_is_unclassified():
    assert bft.classify("mytool --flag", "???") == "unclassified"


@pytest.mark.parametrize(
    ("stderr_text", "expected"),
    [
        ("z" * 10, "unclassified"),
        ("z" * 11, "genuine-command-error"),
    ],
)
def test_classify_genuine_command_error_threshold_boundary(stderr_text, expected):
    assert bft.classify("some-tool --flag", stderr_text) == expected


# ---------------------------------------------------------------------------
# Review-correction regressions (code-review pass on Step 1.2)
# ---------------------------------------------------------------------------


def test_classify_generic_parser_syntax_error_is_not_quoting():
    # A bare "unexpected token" is a generic parser-error phrase used by
    # Node/V8, TypeScript, and many other non-shell tools -- it must not be
    # treated as a bash quoting signature just because the two phrasings
    # overlap. Bash's own quoting errors use the more specific
    # "syntax error near unexpected token" phrasing, which stays covered.
    command = "node build.js"
    error_text = "SyntaxError: Unexpected token '}'"

    assert bft.classify(command, error_text) == "genuine-command-error"


def test_classify_tool_not_present_with_quoted_env_assignment_prefix():
    # A quoted env-var assignment containing a space (`VAR="a b"`) must not
    # corrupt invoked-binary tokenization -- naive whitespace splitting
    # mis-tokenizes it into fragments ('VAR="a', 'b"'), picking the wrong
    # "invoked binary" and corrupting the tool-not-present vs.
    # working-directory disambiguation.
    command = 'VAR="a b" ./mytool arg.txt'
    error_text = "bash: ./mytool: No such file or directory"

    assert bft.classify(command, error_text) == "tool-not-present"


def test_classify_truncates_error_text_before_matching():
    # A classification signal placed beyond _MAX_ERROR_TEXT_LEN characters
    # must not be seen -- classify() truncates error_text before any regex
    # runs (ReDoS-bounding fix). Without truncation this signal (a real
    # "No such file or directory" naming the command's own argument) would
    # classify as working-directory; with truncation it falls out of view
    # entirely and the truncated filler-only prefix falls back to
    # genuine-command-error.
    command = "grep bar.txt"
    filler = "b" * bft._MAX_ERROR_TEXT_LEN
    error_text = f"{filler} grep: bar.txt: No such file or directory"

    assert bft.classify(command, error_text) == "genuine-command-error"


def test_classify_timeout_flag_mention_is_not_timeout_class():
    # The word "timeout" appearing anywhere in the error text (e.g. as part
    # of an "unrecognized option '--timeout'" complaint) must not, by
    # itself, classify as the `timeout` bucket -- only marker-shaped
    # phrasing ("timeout after/exceeded/expired", "command timed out")
    # should.
    command = "mytool --timeout 5"
    error_text = "error: unrecognized option '--timeout'"

    assert bft.classify(command, error_text) == "genuine-command-error"


def test_classify_no_such_file_token_not_an_argument_is_genuine_command_error():
    # `_is_working_directory_error` must confirm the failing "No such file
    # or directory" token is actually an ARGUMENT of the invoked command --
    # not just present anywhere in the error text. Here "some_lib.py" is an
    # incidental path from the tool's own internal error (an import failure
    # inside pytest, say), not an argument of "python -m pytest" (whose
    # arguments are "-m" and "pytest"), so this is not a cd/relative-path
    # failure of the invocation itself.
    command = "python -m pytest"
    error_text = "some_lib.py: No such file or directory"

    assert bft.classify(command, error_text) == "genuine-command-error"


def test_classify_no_such_file_token_that_is_an_argument_stays_working_directory():
    # The positive case must keep working: the failing token IS one of the
    # invoked command's own arguments.
    command = "cat bar.txt"
    error_text = "cat: bar.txt: No such file or directory"

    assert bft.classify(command, error_text) == "working-directory"


def test_tool_result_block_missing_required_fields_skipped_without_raising(tmp_path):
    path = tmp_path / "session.jsonl"
    records = [
        _assistant([_tool_use("t1", "Bash", "false")]),
        # A tool_result-shaped block missing both "content" and
        # "tool_use_id" -- must be skipped, not raise, and not appear as
        # either a pair or an unpaired result.
        _user([{"type": "tool_result", "is_error": True}]),
        _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
    ]
    _write_transcript(path, records)

    result = bft.pair_bash_errors([path])

    assert len(result.pairs) == 1
    assert result.pairs[0].command == "false"
    assert result.unpaired == []


# ---------------------------------------------------------------------------
# Step 1.3: corpus distribution + excluded-denominator reporting
# ---------------------------------------------------------------------------


def _append_bash_pair(records: list[dict], tool_id: str, command: str, error_text: str) -> None:
    records.append(_assistant([_tool_use(tool_id, "Bash", command)]))
    records.append(_user([_tool_result(tool_id, error_text, is_error=True)]))


def test_build_distribution_from_corpus_counts_all_six_buckets(tmp_path):
    path = tmp_path / "session.jsonl"
    records: list[dict] = []
    _append_bash_pair(
        records,
        "t1",
        "echo 'unterminated",
        "bash: -c: line 1: unexpected EOF while looking for matching quote",
    )
    _append_bash_pair(records, "t2", "foobarbaz --version", "bash: foobarbaz: command not found")
    _append_bash_pair(records, "t3", "cat bar.txt", "cat: bar.txt: No such file or directory")
    _append_bash_pair(records, "t4", "sleep 300", "Command timed out after 120000ms")
    _append_bash_pair(
        records,
        "t5",
        "git status",
        "fatal: not a git repository (or any of the parent directories): .git",
    )
    _append_bash_pair(records, "t6", "mytool --flag", "???")
    _write_transcript(path, records)

    distribution = bft.build_distribution_from_corpus([path])

    assert distribution.counts == {
        "quoting": 1,
        "tool-not-present": 1,
        "working-directory": 1,
        "timeout": 1,
        "genuine-command-error": 1,
        "unclassified": 1,
    }
    assert distribution.total == 6
    # timeout + genuine-command-error are excluded from the numerator.
    assert distribution.addressable_count == 4
    assert distribution.addressable_percentage == pytest.approx(4 / 6 * 100, abs=0.01)


def test_build_distribution_zero_addressable_count_all_errors_excluded_class(tmp_path):
    # Every classified error falls into an excluded class -- the addressable
    # count is zero, but the corpus itself is non-empty, so the
    # percentage is a well-defined 0.0, not None and not a
    # ZeroDivisionError.
    path = tmp_path / "session.jsonl"
    records: list[dict] = []
    _append_bash_pair(records, "t1", "sleep 300", "Command timed out after 120000ms")
    _write_transcript(path, records)

    distribution = bft.build_distribution_from_corpus([path])

    assert distribution.total == 1
    assert distribution.addressable_count == 0
    assert distribution.addressable_percentage == 0.0


def test_build_distribution_empty_corpus_percentage_is_none(tmp_path):
    # An empty corpus is the one true 0/0 case -- total is also zero, so the
    # percentage is reported as None rather than 0.0.
    path = tmp_path / "session.jsonl"
    _write_transcript(path, [])

    distribution = bft.build_distribution_from_corpus([path])

    assert distribution.total == 0
    assert distribution.addressable_count == 0
    assert distribution.addressable_percentage is None


def test_distribution_serialized_json_never_contains_raw_marker_text(tmp_path):
    marker = "DISTINCTIVE-MARKER-XYZ123"
    path = tmp_path / "session.jsonl"
    records: list[dict] = []
    _append_bash_pair(records, "t1", f"echo {marker}", f"{marker}: command not found")
    _write_transcript(path, records)

    distribution = bft.build_distribution_from_corpus([path])
    serialized = json.dumps(distribution.to_dict())

    assert marker not in serialized
    # Sanity check the fixture actually produced a countable error --
    # otherwise the marker's absence would prove nothing.
    assert distribution.total == 1


# ---------------------------------------------------------------------------
# CLI: --baseline emits a regeneratable distribution (correctness finding #4)
# ---------------------------------------------------------------------------


def test_main_without_baseline_flag_prints_pairing_counts_only(tmp_path, capsys):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Bash", "false")]),
            _user([_tool_result("t1", "command exited with a real error message", is_error=True)]),
        ],
    )

    exit_code = bft.main(["--transcript", str(path)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {"pairs", "unpaired"}


def test_main_with_baseline_flag_emits_distribution_to_dict(tmp_path, capsys):
    path = tmp_path / "session.jsonl"
    _write_transcript(
        path,
        [
            _assistant([_tool_use("t1", "Bash", "foobarbaz --version")]),
            _user([_tool_result("t1", "bash: foobarbaz: command not found", is_error=True)]),
        ],
    )

    exit_code = bft.main(["--transcript", str(path), "--baseline"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {
        "counts",
        "total",
        "addressable_count",
        "addressable_percentage",
    }
    assert payload["counts"]["tool-not-present"] == 1
    assert payload["total"] == 1


def test_module_docstring_documents_addressable_numerator_exclusion():
    doc = bft.__doc__ or ""
    assert "timeout" in doc
    assert "genuine-command-error" in doc
    assert "excluded" in doc.lower()
    assert "numerator" in doc.lower()
