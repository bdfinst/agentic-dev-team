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
    # timeout + genuine-command-error are excluded from the denominator.
    assert distribution.addressable_denominator == 4
    assert distribution.addressable_percentage == pytest.approx(4 / 6 * 100, abs=0.01)


def test_build_distribution_zero_denominator_all_errors_excluded_class(tmp_path):
    # Every classified error falls into an excluded class -- the addressable
    # denominator is zero, but the corpus itself is non-empty, so the
    # percentage is a well-defined 0.0, not None and not a
    # ZeroDivisionError.
    path = tmp_path / "session.jsonl"
    records: list[dict] = []
    _append_bash_pair(records, "t1", "sleep 300", "Command timed out after 120000ms")
    _write_transcript(path, records)

    distribution = bft.build_distribution_from_corpus([path])

    assert distribution.total == 1
    assert distribution.addressable_denominator == 0
    assert distribution.addressable_percentage == 0.0


def test_build_distribution_empty_corpus_percentage_is_none(tmp_path):
    # An empty corpus is the one true 0/0 case -- total is also zero, so the
    # percentage is reported as None rather than 0.0.
    path = tmp_path / "session.jsonl"
    _write_transcript(path, [])

    distribution = bft.build_distribution_from_corpus([path])

    assert distribution.total == 0
    assert distribution.addressable_denominator == 0
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


def test_module_docstring_documents_addressable_denominator_exclusion():
    doc = bft.__doc__ or ""
    assert "timeout" in doc
    assert "genuine-command-error" in doc
    assert "excluded" in doc.lower()
    assert "denominator" in doc.lower()
